#!/usr/bin/env python3
"""IMDb user rating (x/10) + vote count per movie, stored in imdb_rating_obs for the run.
Source: IMDb's official daily dataset https://datasets.imdbws.com/title.ratings.tsv.gz (same numbers as the title page's
JSON-LD aggregateRating). The title page itself is probed once per run and recorded in sources_checked; scripted clients get
HTTP 202 + AWS WAF 'Human Verification', so it is not scraped. JustWatch's imdbScore/imdbVotes are stored as a cross-check."""
import sys, os, gzip, json, glob, sqlite3, datetime, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import BASE
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
URL='https://datasets.imdbws.com/title.ratings.tsv.gz'; fn=f'{BASE}/raw/imdb_title_ratings_{D}.tsv.gz'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
r=urllib.request.urlopen(urllib.request.Request(URL,headers={'user-agent':UA}),timeout=120); lm=r.headers.get('last-modified')
open(fn,'wb').write(r.read())
rat={}
with gzip.open(fn,'rt') as f:
    next(f)
    for line in f:
        t,a,v=line.rstrip('\n').split('\t'); rat[t]=(float(a),int(v))
jw={}
for p in glob.glob(f'{BASE}/raw/jw_*_{D}.json'):
    for n in json.load(open(p))['nodes']:
        ct=n['content']; i=(ct.get('externalIds') or {}).get('imdbId'); sc=ct.get('scoring') or {}
        if i: jw[i]=(sc.get('imdbScore'),sc.get('imdbVotes'))
c=sqlite3.connect(f'{BASE}/movies.db'); c.execute('PRAGMA foreign_keys=ON')
run=c.execute('select run_id from runs where run_date=?',(D,)).fetchone()[0]
now=datetime.datetime.now().isoformat(timespec='seconds')
def probe(tt):
    try: return urllib.request.urlopen(urllib.request.Request(f'https://www.imdb.com/title/{tt}/',headers={'user-agent':UA,'accept':'text/html'}),timeout=30).status
    except urllib.error.HTTPError as e: return e.code
    except Exception: return -1
c.execute("INSERT OR REPLACE INTO sources_checked(run_id,source,url,checked_at,result,notes) VALUES(?,?,?,?,?,?)",(run,'imdb_dataset',URL,now,'200',f'last-modified {lm}; {len(rat)} rated titles'))
c.execute("DELETE FROM imdb_rating_obs WHERE run_id=?",(run,))
n=0; mism=[]
probe_code=None
for mid,tt in c.execute("select movie_id,imdb_id from movies where imdb_id like 'tt%'").fetchall():
    if probe_code is None:
        probe_code=probe(tt)
        c.execute("INSERT OR REPLACE INTO sources_checked(run_id,source,url,checked_at,result,notes) VALUES(?,?,?,?,?,?)",(run,'imdb_title_page',f'https://www.imdb.com/title/{tt}/',now,str(probe_code),'probe: 202 = AWS WAF human-verification page, not scraped'))
    a,v=rat.get(tt,(None,None)); js,jv=jw.get(tt,(None,None))
    c.execute("""INSERT INTO imdb_rating_obs(run_id,movie_id,imdb_id,rating,votes,imdb_url,source,source_url,source_last_modified,jw_imdb_score,jw_imdb_votes,title_page_http,observed_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(run,mid,tt,a,v,f'https://www.imdb.com/title/{tt}/','imdb_dataset',URL,lm,js,jv,probe_code,now)); n+=1
    if a is not None and js is not None and abs(a-js)>0.3: mism.append((tt,a,js))
c.commit(); print('imdb obs',n,'rated',sum(1 for _ in c.execute('select 1 from imdb_rating_obs where run_id=? and rating is not null',(run,))),'title-page probe',probe_code,'JW mismatch >0.3:',len(mism),mism[:10])
