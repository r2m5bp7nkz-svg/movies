#!/usr/bin/env python3
"""Stage 2: match each unique JustWatch candidate to its RT /m/ page via RT search (JW title, then IMDb English title).
Match rules: compact-normalized title equal (or one is prefix of the other with exact year + cast overlap),
year within 2 of JW or IMDb year; ties broken by cast overlap then year distance. Output raw/rt_match_<date>.json"""
import json, glob, sys, os, urllib.parse, datetime, concurrent.futures as cf, collections
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import *
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
imdb=json.load(open(f'{BASE}/raw/imdb_{D}.json'))
u={}
for f in sorted(glob.glob(f'{BASE}/raw/jw_*_{D}.json')):
    for x in json.load(open(f))['nodes']: u[x['id']]=x
cmp=lambda t: norm(t).replace(' ','')
def pick(rows, titles, years, cast):
    best=None
    for r in rows:
        if not r['url']: continue
        ry=int(r['year']) if (r['year'] or '').isdigit() else None
        rt=cmp(r['title']); rc=set(norm(c) for c in (r['cast'] or '').split(',') if c)
        ov=len(rc & cast)
        for t in titles:
            exact= rt==t
            pref = (not exact) and len(min(rt,t,key=len))>=2 and (rt.startswith(t) or t.startswith(rt))
            if not (exact or pref): continue
            dy=min([abs(ry-y) for y in years if y] or [9]) if ry else 9
            if dy>2: continue
            if pref and not (dy==0 and ov>0): continue
            if dy>=1 and ov==0 and (rc and cast): continue   # off-by-one year needs cast overlap when both sides list cast
            if dy>1 and ov==0: continue
            sc=(0 if exact else 1, -ov, dy)
            if best is None or sc<best[0]: best=(sc,r)
    return best
def work(item):
    jid,x=item; c=x['content']; t=c['title']; y=c['originalReleaseYear']
    im=imdb.get(c['externalIds']['imdbId'] or '') or {}
    titles=[cmp(t)]+([cmp(im['l'])] if im.get('l') and cmp(im['l'])!=cmp(t) else [])
    years=[y, im.get('y')]; cast=set(norm(s) for s in (im.get('s') or '').split(',') if s.strip())
    best=None; tried=[]
    for q in [t]+([im['l']] if len(titles)>1 else []):
        code,s=get('https://www.rottentomatoes.com/search?search='+urllib.parse.quote(q), f'{BASE}/raw/rt_search')
        tried.append((q,code))
        b=pick(parse_search(s) if code==200 else [], titles, years, cast)
        if b and (best is None or b[0]<best[0]): best=b
        if best and best[0][0]==0: break
    return jid, {'title':t,'imdb_title':im.get('l'),'jw_year':y,'imdb_year':im.get('y'),'tried':tried,'match':best[1] if best else None,'match_quality':best[0] if best else None}
out={}
with cf.ThreadPoolExecutor(6) as ex:
    for i,(jid,r) in enumerate(ex.map(work,u.items())): out[jid]=r
json.dump(out,open(f'{BASE}/raw/rt_match_{D}.json','w'))
print(collections.Counter('match' if r['match'] else 'nomatch' for r in out.values()))
