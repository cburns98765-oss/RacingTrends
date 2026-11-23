# Racing Trends

Past-renewal trends for every UK & Irish race, updated twice a day and published as a website.

For each race on today's and tomorrow's cards it finds the same race in previous seasons (up to 10),
summarises what the winners had in common (age, weight off top, rating, price, favourites' record,
repeat trainers/jockeys), and ranks the runners by how well they fit. After racing it records the result
so the **Performance** tab shows whether higher trend scores actually win more often.

## Data sources

| What | Where from | Cost |
|---|---|---|
| History, 2016 onwards (GB + IRE) | [RacingFormBook](https://www.racingformbook.com/past-racing-results-files/) results files, imported once | £38.99 one-off (top up a year at a time later) |
| Today's & tomorrow's cards (GB + IRE) | [The Racing API](https://www.theracingapi.com) free plan, `/v1/racecards/free` | Free |
| Daily results (settles the dashboard, grows the history) | [rpscrape-community](https://github.com/Eatkin/rpscrape-community), one day's races only | Free |

Racing Post blocks bulk scraping (a few hundred races in a row), so rpscrape is only used for one day's
results at a time. If a day is refused, the site still works; that day just isn't scored.

## Schedule (UK time)

| When | What runs |
|---|---|
| ~06:10 | Settle yesterday if the evening run missed it, cards for today and tomorrow |
| ~21:40 | Settle today's results, refresh tomorrow's cards |

GitHub's scheduled runs can start 5–30 minutes late at busy times.

## One-time setup

1. **Site**: *Settings → Pages → Deploy from a branch → `main` / `/docs`*.
   It lives at `https://cburns98765-oss.github.io/RacingTrends/`.
2. **Let workflows save data**: *Settings → Actions → General → Workflow permissions → Read and write*.
3. **Racecards**: create a free account at theracingapi.com, then add two repository secrets
   (*Settings → Secrets and variables → Actions → New repository secret*):
   `RACING_API_USERNAME` and `RACING_API_PASSWORD` (the API username/password from your Racing API dashboard).
4. **History**: buy the RacingFormBook 2016–2026 results files, then on your Mac in this project folder:
   ```bash
   bash scripts/import_rfb.sh ~/Downloads/path/to/files/*.csv     # .zip files work too
   ```
   Upload the resulting `data/history/rfb.csv.gz` (a few MB) to the repo's `data/history` folder on GitHub.
5. **First run**: *Actions → Daily update → Run workflow → morning*. After that it runs on its own.

## How a "past renewal" is matched

Same course, race type (flat/hurdle/chase/NH flat), surface, handicap or not, pattern level, distance within
~1¼f (jumps) or ~½f (sprints), class within one band, run within ±45 days of the same date. If several races
in a season qualify, the closest one wins (penalties for distance, class, date gap and race-kind differences such
as maiden/novice/mares). Runners are only scored when 3+ renewals exist.

## Commands

```bash
python -m trends history RESULTS.csv ...     # add results (rpscrape or RacingFormBook CSV) to the history
python -m trends merge PART.csv.gz ...       # merge compact history files
python -m trends cards RACECARDS.json ...    # analyse cards -> docs/data/cards/<date>.json
python -m trends settle RESULTS.csv ...      # mark winners, update performance + history
python -m trends bundle                      # docs/standalone.html: one file with the data inside
python -m unittest discover tests            # tests
```

## Notes

- GitHub Pages sites are public; the page is marked `noindex` so search engines skip it. Check the data
  providers' terms before sharing the link widely.
- Every file in `data/history/` is read: `rfb.csv.gz` (RacingFormBook import), `races.csv.gz` (daily results),
  `backfill.csv.gz` (an earlier rpscrape backfill attempt). Duplicates across them are harmless.
- `scripts/backfill.sh` (bulk rpscrape backfill) is kept for reference but Racing Post blocks it after a few
  hundred races; use the RacingFormBook files instead.
- The demo data in `docs/data` (Southwell, 24 Nov 2026) is replaced by the first real run.
