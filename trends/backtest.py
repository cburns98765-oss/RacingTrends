"""Replay history: score every past race as the dashboard would have on the day, then settle the picks.

    python -m trends.backtest RFB_FILES... [--from 2019-01-01] [--out backtest/]

For each race the card is rebuilt from the runners that actually ran, trends come only from
earlier seasons (find_renewals never looks at the same or a later season), runners are scored
exactly as live, and the race's clear top fit is settled at starting price (£1 level stakes).
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from multiprocessing import Pool

from . import engine, importers
from . import util as U

_IDX = None


def iter_cards(paths, since):
    """Yield (card, winner_info) per race from runner-level RacingFormBook / rpscrape files."""
    cur_id, rows = None, []
    seen = set()

    def build(rows):
        f = rows[0]
        name = f.get("race_name", "")
        course = U.clean_course(f.get("course", ""))
        runners, win = [], None
        for r in rows:
            x = {"horse": r.get("horse", ""), "age": U.to_int(r.get("age")), "lbs": U.to_int(r.get("lbs")),
                 "or": U.to_int(r.get("or")), "trainer": r.get("trainer", ""), "jockey": r.get("jockey", ""),
                 "number": None}
            runners.append(x)
            if str(r.get("pos", "")).strip() == "1":
                win = {"horse": x["horse"], "dec": U.to_float(r.get("dec")), "sp": r.get("sp", "")}
        card = {
            "race_id": str(f.get("race_id")), "date": f.get("date", ""), "region": f.get("region", ""),
            "course_id": "", "course": course, "off": f.get("off", ""), "race_name": name,
            "type": U.race_type(f.get("type"), name), "surface": U.surface(f.get("surface"), course, f.get("going")),
            "class": U.race_class(f.get("class")), "pattern": U.pattern_level("", name),
            "hcap": int(U.is_handicap(name)), "kinds": U.kinds(name), "dist_f": U.to_float(f.get("dist_f")),
            "going": f.get("going", ""), "runners": runners,
        }
        return card, win

    for row in importers._rows(paths, set()):
        rid = str(row.get("race_id"))
        if rid != cur_id:
            if rows and cur_id not in seen and rows[0].get("date", "") >= since and rows[0].get("region") in ("gb", "ire"):
                seen.add(cur_id)
                c, w = build(rows)
                if w:
                    yield c, w
            cur_id, rows = rid, []
        rows.append(row)
    if rows and cur_id not in seen and rows[0].get("date", "") >= since and rows[0].get("region") in ("gb", "ire"):
        c, w = build(rows)
        if w:
            yield c, w


def _init(hist_path):
    global _IDX
    _IDX = engine.index_history(importers.read_history(hist_path))


def _score(item):
    card, win = item
    try:
        a = engine.analyse(card, _IDX)
    except Exception as e:  # a malformed race shouldn't stop a 90,000-race replay
        return {"race_id": card["race_id"], "error": str(e)}
    out = {"race_id": card["race_id"], "date": card["date"], "course": card["course"], "off": card["off"],
           "race": card["race_name"], "type": card["type"], "surface": card["surface"], "region": card["region"],
           "hcap": card["hcap"], "renewals": a["summary"]["n"], "runners": len(card["runners"]),
           "winner": win["horse"], "winner_sp": win["sp"]}
    if a["summary"]["n"] < engine.MIN_TRENDS or not a["runners"]:
        return out
    top = a["runners"][0]["score"]
    tops = [x for x in a["runners"] if x["score"] == top]
    pick = tops[0] if len(tops) == 1 and top > 0 else None
    out.update({"top_score": top, "max": a["max_core"] + 4, "tied": len(tops)})
    if pick:
        won = U.norm_name(pick["horse"]) == U.norm_name(win["horse"])
        out.update({"pick": pick["horse"], "won": int(won),
                    "pl": round(win["dec"] - 1, 3) if (won and win["dec"]) else (-1.0 if not won else 0.0)})
    return out


def summary(rows):
    n = len(rows)
    w = sum(r["won"] for r in rows)
    pl = round(sum(r["pl"] for r in rows), 2)
    return {"picks": n, "wins": w, "strike": round(100 * w / n, 1) if n else 0.0, "pl": pl,
            "roi": round(100 * pl / n, 1) if n else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--history", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                       "data", "history", "rfb.csv.gz"))
    ap.add_argument("--from", dest="since", default="2019-01-01")
    ap.add_argument("--out", default="backtest")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    cards = list(iter_cards(args.files, args.since))
    print(f"{len(cards)} races since {args.since}", file=sys.stderr)
    with Pool(args.workers, initializer=_init, initargs=(args.history,)) as pool:
        results = []
        for i, r in enumerate(pool.imap_unordered(_score, cards, chunksize=200), 1):
            results.append(r)
            if i % 10000 == 0:
                print(f"  scored {i}", file=sys.stderr)
    results.sort(key=lambda r: (r.get("date", ""), str(r.get("course", "")), str(r.get("off", ""))))

    cols = ["date", "course", "off", "race", "region", "type", "surface", "hcap", "renewals", "runners",
            "top_score", "max", "tied", "pick", "won", "pl", "winner", "winner_sp"]
    with open(os.path.join(args.out, "races.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(r for r in results if "error" not in r)

    clear = [r for r in results if "pick" in r]
    rep = {"races": len(results), "errors": sum(1 for r in results if "error" in r),
           "scored": sum(1 for r in results if "top_score" in r), "clear_top": len(clear)}
    rep["by_threshold"] = {f"{k}+": summary([r for r in clear if r["top_score"] >= k]) for k in range(1, 8)}
    picks = [r for r in clear if r["top_score"] >= 5]
    rep["picks_5plus"] = summary(picks)
    for key in ("year", "score", "type", "region", "hcap", "surface"):
        g = defaultdict(list)
        for r in picks:
            k = {"year": r["date"][:4], "score": f"{r['top_score']}/{r['max']}", "hcap": "handicap" if r["hcap"] else "non-handicap"}.get(key, r.get(key))
            g[k].append(r)
        rep[f"by_{key}"] = {k: summary(v) for k, v in sorted(g.items())}
    with open(os.path.join(args.out, "summary.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps({k: rep[k] for k in ("races", "errors", "scored", "clear_top", "picks_5plus")}, indent=1))


if __name__ == "__main__":
    main()
