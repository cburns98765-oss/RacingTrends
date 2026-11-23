"""Which trend checks actually carry an edge? Runner-level replay since --from.

    python -m trends.factors RFB_FILES... [--from 2019-01-01] [--out backtest/]

Every runner in every scored race is tagged with the checks it passed, then strike rate and
level-stakes ROI at SP are compared with the baseline of backing every runner.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from multiprocessing import Pool

from . import backtest, engine, importers
from . import util as U


def _runner_rows(item):
    card, win = item
    a = engine.analyse(card, backtest._IDX)
    if a["summary"]["n"] < engine.MIN_TRENDS:
        return []
    # starting prices per runner from the raw rows were attached as _dec
    decs = {U.norm_name(x["horse"]): x.get("_dec") for x in card["runners"]}
    top = a["runners"][0]["score"] if a["runners"] else 0
    ntop = sum(1 for x in a["runners"] if x["score"] == top)
    fav_dec = min((d for d in decs.values() if d), default=None)
    out = []
    for x in a["runners"]:
        dec = decs.get(U.norm_name(x["horse"]))
        if not dec:
            continue
        ok = {f["k"]: f["ok"] for f in x["flags"]}
        won = U.norm_name(x["horse"]) == U.norm_name(win["horse"])
        out.append({
            "won": won, "pl": (dec - 1) if won else -1.0, "dec": dec,
            "age": ok.get("age"), "wt": ok.get("wt"), "or": ok.get("or"),
            "trainer": bool(ok.get("trainer")), "jockey": bool(ok.get("jockey")), "cdwin": bool(ok.get("cdwin")),
            "core": sum(1 for k in ("age", "wt", "or") if ok.get(k)), "core_max": a["max_core"],
            "score": x["score"], "clear_top": x["score"] == top and ntop == 1,
            "fav": dec == fav_dec, "hcap": card["hcap"], "type": card["type"], "year": card["date"][:4],
            "fav_rate": a["summary"].get("fav_wins", 0) / max(1, a["summary"]["n"]),
        })
    return out


def iter_cards_with_sp(paths, since):
    """Like backtest.iter_cards but keeps each runner's SP."""
    by_race = {}
    for row in importers._rows(paths, set()):
        if row.get("date", "") >= since and row.get("region") in ("gb", "ire"):
            by_race.setdefault(str(row.get("race_id")), {})[U.norm_name(row.get("horse"))] = U.to_float(row.get("dec"))
    for card, win in backtest.iter_cards(paths, since):
        sp = by_race.get(card["race_id"], {})
        for x in card["runners"]:
            x["_dec"] = sp.get(U.norm_name(x["horse"]))
        yield card, win


def summ(rows):
    n = len(rows)
    w = sum(r["won"] for r in rows)
    pl = sum(r["pl"] for r in rows)
    return {"n": n, "wins": w, "strike": round(100 * w / n, 1) if n else 0, "roi": round(100 * pl / n, 1) if n else 0,
            "pl": round(pl, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--history", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                       "data", "history", "rfb.csv.gz"))
    ap.add_argument("--from", dest="since", default="2019-01-01")
    ap.add_argument("--out", default="backtest")
    args = ap.parse_args()
    cards = list(iter_cards_with_sp(args.files, args.since))
    print(f"{len(cards)} races", file=sys.stderr)
    rows = []
    with Pool(os.cpu_count() or 2, initializer=backtest._init, initargs=(args.history,)) as pool:
        for rs in pool.imap_unordered(_runner_rows, cards, chunksize=200):
            rows.extend(rs)
    rep = {"all_runners": summ(rows), "favourites": summ([r for r in rows if r["fav"]])}
    for k in ("age", "wt", "or"):
        rep[f"{k}_fits"] = summ([r for r in rows if r[k] is True])
        rep[f"{k}_fails"] = summ([r for r in rows if r[k] is False])
    for k in ("trainer", "jockey", "cdwin"):
        rep[f"{k}_yes"] = summ([r for r in rows if r[k]])
        rep[f"{k}_no"] = summ([r for r in rows if not r[k]])
    g = defaultdict(list)
    for r in rows:
        g[f"core {r['core']}/{r['core_max']}"].append(r)
    rep["by_core_fit"] = {k: summ(v) for k, v in sorted(g.items())}
    g = defaultdict(list)
    for r in rows:
        g[f"score {r['score']}"].append(r)
    rep["by_score"] = {k: summ(v) for k, v in sorted(g.items())}
    # price bands: do trend fits help among similar prices?
    bands = [(0, 3), (3, 5), (5, 9), (9, 17), (17, 1000)]
    for lo, hi in bands:
        sub = [r for r in rows if lo < r["dec"] <= hi]
        rep[f"price {lo}-{hi} all"] = summ(sub)
        rep[f"price {lo}-{hi} core full"] = summ([r for r in sub if r["core"] == r["core_max"] and r["core_max"] > 0])
        rep[f"price {lo}-{hi} core 0"] = summ([r for r in sub if r["core"] == 0])
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "factors.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    for k, v in rep.items():
        if isinstance(v, dict) and "n" in v:
            print(f"{k:28} n {v['n']:7}  strike {v['strike']:5}%  ROI {v['roi']:6}%")
        else:
            print(k)
            for kk, vv in v.items():
                print(f"   {kk:25} n {vv['n']:7}  strike {vv['strike']:5}%  ROI {vv['roi']:6}%")


if __name__ == "__main__":
    main()
