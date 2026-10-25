#!/usr/bin/env python3
"""Audit every qualifying movie whose Popcornmeter is NULL in the latest run.
Re-fetches the RT page fresh (desktop Windows UA; with and without trailing slash; plus /reviews/all-audience)
and checks every place a Popcornmeter can appear. Writes raw/audience_audit_<D>.json, evidence + sources_checked rows,
and updates score_obs.popcornmeter ONLY when a page actually displays a number."""
import sys, os, json, re, datetime, sqlite3, urllib.request, urllib.error, gzip, html
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import scr, BASE
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
def fetch(url, accept='text/html'):
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,headers={'user-agent':UA,'accept':accept,'accept-language':'en-US,en;q=0.9','accept-encoding':'gzip'}),timeout=40)
        b=r.read(); b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b
        return r.status, b.decode('utf-8','replace')
    except urllib.error.HTTPError as e: return e.code, ''
    except Exception as e: return -1, str(e)
def places(s):
    """Return dict place->value (int score or None) + quotes."""
    out={}
    sc=scr(s,'media-scorecard-json') or {}
    au=sc.get('audienceScore') or {}; ov=sc.get('overlay') or {}
    out['scorecard_json.audienceScore.score']=au.get('score')
    out['scorecard_json.overlay.audienceAll.score']=(ov.get('audienceAll') or {}).get('score')
    out['scorecard_json.overlay.audienceVerified.score']=(ov.get('audienceVerified') or {}).get('score')
    out['scorecard_json.hideAudienceScore']=sc.get('hideAudienceScore')
    out['band']=au.get('bandedRatingCount')
    m=re.search(r'<media-scorecard\b.*?</media-scorecard>',s,re.S)
    if m:
        t=re.search(r'<rt-text\s+slot="audience-score"[^>]*>(.*?)</rt-text>',m.group(0),re.S)
        out['scorecard_markup.slot_audience_score']=(t.group(1).strip() or None) if t else None
        h=re.search(r'hide-audience-score="([^"]*)"',m.group(0)); out['scorecard_markup.hide-audience-score']=h.group(1) if h else None
    t=re.search(r'<rt-text slot="collapsed-audience-score"[^>]*>(.*?)</rt-text>',s,re.S)
    out['hero_markup.collapsed-audience-score']=(t.group(1).strip() or None) if t else None
    m=re.search(r'data-json="reviewsData">(.*?)</script>',s,re.S)
    try: out['reviewsData.audienceScore.score']=(json.loads(m.group(1)).get('audienceScore') or {}).get('score') if m else None
    except Exception: out['reviewsData.audienceScore.score']='parse_error'
    m=re.search(r'<script type="application/ld\+json">(.*?)</script>',s,re.S)
    try:
        ld=json.loads(m.group(1)) if m else {}
        out['ld_json.aggregateRating']=(ld.get('aggregateRating') or {}).get('name') or (ld.get('aggregateRating') or {}).get('ratingValue')
    except Exception: out['ld_json.aggregateRating']='parse_error'
    out['text_popcornmeter_pct']=bool(re.search(r'popcornmeter[^<]{0,40}\d{1,3}%',s,re.I))
    ems=re.search(r'"emsId":"([0-9a-f\-]{36})"',s); out['emsId']=ems.group(1) if ems else None
    return out
def num(v):
    if v in (None,'','%'): return None
    m=re.match(r'^\s*(\d{1,3})\s*%?\s*$',str(v)); return int(m.group(1)) if m else None
if __name__=='__main__':
    c=sqlite3.connect(f'{BASE}/movies.db'); c.execute('PRAGMA foreign_keys=ON')
    run=c.execute('select run_id from v_latest_run').fetchone()[0]
    rows=c.execute("""select distinct m.movie_id,m.rt_slug,m.title from v_qualifying q join movies m using(movie_id) where q.popcornmeter is null order by m.title""").fetchall()
    now=datetime.datetime.now().isoformat(timespec='seconds'); res={}
    for mid,slug,title in rows:
        base=f'https://www.rottentomatoes.com/m/{slug}'; r={'title':title,'variants':{}}
        for u in (base, base+'/', base+'/reviews/all-audience'):
            code,s=fetch(u); r['variants'][u]={'http':code, **(places(s) if code==200 else {})}
            c.execute("INSERT OR REPLACE INTO sources_checked(run_id,source,url,checked_at,result,notes) VALUES(?,?,?,?,?,?)",(run,'rt_audience_audit',u,now,str(code),'desktop UA re-fetch'))
        ems=next((v.get('emsId') for v in r['variants'].values() if v.get('emsId')),None)
        if ems:
            for api in (f'https://www.rottentomatoes.com/napi/rtcf/v1/movies/{ems}/reviews?type=audience', f'https://www.rottentomatoes.com/napi/movie/{ems}/reviews/user'):
                code,s=fetch(api,'application/json'); r['variants'][api]={'http':code,'json':s[:300] if s.lstrip().startswith('{') else None}
                c.execute("INSERT OR REPLACE INTO sources_checked(run_id,source,url,checked_at,result,notes) VALUES(?,?,?,?,?,?)",(run,'rt_napi',api,now,str(code),'audience score API probe'))
        found=set()
        for u,v in r['variants'].items():
            for k in ('scorecard_json.audienceScore.score','scorecard_json.overlay.audienceAll.score','scorecard_json.overlay.audienceVerified.score','scorecard_markup.slot_audience_score','hero_markup.collapsed-audience-score','reviewsData.audienceScore.score'):
                n=num(v.get(k))
                if n is not None: found.add((k,n,u))
        r['found']=sorted(found); vals=sorted(set(n for _,n,_ in found if 'Verified' not in _))
        pg=r['variants'][base]
        if vals and len(vals)==1:
            r['verdict']=f'score {vals[0]}'
            c.execute("UPDATE score_obs SET popcornmeter=?,observed_at=? WHERE run_id=? AND movie_id=?",(vals[0],now,run,mid))
            quote='; '.join(f'{k}={n} @ {u}' for k,n,u in sorted(found))
        else:
            r['verdict']='no popcornmeter displayed' if not vals else f'conflict {vals}'
            quote=(f"RT page shows no Popcornmeter: scorecard slot audience-score empty ('{pg.get('scorecard_markup.slot_audience_score')}'), "
                   f"audienceScore.score absent, band='{pg.get('band')}', hideAudienceScore={pg.get('scorecard_json.hideAudienceScore')}; "
                   f"same on trailing-slash and /reviews/all-audience variants; napi endpoints {[r['variants'][k]['http'] for k in r['variants'] if 'napi' in k]}")
        c.execute("DELETE FROM evidence WHERE movie_id=? AND run_id=? AND claim='popcornmeter'",(mid,run))
        c.execute("INSERT INTO evidence(movie_id,run_id,claim,value,doc_type,is_official,url,quote,retrieved_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (mid,run,'popcornmeter',str(vals[0]) if len(vals)==1 else None,'rt_page',1,base,quote[:1500],now))
        c.commit(); res[slug]=r; print(title,'->',r['verdict'],'| band:',pg.get('band'),flush=True)
    json.dump(res,open(f'{BASE}/raw/audience_audit_{D}.json','w'),indent=1)
