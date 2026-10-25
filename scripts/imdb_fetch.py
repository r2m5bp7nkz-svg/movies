#!/usr/bin/env python3
"""Stage 1b: IMDb suggestion JSON per candidate (English title, year = first release incl. festivals, type, top cast)."""
import json, glob, sys, os, datetime, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import *
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
ids=set()
for f in glob.glob(f'{BASE}/raw/jw_*_{D}.json'):
    for x in json.load(open(f))['nodes']:
        i=x['content']['externalIds']['imdbId']
        if i: ids.add(i)
def w(i):
    code,s=get(f'https://v3.sg.media-imdb.com/suggestion/x/{i}.json', f'{BASE}/raw/imdb')
    try:
        d=[e for e in json.loads(s)['d'] if e.get('id')==i]
        return i,(d[0] if d else None)
    except Exception: return i,None
out={}
with cf.ThreadPoolExecutor(8) as ex:
    for i,r in ex.map(w,ids): out[i]=r
json.dump(out,open(f'{BASE}/raw/imdb_{D}.json','w'))
import collections; print(len(out), collections.Counter((r or {}).get('qid') for r in out.values()))
