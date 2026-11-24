"""Speed figures from race times, and a test of whether they beat the market.

    python -m trends.speed build --rfb DUO_FILES... --bsp BSP_DIR   # figures for every run (cached)
    python -m trends.speed test                                     # does the clock beat the price?

Method (the usual time-figure recipe):
1. Seconds per furlong for each winner = winning time / exact distance.
2. Standard time for each course, race type, surface and half-furlong distance (median).
3. Each meeting's going allowance = how much faster/slower than standard its races ran, after
   allowing for class (iterated; a meeting with one race is shrunk towards the going average).
4. Winner's figure = lengths faster than standard after the going allowance, turned into pounds
   (lb per length = 15 / furlongs; 5 lengths per second on the flat, 4 over jumps).
5. Each other runner = winner's figure - lengths beaten x lb per length, + weight carried.
Scale: 100 = a standard-time run under 10st (140lb); higher is faster.
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

from . import bsp as B
from . import util as U
from .model import fit_clogit, race_softmax

RUNNERS = "/tmp/inrunning.pkl"
FIGS = "/tmp/speed_runners.pkl"
OUT = "/home/claude/backtest"
C = 0.05

FRAC = {"¼": .25, "½": .5, "¾": .75}
WORDS = {"dh": 0, "nse": .02, "shd": .05, "sht-hd": .05, "hd": .1, "snk": .2, "nk": .25, "dist": 30}


def lengths(s):
    s = str(s or "").strip().lower()
    if not s:
        return np.nan
    if s in WORDS:
        return WORDS[s]
    m = re.match(r"^(\d*)\s*([¼½¾]?)$", s)
    if not m or not (m.group(1) or m.group(2)):
        return np.nan
    return float(m.group(1) or 0) + FRAC.get(m.group(2), 0)


def secs(s):
    m = re.match(r"^(?:(\d+)m\s*)?(\d*\.?\d+)s$", str(s or "").strip())
    return int(m.group(1) or 0) * 60 + float(m.group(2)) if m else np.nan


def yards(s):
    s = str(s or "")
    m = re.search(r"(\d+)m", s)
    f = re.search(r"(\d+)f", s)
    y = re.search(r"(\d+)y", s)
    return (int(m.group(1)) * 1760 if m else 0) + (int(f.group(1)) * 220 if f else 0) + (int(y.group(1)) if y else 0)


def read_duo(paths):
    races, btn = [], []
    for p in paths:
        name = os.path.basename(p).lower()
        with open(p, encoding="cp1252", errors="replace", newline="") as fh:
            rd = csv.DictReader(fh)
            if "main" in name:
                for r in rd:
                    races.append(("rfb" + r["Id"], secs(r.get("WinTime")), yards(r.get("Distance"))))
            elif "detail" in name:
                for r in rd:
                    btn.append(("rfb" + r["MainID"], U.norm_name(r.get("HorseName")), lengths(r.get("DistBtn"))))
    return (pd.DataFrame(races, columns=["race_id", "wintime", "dist_y"]).drop_duplicates("race_id"),
            pd.DataFrame(btn, columns=["race_id", "horse_key", "btn_inc"]).drop_duplicates(["race_id", "horse_key"]))


def figures(df):
    df = df.copy()
    jumps = df["typ"].isin(["hurdle", "chase", "nhf"])
    df["grp"] = np.where(jumps, "J", "F")
    # cumulative lengths behind the winner, through the finishing order
    df = df.sort_values(["race_id", "pos_n"])
    inc = df["btn_inc"].where(df["pos_n"] > 1, 0.0)
    df["btn"] = inc.groupby(df["race_id"]).cumsum()
    df.loc[df["pos_n"].isna() | (df["btn"] > 30), "btn"] = np.nan

    R = df.drop_duplicates("race_id")[["race_id", "date", "course_key", "typ", "surface", "grp", "cls", "going",
                                       "wintime", "dist_y"]].copy()
    R = R[(R["dist_y"] > 900) & R["wintime"].notna()]
    R["spf"] = R["wintime"] / (R["dist_y"] / 220)
    ok = np.where(R["grp"] == "F", R["spf"].between(10.5, 17), R["spf"].between(11.5, 24))
    R = R[ok]
    R["cd"] = R["course_key"] + "|" + R["typ"] + "|" + R["surface"].fillna("") + "|" + (R["dist_y"] / 110).round().astype(int).astype(str)
    R["mtg"] = R["course_key"] + "|" + R["date"].dt.strftime("%Y-%m-%d") + "|" + R["grp"] + "|" + R["surface"].fillna("")
    R["cg"] = R["grp"] + "|" + R["cls"].fillna(0).astype(int).astype(str)
    R["gd"] = R["grp"] + "|" + R["going"].fillna("").str.split(" ").str[0].str.lower()
    R = R[R.groupby("cd")["race_id"].transform("size") >= 8]
    var = pd.Series(0.0, index=R.index)
    ce = pd.Series(0.0, index=R.index)
    for _ in range(5):
        std = (R["spf"] - var - ce).groupby(R["cd"]).transform("median")
        res = R["spf"] - std
        ce = (res - var).groupby(R["cg"]).transform("mean")
        x = res - ce
        gmean = x.groupby(R["gd"]).transform("mean")
        k = 1.0
        var = (x.groupby(R["mtg"]).transform("sum") + k * gmean) / (x.groupby(R["mtg"]).transform("size") + k)
    R["fig_spf"] = R["spf"] - std - var          # seconds per furlong slower than standard after going
    # drop races whose time can't be right (shortened trips, timing faults): > 5 robust SDs out
    med = R.groupby("grp")["fig_spf"].transform("median")
    mad = (R["fig_spf"] - med).abs().groupby(R["grp"]).transform("median") * 1.4826
    R = R[(R["fig_spf"] - med).abs() <= 5 * mad]
    R["dist_fur"] = R["dist_y"] / 220
    lps = np.where(R["grp"] == "F", 5.0, 4.0)
    R["lbpl"] = 15.0 / R["dist_fur"]
    R["win_fig"] = 100 - R["fig_spf"] * R["dist_fur"] * lps * R["lbpl"]
    R["variant"] = var
    df = df.merge(R[["race_id", "win_fig", "lbpl", "variant"]], on="race_id", how="left")
    df["fig"] = df["win_fig"] - df["btn"] * df["lbpl"] + (df["lbs"] - 140)
    return df.sort_values(["date", "off", "race_id"]).reset_index(drop=True)


def build(rfb, bsp_paths):
    df = pd.read_pickle(RUNNERS)
    keep = ["race_id", "date", "off", "region", "course", "course_key", "horse", "horse_key", "typ", "surface", "cls",
            "going", "dist_f", "hcap", "lbs", "or", "age", "pos_n", "win", "ran", "dec", "bsp", "trainer"]
    df = df[keep]
    races, btn = read_duo(rfb)
    df = df.merge(races, on="race_id", how="left").merge(btn, on=["race_id", "horse_key"], how="left")
    print("joined times:", df["wintime"].notna().mean().round(3), "beaten:", df["btn_inc"].notna().mean().round(3), file=sys.stderr)
    df = figures(df)
    prices = B.load(bsp_paths)
    keys = zip(df["date"].dt.strftime("%Y-%m-%d"), df["course_key"], df["horse_key"])
    df["morning"] = [(prices.get(k) or {}).get("morning") for k in keys]
    df.to_pickle(FIGS)
    print("figures:", df["fig"].notna().mean().round(3), file=sys.stderr)


# ---------------------------------------------------------------- test

def prior(df):
    g = df.groupby("horse_key", sort=False)
    df["last_fig"] = g["fig"].shift(1)
    sh = [g["fig"].shift(k) for k in (1, 2, 3)]
    df["best3"] = pd.concat(sh, axis=1).max(axis=1)
    df["avg3"] = pd.concat(sh, axis=1).mean(axis=1)
    df["lto_pos"] = g["pos_n"].shift(1)
    df["lto_days"] = (df["date"] - g["date"].shift(1)).dt.days
    rg = df.groupby("race_id")
    df["cover"] = rg["best3"].transform(lambda s: s.notna().mean())
    for c in ("best3", "last_fig", "avg3"):
        df[c + "_rank"] = rg[c].rank(ascending=False, method="min")
        df[c + "_gap"] = df[c] - rg[c].transform("max")
    # the horse's best recent figure vs its rating: a 'hidden' fast run the form figures don't show
    return df


def roi(sub, price):
    p = sub[price]
    m = p.notna() & (p > 1)
    s = sub[m]
    pl = np.where(s["win"] == 1, (s[price] - 1) * (1 - C), -1.0)
    return {"bets": int(m.sum()), "win%": round(100 * s["win"].mean(), 1) if m.any() else None,
            "roi%": round(100 * pl.mean(), 1) if m.any() else None}


def test():
    df = pd.read_pickle(FIGS)
    df = prior(df)
    T = df[(df["date"] >= "2019-01-01") & (df["cover"] >= 0.7) & df["bsp"].notna()].copy()
    T["period"] = np.where(T["date"] < "2024-01-01", "2019-23", "2024-26")
    rep = {"runs_with_figure_%": round(100 * df["fig"].notna().mean(), 1)}
    # sanity: does the figure predict at all? win% by rank of best-of-last-3
    out = {}
    for col in ("best3", "last_fig", "avg3"):
        for rk in (1, 2, 3):
            for per in ("2019-23", "2024-26"):
                s = T[(T[col + "_rank"] == rk) & (T["period"] == per)]
                out[f"{col} rank {rk} {per}"] = {"bsp": roi(s, "bsp"), "morning": roi(s, "morning")}
    rep["by_rank"] = out
    # top on figures by a clear margin (5lb+)
    gap2 = T.groupby("race_id")["best3"].transform(lambda s: s.nlargest(2).diff().iloc[-1] * -1 if s.notna().sum() >= 2 else np.nan)
    T["clear5"] = (T["best3_rank"] == 1) & (gap2 >= 5)
    rep["clear_top_5lb"] = {p: {"bsp": roi(T[T.clear5 & (T.period == p)], "bsp"), "morning": roi(T[T.clear5 & (T.period == p)], "morning")} for p in ("2019-23", "2024-26")}
    # hidden fast run: top-2 last-time figure in this field but finished 4th or worse last time
    T["hidden"] = (T["last_fig_rank"] <= 2) & (T["lto_pos"] >= 4)
    rep["hidden_fast_run"] = {p: {"bsp": roi(T[T.hidden & (T.period == p)], "bsp"), "morning": roi(T[T.hidden & (T.period == p)], "morning")} for p in ("2019-23", "2024-26")}
    T["hidden_big"] = (T["last_fig_rank"] == 1) & (T["lto_pos"] >= 5) & (T["bsp"] >= 6)
    rep["hidden_top_fig_unplaced_6plus"] = {p: {"bsp": roi(T[T.hidden_big & (T.period == p)], "bsp"), "morning": roi(T[T.hidden_big & (T.period == p)], "morning")} for p in ("2019-23", "2024-26")}

    # model: does the clock add anything to the market? (morning price, as Benter used)
    M = T[T["morning"].notna() & (T["morning"] > 1)].copy()
    M = M[M.groupby("race_id")["race_id"].transform("size") >= 4].sort_values(["race_id"]).reset_index(drop=True)
    p_m = 1 / M["morning"]
    M["lp_m"] = np.log(p_m / p_m.groupby(M["race_id"]).transform("sum"))
    for c in ("best3_gap", "last_fig_gap", "avg3_gap"):
        M[c + "_z"] = M[c].fillna(M[c].groupby(M["race_id"]).transform("min")).fillna(-40).clip(-40, 0) / 10
    M["nofig"] = M["best3"].isna().astype(float)
    feats = ["lp_m", "best3_gap_z", "last_fig_gap_z", "avg3_gap_z", "nofig"]
    tr, te = M[M.period == "2019-23"], M[M.period == "2024-26"]
    res = {}
    for name, cols in (("market only", ["lp_m"]), ("market + speed figures", feats)):
        b = fit_clogit(tr[cols].to_numpy(), tr["win"].to_numpy(), tr["race_id"].to_numpy(), l2=0.1)
        p = race_softmax(te[cols].to_numpy() @ b, te["race_id"].to_numpy())
        ll = float(np.log(p[te["win"].to_numpy() == 1]).sum())
        res[name] = {"coef": dict(zip(cols, np.round(b, 3).tolist())), "test_loglik": round(ll, 1)}
        if name != "market only":
            te = te.assign(p=p)
    n_races = te["race_id"].nunique()
    res["pseudo_R2_gain_vs_market"] = round((res["market + speed figures"]["test_loglik"] - res["market only"]["test_loglik"]) / (-res["market only"]["test_loglik"]), 4)
    bets = {}
    for edge in (1.1, 1.2, 1.3):
        for price in ("morning", "bsp"):
            s = te[te["p"] * te["morning"] > edge]
            bets[f"model x morning > {edge}, settled at {price}"] = roi(s, price)
    res["bets_2024_26"] = bets
    res["test_races"] = int(n_races)
    rep["model"] = res
    with open(os.path.join(OUT, "speed.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "test"])
    ap.add_argument("--rfb", nargs="*")
    ap.add_argument("--bsp", nargs="*")
    a = ap.parse_args()
    build(a.rfb, a.bsp) if a.cmd == "build" else test()


if __name__ == "__main__":
    main()
