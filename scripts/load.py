#!/usr/bin/env python3
"""Stage 4: load raw JW catalog + IMDb + RT pages for a run date into movies.db (idempotent per run)."""
import json, glob, sys, os, re, datetime
sys.path.insert(0, os.path.dirname(__file__)); from common import *
D=sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()
c=connect(); c.executescript(open(os.path.join(BASE,'schema.sql')).read())
for code,name,dom in SERVICES:
    c.execute("INSERT INTO services(service_code,name,official_domain) VALUES(?,?,?) ON CONFLICT(service_code) DO UPDATE SET name=excluded.name, official_domain=excluded.official_domain, updated_at=CURRENT_TIMESTAMP",(code,name,dom))
for svc,pks in INCLUDED_PK.items():
    for pk in pks:
        n,k=PK_INFO[pk]
        c.execute("INSERT OR REPLACE INTO packages(package_code,service_code,source,clear_name,kind,counts_as_included,notes) VALUES(?,?,?,?,?,1,?)",(pk,svc,'justwatch',n,k,
          {'ppe':'Essential tier: some titles only on Premium; noted per title','pcp':'Premium Plus tier','ppp':'Premium tier','pct':'Premium tier'}.get(pk)))
c.execute("INSERT OR IGNORE INTO runs(run_date,scope,rules_version,notes) VALUES(?,?,?,?)",(D,'US; 10 services; movies first released 2025-2026','v1',
 'year=min(IMDb year, RT year); exclude IMDb types short/tvShort/tvSpecial/tvEpisode/tvSeries and runtime<=40 min; Tomatometer>=80'))
run=c.execute("SELECT run_id FROM runs WHERE run_date=?",(D,)).fetchone()[0]
# re-running a date replaces that run's discovery/score/JW/RT observations (official + reelgood checks are re-done by their own scripts)
for t in ('sightings','score_obs'): c.execute(f"DELETE FROM {t} WHERE run_id=?",(run,))
c.execute("DELETE FROM availability_obs WHERE run_id=? AND source IN ('justwatch','rt_where_to_watch')",(run,))
c.execute("DELETE FROM evidence WHERE run_id=? AND doc_type IN ('rt_page','imdb')",(run,))
imdb=json.load(open(f'{BASE}/raw/imdb_{D}.json')); match=json.load(open(f'{BASE}/raw/rt_match_{D}.json'))
pages=json.load(open(f'{BASE}/raw/rt_pages_{D}.json'))
man={k:v for k,v in json.load(open(f'{BASE}/overrides/rt_manual.json')).items() if not k.startswith('_')}
ov={k:v for k,v in json.load(open(f'{BASE}/overrides/movie_overrides.json')).items() if not k.startswith('_')} if os.path.exists(f'{BASE}/overrides/movie_overrides.json') else {}
now=datetime.datetime.now().isoformat(timespec='seconds')
def rt_year(p, mrow):
    if mrow and (mrow.get('year') or '').isdigit(): return int(mrow['year'])
    for v in [p['info'].get('Release Date (Theaters)'), p['info'].get('Release Date (Streaming)')]+(p.get('props') or []):
        m=re.search(r'(19|20)\d\d', v or '')
        if m: return int(m.group(0))
    return None
