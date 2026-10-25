#!/usr/bin/env python3
"""Regenerate report.html + report.md from movies.db (latest run). No network access."""
import sys, os, json, html, datetime
sys.path.insert(0, os.path.dirname(__file__)); from common import *
c=connect()
run=c.execute("SELECT * FROM runs ORDER BY run_id DESC LIMIT 1").fetchone()
D=run['run_date']; R=run['run_id']
AC=c.execute("SELECT MAX(substr(observed_at,1,10)) FROM audience_count_obs WHERE run_id=?",(R,)).fetchone()[0]
CHK=f"{datetime.date.fromisoformat(D):%A, %B %-d, %Y}"+(f"; RT audience rating counts re-checked {datetime.date.fromisoformat(AC):%A, %B %-d, %Y}" if AC and AC!=D else "")
svcs=[(r['service_code'],r['name']) for r in c.execute("SELECT * FROM services")]
order=[s for s,_,_ in SERVICES]; svcs.sort(key=lambda x:order.index(x[0]))
FLAG_SYM={'few_critic_reviews':'†','few_audience_ratings':'‡','availability_conflict':'⚠','year_conflict':'ʸ','tier_note':'◆','leaving_soon':'⏳','official_unverified':'?'}
def flags(mid,svc): return c.execute("SELECT flag_type,detail FROM flags WHERE run_id=? AND movie_id=? AND service_code=?",(R,mid,svc)).fetchall()
def cap(t): return (t[:1].upper()+t[1:]) if t else t
def pct(v): return '—' if v is None else f'{v}%'
def rows(view,svc): return c.execute(f"SELECT t.*, m.kid_friendly, m.rt_genres FROM {view} t JOIN movies m USING(movie_id) WHERE service_code=? ORDER BY rnk",(svc,)).fetchall()
FLAG_SYM['few_imdb_votes']='ⁱ'
def imdb(mid):
    r=c.execute("SELECT rating,votes,imdb_url FROM v_latest_imdb WHERE movie_id=?",(mid,)).fetchone()
    if not r or r['rating'] is None: return '—', False
    return f"{r['rating']:.1f} ({r['votes']:,})", r['votes']<1000
RULE=("A movie makes a service's main table only if its Rotten Tomatoes Tomatometer is at least 80%, its Popcornmeter is at least 80% (and RT actually displays one), "
      "it has at least 20 critic reviews, and it has at least 250 RT audience ratings (RT shows \"250+ Ratings\" or a higher bucket, verified or all-audience, whichever RT displays with the Popcornmeter). Tables are ranked by Tomatometer, ties broken by Popcornmeter, then by critic review count. "
      "Movies that clear 80% with critics but have fewer than 20 reviews, or that have no Popcornmeter yet, or fewer than 250 audience ratings, are listed separately under each table and are not ranked in it. "
      "IMDb ratings (out of 10, vote count in parentheses) are for information only and are never used as a filter.")
FL=("Flags: ‡ Popcornmeter from only 50–99 ratings · † fewer than 20 critic reviews (side lists only) · ʸ sources disagree on the year · ◆ plan-tier note · "
    "⏳ leaving within 45 days · ⚠ availability note · ⁱ IMDb rating from fewer than 1,000 votes.")
md=[f"# Movies (first released 2025–2026) included with US streaming subscriptions\n\n**Date checked: {CHK}** (America/Los_Angeles). Generated from `movies.db` run {R}.\n",
    RULE+" Critics/Audience are Tomatometer/Popcornmeter as read from each movie's own RT page, with critic review counts in parentheses.\n", FL+"\n"]
