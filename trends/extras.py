"""Extra past-winner trends, tested before they go on the dashboard.

    python -m trends.extras build   # per-runner features + each race's renewals and current score (cached)
    python -m trends.extras test    # does each trend pick out winners, and does it beat the price?

Every feature uses only runs before the race. A trend is "active" for a race when 3+ past renewals
give a value; a runner "fits" when it matches what those winners had.
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

from . import engine, importers
from . import util as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNERS = "/tmp/inrunning.pkl"          # built by trends.inrunning (RFB runners + comments + Betfair SP)
FEAT = "/tmp/extras_runners.pkl"
REN = "/tmp/extras_renewals.pkl"
C = 0.05

BOOL_FEATS = {
    "lto_top3": "Finished in the first 3 last time out",
    "won_last3": "Won at least once in its last 3 runs",
    "course_win": "Had already won at this course",
    "dist_win": "Had already won over a similar trip",
    "trainer_14d": "Trainer had a winner in the previous 14 days",
    "handy": "Usually races up with the pace (front or prominent)",
    "back": "Usually held up / mid-division",
}
NUM_FEATS = {
    "days": "Days since last run",
    "or_rank": "Rank on official rating in the field (1 = top-rated)",
    "career": "Career runs before the race",
    "or_vs_win": "Rating now vs mark when last winning (lb)",
}


def add_features(df):
    df = df.sort_values(["date", "off", "race_id"]).reset_index(drop=True)
    g = df.groupby("horse_key", sort=False)
    prev_date = g["date"].shift(1)
    df["days"] = (df["date"] - prev_date).dt.days
    prev_pos = g["pos_n"].shift(1)
    has_prev = prev_date.notna()
    df["lto_top3"] = np.where(has_prev, (prev_pos <= 3).astype(float), np.nan)
    w = df["win"].astype(float)
    last3 = sum(g["win"].shift(k).fillna(0) for k in (1, 2, 3))
    df["won_last3"] = np.where(has_prev, (last3 > 0).astype(float), np.nan)
    df["course_win"] = np.where(has_prev, ((df.groupby(["horse_key", "course_key"])["win"].cumsum() - w) > 0).astype(float), np.nan)
    df["dist_b"] = df["dist_f"].round()
    df["dist_win"] = np.where(has_prev, ((df.groupby(["horse_key", "typ", "dist_b"])["win"].cumsum() - w) > 0).astype(float), np.nan)
    df["career"] = g.cumcount()
    # rating now vs the rating it carried when it last won
    win_or = df["or"].where(df["win"] == 1)
    last_win_or = win_or.groupby(df["horse_key"]).transform(lambda s: s.shift(1).ffill())
    df["or_vs_win"] = df["or"] - last_win_or
    df["or_rank"] = df.groupby("race_id")["or"].rank(ascending=False, method="min")
    # usual running style from earlier runs
    st = df[["prior_st_F", "prior_st_P", "prior_st_M", "prior_st_H"]].to_numpy()
    known = st.sum(1)
    handy = st[:, 0] + st[:, 1]
    df["handy"] = np.where(known >= 2, (handy * 2 > known).astype(float), np.nan)
    df["back"] = np.where(known >= 2, ((known - handy) * 2 > known).astype(float), np.nan)
    # trainer had a winner in the 14 days before
    wins = df.loc[df["win"] == 1, ["trainer", "date"]]
    tw = {t: np.sort(v.to_numpy()) for t, v in wins.groupby("trainer")["date"]}
    out = np.zeros(len(df))
    for t, idx in df.groupby("trainer").indices.items():
        arr = tw.get(t)
        if arr is None:
            continue
        d = df["date"].to_numpy()[idx]
        lo = np.searchsorted(arr, d - np.timedelta64(14, "D"), side="left")
        hi = np.searchsorted(arr, d, side="left")
        out[idx] = (hi - lo) > 0
    df["trainer_14d"] = out
    return df


_IDX = None


def _init():
    global _IDX
    _IDX = engine.index_history(importers.read_history(os.path.join(ROOT, "data", "history", "rfb.csv.gz")))


def _work(card):
    try:
        ren = engine.find_renewals(card, _IDX)
        summ = engine.summarise(ren)
        runners, max_core = engine.score_runners(card, summ, ren)
    except Exception:
        return None
    return (card["race_id"], [r["race_id"] for r in ren], {r["row"]: r["score"] for r in runners}, max_core)


def cards(df):
    cols = ["race_id", "date", "region", "course", "off", "race_name", "type", "surface", "class", "dist_f", "going",
            "horse", "age", "lbs", "or", "trainer", "jockey"]
    sub = df.loc[(df["date"] >= "2018-01-01") & df["region"].isin(["gb", "ire"]), cols].rename(columns={"or": "orr"})
    for rid, g in sub.groupby("race_id", sort=False):
        f = g.iloc[0]
        name, course = f["race_name"], U.clean_course(f["course"])
        runners = [{"row": int(i), "horse": r.horse, "age": U.to_int(r.age), "lbs": U.to_int(r.lbs),
                    "or": U.to_int(r.orr),
                    "trainer": r.trainer, "jockey": r.jockey, "number": None}
                   for i, r in zip(g.index, g.itertuples(index=False, name="R"))]
        yield {"race_id": rid, "date": f["date"].strftime("%Y-%m-%d"), "region": f["region"], "course_id": "",
               "course": course, "off": f["off"], "race_name": name, "type": U.race_type(f["type"], name),
               "surface": U.surface(f["surface"], course, f["going"]), "class": U.race_class(f["class"]),
               "pattern": U.pattern_level("", name), "hcap": int(U.is_handicap(name)), "kinds": U.kinds(name),
               "dist_f": U.to_float(f["dist_f"]), "going": f["going"], "runners": runners}


def build():
    df = pd.read_pickle(RUNNERS)
    df = add_features(df)
    df.to_pickle(FEAT)
    print("features done", len(df), file=sys.stderr)
    res = []
    with Pool(2, initializer=_init) as pool:
        for i, r in enumerate(pool.imap_unordered(_work, cards(df), chunksize=300), 1):
            if r:
                res.append(r)
            if i % 20000 == 0:
                print("  races", i, file=sys.stderr)
    ren = pd.DataFrame(res, columns=["race_id", "renewals", "scores", "max_core"])
    ren.to_pickle(REN)
    print("renewals done", len(ren), file=sys.stderr)


def evaluate():
    df = pd.read_pickle(FEAT)
    ren = pd.read_pickle(REN)
    ren = ren[ren["renewals"].map(len) >= engine.MIN_TRENDS]
    winners = df[df["win"] == 1].drop_duplicates("race_id").set_index("race_id")
    feats = list(BOOL_FEATS) + list(NUM_FEATS)
    # winner values for each race's renewals
    rows = []
    for rid, rl in zip(ren["race_id"], ren["renewals"]):
        wv = winners.reindex([r for r in rl if r in winners.index])[feats]
        rec = {"race_id": rid}
        for f in BOOL_FEATS:
            v = wv[f].dropna()
            rec[f + "_n"] = len(v)
            rec[f + "_share"] = v.mean() if len(v) else np.nan
        for f in NUM_FEATS:
            v = wv[f].dropna()
            rec[f + "_n"] = len(v)
            rec[f + "_min"] = v.min() if len(v) else np.nan
            rec[f + "_max"] = v.max() if len(v) else np.nan
        rows.append(rec)
    T = pd.DataFrame(rows).set_index("race_id")
    R = df[df["race_id"].isin(T.index)].join(T, on="race_id")
    sc = {}
    for rid, s, mc in zip(ren["race_id"], ren["scores"], ren["max_core"]):
        for row, v in s.items():
            sc[row] = v
    R["old_score"] = R.index.map(sc)
    R["period"] = np.where(R["date"] < "2024-01-01", "2018-23", "2024-26")
    R["pl_bsp"] = np.where(R["bsp"].notna(), np.where(R["win"] == 1, (R["bsp"] - 1) * (1 - C), -1.0), np.nan)
    R["pl_sp"] = np.where(R["dec"].notna(), np.where(R["win"] == 1, R["dec"] - 1, -1.0), np.nan)

    # rule per feature -> fit (1/0) or NaN when the trend isn't active / runner value unknown
    fits = {}
    for f in BOOL_FEATS:
        active = (R[f + "_n"] >= 3) & (R[f + "_share"] >= 0.7)
        fits[f] = np.where(active & R[f].notna(), R[f], np.nan)
    tol = {"days": 7, "or_rank": 0, "career": 1, "or_vs_win": 2}
    for f in NUM_FEATS:
        active = R[f + "_n"] >= 3
        lo, hi = R[f + "_min"] - tol[f], R[f + "_max"] + tol[f]
        if f in ("days", "or_rank"):
            ok = R[f] <= hi                     # recent enough / high enough in the ratings
        else:
            ok = (R[f] >= lo) & (R[f] <= hi)
        fits[f] = np.where(active & R[f].notna(), ok.astype(float), np.nan)
    F = pd.DataFrame(fits, index=R.index)

    def stats(mask, period):
        m = mask & (R["period"] == period)
        sub = R[m]
        b = sub["pl_bsp"].dropna()
        return {"runners": int(m.sum()), "win%": round(100 * sub["win"].mean(), 2) if len(sub) else None,
                "roi_bsp%": round(100 * b.mean(), 1) if len(b) else None}

    rep = {"races_with_3plus_renewals": int(len(T)), "features": {}}
    for f in feats:
        on = F[f].notna()
        races_active = R.loc[on, "race_id"].nunique()
        if not races_active:
            continue
        d = {"label": BOOL_FEATS.get(f) or NUM_FEATS[f], "races_active": int(races_active)}
        for p in ("2018-23", "2024-26"):
            fit, no = stats(on & (F[f] == 1), p), stats(on & (F[f] == 0), p)
            d[p] = {"fits": fit, "doesnt_fit": no,
                    "win_lift": round(fit["win%"] / no["win%"], 2) if fit["win%"] and no["win%"] else None}
        # share of race winners that fitted (how often the trend holds)
        wins = on & (R["win"] == 1)
        d["winners_fitting%"] = round(100 * F.loc[wins, f].mean(), 1)
        rep["features"][f] = d
    R = R.join(F.add_prefix("fit_"))
    R.to_pickle("/tmp/extras_eval.pkl")
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "test"])
    ap.add_argument("--out", default="/home/claude/backtest")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    else:
        rep = evaluate()
        with open(os.path.join(a.out, "extras.json"), "w") as fh:
            json.dump(rep, fh, indent=1)
        for f, d in rep["features"].items():
            x, y = d["2018-23"], d["2024-26"]
            print(f"{f:12} races {d['races_active']:6}  winners fit {d['winners_fitting%']:5}% | "
                  f"18-23 lift {x['win_lift']} roi fit {x['fits']['roi_bsp%']} vs {x['doesnt_fit']['roi_bsp%']} | "
                  f"24-26 lift {y['win_lift']} roi fit {y['fits']['roi_bsp%']} vs {y['doesnt_fit']['roi_bsp%']}")


if __name__ == "__main__":
    main()
