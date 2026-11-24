"""Command line entry point.

  python -m trends history  RESULTS.csv [...]        # add results to data/history/races.csv.gz
  python -m trends cards    RACECARDS.json [...]     # analyse cards -> docs/data/cards/<date>.json
  python -m trends settle   RESULTS.csv [...]        # mark winners on cards, update performance, add to history
  python -m trends merge    PART.csv.gz [...]        # merge backfill parts into history
  python -m trends bundle                            # docs/standalone.html with data embedded
"""
import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from . import engine, formtrends, importers, profiles
from . import util as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(ROOT, "data", "history", "races.csv.gz")
SITE = os.environ.get("RT_SITE") or os.path.join(ROOT, "docs")  # tests point this at a temp dir
CARDS = os.path.join(SITE, "data", "cards")
PICKS = os.path.join(SITE, "data", "picks.json")  # permanent log of top picks (cards are pruned)
PROFILES = os.environ.get("RT_PROFILES") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "profiles.json.gz")
KEEP_DAYS = 60
PICK_MIN_SCORE = 5   # a top pick = the race's single clear top fit scoring 5+ (5/7 or 5/6 and above)


def _top_pick(race):
    if not race.get("runners"):
        return None
    top = max(x["score"] for x in race["runners"])
    tops = [x for x in race["runners"] if x["score"] == top]
    return tops[0] if (top >= PICK_MIN_SCORE and len(tops) == 1) else None


def _expand(paths):
    out = []
    for p in paths:
        out.extend(sorted(glob.glob(p)) or [p])
    return [p for p in out if os.path.exists(p)]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def cmd_history(args):
    paths = _expand(args.files)
    new = importers.results_csv_to_races(paths)
    hist = importers.read_history(args.history)
    merged, added = importers.merge(hist, new)
    importers.write_history(args.history, merged)  # creates the folder if needed
    print(f"history: {len(new)} races read, {added} new, {len(merged)} total -> {args.history}")


def cmd_merge(args):
    """Merge compact history parts (from the backfill jobs) into the main history file."""
    merged = importers.read_history(args.history)
    total_added = 0
    for p in _expand(args.files):
        merged, added = importers.merge(merged, importers.read_history(p))
        total_added += added
    importers.write_history(args.history, merged)
    print(f"merge: +{total_added} races, {len(merged)} total -> {args.history}")


def _all_history(main_path):
    """The daily runs write races.csv.gz; the local backfill writes backfill.csv.gz. Read every file."""
    rows = []
    for p in sorted(set(glob.glob(os.path.join(os.path.dirname(os.path.abspath(main_path)), "*.csv.gz"))) | {main_path}):
        rows, _ = importers.merge(rows, importers.read_history(p))
    return rows


def cmd_cards(args):
    hist = _all_history(args.history)
    idx = engine.index_history(hist)
    wf, tw = formtrends.load(), formtrends.trainer_winners(hist)
    regions = {r.strip().lower() for r in (args.regions or "").split(",") if r.strip()}
    by_date = defaultdict(list)
    for p in _expand(args.files):
        for race in importers.racecards_to_races(p, fallback_date=args.date):
            if regions and race["region"] and race["region"] not in regions:
                continue
            if race["date"]:
                by_date[race["date"]].append(race)
    os.makedirs(CARDS, exist_ok=True)
    prof = profiles.load(PROFILES)
    for d, races in by_date.items():
        path = os.path.join(CARDS, f"{d}.json")
        old = _load(path, {}).get("results", {})
        analysed = [formtrends.attach(profiles.attach(engine.analyse(r, idx), prof), wf, tw) for r in races]
        meetings = defaultdict(list)
        for a in analysed:
            meetings[(a["course"], a["region"])].append(a)
        doc = {
            "date": d, "generated": _now(), "results": old,
            "meetings": [{"course": c, "region": reg, "races": sorted(rs, key=lambda x: str(x["off"]))}
                         for (c, reg), rs in sorted(meetings.items(), key=lambda kv: (kv[0][1] != "gb", kv[0][0]))],
        }
        _save(path, doc)
        with_trends = sum(1 for a in analysed if a["summary"]["n"] >= engine.MIN_TRENDS)
        print(f"cards {d}: {len(analysed)} races, {with_trends} with {engine.MIN_TRENDS}+ renewals")
    _write_index()


def cmd_settle(args):
    paths = _expand(args.files)
    new = importers.results_csv_to_races(paths)
    hist = importers.read_history(args.history)
    merged, added = importers.merge(hist, new)
    importers.write_history(args.history, merged)
    by_date = defaultdict(dict)
    for r in new:
        by_date[r["date"]][r["race_id"]] = r
    picks = _load(PICKS, {})
    for d, res in by_date.items():
        path = os.path.join(CARDS, f"{d}.json")
        doc = _load(path, None)
        if not doc:
            continue
        settled = 0
        for m in doc["meetings"]:
            for race in m["races"]:
                r = res.get(race.get("race_id")) or _find_by_course_time(res, race)
                if not r:
                    continue
                win = U.norm_name(r["win_horse"])
                for x in race["runners"]:
                    x["won"] = U.norm_name(x["horse"]) == win or (x.get("horse_id") and x["horse_id"] == r["win_horse_id"])
                top = max((x["score"] for x in race["runners"]), default=0)
                clear = top > 0 and sum(1 for x in race["runners"] if x["score"] == top) == 1
                w = next((x for x in race["runners"] if x.get("won")), None)
                scored = race["summary"]["n"] >= engine.MIN_TRENDS
                doc["results"][race["race_id"]] = {
                    "winner": r["win_horse"], "sp": r["win_sp"], "fav_won": r["fav_won"],
                    "winner_score": w["score"] if w else None, "top_score": top,
                    "top_scored_won": bool(w and w["score"] == top and top > 0),
                    "clear_top": clear, "clear_top_won": bool(clear and w and w["score"] == top),
                    "scored": scored,
                }
                pick = _top_pick(race) if scored else None
                if pick:
                    won = bool(pick.get("won"))
                    dec = U.to_float(r.get("win_dec")) or U.sp_to_dec(r.get("win_sp"))
                    picks[race["race_id"]] = {
                        "date": d, "course": race["course"], "off": race["off"], "race": race["race_name"],
                        "horse": pick["horse"], "score": pick["score"], "max": race.get("max_core", 0) + 4,
                        "won": won, "sp": r["win_sp"] if won else "", "winner": r["win_horse"],
                        "winner_sp": r["win_sp"],
                        "pl": round(dec - 1, 2) if (won and dec) else (-1.0 if not won else None),
                    }
                settled += 1
        doc["settled"] = _now()
        _save(path, doc)
        print(f"settle {d}: {settled} races")
    _save(PICKS, picks)
    _write_performance()
    _write_index()
    print(f"history: +{added} races")