for f in sorted(glob.glob(f'{BASE}/raw/jw_*_{D}.json')):
    d=json.load(open(f)); svc=d['svc']
    c.execute("INSERT OR IGNORE INTO sources_checked(run_id,source,url,checked_at,result,notes) VALUES(?,?,?,?,?,?)",(run,'justwatch_graphql_catalog',
      f"https://apis.justwatch.com/graphql popularTitles(US, packages={d['packages']}, MOVIE, releaseYear 2025-2026, FLATRATE)",D,f"{len(d['nodes'])} titles",None))
    for x in d['nodes']:
        ct=x['content']; jid=x['id']; im=imdb.get(ct['externalIds']['imdbId'] or '') or {}
        mrow=(match.get(jid) or {}).get('match')
        key=jid if jid in man else ct['title']
        url=('https://www.rottentomatoes.com/m/'+man[key]) if key in man else (mrow or {}).get('url')
        p=pages.get(url) if url else None
        mid=None
        if url and p and p.get('http')==200:
            slug=url.split('/m/')[1]
            ry=rt_year(p, mrow if key not in man else None)
            iy=im.get('y'); years=[y for y in (iy,ry) if y]
            year=min(years) if years else ct['originalReleaseYear']
            note=None
            ys={k:v for k,v in (('IMDb',iy),('RT',ry),('JustWatch',ct['originalReleaseYear'])) if v}
            if len(set(ys.values()))>1: note='years differ: '+', '.join(f'{k} {v}' for k,v in ys.items())
            rtm=runtime_min(p['info'].get('Runtime')) or ct.get('runtime')
            itype=im.get('qid')
            excl=None
            if itype in ('short','tvShort'): excl='short film (IMDb type %s)'%itype
            elif itype in ('tvSpecial',): excl='TV special (stand-up/concert/live broadcast), not a film'
            elif itype in ('tvEpisode','tvSeries','tvMiniSeries'): excl='TV series/episode'
            elif rtm is not None and rtm<=40: excl='short film (runtime %d min)'%rtm
            elif year not in (2025,2026): excl='first released %s (before 2025)'%year
            o=ov.get(slug,{})
            if 'exclude_reason' in o: excl=o['exclude_reason']
            ptitle=(p.get('title') or ct['title']).strip()
            c.execute("""INSERT INTO movies(rt_slug,title,original_title,release_year,imdb_year,rt_year,jw_year,year_note,imdb_id,imdb_type,jw_id,tmdb_id,
                runtime_min,rt_genres,original_language,countries,content_rating,exclude_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(rt_slug) DO UPDATE SET title=excluded.title, release_year=excluded.release_year, imdb_year=excluded.imdb_year, rt_year=excluded.rt_year,
                jw_year=excluded.jw_year, year_note=excluded.year_note, imdb_id=COALESCE(excluded.imdb_id,imdb_id), imdb_type=COALESCE(excluded.imdb_type,imdb_type),
                jw_id=excluded.jw_id, tmdb_id=excluded.tmdb_id, runtime_min=excluded.runtime_min, rt_genres=excluded.rt_genres, original_language=excluded.original_language,
                countries=excluded.countries, content_rating=excluded.content_rating, exclude_reason=excluded.exclude_reason, updated_at=CURRENT_TIMESTAMP""",
                (slug,ptitle,ct['title'],year,iy,ry,ct['originalReleaseYear'],note,ct['externalIds']['imdbId'],itype,jid,ct['externalIds']['tmdbId'],
                 rtm,', '.join(p.get('genres') or []),re.sub(r'^e ','',(p['info'].get('Original Language') or '')).split(' (')[0] or None,','.join(ct.get('productionCountries') or []),
                 p.get('ld_rating') or ct.get('ageCertification'),excl))
            mid=c.execute("SELECT movie_id FROM movies WHERE rt_slug=?",(slug,)).fetchone()[0]
            for k in ('genre_label','kid_friendly','is_documentary','is_international','notes'):
                if k in o: c.execute(f"UPDATE movies SET {k}=? WHERE movie_id=?",(o[k],mid))
            # scores
            c.execute("""INSERT OR REPLACE INTO score_obs(run_id,movie_id,tomatometer,critic_reviews,critic_avg,certified_fresh,popcornmeter,audience_band,audience_reviews,audience_ratings,url,http_status,observed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(run,mid,p['tomatometer'],p['critic_reviews'],p['critic_avg'],1 if p['certified_fresh'] else 0,
                 None if p.get('hide_audience') else p['popcorn'],p['audience_band'],p['audience_reviews'],
                 (p['audience_liked'] or 0)+(p['audience_notliked'] or 0) if p['audience_liked'] is not None else None,url,200,p['retrieved_at']))
            if p['tomatometer'] is not None:
                c.execute("INSERT OR REPLACE INTO evidence(movie_id,run_id,claim,value,doc_type,is_official,url,quote,retrieved_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (mid,run,'tomatometer',str(p['tomatometer']),'rt_page',1,url,f"criticsScore.score={p['tomatometer']} reviewCount={p['critic_reviews']}",p['retrieved_at']))
                c.execute("INSERT OR REPLACE INTO evidence(movie_id,run_id,claim,value,doc_type,is_official,url,quote,retrieved_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (mid,run,'popcornmeter',str(p['popcorn']) if p['popcorn'] is not None else None,'rt_page',1,url,f"audienceScore.score={p['popcorn']} band='{p['audience_band']}'",p['retrieved_at']))
            c.execute("INSERT OR REPLACE INTO evidence(movie_id,run_id,claim,value,doc_type,is_official,url,quote,retrieved_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (mid,run,'release_year',str(year),'imdb',0,f"https://www.imdb.com/title/{ct['externalIds']['imdbId']}/",note or f'IMDb {iy}; RT {ry}',now))
            # RT where-to-watch (subscription list parsed from affiliatesText)
            txt=(p.get('wtw') or {}).get('affiliatesText') or ''
            m=re.search(r'with a subscription on (.+?)(?:, rent|, buy|, or buy|\.|$)',txt)
            subs=[s.strip() for s in re.split(r',| or ',m.group(1)) if s.strip()] if m else []
            for s in subs:
                sc=RT_WTW_NAMES.get(s)
                if sc: c.execute("INSERT OR REPLACE INTO availability_obs(run_id,movie_id,service_code,source,offer_type,package,url,http_status,detail,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (run,mid,sc,'rt_where_to_watch','included',s,url,200,txt[:300],p['retrieved_at']))
        # sightings + JW availability
        c.execute("INSERT OR IGNORE INTO sightings(run_id,service_code,movie_id,source,raw_title,raw_year,jw_id,url,seen_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (run,svc,mid,'justwatch_catalog',ct['title'],ct['originalReleaseYear'],jid,'https://www.justwatch.com'+(ct['fullPath'] or ''),D))
        if mid:
            for o in x['offers']:
                pk=o['package']['shortName']; mt=o['monetizationType']
                if pk in INCLUDED_PK[svc] and mt=='FLATRATE': ot='included'
                elif svc=='prime' and 'Amazon Channel' in (o['package']['clearName'] or '') and mt=='FLATRATE': ot='channel_addon'
                elif pk in INCLUDED_PK[svc] and mt=='ADS': ot='free_ads'
                else: continue
                c.execute("INSERT OR IGNORE INTO availability_obs(run_id,movie_id,service_code,source,offer_type,package,url,http_status,detail,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (run,mid,svc,'justwatch',ot,o['package']['clearName'],o['standardWebURL'],None,
                     f"monetizationType={mt}; availableTo={o.get('availableToTime')}; availableFrom={o.get('availableFromTime')}",D))
po={k:v for k,v in json.load(open(f'{BASE}/overrides/pair_overrides.json')).items() if not k.startswith('_')}
c.execute("DELETE FROM availability_obs WHERE run_id=? AND source='manual'",(run,))
for k,v in po.items():
    slug,svc=k.split('|'); r=c.execute("SELECT movie_id FROM movies WHERE rt_slug=?",(slug,)).fetchone()
    if r: c.execute("INSERT OR REPLACE INTO availability_obs(run_id,movie_id,service_code,source,offer_type,detail,observed_at) VALUES(?,?,?,?,?,?,?)",(run,r[0],svc,'manual',v['offer_type'],v['detail'],now))
c.commit()
print('movies',c.execute('select count(*) from movies').fetchone()[0],'scores',c.execute('select count(*) from score_obs where run_id=?',(run,)).fetchone()[0])
