#!/usr/bin/env python3
"""Persist every lookup of a run into lookup_obs, whatever its outcome (never discard a lookup):
 rt_browse     every item on RT's "new fresh movies on <service>" lists (all scores, incl. ones never matched to a candidate)
 rt_search     every JustWatch title's RT search attempt (queries tried, chosen match or none)
 jw_supplement every JustWatch title search for RT-list titles that were not JW-catalog candidates (all returned nodes)
 imdb_suggest  every IMDb suggestion record fetched for a candidate
 audience_audit every NULL-Popcornmeter re-check (all variants checked)
checked_at = fetch_cache.checked_at for the URL when known, else the raw JSON's file time. Idempotent per run."""
import sys, os, json, datetime, sqlite3, urllib.parse, re
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import BASE
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
c=sqlite3.connect(os.path.join(BASE,'movies.db')); c.execute('PRAGMA foreign_keys=ON')
c.executescript(open(os.path.join(BASE,'schema.sql')).read())
run=c.execute("SELECT run_id FROM runs WHERE run_date=?",(D,)).fetchone()[0]
c.execute("DELETE FROM lookup_obs WHERE run_id=?",(run,))
FC={u:t for u,t in c.execute("SELECT url,checked_at FROM fetch_cache")}
SLUG={s:m for s,m in c.execute("SELECT rt_slug,movie_id FROM movies WHERE rt_slug IS NOT NULL")}
JW={}
for j,m,s in c.execute("SELECT jw_id,movie_id,rt_slug FROM movies WHERE jw_id IS NOT NULL ORDER BY rt_slug IS NULL"): JW.setdefault(j,m)
IM={}
for i,m in c.execute("SELECT imdb_id,movie_id FROM movies WHERE imdb_id IS NOT NULL ORDER BY rt_slug IS NULL"): IM.setdefault(i,m)
def ts(path): return datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec='seconds')
def put(stage,key,svc,mid,title,year,url,http,result,data,at):
    c.execute("INSERT OR REPLACE INTO lookup_obs(run_id,stage,lookup_key,service_code,movie_id,title,year,url,http_status,result,data_json,checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              (run,stage,key,svc or '',mid,title,year,url,http,result,json.dumps(data,ensure_ascii=False),FC.get(url) or at))
def yr(v):
    m=re.search(r'(19|20)\d\d',str(v or '')); return int(m.group(0)) if m else None
n={}
f=f'{BASE}/raw/rt_browse_{D}.json'
if os.path.exists(f):
    at=ts(f)
    for svc,d in json.load(open(f)).items():
        for x in d['items']:
            slug=x['mediaUrl'].split('/m/')[-1]; cs=(x.get('criticsScore') or {}).get('score'); au=(x.get('audienceScore') or {}).get('score')
            put('rt_browse',slug,svc,SLUG.get(slug),x.get('title'),yr(x.get('releaseDateText')),'https://www.rottentomatoes.com'+x['mediaUrl'],200,
                f"critics={cs} audience={au} {'in DB' if slug in SLUG else 'not a JW-catalog candidate'}",x,at); n['rt_browse']=n.get('rt_browse',0)+1
f=f'{BASE}/raw/rt_match_{D}.json'
if os.path.exists(f):
    at=ts(f)
    for jid,v in json.load(open(f)).items():
        m=v.get('match') or {}
        url=m.get('url') or ('https://www.rottentomatoes.com/search?search='+urllib.parse.quote(v['tried'][0][0]) if v.get('tried') else None)
        put('rt_search',jid,'',JW.get(jid),v.get('title'),v.get('jw_year'),url,(v.get('tried') or [[None,None]])[-1][1],
            ('matched '+m['url']) if m.get('url') else 'no RT match',v,at); n['rt_search']=n.get('rt_search',0)+1
f=f'{BASE}/raw/jwsearch_extra_{D}.json'
if os.path.exists(f):
    at=ts(f)
    for slug,v in json.load(open(f)).items():
        put('jw_supplement',slug,'',SLUG.get(slug),v.get('rt_title'),None,'https://apis.justwatch.com/graphql searchQuery='+(v.get('rt_title') or ''),200,
            f"{len(v['nodes'])} JustWatch node(s) with the same title",v,at); n['jw_supplement']=n.get('jw_supplement',0)+1
f=f'{BASE}/raw/imdb_{D}.json'
if os.path.exists(f):
    at=ts(f)
    for i,v in json.load(open(f)).items():
        u=f'https://v3.sg.media-imdb.com/suggestion/x/{i}.json'
        put('imdb_suggest',i,'',IM.get(i),(v or {}).get('l'),(v or {}).get('y'),u,200 if v else None,(v or {}).get('qid') or 'no record',v,at); n['imdb_suggest']=n.get('imdb_suggest',0)+1
f=f'{BASE}/raw/audience_audit_{D}.json'
if os.path.exists(f):
    at=ts(f)
    for slug,v in json.load(open(f)).items():
        u='https://www.rottentomatoes.com/m/'+slug
        put('audience_audit',slug,'',SLUG.get(slug),v.get('title'),None,u,(v.get('variants',{}).get(u) or {}).get('http'),'re-checked NULL Popcornmeter',v,at); n['audience_audit']=n.get('audience_audit',0)+1
c.commit(); print(n)
