"""Selection rules and paper-bet maths for the Betfair paper-trading bot.

Everything here is plain Python (no Betfair connection), so it can be tested offline.
Rules are switched on/off and tuned in rules.json.
"""
import re
import unicodedata

STYLE = {"F": "front-runner", "P": "prominent", "M": "mid-division", "H": "held up"}


def norm(s):
    """'Everest (IRE)' -> 'everest'; 'Chelmsford City (AW)' -> 'chelmsford city'."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = s.replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


VENUE_ALIASES = {"bangor on dee": "bangor", "chelmsford": "chelmsford city", "down royal": "down royal",
                 "newcastle": "newcastle", "kempton park": "kempton", "sandown park": "sandown",
                 "haydock park": "haydock", "epsom downs": "epsom", "yarmouth": "great yarmouth"}


def venue_key(s):
    k = norm(s)
    return VENUE_ALIASES.get(k, k)


def race_kind(race):
    t = (race.get("type") or "").lower()
    if t in ("hurdle", "chase"):
        return t.title()
    if t == "flat":
        aw = (race.get("surface") or "").lower() == "aw" or "(aw)" in (race.get("course") or "").lower()
        return "Flat AW" if aw else "Flat turf"
    return ""


def course_bias(race, bias_rows):
    """front-runner bias for this course and race type (1.00 = national average), or None."""
    k, c = race_kind(race), venue_key(race.get("course"))
    for r in bias_rows:
        if r["kind"] == k and venue_key(r["course"]) == c:
            return float(r["bias"])
    return None


def top_pick(race, min_score=5):
    scores = [x.get("score") or 0 for x in race["runners"]]
    if not scores:
        return None
    best = max(scores)
    if best < min_score or scores.count(best) > 1:
        return None
    return race["runners"][scores.index(best)]


def build_selections(card, bias_rows, rules):
    """Turn today's dashboard card + course pace bias into a list of things for the bot to watch."""
    out = []
    for m in card.get("meetings", []):
        for race in m.get("races", []):
            base = {"date": race.get("date") or card.get("date"), "course": race.get("course"), "off": race.get("off"),
                    "race": race.get("race_name", "")}
            bias = course_bias(race, bias_rows)
            pace = race.get("pace") or {}
            lone_f = (pace.get("groups") or {}).get("F") or []
            r = rules.get("front_runner_course_bias", {})
            if r.get("enabled") and bias is not None and bias >= r.get("min_bias", 1.05) and len(lone_f) == 1:
                horse = lone_f[0]
                out.append({**base, "horse": horse, "rule": "front_runner_course_bias", "side": "BACK",
                            "phase": "pre_off", "min_price": r.get("min_price", 3.0), "max_price": r.get("max_price", 15.0),
                            "window_min": r.get("window_minutes", 5),
                            "reason": f"Lone habitual front-runner at a course where front-runners win {bias:.2f}x the average"})
            r = rules.get("trend_top_pick", {})
            tp = top_pick(race, r.get("min_score", 5)) if r.get("enabled") else None
            if tp:
                out.append({**base, "horse": tp["horse"], "rule": "trend_top_pick", "side": "BACK", "phase": "pre_off",
                            "min_price": r.get("min_price", 2.0), "max_price": r.get("max_price", 21.0),
                            "window_min": r.get("window_minutes", 5),
                            "reason": f"Clear top pick on the trends ({tp['score']}/{(race.get('max_core') or 0) + 4})"})
            r = rules.get("folds_when_short_lay", {})
            if r.get("enabled"):
                for x in race.get("runners", []):
                    badges = ((x.get("profile") or {}).get("badges") or [])
                    if any(b.get("k") == "ip_short" for b in badges):
                        out.append({**base, "horse": x["horse"], "rule": "folds_when_short_lay", "side": "LAY", "phase": "in_play",
                                    "max_price": r.get("lay_at_or_below", 1.5),
                                    "reason": "Has traded 1.5 or shorter in running and lost at least half the time"})
    return out


def check_trigger(sel, best_back, best_lay, inplay, minutes_to_off):
    """Return the price the paper bet is struck at, or None. Paper fills assume the whole stake is matched
    at the best price on offer when the condition is met."""
    if sel["phase"] == "pre_off":
        if inplay or minutes_to_off is None or minutes_to_off > sel.get("window_min", 5) or minutes_to_off < -1:
            return None
        if sel["side"] == "BACK" and best_back and sel["min_price"] <= best_back <= sel["max_price"]:
            return best_back
        return None
    if sel["phase"] == "in_play":
        if not inplay:
            return None
        if sel["side"] == "LAY" and best_lay and best_lay <= sel["max_price"]:
            return best_lay
        if sel["side"] == "BACK" and best_back and best_back >= sel.get("min_price", 1.01):
            return best_back
    return None


def profit_loss(side, price, stake, horse_won, commission):
    if side == "BACK":
        return round(stake * (price - 1) * (1 - commission), 2) if horse_won else -stake
    return -round(stake * (price - 1), 2) if horse_won else round(stake * (1 - commission), 2)
