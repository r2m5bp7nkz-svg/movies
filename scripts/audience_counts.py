#!/usr/bin/env python3
"""Rule r3 (2026-10-25): a main-table movie needs >= 250 RT audience ratings, i.e. the rating-count bucket RT displays next to
the shown Popcornmeter must be "250+ Ratings" (or "250+ Verified Ratings") or a higher bucket.
For every movie that passes the r2 rules on ANY service (v_main_r2), re-fetch its RT page fresh and read the count shown
alongside the Popcornmeter in two places that must agree:
  1. visible markup: <media-scorecard> ... <rt-link slot="audience-reviews">250+ Ratings</rt-link>
  2. media-scorecard-json audienceScore.bandedRatingCount (the displayed audience score: verified if RT shows verified, else all)
Writes audience_count_obs (+ evidence claim='audience_rating_count', sources_checked). Counts are never estimated:
if the bucket can't be read (fetch failure, markup/JSON disagree, unparseable), status='unreadable', band_min=NULL and the movie
is flagged 'audience_count_unreadable' and left out of the main tables.
Cache reuse: a movie with an 'ok' observation checked within CACHE_DAYS (7) is not re-fetched; that observation is copied into the
current run with reused_from_obs_id set (same band, url and original observed_at). Pages themselves go through rt_lib.get(), which
reuses any <7-day-old capture logged in fetch_cache. `--refresh` (or MOVIES_REFRESH=1) forces live fetches for both."""
import sys, os, re, json, html, datetime, sqlite3, hashlib, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__)); from rt_lib import get, scr, BASE, REFRESH, CACHE_DAYS, STATS, parse_movie
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
def band_min(b):
    if not b: return None
    b=b.strip()
    if re.match(r'^(Fewer than \d|0 )',b): return 0
    m=re.match(r'^([\d,]+)\+\s+(Verified\s+)?Ratings$',b)
    return int(m.group(1).replace(',','')) if m else None
def read(slug):
    url=f'https://www.rottentomatoes.com/m/{slug}'
    code,s=get(url, f'{BASE}/raw/rt_counts_{D}')
    r={'url':url,'http':code,'retrieved_at':datetime.datetime.now().isoformat(timespec='seconds')}
    if code!=200: r['status']='unreadable'; r['reason']=f'HTTP {code}'; return r
    sc=scr(s,'media-scorecard-json') or {}; au=sc.get('audienceScore') or {}
    r['json_band']=au.get('bandedRatingCount'); r['json_score']=au.get('score'); r['hide']=sc.get('hideAudienceScore')
    pm=parse_movie(s); r['tomatometer_seen']=pm['tomatometer']; r['critic_reviews_seen']=pm['critic_reviews']
    r['verified_shown']=bool(r['json_band'] and 'Verified' in r['json_band'])
    m=re.search(r'<media-scorecard\b.*?</media-scorecard>',s,re.S); blk=m.group(0) if m else ''
    t=re.search(r'<rt-link\s+slot="audience-reviews"[^>]*>(.*?)</rt-link>',blk,re.S)
    r['markup_band']=html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',t.group(1)))).strip() if t else None
    t=re.search(r'<rt-text\s+slot="audience-score"[^>]*>(.*?)</rt-text>',blk,re.S)
    r['markup_score']=re.sub(r'\s+','',t.group(1)) if t else None
    jb,mb=r['json_band'],r['markup_band']
    if not mb and not jb: r['status']='unreadable'; r['reason']='no rating-count text found'
    elif mb and jb and mb!=jb: r['status']='unreadable'; r['reason']=f'markup {mb!r} != json {jb!r}'
    else:
        b=mb or jb; bm=band_min(b)
        if bm is None: r['status']='unreadable'; r['reason']=f'unparseable bucket {b!r}'
        else: r['status']='ok'; r['band']=b; r['band_min']=bm; r['source']='markup+json' if (mb and jb) else ('markup' if mb else 'json')
    return r
