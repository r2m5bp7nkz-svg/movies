#!/usr/bin/env python3
"""One-off, idempotent: register the raw page captures made before fetch_cache existed (raw/<stage>[_<date>]/<md5(url)>.html)
in fetch_cache, so the next run within 7 days reuses them. URLs come from the DB (score_obs, availability_obs, evidence,
sources_checked, audience_count_obs, raw match/page JSON); checked_at = the file's mtime. Unknown files are skipped."""
import os, sys, glob, json, hashlib, sqlite3, datetime, re
sys.path.insert(0, os.path.dirname(__file__)); import rt_lib
BASE=rt_lib.BASE; c=sqlite3.connect(os.path.join(BASE,'movies.db')); rt_lib._db().close()
urls=set()
for q in ("select url from score_obs","select url from availability_obs","select url from evidence","select url from sources_checked","select url from audience_count_obs"):
    urls|={r[0] for r in c.execute(q) if r[0]}
for f in glob.glob(f'{BASE}/raw/rt_pages_*.json'): urls|=set(json.load(open(f)).keys())
extra=set()
for u in list(urls):   # variants the fetchers actually requested
    if 'rottentomatoes.com/m/' in u: extra.add(u.rstrip('/'))
    if '/watch/asset/movies/' in u: extra.add(u.replace('/watch/asset/movies/','/watch-online/movies/'))
    if 'hbomax' in u: extra.add(u.split('?')[0])
urls|=extra
import urllib.parse
for i,t,ot in c.execute("select imdb_id,title,original_title from movies"):
    if i: urls.add(f'https://v3.sg.media-imdb.com/suggestion/x/{i}.json')
    for q in {t,ot}-{None}:
        urls.add('https://www.rottentomatoes.com/search?search='+urllib.parse.quote(q))
        urls.add('https://api.reelgood.com/v3.0/content/search/content?terms='+urllib.parse.quote(q)+'&region=us')
for r in c.execute("select distinct reelgood_slug from movies where reelgood_slug is not null"): urls.add(f'https://api.reelgood.com/v3.0/content/movie/{r[0]}?region=us')
H={hashlib.md5(u.encode()).hexdigest():u for u in urls}
n=0; skipped=0
for fn in glob.glob(f'{BASE}/raw/*/*.html'):
    h=os.path.basename(fn)[:-5]; u=H.get(h)
    if not u: skipped+=1; continue
    ts=datetime.datetime.fromtimestamp(os.path.getmtime(fn)).isoformat(timespec='seconds')
    old=c.execute("select checked_at from fetch_cache where url=?",(u,)).fetchone()
    if old and old[0]>=ts: continue
    c.execute("INSERT OR REPLACE INTO fetch_cache(url,cache_file,http_status,checked_at,bytes,source,reuse_count) VALUES(?,?,200,?,?,?,0)",
              (u,fn,ts,os.path.getsize(fn),'backfill:'+fn.split('/raw/')[1].split('/')[0])); n+=1
c.commit(); print('registered',n,'files; unmatched (no URL known in DB, e.g. search/API queries)',skipped)
print(c.execute("select source,count(*) from fetch_cache group by 1").fetchall())
