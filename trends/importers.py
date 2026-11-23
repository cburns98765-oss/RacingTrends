"""Turn rpscrape output into the two shapes the engine uses.

* results CSV  -> one compact row per race (winner, favourite, field facts)
* racecards JSON -> list of card races with runners
"""
import csv
import gzip
import io
import json
import os
from datetime import datetime

from . import util as U

RACE_FIELDS = [
    "race_id", "date", "region", "course_id", "course", "off", "race_name", "type", "surface",
    "class", "pattern", "hcap", "kinds", "age_band", "rating_band", "dist_f", "going", "ran",
    "top_lbs", "win_horse", "win_horse_id", "win_age", "win_lbs", "win_from_top", "win_or",
    "win_sp", "win_dec", "win_trainer", "win_jockey", "fav_horse", "fav_dec", "fav_pos",
    "fav_won", "second", "third",
]


def _open_text(path):
    """Text handle that copes with UTF-8 or Windows-1252 files (RacingFormBook uses the latter)."""
    raw = gzip.open(path, "rb") if str(path).endswith(".gz") else open(path, "rb")
    head = raw.peek(65536)[:65536] if hasattr(raw, "peek") else b""
    try:
        head.decode("utf-8")
        enc = "utf-8-sig"
    except UnicodeDecodeError:
        enc = "cp1252"
    return io.TextIOWrapper(raw, encoding=enc, errors="replace", newline="")


# RacingFormBook "SFF" results files -> the column names the summariser understands
SFF_TYPES = {"h": "Hurdle", "c": "Chase", "b": "NH Flat", "": "Flat"}


def _sff_row(r):
    course = (r.get("Course") or "").strip()
    region = "ire" if "(IRE)" in course else ("gb" if "(" not in course else course[course.rfind("(") + 1:-1].lower())
    try:
        d = datetime.strptime(r["RaceDate"].strip(), "%d-%b-%y").date().isoformat()
    except (ValueError, KeyError):
        d = r.get("RaceDate", "")
    ratio = U.to_float(r.get("Sp"))
    dec = round(ratio + 1, 3) if ratio is not None else None
    fav = (r.get("Favs") or "").strip()
    fav_tag = {"Fav": "F", "JFav": "J", "CFav": "C"}.get(fav, "")
    sp = (U.frac_from_dec(dec) + fav_tag) if dec else ""
    going = r.get("Going", "")
    yards = U.to_float(r.get("Yards"))
    return {
        "race_id": f"rfb{r.get('Id', '')}", "date": d, "region": region, "course": course,
        "off": r.get("RaceTime", ""), "race_name": r.get("Race", ""),
        "type": SFF_TYPES.get((r.get("Type") or "").strip().lower(), "Flat"),
        "surface": "aw" if "(aw" in going.lower() else "turf", "class": r.get("Class", ""),
        "dist_f": round(yards / 220, 2) if yards else "", "dist": r.get("Distance", ""),
        "going": going, "ran": r.get("Ran", ""), "pos": r.get("FPos", ""), "horse": r.get("HorseName", ""),
        "age": r.get("Age", ""), "lbs": r.get("WeightLBS", ""), "or": r.get("OR", ""), "dec": dec or "",
        "sp": sp, "trainer": r.get("Trainer", ""), "jockey": r.get("Jockey", ""), "rating_band": r.get("Limit", ""),
    }


def _rows(paths, seen_cols):
    for p in paths:
        with _open_text(p) as fh:
            reader = csv.DictReader(fh)
            cols = reader.fieldnames or []
            seen_cols.update(cols)
            sff = "FPos" in cols and "HorseName" in cols
            for row in reader:
                yield _sff_row(row) if sff else row


