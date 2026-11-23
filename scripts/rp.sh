#!/usr/bin/env bash
# Thin wrapper around rpscrape-community (https://github.com/Eatkin/rpscrape-community),
# the maintained continuation of joenano/rpscrape (which went offline).
#   scripts/rp.sh setup                     clone rpscrape + install its Python deps
#   scripts/rp.sh cards today|tomorrow      racecards JSON  -> work/cards_<day>.json
#   scripts/rp.sh results YYYY-MM-DD [END]  results CSV(s) for GB + IRE -> work/results_*.csv
# rpscrape changes its output paths from time to time, so new files are found by timestamp.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RP="$ROOT/vendor/rpscrape"
WORK="$ROOT/work"
REGIONS="${REGIONS:-gb ire}"
mkdir -p "$WORK"

setup() {
  if [ ! -d "$RP/.git" ]; then
    git clone --depth 1 "${RPSCRAPE_REPO:-https://github.com/Eatkin/rpscrape-community}" "$RP"
  fi
  if [ -f "$RP/requirements.txt" ]; then
    python3 -m pip install -q -r "$RP/requirements.txt"
  else
    python3 -m pip install -q curl_cffi jarowinkler lxml orjson python-dotenv tomli tqdm
  fi
  echo "rpscrape at $(git -C "$RP" rev-parse --short HEAD)"
}

newer_than() {  # files of a type created after the marker, largest first, ignoring caches/settings
  find "$RP" -type f -name "$2" -newer "$1" -not -path '*/.git/*' -not -path '*/.cache/*' \
       -not -path '*/settings/*' -not -name '*settings*' -printf '%s %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-
}

cards() {
  local day="$1" marker; marker="$(mktemp)"
  sleep 1
  local n=1; [ "$day" = "tomorrow" ] && n=2
  ( cd "$RP/scripts" && python3 racecards.py --day "$n" ) || ( cd "$RP/scripts" && python3 racecards.py "$day" )
  local f; f="$(newer_than "$marker" '*.json' | head -n1)"
  [ -n "$f" ] || { echo "racecards.py produced no JSON" >&2; exit 1; }
  cp "$f" "$WORK/cards_${day}.json"
  echo "cards: $f -> work/cards_${day}.json"
}

results() {
  local start="${1//-//}" end="${2:-}"
  local span="$start"; [ -n "$end" ] && span="$start-${end//-//}"
  for region in $REGIONS; do
    local marker; marker="$(mktemp)"; sleep 1
    ( cd "$RP/scripts" && python3 rpscrape.py -d "$span" -r "$region" ) || ( cd "$RP/scripts" && python3 rpscrape.py -d "$span" "$region" ) || true
    local n=0
    while IFS= read -r f; do
      n=$((n+1)); cp "$f" "$WORK/results_${region}_$(basename "$f")"
    done < <(newer_than "$marker" '*.csv')
    echo "results $span $region: $n file(s)"
  done
}

case "${1:-}" in
  setup) setup ;;
  cards) cards "${2:?today|tomorrow}" ;;
  results) results "${2:?YYYY-MM-DD}" "${3:-}" ;;
  *) echo "usage: $0 setup | cards today|tomorrow | results YYYY-MM-DD [END]" >&2; exit 2 ;;
esac
