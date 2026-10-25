#!/usr/bin/env python3
"""Discovery cross-check: every RT browse item (>=80%) that is not already a JW-catalog candidate is looked up on JustWatch by title
(searchQuery), so titles JW files under a different year/catalog still get their offers checked. Output raw/jwsearch_extra_<date>.json"""
import json, sys, os, datetime, sqlite3, time
sys.path.insert(0, os.path.dirname(__file__)); from jw_catalog import post, Q; from rt_lib import norm, BASE
def main():
    D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
    QS=Q.replace('query Cat($after:String,$pk:[String!])','query S($q:String!)').replace('first:100, after:$after, sortBy:POPULAR,','first:8,').replace(
     'filter:{packages:$pk, objectTypes:[MOVIE], releaseYear:{min:2025,max:2026}, monetizationTypes:[FLATRATE]}','filter:{searchQuery:$q, objectTypes:[MOVIE], releaseYear:{min:2024,max:2026}}')
    B=json.load(open(f'{BASE}/raw/rt_browse_{D}.json'))
    c=sqlite3.connect(f'{BASE}/movies.db')
    have=set(r[0] for r in c.execute('select rt_slug from movies'))
    todo={}
    for svc,d in B.items():
        for x in d['items']:
            sc=x['criticsScore'].get('score'); slug=x['mediaUrl'].split('/m/')[1]
            if sc and int(sc)>=80 and slug not in have: todo[slug]=x['title']
    out={}
    for slug,t in todo.items():
        r=post(QS,{'q':t}); nodes=[e['node'] for e in r['data']['popularTitles']['edges']] if 'data' in r else []
        nodes=[n for n in nodes if norm(n['content']['title'])==norm(t)]
        out[slug]={'rt_title':t,'nodes':nodes}; time.sleep(0.25)
    json.dump(out,open(f'{BASE}/raw/jwsearch_extra_{D}.json','w'))
    print(len(todo), sum(1 for v in out.values() if v['nodes']))
if __name__=='__main__': main()
