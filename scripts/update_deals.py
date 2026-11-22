#!/usr/bin/env python3
"""Cautious RSS discovery, daily change log, and ranking-ready reviewed deals.

Public feed posts are leads only; the tool NEVER guesses reward eligibility or
stackable coupon savings. Failing sources are recorded and NOT called current.
This is designed for GitHub Actions and requires no account credentials.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
UTC = timezone.utc
USER_AGENT = 'KnoxvilleDealHunter/1.0 (daily RSS reader; contact: project maintainer)'
SOURCES = [
    {'id':'kcl', 'name':'The Krazy Coupon Lady RSS', 'url':'https://thekrazycouponlady.com/rss', 'kind':'coupon-research'},
    {'id':'slickdeals', 'name':'Slickdeals frontpage RSS', 'url':'https://slickdeals.net/rss.php', 'kind':'community-deals'},
]
STORE_TERMS = [
    ('Dollar General',r'\bdollar general\b|\bmydg\b'),
    ('Walgreens',r'\bwalgreens\b|\bmywalgreens\b'),
    ('CVS',r'\bcvs\b|\bextrabucks\b'),
    ('Walmart',r'\bwalmart\b|\bwalmart cash\b'),
    ('Target',r'\btarget\b|\btarget circle\b'),
    ('Kroger',r'\bkroger\b'),
    ('Publix',r'\bpublix\b'),
    ('Food City',r'\bfood city\b'),
    ('ALDI',r'\baldi\b'),
    ('Costco',r'\bcostco\b'),
    ('Sam’s Club',r"\bsam'?s club\b"),
]
STORE_RE = [(name, re.compile(pat,re.I)) for name,pat in STORE_TERMS]
TAG_RE = re.compile(r'<[^>]*>')
SPACE_RE = re.compile(r'\s+')
PERCENT_RE = re.compile(r'\b(\d{1,3})\s*%\s*(?:off|discount|savings?)',re.I)
MONEY_RE = re.compile(r'(?<!\w)\$\s*(\d{1,5}(?:\.\d{1,2})?)')
REWARD_RE = re.compile(r'\b(?:extrabucks|walgreens cash|register rewards|walmart cash|gift cards?|cash ?back|rebates?)\b',re.I)
URL_TRACKING = {'utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid'}

def nowiso(dt=None):
    return (dt or datetime.now(UTC)).astimezone(UTC).isoformat(timespec='seconds').replace('+00:00','Z')

def clean(s, limit=400):
    return SPACE_RE.sub(' ',html.unescape(TAG_RE.sub(' ',s or ''))).strip()[:limit]

def canonical_url(url):
    v = urlsplit((url or '').strip())
    if v.scheme not in ('http','https') or not v.netloc: return ''
    q=[(k,val) for k,val in parse_qsl(v.query) if k.lower() not in URL_TRACKING and not k.lower().startswith('utm_')]
    return urlunsplit((v.scheme,v.netloc.lower(),v.path,urlencode(q),''))

def get_text(node, key):
    # RSS and Atom both supported; namespace-agnostic tag matching.
    for el in node.iter():
        if el is node: continue
        if el.tag.split('}')[-1] == key and el.text:
            return el.text.strip()
    return ''

def parse_date(raw):
    if not raw:return None
    try:
        dt=parsedate_to_datetime(raw)
    except (TypeError,ValueError):
        try: dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
        except ValueError: return None
    if not dt.tzinfo:dt=dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

def parse_feed(xml_bytes,source, now=None):
    now=now or datetime.now(UTC)
    root=ET.fromstring(xml_bytes)
    nodes=[n for n in root.iter() if n.tag.split('}')[-1] in ('item','entry')]
    out=[]
    for node in nodes:
        title=clean(get_text(node,'title'),200)
        desc=clean(get_text(node,'description') or get_text(node,'summary') or get_text(node,'content'),480)
        link=get_text(node,'link')
        if not link:
            for el in node.iter():
                if el.tag.split('}')[-1]=='link' and el.attrib.get('href'):
                    link=el.attrib['href'];break
        link=canonical_url(link)
        when=parse_date(get_text(node,'pubDate') or get_text(node,'published') or get_text(node,'updated'))
        if not title or not link or not when: continue
        # RSS sources do not guarantee validity dates; only use recent posts
        if when < now-timedelta(days=12) or when > now+timedelta(hours=6): continue
        matchtext=f'{title} {desc[:180]}'
        stores=[name for name,pat in STORE_RE if pat.search(matchtext)]
        if not stores:continue
        for store in stores[:2]:
            key=hashlib.sha256((store+'|'+link).encode()).hexdigest()[:18]
            headline_pct=PERCENT_RE.search(title)
            money=MONEY_RE.findall(title)
            signal=[]
            if headline_pct:signal.append(f'{headline_pct.group(1)}% advertised')
            if money:signal.append('Price/reward amount mentioned')
            if re.search(r'\bfree\s+(?:after|product|item|with|when)|\bcompletely free\b',title,re.I):signal.append('Mentions free after conditions')
            if REWARD_RE.search(matchtext):signal.append('Mentions rewards')
            out.append({
                'id':key, 'store':store, 'title':title, 'description':desc[:270],
                'url':link, 'source':source['name'],'source_id':source['id'],
                'published_at':nowiso(when), 'discovered_at':nowiso(now),
                'signals':signal, 'priority_score':min(100,(35 if REWARD_RE.search(matchtext) else 0)+(40 if 'Mentions free after conditions' in signal else 0)+(min(60,int(headline_pct.group(1))) if headline_pct else 0)+(8 if money else 0)), 'stage':'research_lead',
                'notice':'Published deal lead only. Verify local price, quantities, account coupons, stacking, and reward terms before purchase.'
            })
    return out

def read_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError):return default

def valid_reviewed(entry, today):
    required=('id','store','item','regular','checkout','earn','expires','terms','source','verified_at')
    if not all(k in entry for k in required):return False
    try:
        if entry['expires']<today or entry['verified_at'] < today: return False
        regular=float(entry['regular']);checkout=float(entry['checkout'])
        if not 0<regular<1e5 or not 0<=checkout<1e5:return False
        earn=entry['earn']
        if not isinstance(earn,dict) or any(k not in ('eb','wc','rr','rebate') or not 0<=float(v)<1e4 for k,v in earn.items()):return False
        if not entry.get('terms') or not entry.get('source'):return False
    except (TypeError,ValueError):return False
    return True

def generate(fetch,now=None,previous=None,reviewed=None):
    now=now or datetime.now(UTC)
    previous=previous or {}
    reviewed=reviewed or []
    current=[]; status=[]
    for source in SOURCES:
        try:
            payload=fetch(source['url'])
            entries=parse_feed(payload,source,now)
            status.append({'id':source['id'],'name':source['name'],'ok':True,'offers':len(entries),'checked_at':nowiso(now)})
            current+=entries
        except Exception as exc:
            # A bad source is not a success; drop expired leads from rankings.
            status.append({'id':source['id'],'name':source['name'],'ok':False,'offers':0,
                           'checked_at':nowiso(now),'error':type(exc).__name__+': '+str(exc)[:100]})
    unique={d['id']:d for d in current}
    leads=sorted(unique.values(),key=lambda d:(d.get('priority_score',0),d['published_at']),reverse=True)
    checked=nowiso(now)
    last=previous.get('last_successful_at')
    if any(s['ok'] for s in status): last=checked
    # Do not claim that a removed RSS entry expired: it may simply be older than feed window.
    old={e['id']:e for e in previous.get('leads',[])}
    new={e['id']:e for e in leads}
    changed=[k for k in new.keys()&old.keys() if new[k]['title']!=old[k]['title'] or new[k]['description']!=old[k]['description']]
    added=[k for k in new if k not in old]
    missing=[k for k in old if k not in new]
    summary={'date':now.date().isoformat(),'checked_at':checked,
             'new':len(added),'changed':len(changed),'no_longer_in_feed':len(missing),
             'total_leads':len(leads),'sources_successful':sum(s['ok'] for s in status),
             'sources_total':len(status)}
    # Unavailable sources should not cause their posts to be counted as "no longer".
    failed={s['id'] for s in status if not s['ok']}
    if failed:
        kept=[e for e in old.values() if e.get('source_id') in failed and parse_date(e.get('published_at')) and parse_date(e['published_at'])>=now-timedelta(days=12)]
        for e in kept:
            if e['id'] not in new:
                e=dict(e,stage='stale_lead',notice='Feed unavailable today; this offer was NOT reconfirmed.')
                new[e['id']]=e
        leads=sorted(new.values(),key=lambda d:(d.get('priority_score',0),d['published_at']),reverse=True)
        missing=[k for k in missing if old[k].get('source_id') not in failed]
        summary['no_longer_in_feed']=len(missing)
        summary['total_leads']=len(leads)
    verified=[x for x in reviewed if valid_reviewed(x,now.date().isoformat())]
    document={
      'schema_version':2,'checked_at':checked,'last_successful_at':last,
      'collector':'RSS discovery; not retailer-account checkout verification',
      'sources':status,'leads':leads[:200],'reviewed_deals':verified,
      'changes':summary,'new_ids':added[:200], 'updated_ids':changed[:200],
      'note':'Ranked deal values are only allowed for manually reviewed deals checked today. Feed leads are not confirmed coupon stacks.'
    }
    return document,summary

def fetch_url(url):
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/rss+xml, application/xml, text/xml;q=0.9'})
    with urllib.request.urlopen(req,timeout=15) as resp:
        # Hard cap response; avoid grabbing huge feeds accidentally.
        return resp.read(2_000_001)[:2_000_000]

def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture-dir',type=Path,help='Local RSS XML fixtures for offline tests')
    args=p.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    old=read_json(DATA/'latest.json',{})
    history=read_json(DATA/'history.json',[])
    reviewed=read_json(DATA/'reviewed_deals.json',[])
    def load(url):
        if args.fixture_dir:
            name='kcl.xml' if 'krazycouponlady' in url else 'slickdeals.xml'
            return (args.fixture_dir/name).read_bytes()
        return fetch_url(url)
    now=datetime.now(UTC)
    latest,digest=generate(load,now,old,reviewed)
    history=[h for h in history if h.get('date')!=digest['date']]+[digest]
    history=history[-120:]
    # Atomic writes for local processes, and a clear failure signal in Actions.
    for name,data in [('latest.json',latest),('history.json',history)]:
        target=DATA/name;temp=target.with_suffix('.json.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,target)
    print(json.dumps({'checked_at':latest['checked_at'],'sources':latest['sources'],
                      'leads':len(latest['leads']),'reviewed':len(latest['reviewed_deals']), 'changes':digest},indent=2))
    if not any(s['ok'] for s in latest['sources']):
        print('WARNING: no RSS source succeeded; dashboard should report collection failures',file=sys.stderr)
    return 0

if __name__=='__main__':raise SystemExit(main())