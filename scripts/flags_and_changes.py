#!/usr/bin/env python3
"""Stage 7: compute flags for qualifying (movie, service) pairs and change_events vs the previous run."""
import sys, os, re, datetime
from zoneinfo import ZoneInfo
LA=ZoneInfo('America/Los_Angeles')
sys.path.insert(0, os.path.dirname(__file__)); from common import *
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
c=connect(); run=c.execute("SELECT run_id FROM runs WHERE run_date=?",(D,)).fetchone()[0]
c.execute("DELETE FROM flags WHERE run_id=?",(run,))
def flag(mid,svc,t,d): c.execute("INSERT OR REPLACE INTO flags(run_id,movie_id,service_code,flag_type,detail) VALUES(?,?,?,?,?)",(run,mid,svc,t,d))
Q=c.execute("SELECT q.*, m.year_note FROM v_qualifying q JOIN movies m USING(movie_id)").fetchall()
for q in Q:
    mid,svc=q['movie_id'],q['service_code']
    if (q['critic_reviews'] or 0)<20: flag(mid,svc,'few_critic_reviews',f"Tomatometer based on {q['critic_reviews']} reviews")
    b=q['audience_band'] or ''
    if q['popcornmeter'] is not None and re.match(r'^(50\+|Fewer)',b): flag(mid,svc,'few_audience_ratings',f"Popcornmeter from '{b}'")
    if q['year_note']: flag(mid,svc,'year_conflict',q['year_note']+f" -> using {q['release_year']} (earliest of IMDb/RT)")
    av={(r['source'],r['offer_type']):r['detail'] for r in c.execute("SELECT source,offer_type,detail FROM availability_obs WHERE run_id=? AND movie_id=? AND service_code=?",(run,mid,svc))}
    rg=c.execute("SELECT reelgood_slug FROM movies WHERE movie_id=?",(mid,)).fetchone()[0]
    rg_shared=rg and c.execute("SELECT COUNT(*) FROM movies WHERE reelgood_slug=?",(rg,)).fetchone()[0]>1
    if ('reelgood','not_listed') in av and rg_shared: flag(mid,svc,'availability_conflict',f'Reelgood search resolved to a different same-titled film ({rg}), so there is no usable Reelgood cross-check; JustWatch + the service page agree it is included')
    elif ('reelgood','not_listed') in av: flag(mid,svc,'availability_conflict','Reelgood does not list it as subscription here ('+av[('reelgood','not_listed')]+'); JustWatch + service page do')
    if q['basis']!='official+justwatch': flag(mid,svc,'official_unverified',q['basis'])
    if not any(s=='rt_where_to_watch' for s,_ in av): pass
    pk=[r[0] for r in c.execute("SELECT DISTINCT package FROM availability_obs WHERE run_id=? AND movie_id=? AND service_code=? AND source='justwatch' AND offer_type='included'",(run,mid,svc))]
    if svc=='paramount' and pk and all('Premium' in p for p in pk): flag(mid,svc,'tier_note','JustWatch lists it only on Paramount+ Premium (not Essential)')
    if svc=='peacock' and pk and all('Plus' in p for p in pk): flag(mid,svc,'tier_note','JustWatch lists it only on Peacock Premium Plus')
    for r in c.execute("SELECT detail FROM availability_obs WHERE run_id=? AND movie_id=? AND service_code=? AND source='justwatch' AND offer_type='included' AND detail LIKE '%availableTo=2%'",(run,mid,svc)):
        m=re.search(r'availableTo=(\S+?)Z',r[0]); end=datetime.datetime.fromisoformat(m.group(1)).replace(tzinfo=datetime.timezone.utc).astimezone(LA)
        if (end.date()-datetime.date.fromisoformat(D)).days<=45: flag(mid,svc,'leaving_soon',f'JustWatch: leaves {end:%b %-d, %Y} (PT)')
        break
    if svc=='disney' and c.execute("SELECT 1 FROM availability_obs WHERE run_id=? AND movie_id=? AND service_code='hulu' AND source='justwatch' AND offer_type='included'",(run,mid)).fetchone():
        flag(mid,svc,'availability_conflict','Also listed on Hulu; JustWatch and the Disney+ title page list it in Disney+\'s own catalog')
# change events vs previous run
prev=c.execute("SELECT MAX(run_id) FROM runs WHERE run_id<?",(run,)).fetchone()[0]
c.execute("DELETE FROM change_events WHERE run_id=?",(run,))
now=datetime.datetime.now().isoformat(timespec='seconds')
if prev:
    cur={(r[0],r[1]) for r in c.execute("SELECT movie_id,service_code FROM availability_obs WHERE run_id=? AND source='justwatch' AND offer_type='included'",(run,))}
    old={(r[0],r[1]) for r in c.execute("SELECT movie_id,service_code FROM availability_obs WHERE run_id=? AND source='justwatch' AND offer_type='included'",(prev,))}
    for m,s in cur-old: c.execute("INSERT OR IGNORE INTO change_events(run_id,prev_run_id,movie_id,service_code,event_type,detected_at) VALUES(?,?,?,?,?,?)",(run,prev,m,s,'availability_added',now))
    for m,s in old-cur: c.execute("INSERT OR IGNORE INTO change_events(run_id,prev_run_id,movie_id,service_code,event_type,detected_at) VALUES(?,?,?,?,?,?)",(run,prev,m,s,'availability_removed',now))
    for r in c.execute("SELECT a.movie_id,a.tomatometer,b.tomatometer,a.popcornmeter,b.popcornmeter FROM score_obs a JOIN score_obs b ON a.movie_id=b.movie_id AND b.run_id=? WHERE a.run_id=? AND (a.tomatometer IS NOT b.tomatometer OR a.popcornmeter IS NOT b.popcornmeter)",(prev,run)).fetchall():
        c.execute("INSERT OR IGNORE INTO change_events(run_id,prev_run_id,movie_id,event_type,old_value,new_value,detected_at) VALUES(?,?,?,?,?,?,?)",(run,prev,r[0],'score_change',f'{r[2]}/{r[4]}',f'{r[1]}/{r[3]}',now))
    # qualifier churn uses top-10 snapshot stored in notes of runs? compare v_qualifying is latest-only, so recompute old via score/avail would need history; keep added/removed + score events.
else:
    c.execute("UPDATE runs SET notes=COALESCE(notes,'')||' | first run: no previous run to diff' WHERE run_id=? AND notes NOT LIKE '%first run%'",(run,))
c.commit()
for r in c.execute("SELECT flag_type,count(*) FROM flags WHERE run_id=? GROUP BY 1",(run,)): print(tuple(r))
print('change_events',c.execute("SELECT count(*) FROM change_events WHERE run_id=?",(run,)).fetchone()[0])
