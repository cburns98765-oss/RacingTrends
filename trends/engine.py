"""Find past renewals of a card race, summarise the trends, score the runners."""
from collections import Counter
from statistics import median

from . import util as U

YEARS_BACK = 10
WINDOW_DAYS = 45      # how far from the same date a past race may be
MIN_TRENDS = 3        # renewals needed before runners are scored


def _f(v):
    return U.to_float(v) if v not in (None, "") else None


def _i(v):
    return U.to_int(v) if v not in (None, "") else None


def index_history(rows):
    """Group history rows by course for fast lookup; convert types once."""
    idx = {}
    for r in rows:
        try:
            d = U.parse_date(r["date"])
        except Exception:
            continue
        rec = dict(r)
        rec["_date"] = d
        rec["_dist"] = _f(r.get("dist_f"))
        rec["_class"] = _i(r.get("class"))
        rec["_kinds"] = set(filter(None, str(r.get("kinds", "")).split("+")))
        for k in ("win_age", "win_lbs", "win_from_top", "win_or", "ran", "top_lbs"):
            rec[k] = _i(r.get(k))
        for k in ("win_dec", "fav_dec"):
            rec[k] = _f(r.get(k))
        rec["fav_won"] = str(r.get("fav_won")) in ("1", "True", "true")
        rec["hcap"] = str(r.get("hcap")) in ("1", "True", "true")
        rec["_doy"] = d.timetuple().tm_yday
        # bucket by course + race type + surface + handicap so each lookup scans only like-for-like races
        for ck in {U.course_key(r.get("course_id"), r.get("course")), U.course_key(None, r.get("course"))}:
            idx.setdefault((ck, r.get("type"), r.get("surface"), rec["hcap"]), []).append(rec)
    return idx


def _dist_tol(race_type, dist):
    if race_type in ("chase", "hurdle", "nhf"):
        return 1.25
    return 0.6 if (dist or 0) <= 8 else 1.25


def _season(d, race_type):
    """Flat: calendar year. Jumps: season starting in May (Nov 2026 and Mar 2027 are both 2026)."""
    return d.year if race_type == "flat" else (d.year if d.month >= 5 else d.year - 1)


def find_renewals(card, idx):
    d = U.parse_date(card["date"])
    card_season = _season(d, card["type"])
    doy = d.timetuple().tm_yday
    keys = [(ck, card["type"], card["surface"], bool(card["hcap"]))
            for ck in (U.course_key(card.get("course_id"), card.get("course")), U.course_key(None, card.get("course")))]
    pool, seen = [], set()
    for k in keys:
        for r in idx.get(k, []):
            g = abs(r["_doy"] - doy)
            if min(g, 365 - g) > WINDOW_DAYS:
                continue
            if r["race_id"] not in seen:
                seen.add(r["race_id"])
                pool.append(r)
    cand_by_year = {}
    for r in pool:
        rd = r["_date"]
        if rd >= d or (d - rd).days > 366 * YEARS_BACK + 30:
            continue
        if _season(rd, card["type"]) >= card_season:  # earlier this season isn't a past renewal
            continue
        if r["type"] != card["type"] or r["surface"] != card["surface"]:
            continue
        if bool(r["hcap"]) != bool(card["hcap"]):
            continue
        if (r.get("pattern") or "") != (card.get("pattern") or ""):
            continue
        gap = U.doy_gap(rd, d)
        if gap > WINDOW_DAYS:
            continue
        if card.get("dist_f") and r["_dist"]:
            dd = abs(card["dist_f"] - r["_dist"])
            if dd > _dist_tol(card["type"], card["dist_f"]):
                continue
        else:
            dd = 0.6
        cc = card.get("class")
        if cc and r["_class"]:
            if abs(cc - r["_class"]) > 1:
                continue
            cdiff = abs(cc - r["_class"])
        else:
            cdiff = 0.5
        ck = set(card.get("kinds") or [])
        kind_miss = len(ck ^ r["_kinds"])
        score = 100 - dd * 12 - cdiff * 10 - gap * 0.6 - kind_miss * 7
        season = _season(rd, card["type"])
        best = cand_by_year.get(season)
        if best is None or score > best["_score"]:
            r = dict(r)
            r["_score"] = round(score, 1)
            r["_gap"] = gap
            cand_by_year[season] = r
    return sorted(cand_by_year.values(), key=lambda r: r["_date"], reverse=True)


