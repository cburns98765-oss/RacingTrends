"""Do in-running habits repeat? Standing-order replay on Betfair in-play high/low prices.

    python -m trends.inrunning --rfb DUO_FILES... --bsp BSP_DIR --out backtest/

Rule LAY150: a lay at 1.50 left in the in-play market is matched whenever the horse trades at 1.50 or
less (ipmin <= 1.5). Pays +stake x (1 - commission) if it loses, -0.50 if it wins.
Rule BACK2X: for a fancied horse (BSP <= 5), a back at double its BSP is matched whenever it trades
that high in running (ipmax >= 2 x BSP). Pays (2xBSP - 1) x (1 - commission) if it wins, else -1.
Each horse's in-running history uses only its earlier runs. Designed on 2019-2023, checked on 2024+.
Caveat: the files give the in-play high/low, not the time or queue position, so fills are assumed.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from . import bsp, model
from .style import run_style

C = 0.05


def build(rfb, bsp_paths):
    df = model.load_runners(rfb)
    df["style"] = df["comment"].fillna("").map(run_style)
    prices = bsp.load(bsp_paths)
    keys = zip(df["date"].dt.strftime("%Y-%m-%d"), df["course_key"], df["horse_key"])
    got = [prices.get(k) or {} for k in keys]
    for c in ("bsp", "ipmin", "ipmax"):
        df[c] = [g.get(c) for g in got]
    df = df.sort_values(["date", "off"]).reset_index(drop=True)
    df["placed"] = df["pos_n"] <= 3
    # in-running events per run
    df["ev_short"] = df["ipmin"].le(1.5) & df["ipmin"].notna()
    df["ev_short_lost"] = df["ev_short"] & (df["win"] == 0)
    df["ev_drift"] = df["ipmax"].notna() & df["bsp"].notna() & (df["ipmax"] >= 2 * df["bsp"])
    df["ev_comeback"] = df["ev_drift"] & (df["win"] == 1)
    for s in "FPMH":
        df[f"st_{s}"] = (df["style"] == s).astype(int)
    g = df.groupby("horse_key", sort=False)
    for c in ("ev_short", "ev_short_lost", "ev_drift", "ev_comeback", "st_F", "st_P", "st_M", "st_H"):
        df[f"prior_{c}"] = g[c].cumsum() - df[c].astype(int)
    df["prior_runs"] = g.cumcount()
    return df


def summ(pl):
    n = len(pl)
    return {"bets": int(n), "pl": round(float(pl.sum()), 2), "roi": round(100 * float(pl.mean()), 2) if n else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rfb", nargs="+", required=True)
    ap.add_argument("--bsp", nargs="+", required=True)
    ap.add_argument("--out", default="backtest")
    ap.add_argument("--cache", default="/tmp/inrunning.pkl")
    args = ap.parse_args()
    if os.path.exists(args.cache):
        df = pd.read_pickle(args.cache)
    else:
        df = build(args.rfb, args.bsp)
        df.to_pickle(args.cache)
    df = df[(df["date"] >= "2019-01-01") & df["bsp"].notna() & df["pos"].notna()].copy()
    df["period"] = np.where(df["date"] < "2024-01-01", "2019-23", "2024-26")
    rep = {"runners_with_bsp": int(len(df)), "with_inplay_prices": int(df["ipmin"].notna().sum())}

    # LAY150
    lay = df[df["ev_short"]].copy()
    lay["pl"] = np.where(lay["win"] == 1, -0.5, 1 - C)
    lay["prior_rate"] = lay["prior_ev_short_lost"] / lay["prior_ev_short"].replace(0, np.nan)
    groups = {
        "all": lay,
        "no previous 1.5-or-shorter runs": lay[lay["prior_ev_short"] == 0],
        "previously traded <=1.5 and lost 1+": lay[lay["prior_ev_short_lost"] >= 1],
        "previously traded <=1.5 and lost 2+": lay[lay["prior_ev_short_lost"] >= 2],
        "lost every previous time it hit <=1.5 (2+ times)": lay[(lay["prior_ev_short"] >= 2) & (lay["prior_rate"] == 1)],
        "front-runner today": lay[lay["style"] == "F"],
        "usually front-runs (>=50% of runs)": lay[(lay["prior_st_F"] >= 0.5 * lay["prior_runs"]) & (lay["prior_runs"] >= 4)],
        "usually held up (>=50% of runs)": lay[(lay["prior_st_H"] >= 0.5 * lay["prior_runs"]) & (lay["prior_runs"] >= 4)],
        "chase": lay[lay["typ"] == "chase"], "hurdle": lay[lay["typ"] == "hurdle"], "flat": lay[lay["typ"] == "flat"],
    }
    rep["LAY150"] = {k: {p: summ(v.loc[v["period"] == p, "pl"]) for p in ("2019-23", "2024-26")} | {
        "win_rate_when_hit_1.5_%": round(100 * float(v["win"].mean()), 1) if len(v) else 0} for k, v in groups.items()}

    # BACK2X
    fancied = df[(df["bsp"] <= 5) & df["ipmax"].notna()]
    back = fancied[fancied["ev_drift"]].copy()
    back["pl"] = np.where(back["win"] == 1, (2 * back["bsp"] - 1) * (1 - C), -1.0)
    groups = {
        "all fancied (BSP<=5)": back,
        "prior comeback win (won after trading 2x BSP)": back[back["prior_ev_comeback"] >= 1],
        "prior comebacks 2+": back[back["prior_ev_comeback"] >= 2],
        "usually held up (>=50% of runs)": back[(back["prior_st_H"] >= 0.5 * back["prior_runs"]) & (back["prior_runs"] >= 4)],
        "usually front-runs (>=50% of runs)": back[(back["prior_st_F"] >= 0.5 * back["prior_runs"]) & (back["prior_runs"] >= 4)],
        "chase": back[back["typ"] == "chase"], "hurdle": back[back["typ"] == "hurdle"], "flat": back[back["typ"] == "flat"],
        "BSP <= 2.5": back[back["bsp"] <= 2.5],
    }
    rep["BACK2X"] = {k: {p: summ(v.loc[v["period"] == p, "pl"]) for p in ("2019-23", "2024-26")} for k, v in groups.items()}
    # does in-running behaviour repeat at all? P(short-and-lost | had it before) vs base
    hit = df[df["ev_short"]]
    rep["repeat_check_lost_after_hitting_1.5_%"] = {
        "base": round(100 * (1 - hit["win"].mean()), 1),
        "horse lost after 1.5 before": round(100 * (1 - hit.loc[hit["prior_ev_short_lost"] >= 1, "win"].mean()), 1),
        "horse never lost after 1.5 before (2+ hits)": round(100 * (1 - hit.loc[(hit["prior_ev_short"] >= 2) & (hit["prior_ev_short_lost"] == 0), "win"].mean()), 1),
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "inrunning.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
