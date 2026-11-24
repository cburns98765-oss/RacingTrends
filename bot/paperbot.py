"""Racing Trends paper-trading bot for the Betfair Exchange.

Watches today's UK/IRE horse racing win markets for the horses picked by rules.json, and records a
PAPER bet (no money) whenever a price condition is met. Settles each bet when Betfair settles the market.
Bets are written to paper_bets.csv and, if a sheet_webhook is set in config.json, to the
"Paper bets" tab of the Racing Bet Tracker.

Run:  ./run_mac.sh           (asks for your Betfair password; it is never saved)

This bot NEVER places real bets: it only calls Betfair's read-only price endpoints.
"""
import csv
import getpass
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import betfairlightweight
from betfairlightweight import filters

import rules as R

HERE = os.path.dirname(os.path.abspath(__file__))
LON = ZoneInfo("Europe/London")
SITE = "https://cburns98765-oss.github.io/RacingTrends/data"
FIELDS = ["id", "date", "course", "time", "horse", "rule", "side", "price", "stake", "struck_at", "status",
          "horse_result", "profit_loss", "reason", "market_id", "selection_id"]


def log(*a):
    print(datetime.now(LON).strftime("%H:%M:%S"), *a, flush=True)


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_csv(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return list(csv.DictReader(r.read().decode().splitlines()))


def post_sheet(cfg, row):
    url = cfg.get("sheet_webhook")
    if not url:
        return
    try:
        data = json.dumps({**row, "token": cfg.get("sheet_token", "")}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:  # the CSV is the record; the sheet is a convenience
        log("sheet update failed:", e)


class Book:
    """paper_bets.csv for today, so a restart doesn't double-bet."""

    def __init__(self, path):
        self.path = path
        self.rows = {}
        if os.path.exists(path):
            with open(path, newline="") as fh:
                for r in csv.DictReader(fh):
                    self.rows[r["id"]] = r

    def save(self):
        with open(self.path, "w", newline="") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            w.writerows(self.rows.values())


def login(cfg):
    pw = os.environ.get("BETFAIR_PASSWORD") or getpass.getpass("Betfair password (not saved): ")
    certs = os.path.join(HERE, cfg.get("certs_folder", "certs"))
    trading = betfairlightweight.APIClient(cfg["username"], pw, app_key=cfg["app_key"],
                                           certs=certs if os.path.isdir(certs) else None)
    if os.path.isdir(certs) and any(f.endswith(".crt") for f in os.listdir(certs)):
        try:
            trading.login()
            log("logged in with certificate")
            return trading
        except Exception as e:
            log(f"certificate login failed ({e}); trying normal login instead")
            log("  (check client-2048.crt is uploaded under Automated Betting Program Access on Betfair's My Security page)")
    try:
        trading.login_interactive()
        log("logged in with username and password")
    except Exception as e:
        log(f"login failed: {e}")
        log("  check the username in config.json (it's case-sensitive) and your password")
        sys.exit(1)
    return trading


def todays_markets(trading):
    now = datetime.now(timezone.utc)
    end = datetime.now(LON).replace(hour=23, minute=59).astimezone(timezone.utc)
    cat = trading.betting.list_market_catalogue(
        filter=filters.market_filter(event_type_ids=["7"], market_countries=["GB", "IE"], market_type_codes=["WIN"],
                                     market_start_time={"from": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                        "to": end.strftime("%Y-%m-%dT%H:%M:%SZ")}),
        market_projection=["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"], max_results=1000)
    out = []
    for c in cat:
        start = c.market_start_time.replace(tzinfo=timezone.utc).astimezone(LON)
        out.append({"market_id": c.market_id, "venue": R.venue_key(c.event.venue), "start": start,
                    "runners": {R.norm(r.runner_name): r.selection_id for r in c.runners}})
    return out


def match(sel, markets):
    v = R.venue_key(sel["course"])
    hh, mm = map(int, sel["off"].split(":"))
    for m in markets:
        if m["venue"] != v:
            continue
        mins = abs((m["start"].hour * 60 + m["start"].minute) - (hh * 60 + mm))
        if mins <= 3:
            sid = m["runners"].get(R.norm(sel["horse"]))
            if sid:
                return m, sid
    return None, None


def best(prices):
    return prices[0].price if prices else None


def main():
    with open(os.path.join(HERE, "config.json")) as fh:
        cfg = json.load(fh)
    with open(os.path.join(HERE, "rules.json")) as fh:
        rules = json.load(fh)
    stake, comm = float(cfg.get("stake", 20)), float(cfg.get("commission", 0.05))
    today = datetime.now(LON).strftime("%Y-%m-%d")
    card = fetch_json(f"{SITE}/cards/{today}.json")
    bias = fetch_csv(f"{SITE}/course_pace_bias.csv")
    sels = R.build_selections(card, bias, rules)
    log(f"{len(sels)} selections from today's card")
    for s in sels:
        log(f"  {s['off']} {s['course']:18} {s['horse']:22} {s['side']} {s['rule']}")

    trading = login(cfg)
    markets = todays_markets(trading)
    watch = []
    for s in sels:
        m, sid = match(s, markets)
        if m and m["start"] < datetime.now(LON) - timedelta(minutes=20):
            continue  # race already run
        if not m:
            log(f"  no Betfair market found for {s['horse']} ({s['off']} {s['course']})")
            continue
        s.update(market_id=m["market_id"], selection_id=sid, start=m["start"],
                 id=f"{today}|{s['off']}|{R.norm(s['course'])}|{R.norm(s['horse'])}|{s['rule']}")
        watch.append(s)
    log(f"watching {len(watch)} horses in {len({s['market_id'] for s in watch})} markets")

    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    book = Book(os.path.join(HERE, "logs", f"paper_bets_{today}.csv"))
    done = set()  # markets that have closed
    poll = int(cfg.get("poll_seconds", 5))
    last_keepalive = time.time()
    while True:
        open_ids = {s["market_id"] for s in watch if s["market_id"] not in done}
        if not open_ids:
            log("nothing left to watch today. Done.")
            break
        ids = sorted(open_ids)
        books = []
        for i in range(0, len(ids), 10):
            books += trading.betting.list_market_book(
                market_ids=ids[i:i + 10], price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]))
        by_id = {b.market_id: b for b in books}
        now = datetime.now(LON)
        for s in watch:
            b = by_id.get(s["market_id"])
            if not b:
                continue
            row = book.rows.get(s["id"])
            runner = next((r for r in b.runners if r.selection_id == s["selection_id"]), None)
            if runner is None:
                continue
            if row is None and b.status == "OPEN" and runner.status == "ACTIVE":
                mins = (s["start"] - now).total_seconds() / 60
                price = R.check_trigger(s, best(runner.ex.available_to_back), best(runner.ex.available_to_lay), b.inplay, mins)
                if price:
                    row = {"id": s["id"], "date": today, "course": s["course"], "time": s["off"], "horse": s["horse"],
                           "rule": s["rule"], "side": s["side"], "price": price, "stake": stake,
                           "struck_at": now.strftime("%H:%M:%S") + (" in-play" if b.inplay else ""), "status": "open",
                           "horse_result": "", "profit_loss": "", "reason": s["reason"],
                           "market_id": s["market_id"], "selection_id": s["selection_id"]}
                    book.rows[s["id"]] = row
                    book.save()
                    post_sheet(cfg, row)
                    log(f"PAPER {s['side']} {s['horse']} @ {price} ({s['rule']})")
            if row and row["status"] == "open" and b.status == "CLOSED" and runner.status in ("WINNER", "LOSER", "REMOVED"):
                if runner.status == "REMOVED":
                    row.update(status="settled", horse_result="Non-runner", profit_loss=0)
                else:
                    won = runner.status == "WINNER"
                    row.update(status="settled", horse_result="Won" if won else "Lost",
                               profit_loss=R.profit_loss(row["side"], float(row["price"]), float(row["stake"]), won, comm))
                book.save()
                post_sheet(cfg, row)
                log(f"SETTLED {row['horse']}: {row['horse_result']} -> £{row['profit_loss']}")
        for mid, b in by_id.items():
            if b.status == "CLOSED":
                done.add(mid)
        if time.time() - last_keepalive > 15 * 60:
            trading.keep_alive()
            last_keepalive = time.time()
        time.sleep(poll)
    settled = [r for r in book.rows.values() if r["status"] == "settled"]
    pl = sum(float(r["profit_loss"] or 0) for r in settled)
    log(f"day done: {len(settled)} paper bets settled, P/L £{pl:.2f}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("stopped")
        sys.exit(0)
