"""Nine ratings for every runner (2016-2026), each using only what was known before the race.

    python -m trends.ratings build      # -> /tmp/ratings.pkl
    python -m trends.ratings test       # combine, pick a betting bar on 2023, test on 2024-26

1 Form        ability in lb from beaten distances and weights, levelled race-by-race (collateral form)
2 Speed       time figures (trends.speed)
4 Pace fit    does today's likely pace suit its usual run style
5 Conditions  how it runs on today's going / trip / course compared with its own average
6 Connections trainer and jockey actual-vs-expected wins (60 days) + trainer record in today's situation
7 Improvement age, experience, trip/class/rating changes, handicap debut, first-time headgear, layoff
8 Trouble     bad luck in its last runs, read from the race comments
9 Trends      the past-renewal trend score from the dashboard
10 Market     morning Betfair price (combined last, Benter-style)
"""
import argparse
import csv
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

from . import util as U
from .model import fit_clogit, race_softmax
from .speed import prior as speed_prior

OUT = "/tmp/ratings.pkl"
REPORT = "/home/claude/backtest/ratings.json"
C = 0.05

TROUBLE = [  # (pattern, weight)
    (r"badly hampered|brought down|carried out|nearly fell|almost fell|saddle slipped|lost (a |his |her )?shoe|lost irons|clipped heels", 3),
    (r"not clear run|no clear run|denied (a )?clear run|short of room|no room|squeezed|checked|snatched up|hampered|stumbled|blundered|"
     r"bumped|carried (left|right|wide)|interfered|tightened|crowded|switched (several|twice|more than once)", 2),
    (r"slowly away|dwelt|missed break|started slowly|reared|wide throughout|raced wide|bit slowly|hung (badly|left|right)|lost ground", 1),
]
_TR = [(re.compile(p), w) for p, w in TROUBLE]


def trouble_score(c):
    c = str(c or "").lower()
    return sum(w for p, w in _TR if p.search(c))


def going_group(g, surface):
    g = str(g or "").lower()
    if surface == "aw" or g.startswith(("standard", "slow", "fast")):
        return "aw"
    if "heavy" in g:
        return "heavy"
    if "soft" in g or "yielding" in g:
        return "soft"
    if "firm" in g or g.startswith("hard"):
        return "fast"
    return "good"


def load():
    df = pd.read_pickle("/tmp/speed_runners.pkl")
    ir = pd.read_pickle("/tmp/inrunning.pkl")[["race_id", "horse_key", "jockey", "comment", "prior_st_F", "prior_st_P",
                                               "prior_st_M", "prior_st_H"]]
    df = df.merge(ir.drop_duplicates(["race_id", "horse_key"]), on=["race_id", "horse_key"], how="left")
    del ir
    aid = {}
    for p in glob.glob("/home/claude/rfbdata/*/*Details*.csv"):
        with open(p, encoding="cp1252", errors="replace") as fh:
            for r in csv.DictReader(fh):
                aid[("rfb" + r["MainID"], U.norm_name(r["HorseName"]))] = r.get("Aid", "").strip()
    df["aid"] = [aid.get(k, "") for k in zip(df["race_id"], df["horse_key"])]
    df = df.sort_values(["date", "off", "race_id"]).reset_index(drop=True)
    # market probabilities (BSP, falling back to industry SP) for actual-vs-expected
    pr = 1 / df["bsp"].where(df["bsp"] > 1, df["dec"])
    df["p_mkt"] = pr / pr.groupby(df["race_id"]).transform("sum")
    return df


# ---------------------------------------------------------------- 1. form (collateral, race by race)

