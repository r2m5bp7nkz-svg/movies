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
- `audience_count_obs` (r3): the RT audience rating-count bucket shown next to the Popcornmeter (band text, lower bound `band_min`, verified or all-audience, visible markup + scorecard JSON, status ok/unreadable) per run and movie, from `scripts/audience_counts.py`. Evidence claim `audience_rating_count`.
- `score_obs`: Tomatometer, critic review count, average, certified, Popcornmeter, audience band and counts per run.
- `evidence`: claim/value/doc_type/is_official/url/quote/retrieved_at for tomatometer, popcornmeter and release_year.
- `sources_checked`, `flags`, `change_events`.
- `imdb_rating_obs`: IMDb rating/votes per run and movie (source = IMDb dataset, with the IMDb URL, dataset Last-Modified and JustWatch's IMDb score as a cross-check).
- Views: `v_latest_scores`, `v_latest_imdb`, `v_availability`, `v_included`, `v_qualifying` (all Tomatometer ≥80), `v_main_r2` (plus Popcornmeter ≥80 and ≥20 reviews), `v_main` (r3: v_main_r2 plus ≥250 RT audience ratings), `v_few_audience_ratings` (r2 qualifiers dropped by the 250 rule), `v_latest_audience_count`, `v_ranked`, `v_top10`, `v_thin`, `v_no_audience`, `v_audience_below80`, `v_service_counts`.

```sql
SELECT service_code, rnk, title, release_year, tomatometer, critic_reviews, popcornmeter, genre_label FROM v_top10 ORDER BY service_code, rnk;
SELECT * FROM v_service_counts;
```
Counts for run 2026-10-24 (rules r2): service | main-table qualifiers | thin data | no audience score | critics 80+ but audience <80 | all critics 80+
```
appletv | 6 | 0 | 1 | 2 | 9
disney | 7 | 1 | 3 | 2 | 13
hbomax | 18 | 0 | 5 | 7 | 30
hulu | 27 | 0 | 11 | 14 | 52
mgmplus | 6 | 0 | 0 | 3 | 9
netflix | 33 | 10 | 23 | 18 | 84
paramount | 10 | 1 | 2 | 4 | 17
peacock | 6 | 1 | 1 | 3 | 11
prime | 16 | 6 | 23 | 9 | 54
starz | 2 | 0 | 0 | 2 | 4
```

## Rule notes (2026-10-24, v1)
- Release year = the earliest of the IMDb year and the RT year (first release, festivals included). The JustWatch year is recorded but not used, because it sometimes reflects the US or streaming release.
- These are not films: IMDb types short/tvShort/tvSpecial/tvEpisode/tvSeries, runtimes ≤40 min, and stand-up specials. Excluded by review: *Gary* (Hulu files it as a series) and *Color Theories by Julio Torres* (stand-up special).
- Prime Video counts only titles whose Amazon entitlement message says Prime ("Join Prime", "Subscribe to Prime…"). "Free trial of <channel>", "Subscribe to <channel>", "rent or buy" and "Watch for free" (ads) are all excluded.
- Disney+ counts only titles on JustWatch's Disney+ package with a Disney+ title page. Titles RT labels "Disney+" that are only on Hulu are treated as Hulu-in-Disney+ bundle access. *Oasis: Don't Look Back in Anger* was moved to bundle by review (see overrides/pair_overrides.json).
- (Superseded by r2 below) v1 ranked strictly by Tomatometer, so 100% titles with few reviews ranked high (†).

## Rule change 2026-10-24 (r2)
- Main per-service top 10: Tomatometer ≥80 **and** a displayed Popcornmeter ≥80 **and** ≥20 critic reviews. Ranked by Tomatometer, then Popcornmeter, then critic review count.
- Side lists per service, outside the top 10: *thin data* (both ≥80, <20 reviews) and *critics 80%+, no audience score yet*. Critics ≥80 with audience <80 are shown collapsed as not qualifying.
- Audience audit (`scripts/audience_audit.py`): all 68 qualifying movies with a NULL Popcornmeter were re-checked in every place RT can show one. RT truly displays no Popcornmeter for all 68 ("Fewer than 50 Ratings" / "0 Ratings"), so the v1 parser was not failing. Per-movie evidence quotes are in `evidence` (claim = popcornmeter).
- New IMDb column, from IMDb's official ratings dataset (`scripts/imdb_ratings.py`). Informational only; ⁱ = fewer than 1,000 votes.
- Discovery audit: every Prime reference title (Is God Is, The Sheep Detectives, Project Hail Mary, One Battle After Another, Hedda, Deep Cover, John Candy: I Like Me, Crime 101, Roofman) and the Netflix titles KPop Demon Hunters, Frankenstein and Wake Up Dead Man were already in the DB and verified as included. They were hidden by the v1 ranking, not lost by discovery. JustWatch catalog pulls were complete (totalCount = rows fetched for every package). The RT-list titles not found on JustWatch were pre-2025 or rent-only; for example, six 2026 Prime items (Esta Isla, Over/Under, Mustache, Decorado, Kontinental '25, Miroirs No. 3) are "Rent … on Fandango" on RT.

## Rule change 2026-10-25 (r3)
- New rule: a main-table movie must also have **at least 250 RT audience ratings**, i.e. the rating count RT displays next to the shown Popcornmeter is "250+ Ratings" / "250+ Verified Ratings" or a higher bucket (500+, 1,000+, 2,500+, …). Whichever count RT displays (verified when RT shows the verified score, otherwise all-audience) is the one used. All other rules and the sort order (Tomatometer → Popcornmeter → critic reviews) are unchanged; lower-ranked qualifiers backfill each top 10.
- `scripts/audience_counts.py` re-fetches the RT page of every movie that passes r2 on any service (117 movies on 2026-10-25) and reads the bucket from the visible scorecard (`<rt-link slot="audience-reviews">`) and from `media-scorecard-json` `audienceScore.bandedRatingCount`; both must agree. Results go to `audience_count_obs` + `evidence` (claim `audience_rating_count`) + `sources_checked`; raw pages in `raw/rt_counts_<date>/`, summary in `raw/audience_counts_<date>.json`. A count is never estimated: if it can't be read the movie is flagged `audience_count_unreadable` and left out. On 2026-10-25 all 117 were readable (0 flagged), 77 have 250+, 40 drop out. Popcornmeter, Tomatometer and review counts on the re-fetched pages matched the 2026-10-24 run for all 117.
- `scripts/migrate_r3.py` (one-off, idempotent) widened the CHECK constraints on `evidence.claim` and `flags.flag_type` in the existing DB and applied the new schema. A pre-migration copy is at `/workspace/movies.db.bak_2026-10-25`.
- Run order: `audience_counts.py` runs after `flags_and_changes.py` (which clears a run's flags) and before `build_report.py`.
- The Five recommendations section was removed from the report.

Counts for run 2026-10-24 with r3 (counts re-checked 2026-10-25): service | r2 main-table qualifiers | r3 qualifiers (≥250 ratings)
```
appletv | 6 | 3
disney | 7 | 6
hbomax | 18 | 13
hulu | 27 | 18
mgmplus | 6 | 5
netflix | 33 | 22
paramount | 10 | 7
peacock | 6 | 3
prime | 16 | 12
starz | 2 | 2
```
