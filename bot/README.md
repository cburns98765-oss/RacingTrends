# Racing Trends paper-trading bot

Watches today's Betfair horse racing win markets for horses picked by `rules.json` and records **paper bets
only** (no money is ever staked: the bot only reads prices). Each bet is settled when Betfair settles the market.

## Files
- `paperbot.py` – the bot
- `rules.py` / `rules.json` – which horses to watch and the price triggers (switch rules on/off in rules.json)
- `config.json` – your Betfair username, app key, stake and the Google Sheet link (copy from `config.example.json`)
- `certs/` – your Betfair security certificate (`client-2048.crt` and `client-2048.key`)
- `logs/paper_bets_YYYY-MM-DD.csv` – every paper bet
- `apps_script.gs` – paste into the Racing Bet Tracker (Extensions > Apps Script) so bets appear in the "Paper bets" tab

## Run
Open Terminal in this folder and run `./run_mac.sh`. It asks for your Betfair password each time (never saved),
keeps the Mac awake while running, and stops by itself after the last watched race. Start it in the morning
before racing. Ctrl+C stops it at any time.

## Paper-fill assumptions
A paper bet is assumed fully matched at the best price on offer when its trigger is hit. With the free
delayed app key prices lag by 1–180 seconds, so in-running results (the lay rule) are not realistic until
the live key is used.
