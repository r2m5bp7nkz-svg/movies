#!/usr/bin/env python3
"""Stage 3: fetch every matched RT movie page (fresh, no cache reuse across dates) and parse scorecard + where-to-watch.
Output raw/rt_pages_<date>.json keyed by RT url."""
import json, sys, os, datetime, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import *
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
m=json.load(open(f'{BASE}/raw/rt_match_{D}.json'))
man=json.load(open(f'{BASE}/overrides/rt_manual.json'))
urls=set(v['match']['url'] for v in m.values() if v['match'])
urls|=set('https://www.rottentomatoes.com/m/'+s for k,s in man.items() if not k.startswith('_'))
def w(url):
    code,s=get(url, f'{BASE}/raw/rt_pages_{D}')
    return url,dict(parse_movie(s) if code==200 else {}, http=code, url=url, retrieved_at=datetime.datetime.now().isoformat(timespec='seconds'))
out={}
with cf.ThreadPoolExecutor(6) as ex:
    for i,(u,r) in enumerate(ex.map(w,sorted(urls))):
        out[u]=r
        if i%300==0: print(i,flush=True)
json.dump(out,open(f'{BASE}/raw/rt_pages_{D}.json','w'))
import collections; print(len(out), collections.Counter(r['http'] for r in out.values()), sum(1 for r in out.values() if (r.get('tomatometer') or 0)>=80))
