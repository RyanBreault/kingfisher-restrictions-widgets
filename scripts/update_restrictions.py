#!/usr/bin/env python3
from __future__ import annotations
import json,re,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup,Tag
SOURCE_URL='https://fwp.mt.gov/news/current-closures-restrictions/waterbody-closures'
OUTPUT_PATH=Path('river-restrictions.json')
RIVERS={'bitterroot':('Bitterroot River','Bitterroot River'),'blackfoot':('Blackfoot River','Blackfoot River'),'clark-fork':('Clark Fork River','Clark Fork River'),'rock-creek':('Rock Creek','Rock Creek')}
HEADERS={'User-Agent':'KingfisherFlyShopRestrictionsBot/1.0 (+https://kingfisherflyshop.com/)'}
def clean(v): return re.sub(r'\s+',' ',v or '').strip()
def rtype(t):
 l=t.lower()
 if 'closed to floating' in l or 'floating closure' in l:return 'Floating Closure'
 if 'hoot owl' in l:return 'Hoot Owl Restriction'
 if 'fishing prohibited 24 hours' in l or 'fishing closure' in l:return 'Fishing Closure'
 if 'closed to all forms of use' in l:return 'Emergency Closure'
 if 'closure' in l or 'closed' in l:return 'Closure'
 return 'FWP Restriction'
def edate(t):
 for p in (r'\bstarting\s+([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)',r'\bbeginning\s+([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)',r'\beffective\s+([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)'):
  m=re.search(p,t)
  if m:return m.group(1)
 return ''
def section(h):
 parts=[];links=[]
 for s in h.next_siblings:
  if isinstance(s,Tag) and s.name in {'h2','h3'}:break
  if not isinstance(s,Tag):continue
  x=clean(s.get_text(' ',strip=True))
  if x:parts.append(x)
  for a in s.find_all('a',href=True):links.append({'label':clean(a.get_text(' ',strip=True)),'url':urljoin(SOURCE_URL,a['href'])})
 return clean(' '.join(parts)),links
def empty(name):return {'name':name,'restricted':False,'restriction_type':'','effective_date':'','message':'No current fishing restrictions reported.','notice_count':0,'notices':[]}
def scrape():
 r=requests.get(SOURCE_URL,headers=HEADERS,timeout=30);r.raise_for_status()
 soup=BeautifulSoup(r.text,'html.parser')
 hs={clean(h.get_text(' ',strip=True)).lower():h for h in soup.find_all(['h2','h3'])}
 if not hs:raise RuntimeError('FWP page returned no river headings')
 out={}
 for key,(name,heading) in RIVERS.items():
  h=hs.get(heading.lower())
  if h is None:out[key]=empty(name);continue
  body,links=section(h)
  if not body:out[key]=empty(name);continue
  typ=rtype(body);date=edate(body)
  notice={'source':'Montana FWP Current Waterbody Restrictions','type':typ,'waterbody':name,'effective_date':date,'message':body,'url':links[0]['url'] if links else SOURCE_URL,'links':links}
  out[key]={'name':name,'restricted':True,'restriction_type':typ,'effective_date':date,'message':body,'notice_count':1,'notices':[notice]}
 return out
def main():
 try:rivers=scrape()
 except Exception as e:
  print(f'ERROR: Could not read FWP restrictions page: {e}',file=sys.stderr);print('Existing river-restrictions.json was left unchanged.',file=sys.stderr);return 1
 payload={'generated_at':datetime.now(timezone.utc).isoformat(),'source':SOURCE_URL,'rivers':rivers}
 OUTPUT_PATH.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
 for k,v in rivers.items():print(f"{k}: restricted={v['restricted']} type={v['restriction_type'] or 'none'}")
 return 0
if __name__=='__main__':raise SystemExit(main())
