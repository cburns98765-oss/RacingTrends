"""Running style from a race comment, e.g. 'held up in rear, headway 2 out, kept on' -> 'H'.

F = front-runner (made all / led / disputed lead), P = prominent (tracked / chased leaders, close up),
M = mid-division / in touch, H = held up / in rear. '' when the comment says nothing about early position.
"""
import re

PATTERNS = [  # searched within a clause, in this order
    ("F", r"\b(made (all|virtually all|most|the running)|made running|led\b|disputed (the )?lead|set (a |the )?(steady |strong |fair )?pace|"
          r"with leader|joint lead|share(d)? lead)"),
    ("H", r"\b(held up|in rear|towards rear|towards the rear|at the rear|dropped (out|in)|"
          r"detached|always behind|always rear|tailed off early|outpaced in rear)"),
    ("P", r"\b(prominent|track(ed|ing) (the )?leader|chas(ed|ing) (the |clear )?leader|close up|chased leaders|with leaders|"
          r"pressed leader|handy|in touch with leaders|chased winner|raced (in )?(2nd|3rd|second|third))"),
    ("M", r"\b(mid-?division|midfield|in touch|mid pack|never nearer|off the pace|raced (in )?(4th|5th|6th|7th))"),
]
_PAT = [(k, re.compile(p)) for k, p in PATTERNS]
_SKIP = re.compile(r"^(keen|bit keen|went early to post|raced against|raced alone|took (a )?(keen )?hold|raced keenly|pulled hard|in snatches|not fluent|jumped|"
                   r"awkward|unruly|green|wore|reluctant|edgy|sweating|steadied|hampered|bumped|"
                   r"badly hampered|veered|hung|mulish|restless|led to post|early to post|walked to post|dwelt|"
                   r"slowly into stride|started slowly|slowly away|missed break|switched|wide|"
                   r"towards (far|stands'?|near) side|raced (far|stands'?|near) side|raced (wide|centre)|soon)")


def run_style(comment):
    text = str(comment or "").lower().strip().strip('"')
    if not text:
        return ""
    clauses = [c.strip() for c in re.split(r"[,;]", text)][:3]
    for i, clause in enumerate(clauses):
        for k, pat in _PAT:
            if pat.search(clause):
                return k
        if not _SKIP.search(clause):
            break  # first substantive clause didn't name a position: don't read later race events
    if re.match(r"^(slowly into stride|dwelt|slowly away|started slowly|missed break)", text):
        return "H"
    return ""
