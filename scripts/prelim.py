import json,glob,collections,sys
D='2026-10-24'
imdb=json.load(open(f'raw/imdb_{D}.json')); m=json.load(open(f'raw/rt_match_{D}.json')); P=json.load(open(f'raw/rt_pages_{D}.json'))
man={k:v for k,v in json.load(open('overrides/rt_manual.json')).items() if not k.startswith('_')}
res=collections.defaultdict(list)
for f in sorted(glob.glob(f'raw/jw_*_{D}.json')):
    d=json.load(open(f))
    for x in d['nodes']:
        c=x['content']; jid=x['id']
        url=('https://www.rottentomatoes.com/m/'+man[c['title']]) if c['title'] in man else ((m[jid]['match'] or {}).get('url'))
        if not url: continue
        p=P.get(url) or {}
        tm=p.get('tomatometer')
        if tm is None or tm<80: continue
        im=imdb.get(c['externalIds']['imdbId'] or '') or {}
        res[d['svc']].append((tm,p.get('critic_reviews'),p.get('popcorn'),c['title'],c['originalReleaseYear'],im.get('y'),(m[jid]['match'] or {}).get('year'),im.get('qid'),p['info'].get('Runtime'),url.split('/m/')[1]))
for s,L in res.items():
    L.sort(key=lambda r:(-r[0],-(r[1] or 0)))
    print('==',s,len(L))
    for r in L[:25]: print('  ',r)
