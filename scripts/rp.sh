#!/usr/bin/env bash
# Thin wrapper around rpscrape-community (https://github.com/Eatkin/rpscrape-community),
# the maintained continuation of joenano/rpscrape (which went offline). Works on Linux and macOS.
#   scripts/rp.sh setup                     clone rpscrape + install its Python deps
#   scripts/rp.sh cards today|tomorrow      racecards JSON  -> work/cards_<day>.json
#   scripts/rp.sh results YYYY-MM-DD [END]  results CSV(s) for $REGIONS -> work/results_*.csv
# Exit code 3 = Racing Post is blocking us (anything scraped before the block is still copied).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RP="$ROOT/vendor/rpscrape"
WORK="$ROOT/work"
REGIONS="${REGIONS:-gb ire}"
PY="${PYTHON:-python3}"
mkdir -p "$WORK"

setup() {
  local repo="${RPSCRAPE_REPO:-https://github.com/Eatkin/rpscrape-community}"
  if [ ! -d "$RP/scripts" ]; then
    if command -v git >/dev/null && { [ "$(uname)" != Darwin ] || xcode-select -p >/dev/null 2>&1; }; then
      git clone --depth 1 "$repo" "$RP"
    else  # no git (e.g. a Mac without developer tools): download the zip instead
      mkdir -p "$RP" && curl -fsSL "$repo/archive/refs/heads/master.tar.gz" | tar -xz -C "$RP" --strip-components=1
    fi
  fi
  if [ -f "$RP/requirements.txt" ]; then
    "$PY" -m pip install -q -r "$RP/requirements.txt"
  else
    "$PY" -m pip install -q curl_cffi jarowinkler lxml orjson python-dotenv tomli tqdm
  fi
  echo "rpscrape at $(git -C "$RP" rev-parse --short HEAD 2>/dev/null || echo 'downloaded copy')"
}

newer_than() {  # files matching $2 modified after marker $1, largest first, ignoring caches/settings
  "$PY" - "$RP" "$1" "$2" <<'EOF'
import fnmatch, os, sys
root, marker, pat = sys.argv[1], sys.argv[2], sys.argv[3]
t = os.path.getmtime(marker)
out = []
for d, dirs, files in os.walk(root):
    dirs[:] = [x for x in dirs if x not in (".git", ".cache", "settings", "__pycache__")]
    for f in files:
        p = os.path.join(d, f)
        if fnmatch.fnmatch(f, pat) and "settings" not in f and os.path.getmtime(p) > t:
            out.append((os.path.getsize(p), p))
for _, p in sorted(out, reverse=True):
    print(p)
EOF
}

cards() {
  local day="$1" marker n=1; marker="$(mktemp)"
  [ "$day" = "tomorrow" ] && n=2
  sleep 1
  ( cd "$RP/scripts" && "$PY" racecards.py --day "$n" )
  local f; f="$(newer_than "$marker" '*.json' | head -n1)"
  [ -n "$f" ] || { echo "racecards.py produced no JSON" >&2; exit 1; }
  cp "$f" "$WORK/cards_${day}.json"
  echo "cards: $f -> work/cards_${day}.json"
}

results() {
  local start="${1//-//}" end="${2:-}" blocked=0
  local span="$start"; [ -n "$end" ] && span="$start-${end//-//}"
  for region in $REGIONS; do
    local marker log; marker="$(mktemp)"; log="$(mktemp)"; sleep 1
    set +e
    ( cd "$RP/scripts" && "$PY" rpscrape.py -d "$span" -r "$region" ) 2>&1 | tee "$log"
    set -e
    local n=0
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      n=$((n+1)); cp "$f" "$WORK/results_${region}_$(basename "$f")"
    done < <(newer_than "$marker" '*.csv')
    echo "results $span $region: $n file(s)"
    if grep -qE "PersistentBlockError|blocked \(status" "$log"; then
      echo "BLOCKED: Racing Post refused requests during $span $region" >&2
      blocked=1
      break
    fi
  done
  [ "$blocked" = 0 ] || exit 3
}

case "${1:-}" in
  setup) setup ;;
  cards) cards "${2:?today|tomorrow}" ;;
  results) results "${2:?YYYY-MM-DD}" "${3:-}" ;;
  *) echo "usage: $0 setup | cards today|tomorrow | results YYYY-MM-DD [END]" >&2; exit 2 ;;
esac
