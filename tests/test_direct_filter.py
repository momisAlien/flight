import unittest
from dataclasses import replace
from tests.test_combined_prices import CombinedPricesTests
from flightcore.combined_prices import ranking


class DirectFilterTests(unittest.TestCase):
    def test_roundtrip_requires_both_legs_and_filters_before_top20(self):
        fixture=CombinedPricesTests();fixture.setUp()
        task=fixture.task('roundtrip',[1,2,3,4])
        out='08:00ICN\n10:00NRT\n직항, 2시간'
        back='12:00NRT\n14:00ICN\n직항, 2시간'
        for row,text in zip(task['result']['observations'],[out+'\n'+back.replace('직항','경유 1'),out,'unknown',out+'\n'+back]):
            row['text']=text
        c=replace(fixture.c,direct_only=True)
        result=ranking(c,{'naver':[task],'google':[task]},[])
        self.assertEqual([r['amount'] for r in result['roundtrips']],['4'])
        self.assertEqual(result['direct_filter']['naver'],{'outside':1,'unknown':2})
        self.assertEqual(len(ranking(fixture.c,{'naver':[task]},[])['roundtrips']),4)

    def test_oneway_pairs_exclude_unknown_or_connecting_leg(self):
        fixture=CombinedPricesTests();fixture.setUp()
        out=fixture.task('outbound',[10]);back=fixture.task('inbound',[20,30])
        out['result']['observations'][0]['text']='직항'
        back['result']['observations'][0]['text']='경유 1'
        back['result']['observations'][1]['text']='직항'
        result=ranking(replace(fixture.c,direct_only=True),{'google':[out,back]},[])
        self.assertEqual([r['amount'] for r in result['oneway_combinations']],['40'])