def results_csv_to_races(paths):
    """Summarise runner rows race by race, streaming (a race's rows are consecutive in both
    rpscrape and RacingFormBook files, so 10 years of data never has to sit in memory)."""
    seen_cols = set()
    out = {}
    cur_id, cur_rows = None, []

    def flush():
        if cur_rows:
            s = _summarise(cur_id, cur_rows)
            if s and (cur_id not in out or len(cur_rows) >= int(out[cur_id].get("ran") or 0)):
                out[cur_id] = s

    for row in _rows(paths, seen_cols):
        rid = U.pick(row, "race_id", "raceid")
        if not rid:
            rid = "|".join(str(U.pick(row, k, default="")) for k in ("date", "course", "off", "race_name"))
        rid = str(rid)
        if rid != cur_id:
            flush()
            cur_id, cur_rows = rid, []
        cur_rows.append(row)
    flush()
    if seen_cols and not {"pos", "position", "fpos"} & {c.lower() for c in seen_cols}:
        raise SystemExit(f"Results CSV has no position column. Columns found: {sorted(seen_cols)}")
    return list(out.values())


def _summarise(rid, rows):
    first = rows[0]
    name = U.pick(first, "race_name", "race", "title", default="")
    going = U.pick(first, "going", default="")
    course = U.clean_course(U.pick(first, "course", "course_name", default=""))
    try:
        d = U.parse_date(U.pick(first, "date"))
    except Exception:
        return None

    runners = []
    for r in rows:
        sp = U.pick(r, "sp", "starting_price")
        dec = U.to_float(U.pick(r, "dec", "sp_dec", "decimal_sp")) or U.sp_to_dec(sp)
        runners.append({
            "horse": U.pick(r, "horse", "horse_name", "name", default=""),
            "horse_id": str(U.pick(r, "horse_id", default="") or ""),
            "pos": str(U.pick(r, "pos", "position", default="")).strip(),
            "age": U.to_int(U.pick(r, "age")),
            "lbs": U.to_int(U.pick(r, "lbs", "weight_lbs", "wgt_lbs")),
            "or": U.to_int(U.pick(r, "or", "ofr", "official_rating")),
            "sp": sp or "",
            "dec": dec,
            "fav_tag": U.sp_is_fav(sp),
            "trainer": U.pick(r, "trainer", default=""),
            "jockey": U.pick(r, "jockey", default=""),
        })
    winner = next((x for x in runners if x["pos"] == "1"), None)
    if not winner:
        return None  # abandoned / void
    lbs_all = [x["lbs"] for x in runners if x["lbs"]]
    top = max(lbs_all) if lbs_all else None
    tagged = [x for x in runners if x["fav_tag"]]
    priced = [x for x in runners if x["dec"]]
    if tagged:  # SP marked F / J / C: trust the tag
        fav = min(tagged, key=lambda x: x["dec"] or 999)
        fav_won = winner["fav_tag"]
    elif len(priced) >= 2:
        fav = min(priced, key=lambda x: x["dec"])
        fav_won = bool(winner["dec"] and abs(winner["dec"] - fav["dec"]) < 1e-6)
    else:
        fav, fav_won = None, False
    placed = {x["pos"]: x["horse"] for x in runners}
    ran = U.to_int(U.pick(first, "ran", "runners", "field_size")) or len(runners)
    return {
        "race_id": str(rid),
        "date": d.isoformat(),
        "region": str(U.pick(first, "region", default="")).lower(),
        "course_id": str(U.pick(first, "course_id", default="") or ""),
        "course": course,
        "off": U.pick(first, "off", "off_time", "time", default=""),
        "race_name": name,
        "type": U.race_type(U.pick(first, "type", "race_type"), name),
        "surface": U.surface(U.pick(first, "surface"), course, going),
        "class": U.race_class(U.pick(first, "class", "race_class")) or "",
        "pattern": U.pattern_level(U.pick(first, "pattern"), name),
        "hcap": int(U.is_handicap(name)),
        "kinds": "+".join(U.kinds(name)),
        "age_band": U.pick(first, "age_band", default=""),
        "rating_band": U.pick(first, "rating_band", default=""),
        "dist_f": U.dist_furlongs(U.pick(first, "dist_f", "distance_f"), U.pick(first, "dist", "distance")) or "",
        "going": going,
        "ran": ran,
        "top_lbs": top or "",
        "win_horse": winner["horse"],
        "win_horse_id": winner["horse_id"],
        "win_age": winner["age"] or "",
        "win_lbs": winner["lbs"] or "",
        "win_from_top": (top - winner["lbs"]) if (top and winner["lbs"]) else "",
        "win_or": winner["or"] or "",
        "win_sp": winner["sp"],
        "win_dec": winner["dec"] or "",
        "win_trainer": winner["trainer"],
        "win_jockey": winner["jockey"],
        "fav_horse": fav["horse"] if fav else "",
        "fav_dec": (fav["dec"] or "") if fav else "",
        "fav_pos": fav["pos"] if fav else "",
        "fav_won": int(bool(fav_won)),
        "second": placed.get("2", ""),
        "third": placed.get("3", ""),
    }


