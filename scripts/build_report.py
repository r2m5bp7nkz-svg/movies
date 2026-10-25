#!/usr/bin/env python3
"""Regenerate report.html + report.md from movies.db (latest run). No network access."""
import sys, os, json, html, datetime
sys.path.insert(0, os.path.dirname(__file__)); from common import *
c=connect()
run=c.execute("SELECT * FROM runs ORDER BY run_id DESC LIMIT 1").fetchone()
D=run['run_date']; R=run['run_id']
svcs=[(r['service_code'],r['name']) for r in c.execute("SELECT * FROM services")]
order=[s for s,_,_ in SERVICES]; svcs.sort(key=lambda x:order.index(x[0]))
FLAG_SYM={'few_critic_reviews':'†','few_audience_ratings':'‡','availability_conflict':'⚠','year_conflict':'ʸ','tier_note':'◆','leaving_soon':'⏳','official_unverified':'?'}
def flags(mid,svc): return c.execute("SELECT flag_type,detail FROM flags WHERE run_id=? AND movie_id=? AND service_code=?",(R,mid,svc)).fetchall()
def pct(v): return '—' if v is None else f'{v}%'
def rows(view,svc): return c.execute(f"SELECT t.*, m.kid_friendly FROM {view} t JOIN movies m USING(movie_id) WHERE service_code=? ORDER BY rnk",(svc,)).fetchall()
md=[f"# Movies (first released 2025–2026) included with US streaming subscriptions\n\n**Date checked: {datetime.date.fromisoformat(D):%A, %B %-d, %Y}** (America/Los_Angeles). Generated from `movies.db` run {R}.\n",
    "Ranking: Rotten Tomatoes Tomatometer (highest first), ties broken by number of critic reviews, then Popcornmeter. Critics/Audience = Tomatometer/Popcornmeter as read from each movie's own RT page, with critic review counts in parentheses. "
    "Flags: † fewer than 20 critic reviews · ‡ Popcornmeter based on only 50–99 ratings · ʸ sources disagree on the year · ◆ tier note · ⏳ leaving within 45 days · ⚠ availability note.\n"]