def _range_txt(vals, unit=""):
    vals = [v for v in vals if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    return f"{lo}{unit}" if lo == hi else f"{lo}–{hi}{unit}"


def summarise(renewals):
    n = len(renewals)
    if not n:
        return {"n": 0, "insights": []}
    ages = [r["win_age"] for r in renewals if r["win_age"]]
    from_top = [r["win_from_top"] for r in renewals if r["win_from_top"] is not None]
    ors = [r["win_or"] for r in renewals if r["win_or"]]
    decs = [r["win_dec"] for r in renewals if r["win_dec"]]
    fav_w = sum(1 for r in renewals if r["fav_won"])
    trainers = Counter(r["win_trainer"] for r in renewals if r.get("win_trainer"))
    jockeys = Counter(r["win_jockey"] for r in renewals if r.get("win_jockey"))
    fields = [r["ran"] for r in renewals if r["ran"]]

    wt_rule = None
    ins = []
    ins.append({"k": "fav", "txt": f"Favourites won {fav_w} of {n}", "strength": "strong" if n >= 3 and fav_w in (0, n) else "info"})
    if decs:
        biggest = max(decs)
        ins.append({"k": "sp", "txt": f"Winners' SP {U.frac_from_dec(min(decs))} to {U.frac_from_dec(biggest)} (median {U.frac_from_dec(median(decs))})",
                    "strength": "strong" if len(decs) >= 3 and biggest <= 8 else "info"})
    if ages:
        c = Counter(ages)
        top_age, top_n = c.most_common(1)[0]
        if len(c) == 1 and len(ages) >= 3:
            ins.append({"k": "age", "txt": f"All {len(ages)} winners aged {top_age}", "strength": "strong"})
        else:
            ins.append({"k": "age", "txt": f"Winners aged {_range_txt(ages)} ({top_n}/{len(ages)} were {top_age}yo)",
                        "strength": "strong" if len(ages) >= 3 and max(ages) - min(ages) <= 2 else "info"})
    if from_top:
        near = sum(1 for x in from_top if x <= 6)
        if len(from_top) >= 3 and near / len(from_top) >= 0.75:
            wt_rule = "near"
            ins.append({"k": "wt", "txt": f"{near}/{len(from_top)} winners carried within 6lb of top weight", "strength": "strong"})
        elif len(from_top) >= 3 and near / len(from_top) <= 0.25:
            wt_rule = "below"
            ins.append({"k": "wt", "txt": f"{len(from_top) - near}/{len(from_top)} winners carried 7lb+ below top weight", "strength": "strong"})
        else:
            ins.append({"k": "wt", "txt": f"Winners carried {_range_txt(from_top, 'lb')} below top weight", "strength": "info"})
    if ors:
        ins.append({"k": "or", "txt": f"Winners rated {_range_txt(ors)}", "strength": "info"})
    rep_t = [(t, c) for t, c in trainers.most_common() if c >= 2]
    if rep_t:
        ins.append({"k": "trainer", "txt": "Repeat trainers: " + ", ".join(f"{t} ({c})" for t, c in rep_t), "strength": "strong"})
    rep_j = [(t, c) for t, c in jockeys.most_common() if c >= 2]
    if rep_j:
        ins.append({"k": "jockey", "txt": "Repeat jockeys: " + ", ".join(f"{t} ({c})" for t, c in rep_j), "strength": "info"})
    if fields:
        ins.append({"k": "field", "txt": f"Field sizes {_range_txt(fields)}", "strength": "info"})
    return {
        "n": n, "fav_wins": fav_w, "ages": ages, "from_top": from_top, "ors": ors, "decs": decs,
        "trainers": dict(trainers), "jockeys": dict(jockeys), "insights": ins, "wt_rule": wt_rule,
    }


def score_runners(card, summ, renewals):
    runners = card["runners"]
    lbs_all = [r["lbs"] for r in runners if r.get("lbs")]
    top = max(lbs_all) if lbs_all else None
    win_ids = {r.get("win_horse_id") for r in renewals if r.get("win_horse_id")}
    win_names = {U.norm_name(r.get("win_horse")) for r in renewals}
    trainers = summ.get("trainers", {})
    jockeys = summ.get("jockeys", {})
    active = summ["n"] >= MIN_TRENDS
    wt_rule = summ.get("wt_rule")
    out = []
    for r in runners:
        flags = []
        from_top = (top - r["lbs"]) if (top and r.get("lbs")) else None
        if active:
            ages = summ["ages"]
            if len(ages) >= MIN_TRENDS and r.get("age"):
                flags.append({"k": "age", "ok": min(ages) <= r["age"] <= max(ages), "txt": f"Age {r['age']}"})
            ft = summ["from_top"]
            if len(ft) >= MIN_TRENDS and from_top is not None:
                if wt_rule == "near":
                    ok = from_top <= 6
                elif wt_rule == "below":
                    ok = from_top >= 7
                else:
                    ok = max(0, min(ft) - 2) <= from_top <= max(ft) + 2
                flags.append({"k": "wt", "ok": ok, "txt": "Top weight" if from_top == 0 else f"{from_top}lb off top"})
            ors = summ["ors"]
            if card.get("hcap") and len(ors) >= MIN_TRENDS and r.get("or"):
                flags.append({"k": "or", "ok": min(ors) - 3 <= r["or"] <= max(ors) + 3, "txt": f"OR {r['or']}"})
        t = sum(c for name, c in trainers.items() if U.same_person(name, r.get("trainer")))
        if t:
            flags.append({"k": "trainer", "ok": True, "txt": f"Trainer won {t}x"})
        j = sum(c for name, c in jockeys.items() if U.same_person(name, r.get("jockey")))
        if j:
            flags.append({"k": "jockey", "ok": True, "txt": f"Jockey won {j}x"})
        if (r.get("horse_id") and r["horse_id"] in win_ids) or U.norm_name(r.get("horse")) in win_names:
            flags.append({"k": "cdwin", "ok": True, "txt": "Won this race before"})
        score = sum(1 for f in flags if f["ok"]) + sum(1 for f in flags if f["k"] == "cdwin")
        out.append({**r, "from_top": from_top, "flags": flags, "score": score})
    out.sort(key=lambda x: (-x["score"], x.get("number") or 99))
    max_possible = 0
    if active:
        max_possible = sum(1 for k in ("ages", "from_top") if len(summ[k]) >= MIN_TRENDS)
        if card.get("hcap") and len(summ["ors"]) >= MIN_TRENDS:
            max_possible += 1
    return out, max_possible


def analyse(card, idx):
    ren = find_renewals(card, idx)
    summ = summarise(ren)
    runners, max_core = score_runners(card, summ, ren)
    public_ren = [{
        "date": r["date"], "course": r["course"], "race_name": r["race_name"], "class": r.get("class"),
        "dist_f": r["_dist"], "going": r.get("going"), "ran": r["ran"], "winner": r["win_horse"],
        "age": r["win_age"], "lbs": r["win_lbs"], "from_top": r["win_from_top"], "or": r["win_or"],
        "sp": r.get("win_sp") or U.frac_from_dec(r["win_dec"]), "trainer": r["win_trainer"],
        "jockey": r["win_jockey"], "fav": r.get("fav_horse"), "fav_won": r["fav_won"],
        "fav_pos": r.get("fav_pos"), "match": r["_score"],
    } for r in ren]
    s = {k: v for k, v in summ.items() if k in ("n", "fav_wins", "insights")}
    return {**{k: v for k, v in card.items() if k != "runners"}, "renewals": public_ren,
            "summary": s, "runners": runners, "max_core": max_core}