def form_ratings(df):
    n = len(df)
    pre_rating, pre_last, pre_best, perf_out = (np.full(n, np.nan) for _ in range(4))
    hist = {}  # (horse, grp) -> list of recent perfs, newest last
    lbpl = 15.0 / df["dist_f"].clip(lower=4).to_numpy()
    btn, lbs, orr = df["btn"].to_numpy(), df["lbs"].to_numpy(), df["or"].to_numpy()
    keys = list(zip(df["horse_key"], df["grp"]))
    W = np.array([0.1, 0.2, 0.3, 0.4])
    starts = np.flatnonzero(np.r_[True, df["race_id"].to_numpy()[1:] != df["race_id"].to_numpy()[:-1]])
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        idx = range(s, e)
        prior = np.full(e - s, np.nan)
        for j, i in enumerate(idx):
            h = hist.get(keys[i])
            if h:
                w = W[-len(h):]
                prior[j] = np.dot(h[-4:], w) / w.sum()
                pre_rating[i], pre_last[i], pre_best[i] = prior[j], h[-1], max(h[-4:])
            elif orr[i] == orr[i]:
                prior[j] = orr[i]
        rel = -btn[s:e] * lbpl[s:e] + (lbs[s:e] - 140)
        ok = ~np.isnan(prior) & ~np.isnan(rel)
        if ok.sum() < 2:
            continue
        level = np.median(prior[ok] - rel[ok])
        perf = level + rel
        for j, i in enumerate(idx):
            if perf[j] == perf[j]:
                perf_out[i] = perf[j]
                hist.setdefault(keys[i], []).append(perf[j])
                if len(hist[keys[i]]) > 6:
                    hist[keys[i]].pop(0)
    df["form_rating"], df["form_last"], df["form_best"], df["form_perf"] = pre_rating, pre_last, pre_best, perf_out
    return df


# ---------------------------------------------------------------- helpers

def shifted_mean(df, value, keys, shrink):
    g = df.groupby(keys, sort=False)[value]
    s = g.cumsum() - df[value].fillna(0)
    c = g.cumcount() - 0  # rows before (count includes NaNs; fine for our use)
    cnt = df[value].notna().astype(int).groupby([df[k] for k in keys], sort=False).cumsum() - df[value].notna().astype(int)
    return (s / (cnt + shrink)).where(cnt > 0, 0.0)


def rolling_ae(df, who, days=60, shrink=20):
    """actual minus expected wins per run for trainer/jockey over the previous `days` (not including today)."""
    d = df[[who, "date", "win", "p_mkt"]].dropna(subset=[who])
    d = d.assign(x=d["win"] - d["p_mkt"].fillna(0))
    daily = d.groupby([who, "date"]).agg(x=("x", "sum"), n=("x", "size")).reset_index()
    out = {}
    for name, g in daily.groupby(who, sort=False):
        dates = g["date"].to_numpy()
        cx, cn = np.r_[0, g["x"].cumsum().to_numpy()], np.r_[0, g["n"].cumsum().to_numpy()]
        lo = np.searchsorted(dates, dates - np.timedelta64(days, "D"), "left")
        hi = np.arange(len(dates))  # up to but excluding today
        out.update({(name, dd): (cx[h] - cx[l]) / (cn[h] - cn[l] + shrink) for dd, l, h in zip(dates, lo, hi)})
    return pd.Series([out.get(k, 0.0) for k in zip(df[who], df["date"])], index=df.index)


