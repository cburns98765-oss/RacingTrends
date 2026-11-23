"""Do trend fits help pick placers? Runner-level place rates and a one-line-per-leg placepot replay.

    python -m trends.placepot RFB_FILES... [--from 2019-01-01] [--out backtest/]

Place terms (UK placepot): <=4 runners win only; 5-7 first 2; 8+ first 3; handicaps with 16+ first 4.
Placepot = the first six races at each meeting. Dividends aren't in the data, so this measures how
often each approach lands, not what it would have paid.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from multiprocessing import Pool

from . import backtest, engine, importers
from . import util as U


def places_paid(ran, hcap):
    if ran <= 4:
        return 1
    if ran <= 7:
        return 2
    if hcap and ran >= 16:
        return 4
    return 3


def _race(item):
    card, info = item
    a = engine.analyse(card, backtest._IDX)
    n = a["summary"]["n"]
    ran = len(card["runners"])
    paid = places_paid(ran, card["hcap"])
    runners = []
    for x in a["runners"]:
        pos, dec = info.get(U.norm_name(x["horse"]), (None, None))
        if dec is None:
            continue
        runners.append({"score": x["score"], "dec": dec, "placed": pos is not None and pos <= paid,
                        "fits_all": n >= engine.MIN_TRENDS and a["max_core"] > 0 and
                        sum(1 for f in x["flags"] if f["k"] in ("age", "wt", "or") and f["ok"]) == a["max_core"]})
    if not runners:
        return None
    fav = min(runners, key=lambda r: r["dec"])
    top = max(r["score"] for r in runners)
    tops = [r for r in runners if r["score"] == top]
    scored = n >= engine.MIN_TRENDS and top > 0
    clear = tops[0] if (scored and len(tops) == 1) else None
    best_tied = min(tops, key=lambda r: r["dec"]) if scored else None
    for r in runners:
        r["fav"] = r is fav
        r["clear_top"] = r is clear
    return {"date": card["date"], "course": card["course"], "off": card["off"], "scored": scored,
            "runners": runners, "fav": fav, "clear": clear, "best_tied": best_tied, "paid": paid, "ran": ran}


def iter_with_positions(paths, since):
    info = {}
    for row in importers._rows(paths, set()):
        if row.get("date", "") >= since and row.get("region") in ("gb", "ire"):
            pos = str(row.get("pos", "")).strip()
            info.setdefault(str(row.get("race_id")), {})[U.norm_name(row.get("horse"))] = (
                int(pos) if pos.isdigit() else None, U.to_float(row.get("dec")))
    for card, _win in backtest.iter_cards(paths, since):
        yield card, info.get(card["race_id"], {})


def rate(xs, key="placed"):
    n = len(xs)
    return {"n": n, "rate": round(100 * sum(1 for x in xs if x[key]) / n, 1) if n else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--history", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                       "data", "history", "rfb.csv.gz"))
    ap.add_argument("--from", dest="since", default="2019-01-01")
    ap.add_argument("--out", default="backtest")
    args = ap.parse_args()
    items = list(iter_with_positions(args.files, args.since))
    print(f"{len(items)} races", file=sys.stderr)
    races = []
    with Pool(os.cpu_count() or 2, initializer=backtest._init, initargs=(args.history,)) as pool:
        for r in pool.imap_unordered(_race, items, chunksize=200):
            if r:
                races.append(r)
    scored = [r for r in races if r["scored"]]
    allr = [x for r in scored for x in r["runners"]]
    rep = {"races": len(races), "scored": len(scored)}
    rep["place_rate"] = {
        "all runners": rate(allr),
        "favourite": rate([r["fav"] for r in scored]),
        "clear top fit": rate([r["clear"] for r in scored if r["clear"]]),
        "clear top fit, not favourite": rate([r["clear"] for r in scored if r["clear"] and not r["clear"]["fav"]]),
        "top fit incl. ties (shortest priced)": rate([r["best_tied"] for r in scored]),
        "fits all core trends": rate([x for x in allr if x["fits_all"]]),
        "fails a core trend": rate([x for x in allr if not x["fits_all"]]),
    }
    # same price, does fitting the trends place more often?
    bands = [(1, 2), (2, 3), (3, 4.5), (4.5, 6), (6, 9), (9, 13), (13, 21), (21, 1001)]
    rep["by_price"] = {}
    for lo, hi in bands:
        sub = [x for x in allr if lo < x["dec"] <= hi]
        rep["by_price"][f"{lo}-{hi}"] = {"all": rate(sub), "clear top fit": rate([x for x in sub if x["clear_top"]]),
                                         "fits all core": rate([x for x in sub if x["fits_all"]]),
                                         "fails core": rate([x for x in sub if not x["fits_all"]])}
    # placepot replay: first six races at each meeting, one horse per leg
    meets = defaultdict(list)
    for r in races:
        meets[(r["date"], r["course"])].append(r)
    strategies = {"favourite": lambda r: r["fav"],
                  "clear top fit, else favourite": lambda r: r["clear"] or r["fav"],
                  "top fit incl. ties (shortest), else favourite": lambda r: r["best_tied"] or r["fav"]}
    pp = {k: [0, 0, 0] for k in strategies}  # meetings, landed, legs placed
    for legs in meets.values():
        legs = sorted(legs, key=lambda r: str(r["off"]).zfill(5))[:6]
        if len(legs) < 6:
            continue
        for k, f in strategies.items():
            placed = [f(r)["placed"] for r in legs]
            pp[k][0] += 1
            pp[k][1] += all(placed)
            pp[k][2] += sum(placed)
    rep["placepot_one_line"] = {k: {"meetings": m, "landed": l, "landed_pct": round(100 * l / m, 2) if m else 0,
                                    "legs_placed_pct": round(100 * s / (6 * m), 1) if m else 0}
                                for k, (m, l, s) in pp.items()}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "placepot.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
