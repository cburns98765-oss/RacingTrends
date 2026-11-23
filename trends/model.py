"""Ratings model (Benter-style), tested on Betfair prices.

    python -m trends.model --rfb DUO_FILES... --bsp BSP_DIR_OR_ZIP --out backtest/

1. Runner table from RacingFormBook results (2016+), with features known BEFORE each race:
   horse history (runs, wins, last run, course/distance wins, rating and class change, first-time
   headgear), trainer/jockey 30-day form, weight, age, draw, and the past-renewal trend checks.
2. Stage 1: conditional logit on those features only (fit 2019-2022).
3. Stage 2: combine stage-1 score with the morning Betfair market (fit 2023).
4. Test 2024 onward: bet £1 when model chance x price beats 1 + margin; decide on the morning price,
   settle at Betfair SP after commission (and, separately, at the morning price itself).
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import backtest, bsp, engine, importers
from . import util as U

COMMISSION = 0.05  # Betfair base rate; many accounts pay less


# ---------------------------------------------------------------- data

def load_runners(paths):
    rows = []
    for r in importers._rows(paths, set()):
        if r.get("region") not in ("gb", "ire"):
            continue
        rows.append(r)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["race_name"] = df["race_name"].fillna("")
    for c in ("age", "lbs", "or", "ran"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")
    df["dist_f"] = pd.to_numeric(df["dist_f"], errors="coerce")
    df["cls"] = pd.to_numeric(df["class"], errors="coerce")
    df["pos_n"] = pd.to_numeric(df["pos"], errors="coerce")
    df["win"] = (df["pos_n"] == 1).astype(int)
    df["typ"] = [U.race_type(t, n) for t, n in zip(df["type"], df["race_name"])]
    df["hcap"] = df["race_name"].str.lower().str.contains("handicap|nursery").astype(int)
    df["course_key"] = df["course"].map(U.course_name_key)
    df["horse_key"] = df["horse"].map(U.norm_name)
    df["off"] = df["off"].astype(str).str.zfill(5)
    return df.sort_values(["date", "off", "race_id"]).reset_index(drop=True)


def add_features(df):
    g = df.groupby("horse_key", sort=False)
    df["runs_before"] = g.cumcount()
    df["wins_before"] = g["win"].cumsum() - df["win"]
    df["prev_date"] = g["date"].shift()
    df["days_since"] = (df["date"] - df["prev_date"]).dt.days
    df["last_pos_pct"] = g["pos_n"].shift() / g["ran"].shift()
    df["won_last"] = g["win"].shift().fillna(0)
    df["or_change"] = df["or"] - g["or"].shift()
    df["class_drop"] = g["cls"].shift() - df["cls"]
    df["course_wins"] = df.groupby(["horse_key", "course_key"])["win"].cumsum() - df["win"]
    df["dist_bucket"] = (df["dist_f"]).round()
    df["dist_wins"] = df.groupby(["horse_key", "typ", "dist_bucket"])["win"].cumsum() - df["win"]
    # race-relative
    rg = df.groupby("race_id")
    df["from_top"] = rg["lbs"].transform("max") - df["lbs"]
    df["or_rank"] = rg["or"].rank(ascending=False, pct=True)
    df["field"] = rg["horse"].transform("size")
    # trainer / jockey form over the previous 30 days (not including the day itself)
    for who in ("trainer", "jockey"):
        daily = df.groupby([who, "date"]).agg(r=("win", "size"), w=("win", "sum")).reset_index().sort_values([who, "date"])
        parts = []
        for key, sub in daily.groupby(who, sort=False):
            s = sub.set_index("date")[["r", "w"]].rolling("30D", closed="left").sum().fillna(0)
            s[who] = key
            parts.append(s.reset_index())
        roll = pd.concat(parts)
        df = df.merge(roll.rename(columns={"r": f"{who}_r30", "w": f"{who}_w30"}), on=[who, "date"], how="left")
        df[f"{who}_sr30"] = (df[f"{who}_w30"] + 1) / (df[f"{who}_r30"] + 10)  # smoothed strike rate
    return df


def _trend_flags(item):
    card, _ = item
    a = engine.analyse(card, backtest._IDX)
    if a["summary"]["n"] < engine.MIN_TRENDS:
        return []
    out = []
    for x in a["runners"]:
        ok = {f["k"]: f["ok"] for f in x["flags"]}
        out.append((card["race_id"], U.norm_name(x["horse"]), int(bool(ok.get("age"))), int(bool(ok.get("wt"))),
                    int(bool(ok.get("or"))), int(bool(ok.get("trainer"))), int(bool(ok.get("jockey"))),
                    int(bool(ok.get("cdwin"))), x["score"]))
    return out


def add_trends(df, paths, hist, since):
    cards = list(backtest.iter_cards(paths, since))
    rows = []
    with Pool(os.cpu_count() or 2, initializer=backtest._init, initargs=(hist,)) as pool:
        for rs in pool.imap_unordered(_trend_flags, cards, chunksize=200):
            rows.extend(rs)
    t = pd.DataFrame(rows, columns=["race_id", "horse_key", "t_age", "t_wt", "t_or", "t_trainer", "t_jockey",
                                    "t_cdwin", "t_score"])
    return df.merge(t, on=["race_id", "horse_key"], how="left")


FEATURES = ["f_logdays", "f_layoff", "f_runs", "f_winrate", "f_lastpos", "f_wonlast", "f_or_change",
            "f_class_drop", "f_course_win", "f_dist_win", "f_from_top", "f_or_rank", "f_age",
            "f_tr_sr", "f_jk_sr", "f_t_age", "f_t_wt", "f_t_or", "f_t_trainer", "f_t_jockey", "f_t_cdwin"]


def design(df):
    X = pd.DataFrame(index=df.index)
    X["f_logdays"] = np.log1p(df["days_since"].fillna(365).clip(0, 1000))
    X["f_layoff"] = (df["days_since"].fillna(999) > 180).astype(float)
    X["f_runs"] = np.log1p(df["runs_before"])
    X["f_winrate"] = (df["wins_before"] + 0.1) / (df["runs_before"] + 1)
    X["f_lastpos"] = df["last_pos_pct"].fillna(0.6).clip(0, 1)
    X["f_wonlast"] = df["won_last"]
    X["f_or_change"] = df["or_change"].fillna(0).clip(-20, 20) / 10
    X["f_class_drop"] = df["class_drop"].fillna(0).clip(-3, 3)
    X["f_course_win"] = (df["course_wins"] > 0).astype(float)
    X["f_dist_win"] = (df["dist_wins"] > 0).astype(float)
    X["f_from_top"] = df["from_top"].fillna(0).clip(0, 40) / 10
    X["f_or_rank"] = df["or_rank"].fillna(0.5)
    X["f_age"] = (df["age"].fillna(5) - 5).clip(-3, 6)
    X["f_tr_sr"] = df["trainer_sr30"].fillna(0.1) * 10
    X["f_jk_sr"] = df["jockey_sr30"].fillna(0.1) * 10
    for k in ("age", "wt", "or", "trainer", "jockey", "cdwin"):
        X[f"f_t_{k}"] = df[f"t_{k}"].fillna(0)
    return X[FEATURES].astype(float).values


# ---------------------------------------------------------------- conditional logit

def _nll(beta, X, y, starts, l2):
    s = X @ beta
    # race-wise log-softmax
    m = np.maximum.reduceat(s, starts)
    e = np.exp(s - np.repeat(m, np.diff(np.append(starts, len(s)))))
    z = np.add.reduceat(e, starts)
    logp = s - np.repeat(m + np.log(z), np.diff(np.append(starts, len(s))))
    p = np.exp(logp)
    nll = -np.sum(logp[y == 1]) + l2 * np.sum(beta ** 2)
    # gradient: sum over races of (x_winner - E_p[x])
    px = X * p[:, None]
    ex = np.add.reduceat(px, starts, axis=0)
    xw = X[y == 1]
    grad = -(xw.sum(0) - ex.sum(0)) + 2 * l2 * beta
    return nll, grad


def fit_clogit(X, y, race_ids, l2=1.0):
    starts = np.flatnonzero(np.r_[True, race_ids[1:] != race_ids[:-1]])
    res = minimize(_nll, np.zeros(X.shape[1]), args=(X, y, starts, l2), jac=True, method="L-BFGS-B")
    return res.x


def race_softmax(s, race_ids):
    starts = np.flatnonzero(np.r_[True, race_ids[1:] != race_ids[:-1]])
    lens = np.diff(np.append(starts, len(s)))
    m = np.repeat(np.maximum.reduceat(s, starts), lens)
    e = np.exp(s - m)
    return e / np.repeat(np.add.reduceat(e, starts), lens)


# ---------------------------------------------------------------- evaluation

def settle(sub, price_col, commission):
    won = sub["win"].values == 1
    price = sub[price_col].values
    pl = np.where(won, (price - 1) * (1 - commission), -1.0)
    n = len(sub)
    return {"bets": int(n), "wins": int(won.sum()), "strike": round(100 * won.mean(), 1) if n else 0,
            "pl": round(float(pl.sum()), 2), "roi": round(100 * float(pl.sum()) / n, 1) if n else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rfb", nargs="+", required=True)
    ap.add_argument("--bsp", nargs="+", required=True)
    ap.add_argument("--history", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                       "data", "history", "rfb.csv.gz"))
    ap.add_argument("--out", default="backtest")
    ap.add_argument("--cache", default="/tmp/model_runners.parquet")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if os.path.exists(args.cache):
        df = pd.read_parquet(args.cache)
    else:
        print("loading runners...", file=sys.stderr)
        df = load_runners(args.rfb)
        print(f"{len(df)} runners; features...", file=sys.stderr)
        df = add_features(df)
        print("trend flags...", file=sys.stderr)
        df = add_trends(df, args.rfb, args.history, "2019-01-01")
        print("betfair prices...", file=sys.stderr)
        prices = bsp.load(args.bsp)
        keys = list(zip(df["date"].dt.strftime("%Y-%m-%d"), df["course_key"], df["horse_key"]))
        got = [prices.get(k) or {} for k in keys]
        df["bsp"] = [g.get("bsp") for g in got]
        df["morning"] = [g.get("morning") for g in got]
        df["ppwap"] = [g.get("ppwap") for g in got]
        df.to_parquet(args.cache)

    df = df[df["date"] >= "2019-01-01"].copy()
    # race must be fully priced on Betfair (every runner has a BSP) and have a morning market
    df["mkt"] = df["morning"].fillna(df["ppwap"])
    ok = df.groupby("race_id").agg(n=("horse", "size"), b=("bsp", "count"), m=("mkt", "count"))
    good = ok[(ok.b == ok.n) & (ok.m >= 0.8 * ok.n)].index
    df = df[df["race_id"].isin(good) & df["pos"].notna()].copy()
    df["mkt"] = df["mkt"].fillna(df["bsp"])  # a few unpriced morning runners: use their BSP as the market view
    df = df.sort_values(["race_id"]).reset_index(drop=True)
    df["p_mkt"] = 1 / df["mkt"]
    df["p_mkt"] = df["p_mkt"] / df.groupby("race_id")["p_mkt"].transform("sum")
    df["year"] = df["date"].dt.year
    X = design(df)
    y = df["win"].values
    rid = df["race_id"].values

    rep = {"runners": int(len(df)), "races": int(df["race_id"].nunique()),
           "matched_share_of_rfb_runners": None}
    # baselines at BSP
    test = df["year"] >= 2024
    rep["baseline_all_runners_bsp_2024+"] = settle(df[test], "bsp", COMMISSION)
    fav = df[test].loc[df[test].groupby("race_id")["bsp"].idxmin()]
    rep["baseline_bsp_favourites_2024+"] = settle(fav, "bsp", COMMISSION)

    # stage 1: fundamentals only, fit 2019-2022
    tr = (df["year"] <= 2022).values
    beta = fit_clogit(X[tr], y[tr], rid[tr], l2=1.0)
    rep["stage1_coefficients"] = {f: round(float(b), 3) for f, b in zip(FEATURES, beta)}
    s1 = X @ beta
    # stage 2: combine with the morning market, fit on 2023
    Z = np.column_stack([s1, np.log(df["p_mkt"].values)])
    va = (df["year"] == 2023).values
    gamma = fit_clogit(Z[va], y[va], rid[va], l2=0.01)
    rep["stage2_weights"] = {"fundamental": round(float(gamma[0]), 3), "market_log_p": round(float(gamma[1]), 3)}
    df["p_model"] = race_softmax(Z @ gamma, rid)

    # log-loss check vs market alone, test years
    # average -log(chance given to the winner) in the test years: lower = sharper forecasts
    win_t = test.values & (y == 1)
    rep["test_logloss_winners"] = {"market": round(float(-np.mean(np.log(df.loc[win_t, "p_mkt"]))), 4),
                                   "model": round(float(-np.mean(np.log(df.loc[win_t, "p_model"]))), 4)}

    # betting: decide on the morning price, settle at BSP (after commission) and at the morning price
    rep["bets"] = {}
    for margin in (0.0, 0.05, 0.10, 0.20, 0.30):
        for lo, hi in ((1, 1000), (1, 10), (1, 5)):
            edge = df["p_model"] * df["mkt"] - 1
            pick = test & (edge > margin) & (df["mkt"] > lo) & (df["mkt"] <= hi)
            sub = df[pick]
            key = f"edge>{int(margin*100)}% odds {lo}-{hi}"
            rep["bets"][key] = {"at_bsp_5pc_comm": settle(sub, "bsp", COMMISSION),
                                "at_bsp_2pc_comm": settle(sub, "bsp", 0.02),
                                "at_morning_price_5pc": settle(sub, "mkt", COMMISSION)}
    # by test year for a mid setting
    pick = test & ((df["p_model"] * df["mkt"] - 1) > 0.10) & (df["mkt"] <= 10)
    rep["by_year_edge10_odds_to_10"] = {int(yv): settle(df[pick & (df["year"] == yv)], "bsp", COMMISSION)
                                        for yv in sorted(df.loc[test, "year"].unique())}
    with open(os.path.join(args.out, "model.json"), "w") as fh:
        json.dump(rep, fh, indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