def build():
    df = load()
    print("loaded", len(df), file=sys.stderr)
    df = form_ratings(df)
    print("form done", file=sys.stderr)
    df = speed_prior(df)  # last_fig, best3, avg3, lto_pos, lto_days ...
    g = df.groupby("horse_key", sort=False)

    # 5. conditions: residual (perf - rating before) by going / trip / course, own history only
    df["resid"] = df["form_perf"] - df["form_rating"]
    df["going_g"] = [going_group(a, b) for a, b in zip(df["going"], df["surface"])]
    df["dist_b"] = df["dist_f"].round()
    df["cond_going"] = shifted_mean(df, "resid", ["horse_key", "going_g"], 2)
    df["cond_dist"] = shifted_mean(df, "resid", ["horse_key", "dist_b"], 2)
    df["cond_course"] = shifted_mean(df, "resid", ["horse_key", "course_key"], 2)
    print("conditions done", file=sys.stderr)

    # 6. connections
    df["trainer_ae"] = rolling_ae(df, "trainer")
    df["jockey_ae"] = rolling_ae(df, "jockey")
    df["career"] = g.cumcount()
    df["prev_aid"] = g["aid"].shift(1).fillna("")
    df["first_hg"] = ((df["aid"] != "") & (df["prev_aid"] == "") & (df["career"] > 0)).astype(int)
    df["layoff90"] = (df["lto_days"] > 90).astype(int)
    df["sit"] = np.select([df["career"] == 0, df["first_hg"] == 1, df["layoff90"] == 1], ["debut", "hg", "layoff"], "norm")
    df["x_ae"] = df["win"] - df["p_mkt"].fillna(0)
    df["trainer_sit"] = shifted_mean(df, "x_ae", ["trainer", "sit"], 30)
    print("connections done", file=sys.stderr)

    # 7. improvement
    df["prev_dist"] = g["dist_f"].shift(1)
    df["prev_cls"] = g["cls"].shift(1)
    df["prev_or"] = g["or"].shift(1)
    df["dist_change"] = df["dist_f"] - df["prev_dist"]
    df["class_drop"] = df["cls"] - df["prev_cls"]          # +: running in a lower grade than last time
    df["or_change"] = df["or"] - df["prev_or"]
    hc_before = g["hcap"].cumsum() - df["hcap"]
    df["hcap_debut"] = ((df["hcap"] == 1) & (hc_before == 0) & (df["career"] > 0)).astype(int)

    # 8. trouble
    df["trouble"] = df["comment"].map(trouble_score)
    df["trouble_lto"] = g["trouble"].shift(1).fillna(0)
    df["trouble_2"] = df["trouble_lto"] + g["trouble"].shift(2).fillna(0)
    df["unlucky_lto"] = ((df["trouble_lto"] >= 2) & (g["btn"].shift(1) <= 6)).astype(int)

    # 4. pace fit
    st = df[["prior_st_F", "prior_st_P", "prior_st_M", "prior_st_H"]].fillna(0).to_numpy()
    known = st.sum(1)
    usual = np.where(known >= 2, np.array(list("FPMH"))[st.argmax(1)], "")
    df["usual"] = usual
    nf = pd.Series(usual == "F", index=df.index).groupby(df["race_id"]).transform("sum")
    u = df["usual"]
    df["pace_fit"] = np.select(
        [(u == "F") & (nf == 1), (u == "F") & (nf >= 3), (u == "H") & (nf >= 3), (u == "H") & (nf == 0), (u == "P") & (nf == 0)],
        [2.0, -1.0, 1.0, -1.0, 0.5], 0.0)

    # 9. trends score
    ex = pd.read_pickle("/tmp/extras_runners.pkl")[["race_id", "horse_key"]]
    ren = pd.read_pickle("/tmp/extras_renewals.pkl")
    sc = {}
    for s in ren["scores"]:
        sc.update(s)
    ex["trend"] = ex.index.map(sc)
    df = df.merge(ex.dropna().drop_duplicates(["race_id", "horse_key"]), on=["race_id", "horse_key"], how="left")
    keep = ["race_id", "date", "off", "region", "course", "horse", "horse_key", "typ", "hcap", "ran", "pos_n", "win", "bsp",
            "morning", "dec", "trainer", "jockey", "age", "lbs", "or", "form_rating", "form_last", "form_best", "best3", "avg3",
            "last_fig", "cond_going", "cond_dist", "cond_course", "trainer_ae", "jockey_ae", "trainer_sit", "career", "lto_days",
            "dist_change", "class_drop", "or_change", "hcap_debut", "first_hg", "trouble_lto", "trouble_2", "unlucky_lto",
            "usual", "pace_fit", "trend", "lto_pos"]
    df[keep].to_pickle(OUT)
    print("saved", OUT, file=sys.stderr)


# ---------------------------------------------------------------- combine + test

