# Racing Trends

Past-renewal trends for every UK & Irish race, updated twice a day and published as a website.

For each race on today's and tomorrow's cards it finds the same race in previous seasons (up to 10),
summarises what the winners had in common (age, weight off top, rating, price, favourites' record,
repeat trainers/jockeys), and ranks the runners by how well they fit. After racing it records the result
so the **Performance** tab shows whether higher trend scores actually win more often.

## How it works

| When (UK time) | What runs |
|---|---|
| ~06:10 | Settle yesterday's results, build cards for today and tomorrow |
| ~21:40 | Settle today's results, refresh tomorrow's cards |

GitHub Actions runs `scripts/run.sh`, which uses [rpscrape-community](https://github.com/Eatkin/rpscrape-community)
(the maintained continuation of rpscrape, whose original repo went offline) to fetch
racecards and results, then `python -m trends` to do the analysis. The site is static (`docs/`) and served
by GitHub Pages. GitHub's scheduled runs can start 5–30 minutes late at busy times.

**Matching a "past renewal"**: same course, race type (flat/hurdle/chase/NH flat), surface, handicap or not,
pattern level, distance within ~1¼f (jumps) or ~½f (sprints), class within one band, run within ±45 days of
the same date. If several races in a season qualify, the closest one wins (penalties for distance, class,
date gap and race-kind differences such as maiden/novice/mares). Runners are only scored when 3+ renewals exist.

## One-time setup

1. **Let Claude push (optional)** – install the Claude GitHub app on this repo, or upload the files yourself.
2. **Turn on the site** – *Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/docs`*.
   Your dashboard will be at `https://cburns98765-oss.github.io/RacingTrends/`.
3. **Allow the workflows to commit** – *Settings → Actions → General → Workflow permissions → Read and write*.
4. **Load the history from your Mac** (Racing Post blocks GitHub's servers for bulk scraping):
   ```bash
   git clone https://github.com/cburns98765-oss/RacingTrends.git && cd RacingTrends
   bash scripts/backfill.sh 2021 2026
   ```
   Needs Python 3.13+. No admin rights? Install [uv](https://docs.astral.sh/uv/) into your home folder with
   `curl -LsSf https://astral.sh/uv/install.sh | sh` and the script uses it to fetch Python 3.13. No git?
   Download the repo with *Code → Download ZIP* instead of cloning, and upload `data/history/backfill.csv.gz`
   through GitHub's website afterwards. It works newest month first,
   saves and pushes after each month to `data/history/backfill.csv.gz`, keeps the Mac awake, and can be
   stopped (Ctrl+C) and re-run any time – finished months are skipped. rpscrape-community waits ~2–3 s
   between requests, so a month of GB + IRE racing takes roughly 30–60 minutes. If Racing Post starts
   blocking your connection the script stops; wait a day before running it again.
5. **First daily run** – *Actions → Daily update → Run workflow → morning*. After that it runs on its own.

## Run the daily update on your own computer

If Racing Post blocks GitHub's servers (rpscrape gets errors or returns no files in the Actions log),
run the same thing locally (macOS/Linux, or Windows with Git Bash / WSL) and push:

```bash
bash scripts/run.sh morning      # or: evening
git add docs/data data/history && git commit -m "data" && git push
```

## Commands

```bash
python -m trends history RESULTS.csv ...     # add rpscrape results to the history
python -m trends merge PART.csv.gz ...       # merge backfill parts
python -m trends cards RACECARDS.json ...    # analyse cards -> docs/data/cards/<date>.json
python -m trends settle RESULTS.csv ...      # mark winners, update performance + history
python -m trends bundle                      # docs/standalone.html: one file with the data inside
python -m unittest discover tests            # tests (Southwell 24 Nov 2026 fixture)
```

## Notes

- rpscrape scrapes Racing Post, whose terms don't allow scraping. Keep use personal. GitHub Pages sites are
  public, so anyone with the link can see the dashboard (it's marked `noindex` so search engines skip it).
- rpscrape's column names change between versions; the importer accepts the common aliases and stops with a
  list of the columns it found if it can't find finishing positions.
- The demo data in `docs/data` (Southwell, 24 Nov 2026) is replaced by the first real run.
