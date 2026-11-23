"""Betfair SP daily files (promo.betfair.com/betfairsp/prices) -> lookup by (date, course, horse).

Columns: event_id, menu_hint ('Ascot 21st Nov'), event_name ('2m5f Hcap Chs'), event_dt ('21-11-2025 14:00'),
selection_id, selection_name, win_lose, bsp, ppwap, morningwap, ppmax, ppmin, ipmax, ipmin, volumes...
"""
import csv
import glob
import io
import os
import re
import zipfile
from datetime import datetime

from . import util as U

_DAY = re.compile(r"\s+\d{1,2}(st|nd|rd|th)\s+[A-Za-z]{3}$")


def course_from_menu(menu):
    """'Ascot 21st Nov' / 'GB / Lingfield 14th Jun' / 'IRE / Naas 3rd May' -> course name."""
    m = re.sub(r"^[A-Z]{2,4}\s*/\s*", "", str(menu or "").strip())
    return _DAY.sub("", m).strip()


def _f(v):
    try:
        x = float(v)
        return x if x > 1.0 else None
    except (TypeError, ValueError):
        return None


def load(paths_or_zip):
    """Return {(iso_date, course_key, horse_key): {bsp, morning, ppwap, win}}."""
    out = {}

    def read(fh):
        for r in csv.DictReader(fh):
            r = {str(k).strip().lower(): v for k, v in r.items()}  # older files use UPPER-CASE headers
            try:
                d = datetime.strptime(r["event_dt"].strip()[:10], "%d-%m-%Y").date().isoformat()
            except (KeyError, ValueError):
                continue
            k = (d, U.course_name_key(course_from_menu(r.get("menu_hint"))), U.norm_name(r.get("selection_name")))
            out[k] = {"bsp": _f(r.get("bsp")), "morning": _f(r.get("morningwap")), "ppwap": _f(r.get("ppwap")),
                      "ipmin": _f(r.get("ipmin")), "ipmax": _f(r.get("ipmax")),
                      "win": str(r.get("win_lose", "")).strip() == "1"}

    for p in paths_or_zip:
        if p.endswith(".zip"):
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    if n.endswith(".csv"):
                        with z.open(n) as raw:
                            read(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
        else:
            for f in sorted(glob.glob(os.path.join(p, "*.csv")) if os.path.isdir(p) else [p]):
                with open(f, encoding="utf-8", errors="replace") as fh:
                    read(fh)
    return out
