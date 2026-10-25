#!/usr/bin/env python3
"""Discovery source #2: RT 'movies at home' browse lists per streaming affiliate (critics:fresh, sort:newest),
paginated via RT's cnapi until items' streaming dates fall before 2025-01-01. Output raw/rt_browse_<date>.json"""
import json, sys, os, re, datetime, time, urllib.parse
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import get, BASE
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
AFF={'netflix':'netflix','prime':'prime-video','hulu':'hulu','disney':'disney-plus','hbomax':'max','appletv':'apple-tv-plus',
     'paramount':'paramount-plus','peacock':'peacock'}  # RT has no Starz or MGM+ browse filter (returns unfiltered 'undefined' list)
out={}
for svc,aff in AFF.items():
    items=[]; after=None; pages=0
    while pages<60:
        u=f'https://www.rottentomatoes.com/cnapi/browse/movies_at_home/affiliates:{aff}~critics:fresh~sort:newest'+(f'?after={urllib.parse.quote(after)}' if after else '')
        code,s=get(u)
        try: j=json.loads(s)
        except Exception: print(svc,'bad',code,s[:100]); break
        g=j.get('grid',{}); L=g.get('list',[]); items+=L; pages+=1
        old=[x for x in L if re.search(r'(20\d\d)',x.get('releaseDateText') or '') and int(re.search(r'(20\d\d)',x['releaseDateText']).group(1))<2025]
        pi=j.get('pageInfo') or g.get('pageInfo') or {}
        if len(old)>=len(L)*0.8 or not pi.get('hasNextPage'): break
        after=pi.get('endCursor'); time.sleep(0.3)
    out[svc]={'affiliate':aff,'title':j.get('title') if pages else None,'n':len(items),'items':items}
    print(svc,aff,len(items),pages, (items[-1].get('releaseDateText') if items else None))
json.dump(out,open(f'{BASE}/raw/rt_browse_{D}.json','w'))
