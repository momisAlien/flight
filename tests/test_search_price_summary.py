import unittest
from copy import deepcopy
from flightcore.search_price_summary import summarize,minimum

class SearchPriceTests(unittest.TestCase):
    def tasks(self):
        c={'compare_oneways':True,'baggage':'checked_15kg','cabin':'business'}
        return [{'number':i,'status':'observed_partial','request':{'kind':kind,'origin':o,'destination':d,'departure':day,**({'return_date':'2026-10-17'} if kind=='roundtrip' else {})},
                 'result':{'evaluated_conditions':c,'observed_at':'TEST','search_url':'https://example.invalid','observations':[{'amount':price,'currency':'KRW','text':'TEST ONLY','conditional':False}]}}
                for i,(kind,o,d,day,price) in enumerate([('roundtrip','ICN','NRT','2026-10-12','200.25'),('outbound','ICN','NRT','2026-10-12','80.10'),('inbound','NRT','ICN','2026-10-17','90.10')],1)]

    def test_no_detail_baggage_or_schedule_required_and_decimal_difference(self):
        result=summarize('google',self.tasks())
        self.assertEqual(result['queries_with_price'],3)
        self.assertEqual(result['comparisons'][0]['two_oneways'],'170.20')
        self.assertEqual(result['comparisons'][0]['displayed_difference'],'30.05')
        self.assertEqual(result['comparisons'][0]['lower_displayed'],'two_oneways')

    def test_failed_missing_and_zero_never_become_zero_fare(self):
        tasks=self.tasks();tasks[2]['status']='access_stopped'
        result=summarize('naver',tasks)
        self.assertIsNone(result['comparisons'][0]['two_oneways'])
        self.assertIsNone(result['comparisons'][0]['displayed_difference'])
        for value in (None,0,-1,True,'NaN','Infinity'):
            self.assertIsNone(minimum([{'amount':value,'currency':'KRW'}]))

    def test_other_date_route_or_conditions_never_join(self):
        for field,value in [('departure','2026-10-18'),('origin','HND')]:
            tasks=self.tasks();tasks[2]['request'][field]=value
            self.assertIsNone(summarize('naver',tasks)['comparisons'][0]['two_oneways'])
        tasks=self.tasks();tasks[2]['result']['evaluated_conditions']={'compare_oneways':False}
        self.assertIsNone(summarize('naver',tasks)['comparisons'][0]['two_oneways'])

    def test_all_rows_considered_and_discount_preserved(self):
        tasks=self.tasks();rows=tasks[0]['result']['observations']
        rows.extend([{'amount':300,'currency':'KRW'} for _ in range(100)])
        rows.append({'amount':1,'currency':'KRW','conditional':True,'text':'조건부 TEST'})
        result=summarize('naver',tasks)
        self.assertEqual(result['queries'][0]['minimum']['row'],101)
        self.assertTrue(result['comparisons'][0]['conditional'])
        self.assertEqual(result['comparisons'][0]['lower_displayed'],'roundtrip')

    def test_disabled_oneways_and_equal(self):
        tasks=self.tasks();tasks[0]['result']['observations'][0]['amount']='170.20'
        self.assertEqual(summarize('google',tasks)['comparisons'][0]['lower_displayed'],'equal')
        for task in tasks:task['result']['evaluated_conditions']['compare_oneways']=False
        self.assertIsNone(summarize('naver',tasks)['comparisons'][0]['two_oneways'])

    def test_no_input_mutation_and_wrong_currency(self):
        tasks=self.tasks();before=deepcopy(tasks);summarize('naver',tasks)
        self.assertEqual(tasks,before)
        self.assertIsNone(minimum([{'amount':1,'currency':'USD'}]))


    def test_failed_roundtrip_still_shows_two_successful_oneways(self):
        tasks=self.tasks();tasks[0]['status']='unverified_response'
        tasks[0]['result']={'error':'timeout','observations':[]}
        item=summarize('google',tasks)['comparisons'][0]
        self.assertIsNone(item['roundtrip'])
        self.assertEqual(item['two_oneways'],'170.20')
        self.assertIsNone(item['displayed_difference'])