RATINGS = {  # rating name -> model features
    "1 Form": ["form_rating_r", "form_last_r", "form_best_r", "form_none"],
    "2 Speed": ["best3_r", "avg3_r", "last_fig_r", "fig_none"],
    "4 Pace fit": ["pace_fit"],
    "5 Conditions": ["cond_going", "cond_dist", "cond_course"],
    "6 Connections": ["trainer_ae", "jockey_ae", "trainer_sit"],
    "7 Improvement": ["age_r", "log_career", "debut", "log_days", "dist_up", "dist_down", "class_drop", "or_change_c", "hcap_debut", "first_hg"],
    "8 Trouble": ["trouble_lto", "trouble_2", "unlucky_lto"],
    "9 Trends": ["trend_r"],
    "Basics (weight/rating)": ["lbs_r", "or_r"],
}


def features(df):
    rid = df["race_id"]

    def rel(c, fill_low=True):
        x = df[c]
        r = x - x.groupby(rid).transform("mean")
        if fill_low:
            r = r.fillna((x.groupby(rid).transform("min") - x.groupby(rid).transform("mean")))
        return r.fillna(0)

    for c in ("form_rating", "form_last", "form_best"):
        df[c + "_r"] = rel(c).clip(-40, 40) / 10
    df["form_none"] = df["form_rating"].isna().astype(float)
    for c in ("best3", "avg3", "last_fig"):
        df[c + "_r"] = rel(c).clip(-40, 40) / 10
    df["fig_none"] = df["best3"].isna().astype(float)
    for c in ("cond_going", "cond_dist", "cond_course"):
        df[c] = df[c].fillna(0).clip(-20, 20) / 10
    for c in ("trainer_ae", "jockey_ae", "trainer_sit"):
        df[c] = df[c].fillna(0).clip(-0.3, 0.3) * 10
    df["age_r"] = rel("age", False).clip(-4, 4)
    df["log_career"] = np.log1p(df["career"].fillna(0))
    df["debut"] = (df["career"] == 0).astype(float)
    df["log_days"] = np.log1p(df["lto_days"].fillna(0).clip(0, 1000)) / 5
    df["dist_up"] = df["dist_change"].clip(lower=0).fillna(0).clip(0, 8) / 4
    df["dist_down"] = (-df["dist_change"]).clip(lower=0).fillna(0).clip(0, 8) / 4
    df["class_drop"] = df["class_drop"].fillna(0).clip(-3, 3)
    df["or_change_c"] = df["or_change"].fillna(0).clip(-15, 15) / 5
    df["trouble_2"] = df["trouble_2"].clip(0, 6)
    df["trend_r"] = rel("trend", False)
    df["lbs_r"] = rel("lbs", False).clip(-20, 20) / 10
    df["or_r"] = rel("or").clip(-30, 30) / 10
    return df


