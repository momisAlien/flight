import unittest
from copy import deepcopy
from datetime import date
from flightcore.core import Conditions, Request
from flightcore.serde import dumps
from flightcore.observed_comparisons import page
import json

class CandidateTests(unittest.TestCase):
    def tasks(self,n=1,m=1):
        c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,10),5)
        result=[]
        for number,(kind,o,d,day,count) in enumerate([('outbound','ICN','NRT',10,n),('inbound','NRT','ICN',15,m)],1):
            request=Request(kind,o,d,date(2026,12,day))
            row={'text':f'TEST AIR\n10:00{o}\n12:00{d}\n직항, 02시간 00분\n성인/모든 결제수단\n편도\n100\n원~',
                 'seller_detail':{'payment_condition':'성인/모든 결제수단','url':'https://example.invalid',
                                  'observed_at':'2026-10-10T00:00:00+00:00',
                                  'offers':[{'seller':f'TEST ONLY {i}','amount':str(100+i)+'.25','currency':'KRW'} for i in range(count)]}}
            result.append({'number':number,'request':json.loads(dumps(request)),'status':'observed_partial','result':{'evaluated_conditions':json.loads(dumps(c)),'observations':[row]}})
        return result

    def test_full_cross_product_pagination_and_decimal_sum(self):
        tasks=self.tasks(12,13)
        first=page('naver',tasks)
        self.assertEqual((first['total'],first['pages']),(156,16))
        all_items=[x for n in range(1,17) for x in page('naver',tasks,n)['items']]
        pairs={(x['parts'][0]['offer']['seller'],x['parts'][1]['offer']['seller']) for x in all_items}
        self.assertEqual(len(pairs),156)
        self.assertEqual(first['items'][0]['displayed_sum'],'200.50')
        self.assertTrue(all(not x['rankable'] for x in all_items))
        self.assertFalse(first['rankable'])

    def test_conditions_missing_or_different_never_join(self):
        for variant in ('missing','different'):
            tasks=self.tasks()
            if variant=='missing':tasks[0]['result'].pop('evaluated_conditions')
            else:tasks[0]['result']['evaluated_conditions']['baggage']='checked_15kg'
            self.assertEqual(page('naver',tasks)['total'],0)

    def test_search_price_does_not_replace_missing_seller_detail(self):
        tasks=self.tasks();row=tasks[0]['result']['observations'][0]
        row.pop('seller_detail');row['amount']=1
        self.assertEqual(page('naver',tasks)['total'],0)

    def test_return_nights_deadline_route_and_departure_range(self):
        for change in ('nights','deadline','route','start','time'):
            tasks=self.tasks()
            if change=='nights':tasks[1]['request']['departure']='2026-12-16'
            if change=='deadline':
                for t in tasks:t['result']['evaluated_conditions']['return_deadline']='2026-12-14'
            if change=='route':tasks[1]['request']['origin']='KIX'
            if change=='start':
                for t in tasks:t['result']['evaluated_conditions']['start']='2026-12-11';t['result']['evaluated_conditions']['end']='2026-12-11'
            if change=='time':
                for t in tasks:t['result']['evaluated_conditions']['outbound_window']={'start':'13:00','end':'15:00'}
            self.assertEqual(page('naver',tasks)['total'],0,change)

    def test_invalid_prices_and_conditional_payment_excluded(self):
        for key,value in [('amount',None),('amount','NaN'),('currency','USD')]:
            tasks=self.tasks();tasks[0]['result']['observations'][0]['seller_detail']['offers'][0][key]=value
            self.assertEqual(page('naver',tasks)['total'],0)
        tasks=self.tasks();tasks[0]['result']['observations'][0]['seller_detail']['payment_condition']='성인/삼성카드'
        self.assertEqual(page('naver',tasks)['total'],0)

    def test_roundtrip_is_independent_and_source_data_unchanged(self):
        tasks=self.tasks();t=deepcopy(tasks[0]);t['request']['kind']='roundtrip';t['request']['return_date']='2026-12-15'
        t['result']['observations'][0]['text']=t['result']['observations'][0]['text'].replace('성인/','TEST AIR\n10:00NRT\n12:00ICN\n직항, 02시간 00분\n성인/').replace('편도','왕복')
        before=deepcopy(t);result=page('naver',[t])
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['kind'],'roundtrip')
        self.assertEqual(t,before)

    def test_oneways_disabled_and_invalid_page(self):
        tasks=self.tasks()
        for task in tasks:task['result']['evaluated_conditions']['compare_oneways']=False
        self.assertEqual(page('naver',tasks)['total'],0)
        for n in (0,-1,True):
            with self.assertRaises(ValueError):page('naver',tasks,n)


    def test_price_sort_matches_exhaustive_decimal_reference(self):
        from decimal import Decimal
        tasks=self.tasks(12,13)
        for task in tasks:task['result']['observations'][0]['seller_detail']['offers'].reverse()
        expected=sorted(Decimal(a['amount'])+Decimal(b['amount'])
                        for a in tasks[0]['result']['observations'][0]['seller_detail']['offers']
                        for b in tasks[1]['result']['observations'][0]['seller_detail']['offers'])
        actual=[Decimal(item['displayed_sum']) for n in range(1,17) for item in page('naver',tasks,n)['items']]
        self.assertEqual(actual,expected)
        self.assertEqual(page('naver',tasks,17)['items'],[])

    def test_roundtrip_and_oneways_share_global_price_order(self):
        tasks=self.tasks(2,2);rt=deepcopy(tasks[0]);rt['number']=3
        rt['request'].update(kind='roundtrip',return_date='2026-12-15')
        row=rt['result']['observations'][0]
        row['text']=row['text'].replace('성인/','TEST AIR\n10:00NRT\n12:00ICN\n직항, 02시간 00분\n성인/').replace('편도','왕복')
        row['seller_detail']['offers']=[{'seller':'RT TEST','amount':'201','currency':'KRW'}]
        result=page('naver',tasks+[rt])
        self.assertEqual([i['displayed_sum'] for i in result['items']],['200.50','201','201.50','201.50','202.50'])
        self.assertEqual(result['items'][1]['kind'],'roundtrip')