if __name__=='__main__':
    c=sqlite3.connect(f'{BASE}/movies.db'); c.execute('PRAGMA foreign_keys=ON')
    run=c.execute('select run_id from v_latest_run').fetchone()[0]
    rows=c.execute("select distinct m.movie_id,m.rt_slug,m.title,q.popcornmeter from v_main_r2 q join movies m using(movie_id) order by m.title").fetchall()
    cut=(datetime.datetime.now()-datetime.timedelta(days=CACHE_DAYS)).isoformat(timespec='seconds')
    cols='band,band_min,verified_shown,popcornmeter_seen,markup_band,json_band,tomatometer_seen,critic_reviews_seen,status,detail,url,http_status,observed_at'
    def recent(mid):
        if REFRESH: return None
        r=c.execute(f"SELECT obs_id,{cols} FROM audience_count_obs WHERE movie_id=? AND status='ok' AND observed_at>=? ORDER BY observed_at DESC LIMIT 1",(mid,cut)).fetchone()
        return r
    reused={}; todo=[]
    for x in rows:
        r=recent(x[0])
        if r: reused[x[0]]=r
        else: todo.append(x)
    with cf.ThreadPoolExecutor(4) as ex: fetched=dict(zip([x[0] for x in todo], ex.map(lambda x: read(x[1]), todo)))
    res=[]
    for x in rows:
        if x[0] in fetched: res.append(fetched[x[0]]); continue
        r=dict(zip(['obs_id']+cols.split(','),reused[x[0]]))
        res.append({'url':r['url'],'http':r['http_status'],'retrieved_at':r['observed_at'],'status':'ok','band':r['band'],'band_min':r['band_min'],
                    'verified_shown':r['verified_shown'],'json_score':r['popcornmeter_seen'],'markup_band':r['markup_band'],'json_band':r['json_band'],
                    'tomatometer_seen':r['tomatometer_seen'],'critic_reviews_seen':r['critic_reviews_seen'],'reason':None,'source':'markup+json',
                    'reused_from':r['obs_id'],'reused_detail':r['detail']})
    out={}
    c.execute("DELETE FROM flags WHERE run_id=? AND flag_type='audience_count_unreadable'",(run,))
    for (mid,slug,title,pm),r in zip(rows,res):
        r['title']=title; r['db_popcornmeter']=pm; out[slug]=r
        if r.get('reused_from'):
            src=c.execute("SELECT run_id FROM audience_count_obs WHERE obs_id=?",(r['reused_from'],)).fetchone()[0]
            if src==run: continue          # this run's own recent observation: keep it (and its evidence) as is
        c.execute("""INSERT OR REPLACE INTO audience_count_obs(run_id,movie_id,band,band_min,verified_shown,popcornmeter_seen,markup_band,json_band,tomatometer_seen,critic_reviews_seen,reused_from_obs_id,status,detail,url,http_status,observed_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(run,mid,r.get('band'),r.get('band_min'),1 if r.get('verified_shown') else 0,r.get('json_score'),
          r.get('markup_band'),r.get('json_band'),r.get('tomatometer_seen'),r.get('critic_reviews_seen'),r.get('reused_from'),r['status'],
          (f"reused obs {r['reused_from']} ({r['reused_detail']})" if r.get('reused_from') else None) or r.get('reason') or f"read from {r.get('source')}",r['url'],r['http'],r['retrieved_at']))
        c.execute("INSERT OR REPLACE INTO evidence(movie_id,run_id,claim,value,doc_type,is_official,url,quote,retrieved_at) VALUES(?,?,?,?,?,?,?,?,?)",
          (mid,run,'audience_rating_count',r.get('band'),'rt_page',1,r['url'],
           f"<rt-link slot=\"audience-reviews\">{r.get('markup_band')}</rt-link>; audienceScore.bandedRatingCount='{r.get('json_band')}'; audienceScore.score={r.get('json_score')}"+('' if r['status']=='ok' else f"; UNREADABLE: {r.get('reason')}"),r['retrieved_at']))
        c.execute("INSERT OR REPLACE INTO sources_checked(run_id,source,url,checked_at,result,notes) VALUES(?,?,?,?,?,?)",(run,'rt_audience_count',r['url'],r['retrieved_at'],str(r['http']),r['status']))
        if r['status']!='ok':
            c.execute("INSERT OR REPLACE INTO flags(run_id,movie_id,service_code,flag_type,detail) VALUES(?,?,NULL,'audience_count_unreadable',?)",(run,mid,r.get('reason')))
    c.commit()
    json.dump(out,open(f'{BASE}/raw/audience_counts_{D}.json','w'),indent=1)
    import collections
    print('reused observations:',len(reused),'| fetched:',len(todo),'| page fetches live/cache:',STATS['live'],STATS['cache'])
    print(len(out), collections.Counter(r['status'] for r in out.values()), sum(1 for r in out.values() if (r.get('band_min') or 0)>=250),'>=250')
    for r in out.values():
        if r['status']!='ok': print('UNREADABLE',r['title'],r.get('reason'))
        elif r.get('json_score') is not None and str(r['json_score'])!=str(r['db_popcornmeter']): print('POPCORN CHANGED',r['title'],r['db_popcornmeter'],'->',r['json_score'])
