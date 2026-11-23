#!/usr/bin/env bash
# Turn RacingFormBook results files (SFF or Duo CSV, any number, zipped or not) into the
# compact history the dashboard uses: data/history/rfb.csv.gz (a few MB - small enough to
# upload through GitHub's website).
#   bash scripts/import_rfb.sh ~/Downloads/RacingFormBook/*.csv
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$#" -gt 0 ] || { echo "usage: bash scripts/import_rfb.sh FILE.csv [FILE.csv ...]"; exit 2; }
PY="${PYTHON:-}"
[ -n "$PY" ] || { [ -x .venv/bin/python ] && PY=.venv/bin/python || PY=python3; }

tmp="$(mktemp -d)"; files=()
for f in "$@"; do
  case "$f" in
    *.zip) unzip -q -o "$f" -d "$tmp/$(basename "$f" .zip)"
           while IFS= read -r c; do files+=("$c"); done < <(find "$tmp/$(basename "$f" .zip)" -iname '*.csv') ;;
    *) files+=("$f") ;;
  esac
done
echo "Importing ${#files[@]} file(s)..."
"$PY" -m trends --history data/history/rfb.csv.gz history "${files[@]}"
rm -rf "$tmp"
ls -lh data/history/rfb.csv.gz
echo "Done. Upload data/history/rfb.csv.gz to the repo's data/history folder on GitHub (Add file -> Upload files)."
