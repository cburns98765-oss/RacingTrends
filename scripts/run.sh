#!/usr/bin/env bash
# One full update. Used by GitHub Actions, and works the same on your own computer.
#   scripts/run.sh morning   settle yesterday, build cards for today + tomorrow
#   scripts/run.sh evening   settle today, refresh tomorrow's cards
set -euo pipefail
cd "$(dirname "$0")/.."
export TZ=Europe/London
today="$(date +%F)"
yesterday="$(date -d 'yesterday' +%F 2>/dev/null || date -v-1d +%F)"
rm -rf work && mkdir -p work
scripts/rp.sh setup

settle() {
  scripts/rp.sh results "$1"
  if ls work/results_*.csv >/dev/null 2>&1; then
    python3 -m trends settle work/results_*.csv
  else
    echo "no results files for $1 (rpscrape may be blocked or no racing)"
  fi
  rm -f work/results_*.csv
}

case "${1:-morning}" in
  morning)
    settle "$yesterday"
    scripts/rp.sh cards today
    scripts/rp.sh cards tomorrow
    python3 -m trends cards work/cards_today.json --date "$today"
    python3 -m trends cards work/cards_tomorrow.json --date "$(date -d tomorrow +%F 2>/dev/null || date -v+1d +%F)"
    ;;
  evening)
    settle "$today"
    scripts/rp.sh cards tomorrow
    python3 -m trends cards work/cards_tomorrow.json --date "$(date -d tomorrow +%F 2>/dev/null || date -v+1d +%F)"
    ;;
  *) echo "usage: $0 morning|evening" >&2; exit 2 ;;
esac
