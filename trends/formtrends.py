"""Form trends of past winners (placed last time, recent win, trainer in form, rating rank, run style...).

Backtest (trends/extras.py, 2018-2026): runners that fit these trends win more often, but the
market already prices that in. Picks built on them were worse value than the main score, so they
are shown on the dashboard to help read a race and are NOT added to the score.

    python -m trends.formtrends export   # winner features for every RacingFormBook race -> data/form/winner_form.csv.gz
"""
import csv
import gzip
import os
from datetime import timedelta

from . import util as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "form", "winner_form.csv.gz")
FIELDS = ["race_id", "lto_top3", "won_last3", "trainer_14d", "or_rank", "days", "handy", "course_win", "dist_win"]
MIN_N = 3
SHARE = 0.7

BOOL_TXT = {
    "lto_top3": ("finished in the first 3 last time out", "Placed last time"),
    "won_last3": ("had won in their last 3 runs", "Won in last 3"),
    "trainer_14d": ("had a trainer with a winner in the previous 14 days", "Trainer in form"),
    "handy": ("usually raced up with the pace", "Races handy"),
    "course_win": ("had already won at the course", "Course winner"),
    "dist_win": ("had already won over a similar trip", "Distance winner"),
}


def export(src="/tmp/extras_runners.pkl", out=PATH):
    import pandas as pd
    df = pd.read_pickle(src)
    w = df[df["win"] == 1].drop_duplicates("race_id")[FIELDS]
    w.to_csv(out, index=False, compression="gzip", float_format="%.0f")
    print(f"{len(w)} winners -> {out}")


def load(path=PATH):
    if not os.path.exists(path):
        return {}
    out = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["race_id"]] = {k: (float(v) if v not in ("", None) else None) for k, v in r.items() if k != "race_id"}
    return out


def trainer_winners(history):
    """date -> list of person_keys of trainers with a winner that day (from race-level history)."""
    by = {}
    for r in history:
        if r.get("win_trainer") and r.get("date"):
            by.setdefault(str(r["date"])[:10], []).append(U.person_keys(r["win_trainer"]))
    return by


def _form_runs(form):
    """'0113-P' -> ['0','1','1','3','P'] oldest..newest, season separators dropped."""
    return [c for c in str(form or "").upper() if c not in "-/ "]


def runner_values(r, race, tw, profile):
    v = {}
    runs = _form_runs(r.get("form"))
    if runs:
        v["lto_top3"] = 1.0 if runs[-1] in "123" else 0.0
        v["won_last3"] = 1.0 if "1" in runs[-3:] else 0.0
    if tw is not None and r.get("trainer"):
        keys = U.person_keys(r["trainer"])
        d = U.parse_date(race["date"])
        hit = any(keys & k for i in range(1, 15) for k in tw.get((d - timedelta(days=i)).isoformat(), []))
        v["trainer_14d"] = 1.0 if hit else 0.0
    if profile and profile.get("usual"):
        v["handy"] = 1.0 if profile["usual"] in "FP" else 0.0
    return v


def attach(race, winner_form, tw):
    if not winner_form:
        return race
    vals = [winner_form[x["race_id"]] for x in race.get("renewals", []) if x.get("race_id") in winner_form]
    trends, rules = [], {}
    for k, (txt, short) in BOOL_TXT.items():
        xs = [v[k] for v in vals if v.get(k) is not None]
        if len(xs) >= MIN_N:
            hits = int(sum(xs))
            if hits / len(xs) >= SHARE:
                trends.append(f"{hits} of {len(xs)} winners {txt}")
                rules[k] = short
    ranks = [v["or_rank"] for v in vals if v.get("or_rank") is not None]
    if race.get("hcap") and len(ranks) >= MIN_N:
        top = int(max(ranks))
        if top <= max(3, len(race["runners"]) // 2):
            trends.append(f"All {len(ranks)} winners were among the top {top} on official rating")
            rules["or_rank"] = (top, f"Top {top} rated")
    days = [v["days"] for v in vals if v.get("days") is not None]
    if len(days) >= MIN_N:
        trends.append(f"Winners had run within {int(max(days))} days")
    race["form_trends"] = trends
    if not rules:
        return race
    rated = [x["or"] for x in race["runners"] if x.get("or")]
    for r in race["runners"]:
        v = runner_values(r, race, tw, r.get("profile"))
        ticks = []
        for k, short in rules.items():
            if k == "or_rank":
                top, label = short
                if r.get("or") and rated:
                    rank = 1 + sum(1 for o in rated if o > r["or"])
                    ticks.append({"k": k, "ok": rank <= top, "txt": label})
            elif k in v:
                ticks.append({"k": k, "ok": bool(v[k]), "txt": short})
        r["form_ticks"] = ticks
    return race


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["export"]:
        export()
