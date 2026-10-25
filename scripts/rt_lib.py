import re, json, os, time, hashlib, urllib.request, urllib.parse, urllib.error, html, unicodedata, gzip, zlib
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def get(url, cache_dir=None, tries=4, refresh=False):
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        fn=os.path.join(cache_dir, hashlib.md5(url.encode()).hexdigest()+'.html')
        if os.path.exists(fn) and not refresh: return 200, open(fn,encoding='utf-8',errors='replace').read()
    for i in range(tries):
        try:
            r=urllib.request.urlopen(urllib.request.Request(url,headers={'user-agent':UA,'accept-language':'en-US,en;q=0.9'}),timeout=40)
            raw=r.read(); enc=(r.headers.get('content-encoding') or '').lower()
            if enc=='gzip' or raw[:2]==b'\x1f\x8b': raw=gzip.decompress(raw)
            elif enc=='deflate': raw=zlib.decompress(raw)
            body=raw.decode('utf-8','replace'); code=r.status; final_url=r.geturl()
            if cache_dir: open(fn,'w',encoding='utf-8').write(body)
            return code, body
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503) and i<tries-1: time.sleep(5*(i+1)); continue
            return e.code, ''
        except Exception as e:
            if i<tries-1: time.sleep(3); continue
            return -1, str(e)
def norm(t):
    t=unicodedata.normalize('NFKD',html.unescape(t or '')).encode('ascii','ignore').decode().lower()
    t=t.replace('&',' and ')
    t=re.sub(r"[^a-z0-9 ]+",' ',t); t=re.sub(r'\b(the|a|an)\b',' ',t)
    return re.sub(r'\s+',' ',t).strip()
def parse_search(s):
    rows=[]
    m=re.search(r'<search-page-result[^>]*type="movie"[^>]*>(.*?)</search-page-result>',s,re.S)
    if not m: return rows
    for r in re.finditer(r'<search-page-media-row(.*?)</search-page-media-row>',m.group(1),re.S):
        b=r.group(1)
        a=lambda k: (re.search(k+r'="([^"]*)"',b) or [None,None])[1]
        url=(re.search(r'href="(https://www\.rottentomatoes\.com/m/[^"]+)"',b) or [None,None])[1]
        title=(re.search(r'data-qa="info-name"[^>]*>\s*([^<]+?)\s*</a>',b) or re.search(r'alt="([^"]*)"',b) or [None,None])[1]
        rows.append({'url':url,'title':html.unescape(title or ''),'year':a('release-year'),'tm':a('tomatometer-score'),'cast':a('cast')})
    return rows
def scr(s, sid):
    m=re.search(r'<script[^>]*id="%s"[^>]*>(.*?)</script>'%sid,s,re.S)
    try: return json.loads(m.group(1)) if m else None
    except Exception: return None
def info(s,label):
    i=s.find('>'+label+'<')
    if i<0:
        i=s.find(label)
        if i<0: return None
    seg=s[i:i+900]; seg=re.sub(r'<[^>]+>',' ',seg); seg=html.unescape(re.sub(r'\s+',' ',seg)).strip()
    return seg[len(label):].strip()
def parse_movie(s):
    sc=scr(s,'media-scorecard-json') or {}; hero=scr(s,'media-hero-json') or {}; wtw=scr(s,'where-to-watch-json') or {}
    ld=None
    m=re.search(r'<script type="application/ld\+json">(.*?)</script>',s,re.S)
    if m:
        try: ld=json.loads(m.group(1))
        except Exception: ld=None
    cs=sc.get('criticsScore') or {}; au=sc.get('audienceScore') or {}
    def cut(v,stops):
        if not v: return v
        for st in stops:
            j=v.find(st)
            if j>0: v=v[:j]
        return v.strip(' ,')
    stops=['Release Date','Runtime','Box Office','Sound Mix','Aspect','Original Language','Producer','Screenwriter','Distributor','Production Co','Rating','Genre','Director','Writer']
    rd={k:cut(info(s,k),[x for x in stops if x!=k]) for k in ['Release Date (Theaters)','Release Date (Streaming)','Runtime','Original Language','Genre','Rating']}
    return {
      'title': (hero.get('content') or {}).get('title') or (ld or {}).get('name'),
      'tomatometer': int(cs['score']) if cs.get('score') not in (None,'') else None,
      'critic_reviews': cs.get('reviewCount'), 'critic_avg': cs.get('averageRating'), 'certified_fresh': cs.get('certified'),
      'popcorn': int(au['score']) if au.get('score') not in (None,'') else None,
      'audience_band': au.get('bandedRatingCount'), 'audience_reviews': au.get('reviewCount'),
      'audience_liked': au.get('likedCount'), 'audience_notliked': au.get('notLikedCount'),
      'hide_audience': sc.get('hideAudienceScore'),
      'genres': (hero.get('content') or {}).get('metadataGenres'), 'props': (hero.get('content') or {}).get('metadataProps'),
      'wtw': wtw, 'info': rd, 'ld_genre': (ld or {}).get('genre'), 'ld_rating': (ld or {}).get('contentRating'),
      'cta': sc.get('cta'),
    }