# ---------------------------------------------------------------- racecards

def _iter_races(obj, path=()):
    """Walk any racecards JSON layout and yield (race_dict, key_path) for dicts with a runners list."""
    if isinstance(obj, dict):
        if isinstance(obj.get("runners"), list):
            yield obj, path
            return
        for k, v in obj.items():
            yield from _iter_races(v, path + (str(k),))
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_races(v, path)


def racecards_to_races(path, fallback_date=None):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for r, path in _iter_races(data):
        name = U.pick(r, "race_name", "name", "title", default="")
        course = U.clean_course(U.pick(r, "course", "course_name", default="")) or (path[1] if len(path) > 1 else "")
        region_from_path = next((k for k in path if k.isalpha() and 2 <= len(k) <= 4), "")
        going = U.pick(r, "going", "going_detailed", default="")
        d = U.pick(r, "date", default=fallback_date)
        runners = []
        for x in r["runners"]:
            if str(U.pick(x, "non_runner", "nr", default="")).lower() in ("true", "1", "yes"):
                continue
            runners.append({
                "horse": U.pick(x, "name", "horse", "horse_name", default=""),
                "horse_id": str(U.pick(x, "horse_id", "id", default="") or ""),
                "number": U.to_int(U.pick(x, "number", "num", "saddle_cloth")),
                "age": U.to_int(U.pick(x, "age")),
                "lbs": U.to_int(U.pick(x, "lbs", "weight_lbs")),
                "or": U.to_int(U.pick(x, "ofr", "or", "official_rating", "rating")),
                "rpr": U.to_int(U.pick(x, "rpr")),
                "ts": U.to_int(U.pick(x, "ts", "topspeed")),
                "trainer": U.pick(x, "trainer", "trainer_name", default=""),
                "jockey": U.pick(x, "jockey", "jockey_name", default=""),
                "form": str(U.pick(x, "form", default="") or ""),
            })
        out.append({
            "race_id": str(U.pick(r, "race_id", "id", default="") or ""),
            "date": str(d)[:10] if d else "",
            "region": str(U.pick(r, "region", default=region_from_path)).lower(),
            "course_id": str(U.pick(r, "course_id", default="") or ""),
            "course": course,
            # The Racing API gives off_time on a 12-hour clock ("1:30"); off_dt has the real 24h time
            "off": (str(U.pick(r, "off_dt"))[11:16] if U.pick(r, "off_dt") else U.pick(r, "off_time", "off", "time", default="")),
            "race_name": name,
            "type": U.race_type(U.pick(r, "type", "race_type"), name),
            "surface": U.surface(U.pick(r, "surface"), course, going),
            "class": U.race_class(U.pick(r, "race_class", "class")),
            "pattern": U.pattern_level(U.pick(r, "pattern"), name),
            "hcap": int(U.is_handicap(name)),
            "kinds": U.kinds(name),
            "dist_f": U.dist_furlongs(U.pick(r, "distance_f", "dist_f"), U.pick(r, "distance", "dist", "distance_round")),
            "dist": U.pick(r, "distance", "distance_round", "dist", default=""),
            "going": going,
            "prize": U.pick(r, "prize", default=""),
            "runners": runners,
        })
    return out


# ---------------------------------------------------------------- storage

def read_history(path):
    try:
        with _open_text(path) as fh:
            return list(csv.DictReader(fh))
    except FileNotFoundError:
        return []


def write_history(path, races):
    races = sorted(races, key=lambda r: (r["date"], str(r["course"]), str(r["off"])))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RACE_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in races:
            w.writerow(r)


def merge(existing, new):
    by_id = {r["race_id"]: r for r in existing}
    added = 0
    for r in new:
        if r["race_id"] not in by_id:
            added += 1
        by_id[r["race_id"]] = r
    return list(by_id.values()), added
