"""Parsing helpers shared by the results and racecard importers.

rpscrape's field names have changed between versions, so every lookup goes
through `pick()` with a list of accepted aliases.
"""
import re
from datetime import date, datetime


def pick(row, *names, default=None):
    """Return the first non-empty value among alias keys (case-insensitive)."""
    if not row:
        return default
    lower = {str(k).lower().strip(): v for k, v in row.items()}
    for n in names:
        v = lower.get(n.lower())
        if v is not None and str(v).strip() not in ("", "-", "–", "None", "nan"):
            return v
    return default


def to_int(v):
    if v is None:
        return None
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def to_float(v):
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        m = re.search(r"-?\d+(\.\d+)?", str(v))
        return float(m.group()) if m else None


_FRAC = {"½": 0.5, "¼": 0.25, "¾": 0.75}


def dist_furlongs(*candidates):
    """Accepts 20.5, '20.5f', '2m4½f', '2m4f88y', '1m7f182y'. Returns furlongs."""
    for c in candidates:
        if c is None or str(c).strip() == "":
            continue
        s = str(c).strip().lower().replace(" ", "")
        if re.fullmatch(r"\d+(\.\d+)?f?", s):
            return float(s.rstrip("f"))
        m = re.fullmatch(r"(?:(\d+)m)?(?:(\d+)([½¼¾])?f)?(?:(\d+)y(?:ds)?)?", s)
        if m and any(m.groups()):
            miles = int(m.group(1) or 0)
            furl = int(m.group(2) or 0) + _FRAC.get(m.group(3) or "", 0)
            yards = int(m.group(4) or 0)
            if m.group(2) is None and m.group(3):
                furl = _FRAC[m.group(3)]
            return round(miles * 8 + furl + yards / 220.0, 2)
    return None


def race_type(v, name=""):
    s = f"{v or ''} {name or ''}".lower()
    if "chase" in s or "chs" in s:
        return "chase"
    if "hurdle" in s or "hrd" in s or "hdl" in s:
        return "hurdle"
    if "nh flat" in s or "bumper" in s or "national hunt flat" in s or "nhf" in s:
        return "nhf"
    return "flat"


AW_GOINGS = {"standard", "standard to slow", "standard to fast", "slow", "fast"}


def surface(v=None, course="", going=""):
    s = str(v or "").lower()
    if "aw" in s or "all" in s or "polytrack" in s or "tapeta" in s or "fibresand" in s:
        return "aw"
    if "turf" in s:
        return "turf"
    if "(aw)" in str(course).lower():
        return "aw"
    if str(going or "").lower().strip() in AW_GOINGS:
        return "aw"
    return "turf"


def race_class(v):
    n = to_int(v)
    return n if n and 1 <= n <= 7 else None


KIND_WORDS = {
    "maiden": ["maiden"],
    "novice": ["novice", "beginners"],
    "juvenile": ["juvenile"],
    "mares": ["mares", "fillies"],
    "conditional": ["conditional", "amateur", "apprentice", "hunters", "point-to-point"],
    "selling": ["selling", "seller", "claiming"],
}


def kinds(name):
    n = (name or "").lower()
    return sorted(k for k, words in KIND_WORDS.items() if any(w in n for w in words))


def is_handicap(name, rating_band=""):
    n = (name or "").lower()
    return "handicap" in n or "nursery" in n or "h'cap" in n


def pattern_level(pattern, name=""):
    s = f"{pattern or ''} {name or ''}".lower()
    for tag in ("grade 1", "group 1", "grade 2", "group 2", "grade 3", "group 3", "listed"):
        if tag in s:
            return tag.replace("group", "grade")
    return ""


def parse_date(v):
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10].replace("/", "-")
    return datetime.strptime(s, "%Y-%m-%d").date()


def doy_gap(a, b):
    """Circular day-of-year distance between two dates."""
    d = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(d, 365 - d)


