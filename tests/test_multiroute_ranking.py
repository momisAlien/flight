"""Synthetic fixtures: independently enumerate every legal route/date pair."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from flightcore.core import Conditions,plan
from flightcore.serde import dumps
from flightcore.combined_prices import ranking


class MultiRouteRankingTests(unittest.TestCase):
    def setUp(self):
        self.c=Conditions(('ICN','GMP'),('NRT','HND'),date(2026,12,10),date(2026,12,12),5)
        self.data={}
        for provider,discount in (('naver',0),('google',100)):
            self.data[provider]=[]
            for n,request in enumerate(plan(self.c),1):
                self.data[provider].append({'number':n,'status':'observed_partial','request':json.loads(dumps(request)),
                    'result':{'observations':[{'amount':str(Decimal(1000-n*10-discount+i)/100),'currency':'KRW','text':f'fixture {n} {i}'} for i in range(3)]}})

    def brute(self,c):
        all_tasks=[t for rows in self.data.values() for t in rows]
        amounts=[]
        for rt in (req for req in plan(c) if req.kind=='roundtrip'):
            left=[row for task in all_tasks if task['request']['kind']=='outbound' and task['request']['origin']==rt.origin and task['request']['destination']==rt.destination and task['request']['departure']==str(rt.departure) for row in task['result']['observations']]
            right=[row for task in all_tasks if task['request']['kind']=='inbound' and task['request']['origin']==rt.destination and task['request']['destination']==rt.origin and task['request']['departure']==str(rt.return_date) for row in task['result']['observations']]
            amounts.extend(Decimal(a['amount'])+Decimal(b['amount']) for a in left for b in right)
        return sorted(amounts)

    def test_all_routes_dates_sources_equal_independent_full_enumeration(self):
        result=ranking(self.c,self.data,[]);expected=self.brute(self.c)
        self.assertEqual(result['oneway_total'],len(expected))
        self.assertEqual(len(expected),432)
        self.assertEqual([Decimal(x['amount']) for x in result['oneway_combinations']],expected[:20])
        self.assertEqual(result['roundtrip_total'],72)
        for item in result['oneway_combinations']:
            a,b=item['outbound']['request'],item['inbound']['request']
            self.assertEqual((a['origin'],a['destination']),(b['destination'],b['origin']))
            self.assertEqual((date.fromisoformat(b['departure'])-date.fromisoformat(a['departure'])).days,5)

    def test_other_airports_dates_do_not_leak_into_narrowed_condition(self):
        c=replace(self.c,origins=('GMP',),destinations=('HND',),start=date(2026,12,12))
        result=ranking(c,self.data,[])
        self.assertEqual(result['oneway_total'],36)
        self.assertEqual([Decimal(x['amount']) for x in result['oneway_combinations']],self.brute(c)[:20])
        self.assertEqual(result['roundtrip_total'],6)

    def test_roundtrip_only_keeps_all_dates_without_oneway_combinations(self):
        result=ranking(replace(self.c,compare_oneways=False),self.data,[])
        self.assertEqual(result['roundtrip_total'],72)
        self.assertEqual(result['oneway_total'],0)
