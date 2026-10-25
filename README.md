# Movie streaming DB (US): 2025–2026 films included with subscriptions

Built for Emil Frojd (Mountain View, CA). It follows the same pattern as the speaker DB: SQLite, an idempotent schema, dated runs, an evidence table, sources_checked, sightings, change_events, and views that produce the eligible list. A generated HTML report is published to GitHub Pages.

**Files:** `schema.sql` (tables + views), `movies.db`, `scripts/` (pipeline), `overrides/` (reviewed manual decisions), `raw/` (dated API/page captures; not published), `method.md` (method and rules), `run_all.sh` (full re-check), `publish.sh` (build + push to Pages), `report.html` / `report.md` (generated).

## Re-run / re-check
```bash
cd /workspace/movies
./run_all.sh 2026-11-24      # new dated run: re-pulls JustWatch, RT, IMDb, service pages and Reelgood, then diffs vs the previous run
./publish.sh "re-check Nov 24"
```
Every stage is keyed by run date. Re-running the same date replaces that run's observations, and a new date creates a new `runs` row. `flags_and_changes.py` writes `change_events` (availability_added / availability_removed / score_change) against the previous run.

## Adding years or services
- **Years:** change `releaseYear:{min:2025,max:2026}` in `scripts/jw_catalog.py` and the `release_year IN (2025,2026)` filter in the `v_qualifying` view.
- **Services:** add a row to `SERVICES` / `INCLUDED_PK` / `PK_INFO` / `REELGOOD_SRC` in `scripts/common.py` (JustWatch package shortName), then add an RT browse affiliate (if RT has one) in `scripts/rt_browse.py` and a page parser in `scripts/official_check.py` → `judge()`.

## Schema overview
- `services`, `packages`: each JustWatch package and whether it counts as included (e.g. Prime `amp` = included; Amazon Channels = `channel_addon`).
- `runs`: one per check date.
- `movies`: keyed by RT slug. Holds release_year (rule in method.md), the IMDb/RT/JW years, runtime, IMDb type, genre_label, kid_friendly and exclude_reason.
- `sightings`: candidate discovery per run/service/source.
- `availability_obs`: per run × movie × service × source (`justwatch`, `official`, `reelgood`, `rt_where_to_watch`, `manual`) × offer_type (`included`, `channel_addon`, `rent`, `buy`, `bundle`, `free_ads`, `not_listed`, `coming_soon`, `unreachable`, `unknown`), with URL, HTTP status and detail.
- `score_obs`: Tomatometer, critic review count, average, certified, Popcornmeter, audience band and counts per run.
- `evidence`: claim/value/doc_type/is_official/url/quote/retrieved_at for tomatometer, popcornmeter and release_year.
- `sources_checked`, `flags`, `change_events`.
- Views: `v_latest_scores`, `v_availability`, `v_included`, `v_qualifying`, `v_ranked`, `v_top10`, `v_top10_min20` (alternative cut with ≥20 reviews), `v_service_counts`.

```sql
SELECT service_code, rnk, title, release_year, tomatometer, critic_reviews, popcornmeter, genre_label FROM v_top10 ORDER BY service_code, rnk;
SELECT * FROM v_service_counts;
```
Qualifying counts for run 2026-10-24:
```
appletv | 9
disney | 13
hbomax | 30
hulu | 52
mgmplus | 9
netflix | 84
paramount | 17
peacock | 11
prime | 54
starz | 4
```

## Rule notes (2026-10-24, v1)
- Release year = the earliest of the IMDb year and the RT year (first release, festivals included). The JustWatch year is recorded but not used, because it sometimes reflects the US or streaming release.
- These are not films: IMDb types short/tvShort/tvSpecial/tvEpisode/tvSeries, runtimes ≤40 min, and stand-up specials. Excluded by review: *Gary* (Hulu files it as a series) and *Color Theories by Julio Torres* (stand-up special).
- Prime Video counts only titles whose Amazon entitlement message says Prime ("Join Prime", "Subscribe to Prime…"). "Free trial of <channel>", "Subscribe to <channel>", "rent or buy" and "Watch for free" (ads) are all excluded.
- Disney+ counts only titles on JustWatch's Disney+ package with a Disney+ title page. Titles RT labels "Disney+" that are only on Hulu are treated as Hulu-in-Disney+ bundle access. *Oasis: Don't Look Back in Anger* was moved to bundle by review (see overrides/pair_overrides.json).
- Ranking strictly follows the request (Tomatometer), so low-review-count 100% titles rank high and are flagged †. `v_top10_min20` gives a ≥20-review alternative.
