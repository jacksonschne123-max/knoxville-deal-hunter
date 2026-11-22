import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

PATH=Path(__file__).resolve().parents[1]/'scripts'/'update_deals.py'
spec=importlib.util.spec_from_file_location('updater',PATH)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
FIX=Path(__file__).parent/'fixtures'
NOW=datetime(2026,11,22,15,0,tzinfo=timezone.utc)

def fetch(url):
    return (FIX/('kcl.xml' if 'krazycouponlady' in url else 'slickdeals.xml')).read_bytes()

class DealTests(unittest.TestCase):
    def test_feed_read_and_store_extraction(self):
        items=mod.parse_feed((FIX/'kcl.xml').read_bytes(),mod.SOURCES[0],NOW)
        self.assertEqual(len(items),2)
        self.assertEqual({i['store'] for i in items},{'CVS','Publix'})
        self.assertTrue(all(i['stage']=='research_lead' for i in items))
        self.assertEqual(items[0]['url'],'https://example.com/cvs-test')
        self.assertNotIn('regular',items[0])
        self.assertNotIn('checkout',items[0])
    def test_daily_diff_and_stable_ids(self):
        a,d=mod.generate(fetch,NOW)
        self.assertEqual(d['new'],4)
        self.assertEqual(d['sources_successful'],2)
        b,d2=mod.generate(fetch,NOW,a)
        self.assertEqual(d2['new'],0)
        self.assertEqual(d2['no_longer_in_feed'],0)
        self.assertEqual({i['id'] for i in a['leads']},{i['id'] for i in b['leads']})
    def test_fetch_failure_not_marked_current(self):
        first,_=mod.generate(fetch,NOW)
        def fail(_):raise ConnectionError('blocked')
        result,d=mod.generate(fail,NOW,first)
        self.assertEqual(d['sources_successful'],0)
        self.assertEqual(d['no_longer_in_feed'],0)
        self.assertTrue(all(i['stage']=='stale_lead' for i in result['leads']))
    def test_manual_review_requires_same_day(self):
        valid={'id':'a','store':'CVS','item':'Example','regular':10,'checkout':5,'earn':{'eb':3},'expires':'2026-11-24','terms':'Specific SKU','source':'https://example.com','verified_at':'2026-11-22'}
        self.assertTrue(mod.valid_reviewed(valid,'2026-11-22'))
        self.assertFalse(mod.valid_reviewed(valid,'2026-11-23'))
        self.assertFalse(mod.valid_reviewed({**valid,'earn':{'fake':5}},'2026-11-22'))

if __name__=='__main__':unittest.main()