#!/usr/bin/env bash
# One full update. Used by GitHub Actions, and works the same on your own computer.
#   scripts/run.sh morning   settle yesterday (if the evening run didn't), cards for today + tomorrow
#   scripts/run.sh evening   settle today, refresh tomorrow's cards
# Cards: The Racing API free plan (needs RACING_API_USERNAME / RACING_API_PASSWORD).
# Results: rpscrape for one day only (~70 races) - well under the volume Racing Post blocks.
set -euo pipefail
cd "$(dirname "$0")/.."
export TZ=Europe/London
PY="${PYTHON:-python3}"
day() { "$PY" -c "import datetime as d; print((d.date.today()+d.timedelta(days=$1)).isoformat())"; }
today="$(day 0)"; yesterday="$(day -1)"; tomorrow="$(day 1)"
rm -rf work && mkdir -p work

settled() { "$PY" -c "import json,sys; d=json.load(open('docs/data/cards/$1.json')); sys.exit(0 if d.get('settled') else 1)" 2>/dev/null; }

settle() {
  if [ ! -f "docs/data/cards/$1.json" ]; then echo "no cards for $1 - nothing to settle"; return; fi
  scripts/rp.sh setup >/dev/null
  scripts/rp.sh results "$1" || echo "WARNING: results for $1 incomplete (exit $?) - using what was fetched"
  if ls work/results_*.csv >/dev/null 2>&1; then
    "$PY" -m trends settle work/results_*.csv
  else
    echo "no results for $1 (no racing, or Racing Post refused the request)"
  fi
  rm -f work/results_*.csv
}

cards() {
  "$PY" scripts/fetch_cards.py "$1"
  "$PY" -m trends cards "work/cards_$1.json" --date "$2"
}

case "${1:-morning}" in
  morning)
    settled "$yesterday" && echo "$yesterday already settled" || settle "$yesterday"
    cards today "$today"
    cards tomorrow "$tomorrow"
    ;;
  evening)
    settle "$today"
    cards tomorrow "$tomorrow"
    ;;
  *) echo "usage: $0 morning|evening" >&2; exit 2 ;;
esac
