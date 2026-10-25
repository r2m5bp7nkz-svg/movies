import os, re, json, sqlite3
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB=os.path.join(BASE,'movies.db')
SERVICES=[('netflix','Netflix','netflix.com'),('prime','Amazon Prime Video','amazon.com / watch.amazon.com'),('hulu','Hulu','hulu.com'),
 ('disney','Disney+','disneyplus.com'),('hbomax','HBO Max','hbomax.com'),('appletv','Apple TV+ (now "Apple TV")','tv.apple.com'),
 ('paramount','Paramount+','paramountplus.com'),('peacock','Peacock','peacocktv.com'),('starz','Starz','starz.com'),('mgmplus','MGM+','mgmplus.com')]
# JustWatch packages that count as "included with the service subscription"
INCLUDED_PK={'netflix':['nfx'],'prime':['amp'],'hulu':['hlu'],'disney':['dnp'],'hbomax':['mxx'],'appletv':['atp'],
 'paramount':['ppp','ppe'],'peacock':['pct','pcp'],'starz':['stz'],'mgmplus':['epx']}
PK_INFO={'nfx':('Netflix','core'),'amp':('Amazon Prime Video (included with Prime)','core'),'hlu':('Hulu','core'),'dnp':('Disney Plus','core'),
 'mxx':('HBO Max','core'),'atp':('Apple TV (subscription, formerly Apple TV+)','core'),'ppp':('Paramount Plus Premium','tier'),
 'ppe':('Paramount Plus Essential','tier'),'pct':('Peacock Premium','tier'),'pcp':('Peacock Premium Plus','tier'),'stz':('Starz','core'),'epx':('MGM Plus','core')}
RT_WTW_NAMES={'Netflix':'netflix','Prime Video':'prime','Hulu':'hulu','Disney+':'disney','HBO Max':'hbomax','Apple TV':'appletv','Apple TV+':'appletv',
 'Paramount+':'paramount','Peacock':'peacock','Starz':'starz','STARZ':'starz','MGM+':'mgmplus'}
REELGOOD_SRC={'netflix':['netflix'],'prime':['amazon_prime'],'hulu':['hulu_plus','hulu'],'disney':['disney_plus'],'hbomax':['hbo_max'],
 'appletv':['apple_tv_plus'],'paramount':['cbs_all_access','paramount_plus'],'peacock':['peacock'],'starz':['starz'],'mgmplus':['epix','mgm_plus']}
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def runtime_min(s):
    if not s: return None
    m=re.match(r'\s*(?:(\d+)h)?\s*(?:(\d+)m)?',s)
    if not m or not (m.group(1) or m.group(2)): return None
    return int(m.group(1) or 0)*60+int(m.group(2) or 0)
