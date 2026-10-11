import unittest
from datetime import date
from copy import deepcopy
from flightcore.core import Conditions
from flightcore.combined_prices import ranking


class CombinedPricesTests(unittest.TestCase):
    def setUp(self):
        self.c = Conditions(('ICN',), ('NRT',), date(2026,10,12), date(2026,10,13), 5)

    def task(self, kind, prices, day=None):
        inbound = kind == 'inbound'
        return {'number':1,'status':'observed_partial','request':{
            'kind':kind,'origin':'NRT' if inbound else 'ICN',
            'destination':'ICN' if inbound else 'NRT',
            'departure':day or ('2026-10-17' if inbound else '2026-10-12'),
            'return_date':'2026-10-17' if kind=='roundtrip' else None},
            'result':{'observations':[{'amount':p,'currency':'KRW','text':f'fixture {i}'} for i,p in enumerate(prices)]}}

    def test_top20_uses_all_rows_and_all_cross_provider_pairs(self):
        data={'naver':[self.task('roundtrip',list(range(200,100,-1))),self.task('outbound',[100,50]),self.task('inbound',[200])],
              'google':[self.task('outbound',[70]),self.task('inbound',list(range(90,60,-1)))]}
        before=deepcopy(data)
        r=ranking(self.c,data,[])
        self.assertEqual([int(x['amount']) for x in r['roundtrips']],list(range(101,121)))
        self.assertEqual(r['roundtrip_total'],100)
        self.assertEqual(r['oneway_total'],93)
        expected=sorted(a+b for a in [100,50,70] for b in [200]+list(range(90,60,-1)))[:20]
        self.assertEqual([int(x['amount']) for x in r['oneway_combinations']],expected)
        first=r['oneway_combinations'][0]
        self.assertEqual((first['outbound']['source'],first['inbound']['source']),('naver','google'))
        self.assertEqual(data,before)

    def test_wrong_date_failed_currency_and_invalid_prices_excluded(self):
        rt=self.task('roundtrip',[0,-1,True,None,'NaN','Infinity','bad',12])
        rt['result']['observations'][-1]['currency']='USD'
        failed=self.task('roundtrip',[1]);failed['status']='access_stopped'
        data={'naver':[rt,failed,self.task('roundtrip',[2],'2026-10-14'),self.task('outbound',[3]),self.task('inbound',[4],'2026-10-18')]}
        r=ranking(self.c,data,[])
        self.assertEqual(r['roundtrips'],[])
        self.assertEqual(r['oneway_combinations'],[])

    def test_cache_is_labelled_and_never_creates_oneways(self):
        ref={'status':'references_received','fetched_at':'TEST','references':[{'fromCity':'ICN','toCity':'NRT','departureDate':'2026-10-12','returnDate':'2026-10-17','totalPrice':10,'airline':'TEST'}]}
        r=ranking(self.c,{},[ref,ref])
        self.assertEqual(r['roundtrip_total'],1)
        self.assertEqual(r['roundtrips'][0]['basis'],'cached_reference')
        self.assertIsNone(r['roundtrips'][0]['observed_at'])
        self.assertEqual(r['oneway_total'],0)

    def test_ties_duplicates_and_disabled_oneways(self):
        task=self.task('roundtrip',[10]);task['result']['observations']*=2
        r=ranking(self.c,{'naver':[task],'google':[task]},[])
        self.assertEqual(r['roundtrip_total'],2)
        from dataclasses import replace
        r=ranking(replace(self.c,compare_oneways=False),{'naver':[self.task('outbound',[1]),self.task('inbound',[2])]},[])
        self.assertEqual(r['oneway_total'],0)