H=[]
H.append(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Streaming movies 2025–2026 · checked {D}</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1d1d1f;line-height:1.45}}
h1{{font-size:1.6em}} h2{{margin-top:2em;border-bottom:2px solid #eee;padding-bottom:4px}} table{{border-collapse:collapse;width:100%;font-size:.93em}}
th,td{{border:1px solid #e3e3e3;padding:5px 8px;text-align:left;vertical-align:top}} th{{background:#f6f6f6}} td.n{{text-align:right;white-space:nowrap}}
.flag{{color:#b45309;font-size:.85em}} .kid{{background:#e8f7ee;border-radius:4px;padding:0 4px;font-size:.8em;color:#166534}}
.note{{background:#fff8e6;border-left:4px solid #f0b429;padding:8px 12px;margin:10px 0}} details{{margin:8px 0}} small{{color:#666}}
</style></head><body>
<h1>Movies first released in 2025–2026 that are included with US streaming subscriptions</h1>
<p><b>Date checked: {datetime.date.fromisoformat(D):%A, %B %-d, %Y}</b> (America/Los_Angeles) · for Emil Frojd (Mountain View, CA) · generated from <code>movies.db</code> (run {R}).</p>
<div class="note"><b>How to read this:</b> up to 10 movies per service with a Rotten Tomatoes Tomatometer of at least 80%, ranked by Tomatometer (ties go to the movie with more critic reviews, then the higher Popcornmeter).
Both scores were read from each movie's own RT page today, and the number in parentheses is the critic review count.
Availability required two things: JustWatch lists the movie as included with the subscription (FLATRATE on the service's own package) <i>and</i> the service's own public title page confirms it. Reelgood and RT's "where to watch" were used as further cross-checks.
Rentals, purchases, Amazon Channels, free-with-ads, and Hulu-in-Disney+ bundle access are excluded.<br>
Flags: † fewer than 20 critic reviews · ‡ Popcornmeter from only 50–99 ratings · ʸ year sources disagree · ◆ plan-tier note · ⏳ leaving within 45 days · ⚠ availability note · <span class="kid">kids</span> suitable for young kids.</div>""")
for svc,name in svcs:
    n=c.execute("SELECT n_qualifying FROM v_service_counts WHERE service_code=?",(svc,)).fetchone(); n=n[0] if n else 0
    rs=rows('v_top10',svc)
    hdr=f"{name} — {n} qualifying movie{'s' if n!=1 else ''} found" + ("" if n>=10 else f" (only {n}; fewer than 10 qualify)")
    md.append(f"\n## {hdr}\n\n| # | Movie | Year | Critics | Audience | Type of movie |\n|---|---|---|---|---|---|")
    H.append(f"<h2>{html.escape(hdr)}</h2><table><tr><th>#</th><th>Movie</th><th>Year</th><th>Critics</th><th>Audience</th><th>Type of movie</th><th>Flags</th></tr>")
    notes=[]
    for r in rs:
        fl=flags(r['movie_id'],svc); sym=''.join(FLAG_SYM[f[0]] for f in fl if f[0] in FLAG_SYM)
        url='https://www.rottentomatoes.com/m/'+r['rt_slug']
        md.append(f"| {r['rnk']} | [{r['title']}]({url}){(' '+sym) if sym else ''} | {r['release_year']} | {r['tomatometer']}% ({r['critic_reviews']}) | {pct(r['popcornmeter'])} | {r['genre_label']} |")
        kid=f' <span class="kid">kids: {html.escape(r["kid_friendly"])}</span>' if r['kid_friendly'] else ''
        H.append(f"<tr><td class=n>{r['rnk']}</td><td><a href='{url}'>{html.escape(r['title'])}</a>{kid}</td><td>{r['release_year']}</td><td class=n>{r['tomatometer']}% <small>({r['critic_reviews']} reviews)</small></td>"
                 f"<td class=n>{pct(r['popcornmeter'])} <small>{html.escape(r['audience_band'] or '') if r['popcornmeter'] is not None else ''}</small></td><td>{html.escape(r['genre_label'] or '')}</td>"
                 f"<td class=flag>{'<br>'.join(FLAG_SYM.get(f[0],'')+' '+html.escape(f[1]) for f in fl)}</td></tr>")
        for f in fl:
            if f[0] in ('availability_conflict','tier_note','leaving_soon','year_conflict'): notes.append(f"{FLAG_SYM[f[0]]} {r['title']}: {f[1]}")
    H.append("</table>")
    few=[r['title'] for r in rs if any(f[0]=='few_critic_reviews' for f in flags(r['movie_id'],svc))]
    if few: md.append(f"\n*{len(few)} of these rank on fewer than 20 critic reviews (†).*")
    for x in notes: md.append(f"- {x}")
    alt=rows('v_top10_min20',svc)
    if few and alt:
        H.append(f"<details><summary>Alternative view: top {len(alt)} with ≥20 critic reviews (not the requested ranking; same rules otherwise)</summary><table><tr><th>#</th><th>Movie</th><th>Year</th><th>Critics</th><th>Audience</th><th>Type of movie</th></tr>")
        for r in alt: H.append(f"<tr><td class=n>{r['rnk']}</td><td><a href='https://www.rottentomatoes.com/m/{r['rt_slug']}'>{html.escape(r['title'])}</a></td><td>{r['release_year']}</td><td class=n>{r['tomatometer']}% <small>({r['critic_reviews']})</small></td><td class=n>{pct(r['popcornmeter'])}</td><td>{html.escape(r['genre_label'] or '(not labelled)')}</td></tr>")
        H.append("</table></details>")
# recommendations
recs=json.load(open(f'{BASE}/overrides/recommendations.json'))
md.append("\n## Five recommendations\n"); H.append("<h2>Five recommendations</h2><ol>")
for i,rc in enumerate(recs,1):
    m=c.execute("SELECT m.title,m.release_year,s.tomatometer,s.popcornmeter,m.kid_friendly FROM movies m JOIN v_latest_scores s USING(movie_id) WHERE rt_slug=?",(rc['slug'],)).fetchone()
    where=', '.join(dict(svcs)[r[0]] for r in c.execute("SELECT service_code FROM v_qualifying WHERE rt_slug=?",(rc['slug'],)))
    md.append(f"{i}. **[{m['title']}](https://www.rottentomatoes.com/m/{rc['slug']})** ({m['release_year']}; {m['tomatometer']}% / {pct(m['popcornmeter'])}; on {where}): {rc['why']}")
    H.append(f"<li><b><a href='https://www.rottentomatoes.com/m/{rc['slug']}'>{html.escape(m['title'])}</a></b> ({m['release_year']}; {m['tomatometer']}% / {pct(m['popcornmeter'])}; on {html.escape(where)}): {html.escape(rc['why'])}</li>")
H.append("</ol>")
# method + exclusions
nsrc=c.execute("SELECT COUNT(*) FROM sources_checked WHERE run_id=?",(R,)).fetchone()[0]
ncand=c.execute("SELECT COUNT(DISTINCT raw_title||raw_year) FROM sightings WHERE run_id=?",(R,)).fetchone()[0]
nrt=c.execute("SELECT COUNT(*) FROM score_obs WHERE run_id=?",(R,)).fetchone()[0]
excl=c.execute("SELECT exclude_reason, COUNT(*) FROM movies m JOIN score_obs s USING(movie_id) WHERE s.run_id=? AND s.tomatometer>=80 AND exclude_reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",(R,)).fetchall()
neg=c.execute("""SELECT a.service_code,a.offer_type,COUNT(*) FROM availability_obs a JOIN movies m USING(movie_id) JOIN score_obs s ON s.movie_id=m.movie_id AND s.run_id=a.run_id WHERE a.run_id=? AND a.source IN ('official','manual')
 AND a.offer_type NOT IN ('included') AND m.exclude_reason IS NULL AND s.tomatometer>=80 GROUP BY 1,2""",(R,)).fetchall()
H.append(f"""<h2>Method and coverage</h2><ul>
<li><b>Discovery:</b> the full JustWatch US catalog of 2025–2026 movies for each service's own subscription package ({ncand} distinct titles), plus Rotten Tomatoes' "new fresh movies on &lt;service&gt;" lists, each looked up again on JustWatch. RT has no Starz or MGM+ list.</li>
<li><b>Scores:</b> {nrt} RT movie pages were fetched and parsed today, using the scorecard JSON (Tomatometer, critic review count, Popcornmeter, rating band). If RT shows no Popcornmeter, the table shows "—".</li>
<li><b>Year rule:</b> the earliest of the IMDb year and the RT year, i.e. the first release, festivals included. Streaming dates are never used. Disagreements are flagged ʸ.</li>
<li><b>Not films:</b> IMDb types short, TV short, TV special (stand-up, concerts, live broadcasts), episodes and series are excluded, as is anything 40 minutes or shorter.</li>
<li><b>Availability:</b> JustWatch FLATRATE on the service's own package, confirmed on the service's own title page. Prime pages were read through Amazon's entitlement message, and "Subscribe to &lt;channel&gt;", "rent or buy" and "Watch for free" (ads) were all rejected. Peacock was checked through its public watch-online page. Reelgood and RT where-to-watch are cross-checks. {nsrc} source URLs were logged.</li>
<li><b>Excluded despite ≥80%:</b> {'; '.join(f'{n} × {html.escape(r)}' for r,n in excl)}.</li>
<li><b>Service-page rejections among ≥80% candidates:</b> {'; '.join(f'{s}: {n} {o}' for s,o,n in neg)}. "Unreachable" for Disney+ means RT listed "Disney+" but JustWatch had no Disney+-own listing (these are Hulu titles that appear in Disney+ through the bundle).</li>
</ul><p><small>Rebuild: see README.md in the repository. Raw API/page captures are kept on the research box under /workspace/movies/raw.</small></p></body></html>""")
open(f'{BASE}/report.html','w').write('\n'.join(H)); open(f'{BASE}/report.md','w').write('\n'.join(md)+'\n')
print('wrote report.html / report.md')
