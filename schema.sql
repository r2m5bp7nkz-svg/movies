-- Movie streaming DB (US). Idempotent: CREATE IF NOT EXISTS everywhere. Views are dropped/recreated.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS services(
 service_code TEXT PRIMARY KEY,               -- netflix, prime, hulu, disney, hbomax, appletv, paramount, peacock, starz, mgmplus
 name TEXT NOT NULL, official_domain TEXT, notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- Every package/offer bucket seen in availability sources, and whether it counts as "included with the base subscription".
CREATE TABLE IF NOT EXISTS packages(
 package_code TEXT PRIMARY KEY,               -- JustWatch shortName (nfx, amp, ppp...) or other-source code
 service_code TEXT REFERENCES services(service_code),
 source TEXT NOT NULL DEFAULT 'justwatch', clear_name TEXT, jw_package_id INTEGER,
 kind TEXT NOT NULL CHECK(kind IN ('core','tier','channel_addon','bundle','store','other')),
 counts_as_included INTEGER NOT NULL CHECK(counts_as_included IN (0,1)), notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- One row per research run (a dated re-check). All observations hang off a run so re-runs can be diffed.
CREATE TABLE IF NOT EXISTS runs(
 run_id INTEGER PRIMARY KEY, run_date TEXT NOT NULL UNIQUE, scope TEXT, rules_version TEXT, notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS movies(
 movie_id INTEGER PRIMARY KEY,
 rt_slug TEXT UNIQUE,                         -- rottentomatoes.com/m/<rt_slug>
 title TEXT NOT NULL, original_title TEXT,
 release_year INTEGER,                        -- rule: earliest of IMDb year and RT year (first release incl. festivals)
 imdb_year INTEGER, rt_year INTEGER, jw_year INTEGER, year_note TEXT,
 imdb_id TEXT, imdb_type TEXT, jw_id TEXT, tmdb_id TEXT, reelgood_slug TEXT,
 runtime_min INTEGER, rt_genres TEXT, genre_label TEXT, original_language TEXT, countries TEXT,
 content_rating TEXT, is_documentary INTEGER, is_international INTEGER, kid_friendly TEXT,
 exclude_reason TEXT,                         -- NULL = eligible film; else 'short','tv_special','pre_2025','tv_series',...
 notes TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX IF NOT EXISTS ux_movies_jw ON movies(jw_id) WHERE jw_id IS NOT NULL AND rt_slug IS NULL;

-- Candidate discovery: which titles each source listed for each service in each run.
CREATE TABLE IF NOT EXISTS sightings(
 sighting_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 service_code TEXT NOT NULL REFERENCES services(service_code), movie_id INTEGER REFERENCES movies(movie_id),
 source TEXT NOT NULL,                        -- 'justwatch_catalog','rt_best_list','service_new_releases'
 raw_title TEXT NOT NULL, raw_year INTEGER, jw_id TEXT, url TEXT, seen_at TEXT NOT NULL,
 UNIQUE(run_id, service_code, source, raw_title, raw_year));

-- Availability observations: one per (run, movie, service, source, offer_type, package).
CREATE TABLE IF NOT EXISTS availability_obs(
 obs_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 movie_id INTEGER NOT NULL REFERENCES movies(movie_id), service_code TEXT NOT NULL REFERENCES services(service_code),
 source TEXT NOT NULL CHECK(source IN ('justwatch','official','reelgood','rt_where_to_watch','manual')),  -- manual = reviewed override (overrides/pair_overrides.json)
 offer_type TEXT NOT NULL CHECK(offer_type IN ('included','channel_addon','rent','buy','bundle','free_ads','not_listed','coming_soon','unreachable','unknown')),
 package TEXT, url TEXT, http_status INTEGER, detail TEXT, observed_at TEXT NOT NULL,
 UNIQUE(run_id, movie_id, service_code, source, offer_type, package));

-- Rotten Tomatoes score observations (read from the movie's own RT page scorecard JSON).
CREATE TABLE IF NOT EXISTS score_obs(
 obs_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
 tomatometer INTEGER, critic_reviews INTEGER, critic_avg TEXT, certified_fresh INTEGER,
 popcornmeter INTEGER, audience_band TEXT, audience_reviews INTEGER, audience_ratings INTEGER,
 url TEXT NOT NULL, http_status INTEGER, observed_at TEXT NOT NULL,
 UNIQUE(run_id, movie_id));

CREATE TABLE IF NOT EXISTS evidence(
 evidence_id INTEGER PRIMARY KEY, movie_id INTEGER NOT NULL REFERENCES movies(movie_id) ON DELETE CASCADE,
 run_id INTEGER REFERENCES runs(run_id),
 claim TEXT NOT NULL CHECK(claim IN ('tomatometer','popcornmeter','audience_rating_count','availability','release_year','runtime','genre','type','rating')),
 service_code TEXT, value TEXT,
 doc_type TEXT NOT NULL CHECK(doc_type IN ('rt_page','service_page','justwatch_api','reelgood_api','imdb','rt_search','manual')),
 is_official INTEGER NOT NULL CHECK(is_official IN (0,1)), url TEXT, quote TEXT, retrieved_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(movie_id, run_id, claim, service_code, doc_type, url));

CREATE TABLE IF NOT EXISTS sources_checked(
 check_id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES runs(run_id), source TEXT NOT NULL, url TEXT,
 checked_at TEXT NOT NULL, result TEXT, notes TEXT,
 UNIQUE(run_id, source, url));

CREATE TABLE IF NOT EXISTS flags(
 flag_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 movie_id INTEGER NOT NULL REFERENCES movies(movie_id), service_code TEXT,
 flag_type TEXT NOT NULL CHECK(flag_type IN ('few_critic_reviews','few_audience_ratings','availability_conflict','year_conflict','official_unverified','title_match_check','tier_note','leaving_soon','audience_count_unreadable')),
 detail TEXT, UNIQUE(run_id, movie_id, service_code, flag_type));

CREATE TABLE IF NOT EXISTS change_events(
 event_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id), prev_run_id INTEGER REFERENCES runs(run_id),
 movie_id INTEGER REFERENCES movies(movie_id), service_code TEXT,
 event_type TEXT NOT NULL CHECK(event_type IN ('new_candidate','left_catalog','availability_added','availability_removed','score_change','new_qualifier','dropped_qualifier')),
 old_value TEXT, new_value TEXT, detected_at TEXT NOT NULL, notes TEXT,
 UNIQUE(run_id, movie_id, service_code, event_type));

-- ---------- views ----------
DROP VIEW IF EXISTS v_latest_run;
CREATE VIEW v_latest_run AS SELECT MAX(run_id) AS run_id FROM runs;

DROP VIEW IF EXISTS v_latest_scores;
CREATE VIEW v_latest_scores AS
 SELECT s.* FROM score_obs s WHERE s.run_id=(SELECT run_id FROM v_latest_run);

-- per (movie, service) availability verdict for the latest run
DROP VIEW IF EXISTS v_availability;
CREATE VIEW v_availability AS
 SELECT a.movie_id, a.service_code,
  MAX(CASE WHEN a.source='justwatch' AND a.offer_type='included' THEN 1 ELSE 0 END) AS jw_included,
  MAX(CASE WHEN a.source='official'  AND a.offer_type='included' THEN 1 ELSE 0 END) AS official_included,
  MAX(CASE WHEN a.source IN ('official','manual') AND a.offer_type IN ('not_listed','rent','buy','channel_addon','coming_soon','free_ads','bundle') THEN 1 ELSE 0 END) AS official_negative,
  MAX(CASE WHEN a.source='official'  AND a.offer_type IN ('unreachable','unknown') THEN 1 ELSE 0 END) AS official_unclear,
  MAX(CASE WHEN a.source='reelgood'  AND a.offer_type='included' THEN 1 ELSE 0 END) AS rg_included,
  MAX(CASE WHEN a.source='reelgood'  AND a.offer_type='not_listed' THEN 1 ELSE 0 END) AS rg_not_listed,
  MAX(CASE WHEN a.source='rt_where_to_watch' AND a.offer_type='included' THEN 1 ELSE 0 END) AS rt_included
 FROM availability_obs a WHERE a.run_id=(SELECT run_id FROM v_latest_run)
 GROUP BY a.movie_id, a.service_code;

-- Included = JustWatch FLATRATE on the service's own package AND (official page confirms
--   OR (official unclear AND an independent source (Reelgood or RT where-to-watch) confirms)). Official negative = excluded.
DROP VIEW IF EXISTS v_included;
CREATE VIEW v_included AS
 SELECT v.*, CASE WHEN official_included=1 THEN 'official+justwatch' ELSE 'justwatch+secondary (official page unclear)' END AS basis
 FROM v_availability v
 WHERE jw_included=1 AND official_negative=0 AND (official_included=1 OR (official_unclear=1 AND (rg_included=1 OR rt_included=1)));

-- Rule r3 (2026-10-25): RT audience rating-count bucket shown next to the displayed Popcornmeter (scripts/audience_counts.py).
-- band = the text RT shows ("250+ Ratings", "1,000+ Verified Ratings", ...); band_min = its lower bound (never an estimate).
-- status 'unreadable' => band_min NULL, flagged audience_count_unreadable, excluded from the main tables.
CREATE TABLE IF NOT EXISTS audience_count_obs(
 obs_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
 band TEXT, band_min INTEGER, verified_shown INTEGER, popcornmeter_seen INTEGER, markup_band TEXT, json_band TEXT,
 status TEXT NOT NULL CHECK(status IN ('ok','unreadable')), detail TEXT,
 url TEXT NOT NULL, http_status INTEGER, observed_at TEXT NOT NULL,
 UNIQUE(run_id, movie_id));
DROP VIEW IF EXISTS v_latest_audience_count;
CREATE VIEW v_latest_audience_count AS SELECT * FROM audience_count_obs WHERE run_id=(SELECT run_id FROM v_latest_run);

DROP VIEW IF EXISTS v_qualifying;
CREATE VIEW v_qualifying AS
 SELECT i.service_code, m.movie_id, m.title, m.release_year, m.rt_slug, m.genre_label, m.kid_friendly,
  s.tomatometer, s.critic_reviews, s.popcornmeter, s.audience_band, s.audience_reviews, i.basis
 FROM v_included i JOIN movies m USING(movie_id) JOIN v_latest_scores s USING(movie_id)
 WHERE m.exclude_reason IS NULL AND m.release_year IN (2025,2026) AND s.tomatometer>=80;

-- Rule change 2026-10-24 (r2): main per-service tables need Tomatometer>=80 AND a displayed Popcornmeter>=80
-- AND >=20 critic reviews; ranked by Tomatometer, then Popcornmeter, then critic review count.
DROP VIEW IF EXISTS v_ranked;
DROP VIEW IF EXISTS v_top10;
DROP VIEW IF EXISTS v_top10_min20;
DROP VIEW IF EXISTS v_main;
DROP VIEW IF EXISTS v_main_r2;
DROP VIEW IF EXISTS v_few_audience_ratings;
CREATE VIEW v_main_r2 AS SELECT * FROM v_qualifying WHERE popcornmeter>=80 AND critic_reviews>=20;   -- r2 candidates (audited by audience_counts.py)
-- Rule change 2026-10-25 (r3): also >=250 RT audience ratings (bucket "250+ Ratings"/"250+ Verified Ratings" or higher, as displayed).
CREATE VIEW v_main AS SELECT q.*, a.band AS audience_count_band, a.band_min AS audience_count_min
 FROM v_main_r2 q JOIN v_latest_audience_count a USING(movie_id) WHERE a.status='ok' AND a.band_min>=250;
-- r2 candidates removed by the 250 rule (or with an unreadable count): not ranked
CREATE VIEW v_few_audience_ratings AS SELECT q.*, a.band AS audience_count_band, a.band_min AS audience_count_min, a.status AS audience_count_status,
  ROW_NUMBER() OVER (PARTITION BY service_code ORDER BY tomatometer DESC, popcornmeter DESC, critic_reviews DESC, title) AS rnk
 FROM v_main_r2 q LEFT JOIN v_latest_audience_count a USING(movie_id) WHERE a.movie_id IS NULL OR a.status<>'ok' OR a.band_min<250;
CREATE VIEW v_ranked AS
 SELECT q.*, ROW_NUMBER() OVER (PARTITION BY service_code ORDER BY tomatometer DESC, popcornmeter DESC, critic_reviews DESC, title) AS rnk
 FROM v_main q;
CREATE VIEW v_top10 AS SELECT * FROM v_ranked WHERE rnk<=10;
-- Side lists (not ranked into the top 10)
DROP VIEW IF EXISTS v_thin;
CREATE VIEW v_thin AS SELECT q.*, ROW_NUMBER() OVER (PARTITION BY service_code ORDER BY tomatometer DESC, popcornmeter DESC, critic_reviews DESC, title) AS rnk
 FROM v_qualifying q WHERE popcornmeter>=80 AND critic_reviews<20;           -- both >=80 but <20 critic reviews
DROP VIEW IF EXISTS v_no_audience;
CREATE VIEW v_no_audience AS SELECT q.*, ROW_NUMBER() OVER (PARTITION BY service_code ORDER BY tomatometer DESC, critic_reviews DESC, title) AS rnk
 FROM v_qualifying q WHERE popcornmeter IS NULL;                              -- critics 80%+, RT shows no Popcornmeter yet
DROP VIEW IF EXISTS v_audience_below80;
CREATE VIEW v_audience_below80 AS SELECT q.*, ROW_NUMBER() OVER (PARTITION BY service_code ORDER BY tomatometer DESC, popcornmeter DESC, critic_reviews DESC, title) AS rnk
 FROM v_qualifying q WHERE popcornmeter<80;                                   -- critics 80%+, audience below 80%: does not qualify
DROP VIEW IF EXISTS v_service_counts;
CREATE VIEW v_service_counts AS SELECT service_code,
  SUM(popcornmeter>=80 AND critic_reviews>=20 AND movie_id IN (SELECT movie_id FROM v_latest_audience_count WHERE status='ok' AND band_min>=250)) AS n_qualifying,
  SUM(popcornmeter>=80 AND critic_reviews>=20) AS n_qualifying_r2,
  SUM(popcornmeter>=80 AND critic_reviews<20) AS n_thin,
  SUM(popcornmeter IS NULL) AS n_no_audience,
  SUM(popcornmeter<80) AS n_audience_below80,
  COUNT(*) AS n_critics80
 FROM v_qualifying GROUP BY service_code;

-- IMDb user rating observations (informational only; never a filter). Source: IMDb's official daily dataset title.ratings.tsv.gz
-- (title pages are behind an AWS WAF human-verification challenge for scripted clients); JustWatch's copy of the IMDb score is kept as a cross-check.
CREATE TABLE IF NOT EXISTS imdb_rating_obs(
 obs_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 movie_id INTEGER NOT NULL REFERENCES movies(movie_id), imdb_id TEXT NOT NULL,
 rating REAL, votes INTEGER, imdb_url TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT, source_last_modified TEXT,
 jw_imdb_score REAL, jw_imdb_votes INTEGER, title_page_http INTEGER, observed_at TEXT NOT NULL,
 UNIQUE(run_id, movie_id));
DROP VIEW IF EXISTS v_latest_imdb;
CREATE VIEW v_latest_imdb AS SELECT * FROM imdb_rating_obs WHERE run_id=(SELECT run_id FROM v_latest_run);
