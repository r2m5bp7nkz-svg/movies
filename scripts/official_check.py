#!/usr/bin/env python3
"""Stage 5: check each candidate (movie, service) on the service's OWN public title page (URL taken from the JustWatch offer).
Candidates = eligible films (2025/2026, not short/special) with Tomatometer>=80 that JustWatch or RT lists as included on the service.
Writes availability_obs(source='official'). Page HTML cached in raw/official_<date>/."""
import sys, os, re, json, html, datetime, time, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__)); from common import *; from rt_lib import get, norm
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
c=connect(); run=c.execute("SELECT run_id FROM runs WHERE run_date=?",(D,)).fetchone()[0]
pairs=c.execute("""SELECT DISTINCT m.movie_id, m.title, m.original_title, a.service_code FROM availability_obs a JOIN movies m USING(movie_id) JOIN score_obs s ON s.movie_id=m.movie_id AND s.run_id=a.run_id
 WHERE a.run_id=? AND a.offer_type='included' AND a.source IN ('justwatch','rt_where_to_watch') AND m.exclude_reason IS NULL AND m.release_year IN (2025,2026) AND s.tomatometer>=80""",(run,)).fetchall()
URLS={}
for r in c.execute("SELECT movie_id,service_code,url FROM availability_obs WHERE run_id=? AND source='justwatch' AND offer_type='included' AND url IS NOT NULL ORDER BY length(url) DESC",(run,)):
    URLS[(r[0],r[1])]=r[2]
def jw_url(mid,svc):
    return URLS.get((mid,svc))
def _unused(mid,svc):
    r=c.execute("SELECT url FROM availability_obs WHERE run_id=? AND movie_id=? AND service_code=? AND source='justwatch' AND offer_type='included' AND url IS NOT NULL ORDER BY length(url) LIMIT 1",(run,mid,svc)).fetchone()
    return r[0] if r else None
def fix(svc,u):
    if svc=='peacock': u=u.replace('/watch/asset/movies/','/watch-online/movies/')
    if svc=='hbomax': u=u.split('?')[0]
    return u
def titles_in(s, titles):
    S=norm(re.sub(r'<[^>]+>',' ',s))
    return any(norm(t) and norm(t) in S for t in titles if t)
def judge(svc, s, titles):
    tt=(re.search(r'<title[^>]*>(.*?)</title>',s,re.S) or [None,''])[1]; tt=html.unescape(tt).strip()
    found=titles_in(tt,titles) or titles_in(s,titles) or titles_in(s,[' '.join(norm(t).split()[:3]) for t in titles if t and len(norm(t).split())>=3])
    if not found: return 'not_listed', f'title not found on page; <title>={tt[:80]!r}'
    low=s.lower()
    if svc=='prime':
        m=re.search(r'data-testid="entitlement-message"[^>]*>([^<]+)<',s)
        msg=html.unescape(m.group(1)) if m else ''
        if re.search(r'(Subscribe to Prime|Included with (Amazon )?Prime|Watch with Prime|Prime membership|free Prime trial|Join Prime)',msg): return 'included', 'entitlement-message: '+msg
        if re.search(r'^(Subscribe to|Start your free trial of|Watch with) ',msg) and 'Prime' not in msg: return 'channel_addon', 'entitlement-message: '+msg
        if re.search(r'(Free trial of|Subscribe to) ',msg): return 'channel_addon', 'entitlement-message: '+msg
        if re.search(r'^Watch for free',msg): return 'free_ads', 'entitlement-message: '+msg+' (free with ads, not a Prime-membership entitlement)'
        if re.search(r'(Rent|Buy|rent|buy)',msg): return 'rent', 'entitlement-message: '+msg
        return 'unknown', 'entitlement-message: '+(msg or 'none found')
    if svc=='appletv':
        if re.search(r'(Accept Free Trial|days free, then \$[\d.]+/month|Watch with Apple TV|Apple TV\+? subscription)',s): return 'included','Apple TV subscription offer on page (free trial / monthly price)'
        if re.search(r'\b(Buy|Rent) \$\d',s): return 'rent','only buy/rent prices found'
        return 'unknown','no subscription marker'
    if svc=='peacock':
        if re.search(r'You can watch .{1,200}? on Peacock',s): return 'included','"You can watch … on Peacock"'
        return 'unknown','title present, no Peacock watch statement'
    if svc=='hbomax':
        if re.search(r'Coming Soon',s) and not re.search(r'Now Streaming',s): return 'coming_soon','Coming Soon on page'
        return 'included','title page live: '+tt[:80]
    if svc=='disney':
        hulu = bool(re.search(r'(Hulu on Disney\+|with Hulu|Disney\+, Hulu)',s))
        return 'included','title page live: '+tt[:80]+('; page mentions Hulu bundle' if hulu else '')
    if svc=='netflix':
        m=re.search(r'"availabilityStartTime"\s*:\s*"([^"]+)"',s)
        if m and m.group(1)[:10]>D: return 'coming_soon','availabilityStartTime '+m.group(1)
        return 'included','title page live'+(f' (availabilityStartTime {m.group(1)[:10]})' if m else '')
    if svc=='paramount':
        prem = bool(re.search(r'(Paramount\+ (with SHOWTIME|Premium) (only|required)|Premium plan)',s))
        return 'included','title page live: '+tt[:80]+('; mentions Premium' if prem else '')
    return 'included','title page live: '+tt[:80]
def work(p):
    mid,t,ot,svc=p; u=jw_url(mid,svc)
    if not u: return p,None,None,'unreachable','no service URL (not listed by JustWatch for this service)'
    u=fix(svc,u); code,s=get(u, f'{BASE}/raw/official_{D}')
    tries=0
    while svc=='prime' and code==200 and len(s)<20000 and 'Continue shopping' in s and tries<1:   # Amazon bot interstitial: back off and retry
        time.sleep(3); tries+=1; code,s=get(u, f'{BASE}/raw/official_{D}', refresh=True)
    if svc=='prime' and 'Continue shopping' in s and len(s)<20000 and 'gti=' in u:   # fall back to the primevideo.com detail page for the same GTI
        u='https://www.primevideo.com/detail/'+u.split('gti=')[1].split('&')[0]; code,s=get(u, f'{BASE}/raw/official_{D}')
    if svc=='prime' and 'Continue shopping' in s and len(s)<20000: return p,u,code,'unreachable','Amazon bot-check interstitial after retries'
    if code!=200: return p,u,code,'unreachable' if code<0 or code>=500 or code==403 else 'not_listed', f'HTTP {code}'
    ot_,det=judge(svc,s,[t,ot]); return p,u,code,ot_,det
c.execute("DELETE FROM availability_obs WHERE run_id=? AND source='official'",(run,))
now=datetime.datetime.now().isoformat(timespec='seconds')
with cf.ThreadPoolExecutor(3) as ex:
    for p,u,code,ot_,det in ex.map(work,pairs):
        c.execute("INSERT OR REPLACE INTO availability_obs(run_id,movie_id,service_code,source,offer_type,package,url,http_status,detail,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
          (run,p[0],p[3],'official',ot_,None,u,code,det,now))
        if u: c.execute("INSERT OR IGNORE INTO sources_checked(run_id,source,url,checked_at,result) VALUES(?,?,?,?,?)",(run,'official:'+p[3],u,now,f'{code} {ot_}'))
c.commit()
for r in c.execute("SELECT service_code,offer_type,count(*) FROM availability_obs WHERE run_id=? AND source='official' GROUP BY 1,2",(run,)): print(tuple(r))
