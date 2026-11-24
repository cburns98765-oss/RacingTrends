#!/bin/bash
# Starts the paper-trading bot. Uses uv (no admin rights needed) to get Python and the Betfair library.
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "Installing uv (one-off)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -f config.json ]; then
  echo "config.json is missing: copy config.example.json to config.json and fill in your username and app key."
  exit 1
fi
caffeinate -i "$UV" run --python 3.12 --with betfairlightweight python paperbot.py