def course_key(course_id, course_name):
    if course_id not in (None, ""):
        return f"id:{str(course_id).strip()}"
    n = re.sub(r"\(.*?\)", "", str(course_name or "")).strip().lower()
    return f"name:{n}"


def clean_course(name):
    return re.sub(r"\s+", " ", str(name or "")).strip()


def norm_name(n):
    """Horse/trainer/jockey name for matching: strip country suffix and punctuation."""
    s = re.sub(r"\((gb|ire|fr|ger|usa|ity|aus|nz|saf|jpn|spa|pol|cze|bel|hol|swe|nor|den|arg|bra|chi|uae|qat)\)", "", str(n or ""), flags=re.I)
    s = re.sub(r"\b(gb|ire|fr|ger|usa)$", "", s.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())


_TITLES = {"mr", "mrs", "miss", "ms", "dr", "sir", "lady", "capt", "major", "jr", "jnr", "snr", "sr"}


def person_keys(name):
    """'O Greenall & J Guerriero' and 'Oliver Greenall & Josh Guerriero' -> {('o','greenall'),('j','guerriero')}.
    'J & A O'Neill' -> {('j','oneill'),('a','oneill')} (a bare initial borrows the next surname)."""
    parts = re.split(r"\s*&\s*|\s+and\s+", str(name or "").lower())
    people = []
    for p in parts:
        toks = [re.sub(r"[^a-z]", "", t) for t in re.split(r"[\s.]+", p)]
        toks = [t for t in toks if t and t not in _TITLES]
        people.append(toks)
    keys, pending = set(), []
    for toks in people:
        if len(toks) == 1 and len(toks[0]) == 1:
            pending.append(toks[0])  # bare initial, surname comes later
            continue
        if not toks:
            continue
        surname = toks[-1]
        keys.add((toks[0][0], surname))
        for ini in pending:
            keys.add((ini, surname))
        pending = []
    return keys


def same_person(a, b):
    ka, kb = person_keys(a), person_keys(b)
    return bool(ka and kb and ka & kb)


def frac_from_dec(dec):
    if not dec:
        return ""
    table = [(1.1, "1/10"), (1.2, "1/5"), (1.25, "1/4"), (1.33, "1/3"), (1.4, "2/5"), (1.5, "1/2"),
             (1.62, "8/13"), (1.67, "4/6"), (1.73, "8/11"), (1.83, "5/6"), (1.91, "10/11"), (2.0, "evs"),
             (2.1, "11/10"), (2.25, "5/4"), (2.38, "11/8"), (2.5, "6/4"), (2.62, "13/8"), (2.75, "7/4"),
             (3.0, "2/1"), (3.25, "9/4"), (3.5, "5/2"), (4.0, "3/1"), (4.33, "10/3"), (4.5, "7/2"),
             (5.0, "4/1"), (5.5, "9/2"), (6.0, "5/1"), (6.5, "11/2"), (7.0, "6/1"), (7.5, "13/2"),
             (8.0, "7/1"), (9.0, "8/1"), (10.0, "9/1"), (11.0, "10/1"), (12.0, "11/1"), (13.0, "12/1"),
             (15.0, "14/1"), (17.0, "16/1"), (21.0, "20/1"), (26.0, "25/1"), (34.0, "33/1"), (41.0, "40/1"),
             (51.0, "50/1"), (67.0, "66/1"), (101.0, "100/1")]
    best = min(table, key=lambda t: abs(t[0] - dec))
    return best[1]


def sp_to_dec(sp):
    """'9/4F', '11/10fav', 'Evens', '5/6jf' -> decimal odds."""
    if sp is None:
        return None
    s = str(sp).lower().strip()
    if s.startswith("ev"):
        return 2.0
    m = re.search(r"(\d+)\s*/\s*(\d+)", s)
    if m:
        return round(int(m.group(1)) / int(m.group(2)) + 1, 3)
    return to_float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def sp_is_fav(sp):
    s = str(sp or "").lower()
    return bool(re.search(r"\d(f|fav|jf|cf|j|c)\b", s)) or s.endswith("f")
