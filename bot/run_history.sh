#!/bin/bash
# Downloads your free Betfair BASIC horse racing history and condenses it. Usage: ./run_history.sh 2025-01 2026-10
cd "$(dirname "$0")"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
caffeinate -i "$UV" run --python 3.12 --with betfairlightweight python history_download.py "$@"
