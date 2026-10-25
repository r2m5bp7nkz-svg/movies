#!/bin/bash
# Full re-check for a date (default: today). Every stage is idempotent for that date; raw captures land in raw/.
set -e
cd "$(dirname "$0")"
D=${1:-$(date +%F)}
# Pages/API responses fetched within the last 7 days (fetch_cache) are reused; add --refresh as 2nd arg (or MOVIES_REFRESH=1) to force live fetches.
if [ "$2" = "--refresh" ]; then export MOVIES_REFRESH=1; fi
python3 scripts/jw_catalog.py            # JustWatch catalog per service (writes raw/jw_<svc>_$D.json)
python3 scripts/imdb_fetch.py $D         # IMDb year/type per candidate
python3 scripts/rt_browse.py $D          # RT "new fresh movies on <service>" lists
python3 scripts/rt_search.py $D          # JW title -> RT /m/ page
python3 scripts/rt_pages.py $D           # fetch + parse every matched RT page (scores, review counts, where-to-watch)
python3 scripts/load.py $D               # load everything into movies.db (run = $D)
python3 scripts/jw_supplement.py $D      # JW lookups for RT-list titles that aren't JW-catalog candidates (report-only cross-check)
python3 scripts/official_check.py $D     # service's own title pages
python3 scripts/reelgood_check.py $D     # Reelgood cross-check
python3 scripts/audience_audit.py $D     # re-verify every NULL Popcornmeter in all RT places (evidence)
python3 scripts/imdb_ratings.py $D       # IMDb rating/votes (official dataset) -> imdb_rating_obs
python3 scripts/flags_and_changes.py $D  # flags + change_events vs previous run
python3 scripts/audience_counts.py $D    # r3: RT audience rating-count bucket (>=250) for every r2 candidate, evidence + unreadable flags
python3 scripts/persist_lookups.py $D    # store every lookup (RT lists, RT search, JW searches, IMDb, audits) in lookup_obs, whatever the outcome
python3 scripts/build_report.py          # report.html + report.md
