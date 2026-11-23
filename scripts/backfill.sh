#!/usr/bin/env bash
# Load past seasons into data/history from your own computer (Racing Post blocks GitHub's servers).
#   bash scripts/backfill.sh 2021 2026      # newest month first; safe to stop and re-run any time
# Each finished month is recorded in data/history/done_months.txt and skipped next time.
# Stops (exit 3) if Racing Post starts refusing requests - wait a day before running again.
set -euo pipefail
cd "$(dirname "$0")/.."
# keep the Mac awake while this runs
if command -v caffeinate >/dev/null && [ -z "${CAFFEINATED:-}" ]; then
  export CAFFEINATED=1; exec caffeinate -i bash "$0" "$@"
fi
HIST=data/history/backfill.csv.gz   # separate from races.csv.gz (written by the daily runs) so pushes never clash
FROM="${1:?first year, e.g. 2021}"; TO="${2:-$(date +%Y)}"
DONE=data/history/done_months.txt
mkdir -p data/history && touch "$DONE"

# Python 3.13+ in a local virtualenv (rpscrape-community needs 3.13)
if [ ! -x .venv/bin/python ]; then
  PYBIN="$(command -v python3.14 || command -v python3.13 || command -v python3)"
  "$PYBIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,13) else 1)' || {
    echo "Python 3.13 or newer is needed. Install it from https://www.python.org/downloads/ then re-run." >&2; exit 1; }
  "$PYBIN" -m venv .venv
fi
export PYTHON="$PWD/.venv/bin/python"
scripts/rp.sh setup

months="$("$PYTHON" - "$FROM" "$TO" <<'EOF'
import calendar, datetime, sys
f, t = int(sys.argv[1]), int(sys.argv[2])
yday = datetime.date.today() - datetime.timedelta(days=1)
for y in range(t, f - 1, -1):
    for m in range(12, 0, -1):
        start = datetime.date(y, m, 1)
        if start > yday:
            continue
        end = min(datetime.date(y, m, calendar.monthrange(y, m)[1]), yday)
        full = end == datetime.date(y, m, calendar.monthrange(y, m)[1])
        print(f"{start} {end} {int(full)}")
EOF
)"

while read -r start end full; do
  key="${start:0:7}"
  grep -qx "$key" "$DONE" && { echo "skip $key (done)"; continue; }
  echo "=== $key  ($start to $end) $(date '+%H:%M')"
  rm -rf work && mkdir -p work
  set +e; scripts/rp.sh results "$start" "$end"; rc=$?; set -e
  if ls work/results_*.csv >/dev/null 2>&1; then
    "$PYTHON" -m trends --history "$HIST" history work/results_*.csv
  fi
  if [ "$rc" = 3 ]; then
    echo "Racing Post is blocking requests. Data up to the block is saved. Wait a day, then run this again." >&2
    exit 3
  fi
  [ "$full" = 1 ] && [ "$rc" = 0 ] && echo "$key" >> "$DONE"
  git add data/history && git commit -qm "History: $key" && \
    { git pull --rebase --autostash -q && git push -q || echo "(push failed - run 'git pull --rebase && git push' later)"; } || true
done <<< "$months"
echo "Backfill finished for $FROM-$TO."
