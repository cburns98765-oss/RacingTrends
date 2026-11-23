#!/usr/bin/env bash
# One full update. Used by GitHub Actions, and works the same on your own computer.
#   scripts/run.sh morning   settle yesterday, build cards for today + tomorrow
#   scripts/run.sh evening   settle today, refresh tomorrow's cards
set -euo pipefail
cd "$(dirname "$0")/.."
export TZ=Europe/London
PY="${PYTHON:-python3}"
day() { "$PY" -c "import datetime as d; print((d.date.today()+d.timedelta(days=$1)).isoformat())"; }
today="$(day 0)"; yesterday="$(day -1)"; tomorrow="$(day 1)"
rm -rf work && mkdir -p work
scripts/rp.sh setup

settle() {
  scripts/rp.sh results "$1" || echo "WARNING: results for $1 incomplete (exit $?) - using what was fetched"
  if ls work/results_*.csv >/dev/null 2>&1; then
    "$PY" -m trends settle work/results_*.csv
  else
    echo "no results files for $1 (no racing, or Racing Post blocked the request)"
  fi
  rm -f work/results_*.csv
}

case "${1:-morning}" in
  morning)
    settle "$yesterday"
    scripts/rp.sh cards today
    scripts/rp.sh cards tomorrow
    "$PY" -m trends cards work/cards_today.json --date "$today"
    "$PY" -m trends cards work/cards_tomorrow.json --date "$tomorrow"
    ;;
  evening)
    settle "$today"
    scripts/rp.sh cards tomorrow
    "$PY" -m trends cards work/cards_tomorrow.json --date "$tomorrow"
    ;;
  *) echo "usage: $0 morning|evening" >&2; exit 2 ;;
esac
