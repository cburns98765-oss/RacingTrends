"""Download your free Betfair BASIC historic data (GB/IE horse racing WIN markets) and condense it to
one row per runner: last traded price 15, 10, 5, 3, 2 and 1 minutes before the off, at the off, plus BSP
and result. Output: logs/steam_prices.csv.gz (upload this file to Claude).

Run:  ./run_history.sh 2025-01 2026-10      (months from / to, inclusive)

Uses config.json and certs/ from the bot. Resumable: re-running skips markets already done.
"""
import bz2
import csv
import gzip
import io
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import betfairlightweight

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "logs", "steam_prices.csv.gz")
DONE = os.path.join(HERE, "logs", "steam_done.txt")
MARKS = [15, 10, 5, 3, 2, 1, 0]
FIELDS = ["market_id", "date", "venue", "market_time", "off_time", "race", "n_runners", "selection_id", "horse",
          "status", "bsp"] + [f"ltp_{m}m" for m in MARKS] + ["ltp_first", "ltp_max_pre", "ltp_min_pre"]


def parse_basic(raw_lines):
    """Parse one BASIC market file (JSON lines of stream messages)."""
    defn, ltps = {}, {}          # ltps: selection_id -> list of (pt_ms, ltp) before the off
    off_pt = None
    for line in raw_lines:
        if not line.strip():
            continue
        msg = json.loads(line)
        pt = msg.get("pt")
        for mc in msg.get("mc", []):
            d = mc.get("marketDefinition")
            if d:
                defn = d
                if d.get("inPlay") and off_pt is None:
                    off_pt = pt
            if off_pt is None:
                for rc in mc.get("rc", []):
                    if "ltp" in rc:
                        ltps.setdefault(rc["id"], []).append((pt, rc["ltp"]))
    if not defn or defn.get("marketType") not in (None, "WIN"):
        return []
    mt = datetime.fromisoformat(defn["marketTime"].replace("Z", "+00:00"))
    off_ms = off_pt or int(mt.timestamp() * 1000)
    runners = defn.get("runners", [])
    active = [r for r in runners if r.get("status") in ("WINNER", "LOSER", "PLACED")]
    rows = []
    for r in runners:
        series = sorted(ltps.get(r["id"], []))
        row = {"market_id": defn.get("marketId") or "", "date": mt.strftime("%Y-%m-%d"), "venue": defn.get("venue", ""),
               "market_time": mt.strftime("%H:%M"),
               "off_time": datetime.fromtimestamp(off_ms / 1000, timezone.utc).strftime("%H:%M:%S"),
               "race": defn.get("name", ""), "n_runners": len(active), "selection_id": r["id"],
               "horse": r.get("name", ""), "status": r.get("status", ""), "bsp": r.get("bsp", "")}
        for m in MARKS:
            cutoff = off_ms - m * 60000
            before = [p for t, p in series if t <= cutoff]
            row[f"ltp_{m}m"] = before[-1] if before else ""
        row["ltp_first"] = series[0][1] if series else ""
        pre = [p for t, p in series if t >= off_ms - 30 * 60000]
        row["ltp_max_pre"] = max(pre) if pre else ""
        row["ltp_min_pre"] = min(pre) if pre else ""
        rows.append(row)
    return rows


def months(a, b):
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    while (y, m) <= (y2, m2):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def main():
    if len(sys.argv) < 3:
        print("usage: run_history.sh FROM_YYYY-MM TO_YYYY-MM")
        sys.exit(1)
    import getpass
    with open(os.path.join(HERE, "config.json")) as fh:
        cfg = json.load(fh)
    pw = os.environ.get("BETFAIR_PASSWORD") or getpass.getpass("Betfair password (not saved): ")
    trading = betfairlightweight.APIClient(cfg["username"], pw, app_key=cfg["app_key"], certs=os.path.join(HERE, "certs"))
    trading.login()
    print("logged in")
    mine = trading.historic.get_my_data()
    racing = [x for x in mine if x.get("sport") == "Horse Racing"]
    print(f"your free/purchased data: {len(racing)} horse racing month(s) on your account,"
          f" plans: {sorted({x.get('plan') for x in racing})}")
    if not racing:
        print("No horse racing data on your account yet: claim the Basic plan for Horse Racing on historicdata.betfair.com first.")
        sys.exit(1)
    plan = "Basic Plan" if any(x.get("plan") == "Basic Plan" for x in racing) else racing[0]["plan"]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
    new_file = not os.path.exists(OUT)
    lock = threading.Lock()
    out = gzip.open(OUT, "at", newline="", encoding="utf-8")
    w = csv.DictWriter(out, FIELDS)
    if new_file:
        w.writeheader()
    donefh = open(DONE, "a")
    tmp = tempfile.mkdtemp()

    def work(path):
        local = trading.historic.download_file(file_path=path, store_directory=tmp)
        try:
            with bz2.open(local, "rt", encoding="utf-8") as fh:
                rows = parse_basic(fh)
        finally:
            os.remove(local)
        with lock:
            w.writerows(rows)
            donefh.write(path + "\n")
        return len(rows)

    for y, m in months(sys.argv[1], sys.argv[2]):
        last_day = 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30 if m != 2 else 29
        files = trading.historic.get_file_list(
            "Horse Racing", plan, from_day=1, from_month=m, from_year=y, to_day=last_day, to_month=m, to_year=y,
            market_types_collection=["WIN"], countries_collection=["GB", "IE"], file_type_collection=["M"])
        todo = [f for f in files if f not in done]
        print(f"{y}-{m:02d}: {len(files)} markets, {len(todo)} to download", flush=True)
        n = 0
        with ThreadPoolExecutor(6) as ex:
            futs = [ex.submit(work, f) for f in todo]
            for i, fu in enumerate(as_completed(futs), 1):
                try:
                    n += fu.result()
                except Exception as e:
                    print("  skipped a file:", str(e)[:120], flush=True)
                if i % 200 == 0:
                    print(f"  {i}/{len(todo)}", flush=True)
                    out.flush()
                    donefh.flush()
        out.flush()
        donefh.flush()
        print(f"  {y}-{m:02d} done: {n} runners", flush=True)
        try:
            trading.keep_alive()
        except Exception:
            pass
    out.close()
    print(f"\nFinished. Upload this file to Claude: {OUT}")


if __name__ == "__main__":
    main()