def test():
    df = pd.read_pickle(OUT)
    df = df[(df["date"] >= "2019-01-01") & df["pos_n"].notna() | (df["date"] >= "2019-01-01") & df["bsp"].notna()]
    ok = df.groupby("race_id")["bsp"].transform(lambda s: s.notna().all())
    df = df[ok & (df["date"] >= "2019-01-01")].copy()
    df = df[df.groupby("race_id")["race_id"].transform("size") >= 4]
    df = features(df).sort_values(["race_id"]).reset_index(drop=True)
    mp = 1 / df["morning"].where(df["morning"] > 1)
    df["has_m"] = df["morning"].notna() & (df["morning"] > 1)
    df["lp_m"] = np.log(mp / mp.groupby(df["race_id"]).transform("sum"))
    df["lp_m"] = df["lp_m"].fillna(df.groupby("race_id")["lp_m"].transform("min") - 1).fillna(-5)
    df["period"] = np.select([df["date"] < "2023-01-01", df["date"] < "2024-01-01"], ["fit", "tune"], "test")
    allf = [f for fs in RATINGS.values() for f in fs]
    y, rid = df["win"].to_numpy(), df["race_id"].to_numpy()
    X = df[allf].to_numpy(float)
    fit, tune, tst = ((df["period"] == p).to_numpy() for p in ("fit", "tune", "test"))
    rep = {"runners": int(len(df)), "races": int(df["race_id"].nunique())}

    def ll(p, m):
        return float(np.log(np.clip(p[m & (y == 1)], 1e-9, 1)).sum())

    # each rating on its own (no market): how much does it know?
    solo = {}
    base_ll = None
    for name, fs in RATINGS.items():
        cols = [allf.index(f) for f in fs]
        b = fit_clogit(X[fit][:, cols], y[fit], rid[fit], l2=1.0)
        p = race_softmax(X[:, cols] @ b, rid)
        solo[name] = {"coef": dict(zip(fs, np.round(b, 3).tolist())), "test_ll": round(ll(p, tst), 1)}
    nraces = df.loc[tst, "race_id"].nunique()
    uniform = float(-np.log(df[tst].groupby("race_id").size()).sum())
    for v in solo.values():
        v["pseudo_R2"] = round(1 - v["test_ll"] / uniform, 4)

    # stage 1: all ratings together (fundamental model)
    b1 = fit_clogit(X[fit], y[fit], rid[fit], l2=1.0)
    s1 = X @ b1
    p1 = race_softmax(s1, rid)
    rep["fundamental"] = {"coef": dict(zip(allf, np.round(b1, 3).tolist())), "test_pseudo_R2": round(1 - ll(p1, tst) / uniform, 4)}
    # market alone
    lpm = df["lp_m"].to_numpy()
    pm = race_softmax(lpm, rid)
    rep["market_test_pseudo_R2"] = round(1 - ll(pm, tst) / uniform, 4)
    # stage 2: combine fundamental with market, fitted on 2023
    Z = np.c_[np.log(np.clip(p1, 1e-9, 1)), lpm]
    b2 = fit_clogit(Z[tune], y[tune], rid[tune], l2=0.01)
    pc = race_softmax(Z @ b2, rid)
    rep["combined"] = {"weights": {"ratings": round(b2[0], 3), "market": round(b2[1], 3)},
                       "test_pseudo_R2": round(1 - ll(pc, tst) / uniform, 4),
                       "gain_over_market": round((ll(pc, tst) - ll(pm, tst)) / -uniform, 5)}
    rep["solo"] = solo
    df["p_fund"], df["p_comb"], df["p_mkt_m"] = p1, pc, pm
    df["edge"] = df["p_comb"] * df["morning"] - 1
    df["pl_bsp"] = np.where(df["win"] == 1, (df["bsp"] - 1) * (1 - C), -1.0)
    df["pl_m"] = np.where(df["win"] == 1, (df["morning"] - 1) * (1 - C), -1.0)
    # combined rating 0-100 within the race: 100 = top-rated on the fundamental model
    df["rating"] = (100 * df["p_fund"] / df.groupby("race_id")["p_fund"].transform("max")).round()

    def bets(sub):
        b = sub[sub["has_m"]]
        return {"bets": int(len(b)), "win%": round(100 * b["win"].mean(), 1) if len(b) else None,
                "roi_bsp%": round(100 * b["pl_bsp"].mean(), 1) if len(b) else None,
                "roi_morning%": round(100 * b["pl_m"].mean(), 1) if len(b) else None,
                "pl_bsp_£1": round(float(b["pl_bsp"].sum()), 1)}

    bars = {}
    for e in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5):
        for per in ("tune", "test"):
            sub = df[(df["period"] == per) & (df["edge"] > e) & (df["morning"] <= 21)]
            bars[f"edge > {int(100 * e)}% (up to 20/1), {'2023' if per == 'tune' else '2024-26'}"] = bets(sub)
    rep["value_bars"] = bars
    top = {}
    for per in ("tune", "test"):
        t = df[(df["period"] == per) & (df["rating"] == 100)]
        top[f"top-rated (fundamental) {'2023' if per == 'tune' else '2024-26'}"] = bets(t)
        t2 = t[t["p_fund"] > t["p_mkt_m"] * 1.2]
        top[f"top-rated and model chance > market x1.2, {'2023' if per == 'tune' else '2024-26'}"] = bets(t2)
    rep["top_rated"] = top
    df[["race_id", "date", "course", "off", "horse", "rating", "p_fund", "p_comb", "p_mkt_m", "edge", "morning", "bsp", "win",
        "period"]].to_pickle("/tmp/ratings_scored.pkl")
    with open(REPORT, "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "test"])
    a = ap.parse_args()
    build() if a.cmd == "build" else test()