H=[]
H.append(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Streaming movies 2025–2026 · checked {D}</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1150px;margin:24px auto;padding:0 16px;color:#1d1d1f;line-height:1.45}}
h1{{font-size:1.6em}} h2{{margin-top:2em;border-bottom:2px solid #eee;padding-bottom:4px}} h3{{font-size:1em;margin:14px 0 4px;color:#444}} table{{border-collapse:collapse;width:100%;font-size:.93em}}
th,td{{border:1px solid #e3e3e3;padding:5px 8px;text-align:left;vertical-align:top}} th{{background:#f6f6f6}} td.n{{text-align:right;white-space:nowrap}}
table.side{{font-size:.85em;color:#333}} .flag{{color:#b45309;font-size:.85em}} .kid{{background:#e8f7ee;border-radius:4px;padding:0 4px;font-size:.8em;color:#166534}}
.note{{background:#fff8e6;border-left:4px solid #f0b429;padding:8px 12px;margin:10px 0}} details{{margin:8px 0}} small{{color:#666}}
</style></head><body>
<h1>Movies first released in 2025–2026 that are included with US streaming subscriptions</h1>
<p><b>Date checked: {CHK}</b> (America/Los_Angeles) · for Emil Frojd (Mountain View, CA) · generated from <code>movies.db</code> (run {R}).</p>
<div class="note"><b>How to read this:</b> {html.escape(RULE)}
Both RT scores were read from each movie's own RT page today; where the Popcornmeter is missing, RT's page really shows none (checked in the scorecard markup, the embedded JSON and the audience-reviews page).
Availability required two things: JustWatch lists the movie as included with the subscription (FLATRATE on the service's own package) <i>and</i> the service's own public title page confirms it. Reelgood and RT's "where to watch" were used as further cross-checks.
Rentals, purchases, Amazon Channels, free-with-ads, and Hulu-in-Disney+ bundle access are excluded.<br>{html.escape(FL)} <span class="kid">kids</span> marks titles suitable for young kids.</div>""")
def symfl(mid,svc):
    fl=flags(mid,svc); return fl,''.join(FLAG_SYM[f[0]] for f in fl if f[0] in FLAG_SYM)
def mdrow(r,svc,num):
    fl,sym=symfl(r['movie_id'],svc); im,low=imdb(r['movie_id']); url='https://www.rottentomatoes.com/m/'+r['rt_slug']
    return f"| {num} | [{r['title']}]({url}){(' '+sym) if sym else ''} | {r['release_year']} | {r['tomatometer']}% ({r['critic_reviews']}) | {pct(r['popcornmeter'])} | {im}{' ⁱ' if low else ''} | {cap(r['genre_label']) or ''} |"
def hrow(r,svc,num,side=False):
    fl,sym=symfl(r['movie_id'],svc); im,low=imdb(r['movie_id']); url='https://www.rottentomatoes.com/m/'+r['rt_slug']
    kid=f' <span class="kid">kids: {html.escape(r["kid_friendly"])}</span>' if r['kid_friendly'] and not side else ''
    return (f"<tr><td class=n>{num}</td><td><a href='{url}'>{html.escape(r['title'])}</a>{kid}</td><td>{r['release_year']}</td><td class=n>{r['tomatometer']}% <small>({r['critic_reviews']} reviews)</small></td>"
            f"<td class=n>{pct(r['popcornmeter'])} <small>{html.escape(r['audience_band'] or '') if r['popcornmeter'] is not None else ''}</small></td><td class=n>{im}{' ⁱ' if low else ''}</td><td>{html.escape(cap(r['genre_label']) or (r['rt_genres'] or ''))}</td>"
            f"<td class=flag>{'<br>'.join(FLAG_SYM.get(f[0],'')+' '+html.escape(f[1]) for f in fl)}</td></tr>")
TH="<tr><th>#</th><th>Movie</th><th>Year</th><th>Critics</th><th>Audience</th><th>IMDb</th><th>Type of movie</th><th>Flags</th></tr>"
MDH="| # | Movie | Year | Critics | Audience | IMDb | Type of movie |\n|---|---|---|---|---|---|---|"
for svc,name in svcs:
    cn=c.execute("SELECT * FROM v_service_counts WHERE service_code=?",(svc,)).fetchone()
    n=cn['n_qualifying'] if cn else 0
    rs=rows('v_top10',svc)
    hdr=f"{name}: {n} qualifying movie{'s' if n!=1 else ''}" + ("" if n>=10 else f" (fewer than 10 qualify)")
    md.append(f"\n## {hdr}\n\n{MDH}")
    H.append(f"<h2>{html.escape(hdr)}</h2><table>{TH}")
    notes=[]
    for r in rs:
        md.append(mdrow(r,svc,r['rnk'])); H.append(hrow(r,svc,r['rnk']))
        for f in flags(r['movie_id'],svc):
            if f[0] in ('availability_conflict','tier_note','leaving_soon','year_conflict'): notes.append(f"{FLAG_SYM[f[0]]} {r['title']}: {f[1]}")
    if not rs: H.append("<tr><td colspan=8><i>No movie meets all the rules.</i></td></tr>")
    H.append("</table>")
    for x in notes: md.append(f"- {x}")
    for view,label in (('v_thin','Also qualifies, thin data (critics and audience both 80%+, but fewer than 20 critic reviews)'),
                       ('v_no_audience','Critics 80%+, no audience score yet (RT displays no Popcornmeter)')):
        side=rows(view,svc)
        if not side: continue
        md.append(f"\n**{label}: {len(side)}**\n\n{MDH}"); [md.append(mdrow(r,svc,r['rnk'])) for r in side]
        H.append(f"<h3>{html.escape(label)}: {len(side)}</h3><table class=side>{TH}"+''.join(hrow(r,svc,r['rnk'],True) for r in side)+"</table>")
    few=rows('v_few_audience_ratings',svc)
    if few:
        md.append(f"\n*Not qualifying: {len(few)} more with critics and audience 80%+ and 20+ reviews but fewer than 250 audience ratings ({', '.join(r['title']+' ('+(r['audience_count_band'] or 'count unreadable')+')' for r in few)}).*")
        H.append(f"<details><summary>Critics and audience 80%+ with 20+ reviews, but fewer than 250 RT audience ratings, so not qualifying: {len(few)}</summary><table class=side>{TH}"+''.join(hrow(r,svc,r['rnk'],True) for r in few)+"</table></details>")
    below=rows('v_audience_below80',svc)
    if below:
        md.append(f"\n*Not qualifying: {len(below)} more with critics 80%+ but audience below 80% (e.g. {', '.join(r['title']+' '+str(r['tomatometer'])+'/'+str(r['popcornmeter']) for r in below[:4])}).*")
        H.append(f"<details><summary>Critics 80%+ but Popcornmeter below 80%, so not qualifying: {len(below)}</summary><table class=side>{TH}"+''.join(hrow(r,svc,r['rnk'],True) for r in below)+"</table></details>")
# method + exclusions
nsrc=c.execute("SELECT COUNT(*) FROM sources_checked WHERE run_id=?",(R,)).fetchone()[0]
ncand=c.execute("SELECT COUNT(DISTINCT raw_title||raw_year) FROM sightings WHERE run_id=?",(R,)).fetchone()[0]
nrt=c.execute("SELECT COUNT(*) FROM score_obs WHERE run_id=?",(R,)).fetchone()[0]
excl=c.execute("SELECT exclude_reason, COUNT(*) FROM movies m JOIN score_obs s USING(movie_id) WHERE s.run_id=? AND s.tomatometer>=80 AND exclude_reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",(R,)).fetchall()
neg=c.execute("""SELECT a.service_code,a.offer_type,COUNT(*) FROM availability_obs a JOIN movies m USING(movie_id) JOIN score_obs s ON s.movie_id=m.movie_id AND s.run_id=a.run_id WHERE a.run_id=? AND a.source IN ('official','manual')
 AND a.offer_type NOT IN ('included') AND m.exclude_reason IS NULL AND s.tomatometer>=80 GROUP BY 1,2""",(R,)).fetchall()
H.append(f"""<h2>Method and coverage</h2><ul>
<li><b>Discovery:</b> the full JustWatch US catalog of 2025–2026 movies for each service's own subscription package ({ncand} distinct titles), plus Rotten Tomatoes' "new fresh movies on &lt;service&gt;" lists, each looked up again on JustWatch. RT has no Starz or MGM+ list.</li>
<li><b>Scores:</b> {nrt} RT movie pages were fetched and parsed today, using the scorecard JSON (Tomatometer, critic review count, Popcornmeter, rating band). The audience rating-count bucket shown next to the Popcornmeter was re-read from every r2 candidate's page by <code>audience_counts.py</code> (visible scorecard text and scorecard JSON must agree; never estimated). If RT shows no Popcornmeter, the table shows "—". Every such movie was re-checked by <code>audience_audit.py</code> (scorecard markup, embedded JSON, trailing-slash variant, audience-reviews page, RT API probes) and the evidence is stored.</li><li><b>IMDb:</b> user rating and vote count from IMDb's official daily ratings dataset (title.ratings.tsv.gz), which carries the same numbers as each title page. The pages themselves show scripted clients a human-verification wall. Informational only.</li>
<li><b>Year rule:</b> the earliest of the IMDb year and the RT year, i.e. the first release, festivals included. Streaming dates are never used. Disagreements are flagged ʸ.</li>
<li><b>Not films:</b> IMDb types short, TV short, TV special (stand-up, concerts, live broadcasts), episodes and series are excluded, as is anything 40 minutes or shorter.</li>
<li><b>Availability:</b> JustWatch FLATRATE on the service's own package, confirmed on the service's own title page. Prime pages were read through Amazon's entitlement message, and "Subscribe to &lt;channel&gt;", "rent or buy" and "Watch for free" (ads) were all rejected. Peacock was checked through its public watch-online page. Reelgood and RT where-to-watch are cross-checks. {nsrc} source URLs were logged.</li>
<li><b>Excluded despite ≥80%:</b> {'; '.join(f'{n} × {html.escape(r)}' for r,n in excl)}.</li>
<li><b>Service-page rejections among ≥80% candidates:</b> {'; '.join(f'{s}: {n} {o}' for s,o,n in neg)}. "Unreachable" for Disney+ means RT listed "Disney+" but JustWatch had no Disney+-own listing (these are Hulu titles that appear in Disney+ through the bundle).</li>
</ul><p><small>Rebuild: see README.md in the repository. Raw API/page captures are kept on the research box under /workspace/movies/raw.</small></p></body></html>""")
open(f'{BASE}/report.html','w').write('\n'.join(H)); open(f'{BASE}/report.md','w').write('\n'.join(md)+'\n')
print('wrote report.html / report.md')
