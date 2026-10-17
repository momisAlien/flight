import unittest
from dataclasses import replace
from datetime import date, time
from flightcore.core import Conditions, TimeWindow
from flightcore.departure_filter import check
from flightcore.combined_prices import ranking
from flightcore.combined_jobs import reference_reason

class DepartureFilterTests(unittest.TestCase):
    def setUp(self):
        self.c=Conditions(('ICN',),('NRT',),date(2027,1,18),date(2027,1,18),6,outbound_window=TimeWindow(time(20),time(6)),inbound_window=TimeWindow(time(9),time(12)))
        self.req=dict(kind='roundtrip',origin='ICN',destination='NRT',departure='2027-01-18',return_date='2027-01-24')
        self.text='20:40ICN\n22:25NRT\n09:50NRT\n11:55ICN'
    def test_routes_overnight_and_boundaries(self):
        self.assertEqual(check(self.c,'naver',self.req,self.text),'matched')
        self.assertEqual(check(self.c,'naver',self.req,self.text.replace('20:40','06:00')),'matched')
        self.assertEqual(check(self.c,'naver',self.req,self.text.replace('20:40','06:01')),'outside')
        self.assertEqual(check(self.c,'naver',self.req,self.text.replace('09:50','12:01')),'outside')
        self.assertEqual(check(self.c,'naver',self.req,self.text.replace('NRT','KIX')),'unknown')
    def test_google_missing_return_and_ampm(self):
        text='1월 18 오후 8:40에 인천에서 출발하여'
        self.assertEqual(check(self.c,'google',self.req,text),'unknown')
        self.assertEqual(check(replace(self.c,inbound_window=None),'google',self.req,text),'matched')
        self.assertEqual(check(self.c,'google',dict(self.req,kind='inbound'),text),'outside')
        self.assertEqual(check(self.c,'google',dict(self.req,kind='inbound'),text.replace('오후 8:40','오전 9:00')),'matched')
    def test_ranking_filters_before_top20_and_pairs(self):
        tasks=[]
        for i,text in enumerate([self.text,self.text.replace('20:40','13:00'),'unknown']):
            tasks.append(dict(number=i,status='observed_partial',request=self.req,result={'observations':[dict(amount=100+i,currency='KRW',text=text)]}))
        r=ranking(self.c,{'naver':tasks},[])
        self.assertEqual(r['roundtrip_total'],1)
        self.assertEqual(r['time_filter']['naver'],dict(outside=1,unknown=1))
        self.assertEqual(ranking(replace(self.c,outbound_window=None,inbound_window=None),{'naver':tasks},[])['roundtrip_total'],3)
    def test_single_day_reason(self):
        self.assertIn('2일 이상',reference_reason(self.c))

    def test_oneway_pairs_and_cached_unknowns(self):
        def task(kind, origin, destination, day, text, price):
            return dict(number=1,status='observed_partial',request=dict(kind=kind,origin=origin,destination=destination,departure=day),result={'observations':[dict(amount=price,currency='KRW',text=text)]})
        data={'naver':[task('outbound','ICN','NRT','2027-01-18','20:40ICN\n22:25NRT',100),task('inbound','NRT','ICN','2027-01-24','09:50NRT\n11:55ICN',200),task('inbound','NRT','ICN','2027-01-24','19:50NRT\n21:55ICN',1)]}
        ref={'status':'references_received','references':[dict(fromCity='ICN',toCity='NRT',departureDate='2027-01-18',returnDate='2027-01-24',totalPrice=50)]}
        result=ranking(self.c,data,[ref])
        self.assertEqual(result['oneway_total'],1)
        self.assertEqual(result['oneway_combinations'][0]['amount'],'300')
        self.assertEqual(result['time_filter']['myrealtrip']['unknown'],1)
        self.assertEqual(result['roundtrip_total'],0)
