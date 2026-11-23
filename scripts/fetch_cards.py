"""Fetch today's or tomorrow's GB + IRE racecards from The Racing API's free plan.

    RACING_API_USERNAME=... RACING_API_PASSWORD=... python3 scripts/fetch_cards.py today|tomorrow

Writes work/cards_<day>.json. Credentials come from your Racing API dashboard (free account).
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

URL = "https://api.theracingapi.com/v1/racecards/free"


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "today"
    user, pw = os.environ.get("RACING_API_USERNAME"), os.environ.get("RACING_API_PASSWORD")
    if not user or not pw:
        sys.exit("Set RACING_API_USERNAME and RACING_API_PASSWORD (GitHub: Settings -> Secrets -> Actions).")
    q = urllib.parse.urlencode([("day", day), ("region_codes", "gb"), ("region_codes", "ire"), ("limit", 500)])
    req = urllib.request.Request(f"{URL}?{q}", headers={
        "Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode(),
        "Accept": "application/json", "User-Agent": "racing-trends/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(2 + attempt * 3)
                continue
            body = e.read().decode(errors="replace")[:300]
            sys.exit(f"Racing API {e.code}: {body}")
    cards = data.get("racecards", data)
    os.makedirs("work", exist_ok=True)
    out = os.path.join("work", f"cards_{day}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    n = len(cards) if isinstance(cards, list) else "?"
    print(f"cards {day}: {n} races -> {out}")
    time.sleep(1.1)  # free plan: 1 request per second


if __name__ == "__main__":
    main()