def _find_by_course_time(res, race):
    def hm(t):  # '1:30', '13:30', '13:30:00' -> minutes past midnight, treating 1:00-11:59 as afternoon if needed
        try:
            h, m = (int(x) for x in str(t).strip()[:5].split(":")[:2])
        except ValueError:
            return None
        return h * 60 + m
    want = hm(race["off"])
    for r in res.values():
        if U.course_name_key(r["course"]) != U.course_name_key(race["course"]):
            continue
        got = hm(r["off"])
        if want is not None and got is not None and (got == want or (got + 720) % 1440 == want or (want + 720) % 1440 == got):
            return r
    return None


def _write_performance():
    """Results of top picks only: wins, strike rate and level-stakes P/L at SP (£1 a pick)."""
    picks = sorted(_load(PICKS, {}).values(), key=lambda p: (p["date"], str(p["off"])))

    def summary(ps):
        n, w = len(ps), sum(1 for p in ps if p["won"])
        pl = round(sum(p["pl"] for p in ps if p["pl"] is not None), 2)
        return {"picks": n, "wins": w, "strike": round(100 * w / n, 1) if n else 0.0, "pl": pl,
                "roi": round(100 * pl / n, 1) if n else 0.0}

    by_score = defaultdict(list)
    for p in picks:
        by_score[f"{p['score']}/{p['max']}"].append(p)
    days = defaultdict(list)
    for p in picks:
        days[p["date"]].append(p)
    perf = {
        "updated": _now(), "min_score": PICK_MIN_SCORE, **summary(picks),
        "by_score": [{"label": k, **summary(v)} for k, v in sorted(by_score.items(), reverse=True)],
        "days": [{"date": d, **summary(v)} for d, v in sorted(days.items())],
        "recent": picks[-100:][::-1],
    }
    _save(os.path.join(SITE, "data", "performance.json"), perf)


def _write_sheet_csv():
    """Today's and later cards as Date,Course,Time,Horse for the bet-tracker Google Sheet (IMPORTDATA)."""
    import csv
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")
    rows = []
    for f in sorted(glob.glob(os.path.join(CARDS, "*.json"))):
        d = os.path.basename(f)[:10]
        if d < today:
            continue
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        for m in doc.get("meetings", []):
            for r in m.get("races", []):
                for x in r.get("runners", []):
                    rows.append((d, r.get("course") or m.get("course"), r.get("off", ""), x.get("horse", "")))
    rows.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    with open(os.path.join(SITE, "data", "sheet_cards.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Course", "Time", "Horse"])
        w.writerows(rows)


def _write_index():
    _write_sheet_csv()
    files = sorted(glob.glob(os.path.join(CARDS, "*.json")))
    for old in files[:-KEEP_DAYS]:
        os.remove(old)
    files = files[-KEEP_DAYS:]
    dates = []
    for p in files:
        doc = _load(p, {})
        n = sum(len(m["races"]) for m in doc.get("meetings", []))
        dates.append({"date": doc.get("date"), "races": n, "meetings": len(doc.get("meetings", [])),
                      "settled": bool(doc.get("results"))})
    _save(os.path.join(SITE, "data", "index.json"), {"updated": _now(), "dates": dates})


def cmd_bundle(args):
    """Inline all JSON into one HTML file (for previews and offline use)."""
    blob = {"index": _load(os.path.join(SITE, "data", "index.json"), {}),
            "performance": _load(os.path.join(SITE, "data", "performance.json"), {}),
            "cards": {}}
    for p in glob.glob(os.path.join(CARDS, "*.json")):
        d = _load(p, {})
        blob["cards"][d.get("date")] = d
    with open(os.path.join(SITE, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    tag = "<script>window.__BUNDLE__=" + json.dumps(blob, separators=(",", ":")).replace("</", "<\\/") + ";</script>"
    html = html.replace("<!--BUNDLE-->", tag)
    out = args.out or os.path.join(SITE, "standalone.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"bundle -> {out}")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(prog="trends")
    ap.add_argument("--history", default=HISTORY)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("history", cmd_history), ("cards", cmd_cards), ("settle", cmd_settle), ("merge", cmd_merge)):
        p = sub.add_parser(name)
        p.add_argument("files", nargs="+")
        p.add_argument("--date", help="fallback date for cards without one (YYYY-MM-DD)")
        p.add_argument("--regions", default="gb,ire", help="card regions to keep (comma list; empty = all)")
        p.set_defaults(fn=fn)
    p = sub.add_parser("bundle")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_bundle)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
