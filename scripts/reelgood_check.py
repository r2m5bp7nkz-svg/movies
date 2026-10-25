#!/usr/bin/env python3
"""Stage 6: independent cross-check via Reelgood's public API for every candidate (movie, service) pair checked in Stage 5.
access_type 2 = subscription. Writes availability_obs(source='reelgood') as included / not_listed / unknown (no Reelgood match)."""
import sys, os, json, re, datetime, urllib.parse, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__)); from common import *; from rt_lib import get, norm
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
c=connect(); run=c.execute("SELECT run_id FROM runs WHERE run_date=?",(D,)).fetchone()[0]
movies=c.execute("""SELECT DISTINCT m.movie_id,m.title,m.original_title,m.release_year,m.jw_year,m.imdb_year FROM availability_obs a JOIN movies m USING(movie_id)
 WHERE a.run_id=? AND a.source='official'""",(run,)).fetchall()
pairs={}
for r in c.execute("SELECT movie_id,service_code FROM availability_obs WHERE run_id=? AND source='official'",(run,)): pairs.setdefault(r[0],set()).add(r[1])
def work(m):
    mid,t,ot,y,jy,iy=m; ys={v for v in (y,jy,iy) if v}
    best=None
    for q in [t]+([ot] if ot and ot!=t else []):
        code,s=get('https://api.reelgood.com/v3.0/content/search/content?terms='+urllib.parse.quote(q)+'&region=us', f'{BASE}/raw/reelgood_{D}')
        try: items=json.loads(s).get('items',[])
        except Exception: items=[]
        for it in items:
            if it.get('content_type')!='m': continue
            ry=int((it.get('released_on') or '0000')[:4] or 0)
            if norm(it['title']) in (norm(t),norm(ot or '')) and any(abs(ry-v)<=1 for v in ys): best=it; break
        if best: break
    if not best: return mid,None,None
    code,s=get(f"https://api.reelgood.com/v3.0/content/movie/{best['slug']}?region=us", f'{BASE}/raw/reelgood_{D}')
    try: d=json.loads(s)
    except Exception: return mid,best['slug'],None
    subs=set(a['source_name'] for a in d.get('availability',[]) if a.get('access_type')==2)
    return mid,best['slug'],subs
c.execute("DELETE FROM availability_obs WHERE run_id=? AND source='reelgood'",(run,))
now=datetime.datetime.now().isoformat(timespec='seconds')
with cf.ThreadPoolExecutor(4) as ex:
    for i,(mid,slug,subs) in enumerate(ex.map(work,movies)):
        for svc in pairs[mid]:
            if subs is None: ot,det='unknown','no Reelgood match' if not slug else 'Reelgood detail unreadable'
            else:
                hit=[s for s in subs if s in REELGOOD_SRC[svc]]
                ot,det=('included','subscription source(s): '+','.join(hit)) if hit else ('not_listed','Reelgood subscription sources: '+(','.join(sorted(subs)) or 'none'))
            c.execute("INSERT OR REPLACE INTO availability_obs(run_id,movie_id,service_code,source,offer_type,package,url,http_status,detail,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (run,mid,svc,'reelgood',ot,None,f'https://reelgood.com/movie/{slug}' if slug else None,200,det,now))
        if slug: c.execute("UPDATE movies SET reelgood_slug=? WHERE movie_id=?",(slug,mid))
        if i%25==0: c.commit()
c.commit()
for r in c.execute("SELECT service_code,offer_type,count(*) FROM availability_obs WHERE run_id=? AND source='reelgood' GROUP BY 1,2",(run,)): print(tuple(r))
