#!/usr/bin/env python3
"""Pull JustWatch US catalog of 2025-2026 movies per provider package (FLATRATE). Saves raw JSON to raw/jw_<svc>_<date>.json"""
import json, sys, time, urllib.request, urllib.error, datetime
URL="https://apis.justwatch.com/graphql"
Q="""query Cat($after:String,$pk:[String!]){popularTitles(country:US, first:100, after:$after, sortBy:POPULAR,
 filter:{packages:$pk, objectTypes:[MOVIE], releaseYear:{min:2025,max:2026}, monetizationTypes:[FLATRATE]}){
 totalCount pageInfo{hasNextPage endCursor}
 edges{node{ id objectId objectType
  content(country:US, language:"en"){ title originalReleaseYear originalReleaseDate runtime fullPath shortDescription
   genres{shortName} externalIds{imdbId tmdbId} scoring{tomatoMeter certifiedFresh imdbScore imdbVotes}
   ageCertification productionCountries isReleased }
  offers(country:US, platform:WEB){ monetizationType presentationType standardWebURL availableToTime availableFromTime
   package{packageId clearName shortName technicalName} }
 }}}}"""
SVCS={'netflix':['nfx'],'prime':['amp'],'hulu':['hlu'],'disney':['dnp'],'hbomax':['mxx'],'appletv':['atp'],
      'paramount':['ppp','ppe'],'peacock':['pct','pcp'],'starz':['stz'],'mgmplus':['epx']}
def post(q,v,tries=6):
  for i in range(tries):
   try:
    req=urllib.request.Request(URL,data=json.dumps({'query':q,'variables':v}).encode(),headers={'content-type':'application/json','user-agent':'Mozilla/5.0'})
    return json.load(urllib.request.urlopen(req,timeout=60))
   except urllib.error.HTTPError as e:
    if e.code==429 and i<tries-1: time.sleep(10*(i+1)); continue
    raise
def main(only=None):
    d=datetime.date.today().isoformat()
    for svc,pk in SVCS.items():
        if only and svc not in only: continue
        nodes=[];after=None
        while True:
            r=post(Q,{'after':after,'pk':pk})
            if 'errors' in r: print(svc,r['errors']);break
            pt=r['data']['popularTitles']; nodes+= [e['node'] for e in pt['edges']]
            if not pt['pageInfo']['hasNextPage']: break
            after=pt['pageInfo']['endCursor']; time.sleep(0.3)
        json.dump({'svc':svc,'packages':pk,'date':d,'total':pt.get('totalCount'),'nodes':nodes},open(f'raw/jw_{svc}_{d}.json','w'))
        print(svc,pt.get('totalCount'),len(nodes))
if __name__=='__main__': main(sys.argv[1:])
