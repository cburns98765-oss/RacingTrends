"""Per-horse running-style and in-running profiles, plus a pace map per race.

Build (needs the RacingFormBook Duo files and the Betfair SP folder; run on a machine that has them):
    python -m trends.profiles build --rfb DUO_FILES... --bsp BSP_DIR --out data/profiles.json.gz

Each profile: s = run styles of the last 6 runs, newest first (F front, P prominent, M mid-division,
H held up, - unknown); ip = [times traded <=1.50 in running, lost after doing so,
times traded >= 2x its BSP in running, won after doing so]; last = date of last run.
"""
import argparse
import gzip
import json
import os
from collections import Counter

from . import util as U

STYLE_NAMES = {"F": "Front-runner", "P": "Prominent", "M": "Mid-division", "H": "Held up"}
LAST_N = 6


def build(rfb, bsp_paths, since="2023-01-01", cache=None):
    import pandas as pd
    from .inrunning import build as build_df
    if cache and os.path.exists(cache):
        df = pd.read_pickle(cache)
    else:
        df = build_df(rfb, bsp_paths)
    df = df.sort_values(["date", "off"])
    out = {}
    for hk, g in df.groupby("horse_key", sort=False):
        if not hk or g["date"].iloc[-1] < pd.Timestamp(since):
            continue
        styles = "".join(s or "-" for s in g["style"].iloc[::-1].iloc[:LAST_N])
        ip = [int(g["ev_short"].sum()), int(g["ev_short_lost"].sum()),
              int(g["ev_drift"].sum()), int(g["ev_comeback"].sum())]
        out[hk] = {"s": styles, "ip": ip, "last": g["date"].iloc[-1].strftime("%Y-%m-%d")}
    return out


def load(path):
    if not path or not os.path.exists(path):
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def usual_style(s):
    known = [c for c in s if c in STYLE_NAMES]
    if len(known) < 2:
        return ""
    (top, n), = Counter(known).most_common(1)
    return top if n >= 2 else ""


def runner_profile(p):
    if not p:
        return None
    usual = usual_style(p["s"])
    hit, lost, drift, comeback = p["ip"]
    badges = []
    if hit >= 2 and lost >= 2 and lost / hit >= 0.5:
        badges.append({"k": "ip_short", "txt": f"Traded 1.5 or shorter and lost {lost} of {hit}"})
    if comeback >= 2:
        badges.append({"k": "ip_comeback", "txt": f"Won {comeback}x after drifting to 2x its SP in running"})
    return {"usual": usual, "recent": p["s"], "ip": p["ip"], "badges": badges}


def pace_map(runners):
    """Group runners by usual style and describe the likely pace."""
    groups = {k: [] for k in STYLE_NAMES}
    unknown = []
    for r in runners:
        u = (r.get("profile") or {}).get("usual", "")
        (groups[u] if u else unknown).append(r["horse"])
    nf = len(groups["F"])
    if len(unknown) * 2 > len(runners):
        verdict = f"Too few known running styles to read the pace ({len(unknown)} of {len(runners)} have no profile)"
        if nf == 1:
            verdict += f"; {groups['F'][0]} is the only known front-runner"
    elif nf == 0:
        verdict = "No habitual front-runner: pace could be steady"
        if groups["P"]:
            verdict += f"; a prominent racer ({groups['P'][0]}) may end up leading"
    elif nf == 1:
        verdict = f"Lone front-runner: {groups['F'][0]} could get an easy lead"
    elif nf == 2:
        verdict = "Two habitual front-runners: likely a contested pace"
    else:
        verdict = f"{nf} habitual front-runners: likely a strong pace, which tends to suit hold-up horses"
    return {"groups": groups, "unknown": unknown, "verdict": verdict}


def attach(race, profiles):
    if not profiles:
        return race
    for r in race["runners"]:
        r["profile"] = runner_profile(profiles.get(U.norm_name(r.get("horse"))))
    race["pace"] = pace_map(race["runners"])
    return race


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--rfb", nargs="+", required=True)
    b.add_argument("--bsp", nargs="+", required=True)
    b.add_argument("--out", default="data/profiles.json.gz")
    b.add_argument("--cache", default="/tmp/inrunning.pkl")
    args = ap.parse_args()
    prof = build(args.rfb, args.bsp, cache=args.cache)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as fh:
        json.dump(prof, fh, separators=(",", ":"))
    print(f"{len(prof)} horse profiles -> {args.out} ({os.path.getsize(args.out) // 1024} KB)")


if __name__ == "__main__":
    main()
