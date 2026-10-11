import unittest
from flightcore.naver_policies import parse_policy,collect_policies
from unittest.mock import Mock
from flightcore.provider_probe import ProbeStopped

TEXT='항공권 규정\n환불/취소\n수하물\nBX0265 인천국제공항 - 나리타국제공항\n타입\t수량 (무게)\n기내 수하물\t정보확인필요\n위탁 수하물\t1pc, 15kg\n기내 수하물 :\n설명\n마일리지'

class PolicyTests(unittest.TestCase):
    def test_segment_and_unknown_cabin_retained(self):
        p=parse_policy(TEXT)
        self.assertEqual(p['status'],'observed')
        self.assertEqual(p['segments'][0]['flight_number'],'BX0265')
        self.assertEqual(p['segments'][0]['checked']['pieces'],1)
        self.assertEqual(p['segments'][0]['cabin']['status'],'unverified')
        self.assertFalse(p['segments'][0]['checked']['allowance_verified'])
        self.assertFalse(p['comparison_eligible'])

    def test_selenium_newline_table_format(self):
        self.assertEqual(parse_policy(TEXT.replace('\t','\n'))['status'],'observed')

    def test_unknown_or_conditional_quantity_is_not_guessed(self):
        for value in ('0pc, 15kg','1pc, 15kg 일부구간','정보확인필요'):
            p=parse_policy(TEXT.replace('1pc, 15kg',value))
            self.assertIsNone(p['segments'][0]['checked']['pieces'])

    def test_multiple_segments_do_not_merge(self):
        block=TEXT.split('수하물\n',1)[1].split('기내 수하물 :')[0]
        p=parse_policy(TEXT.replace('기내 수하물 :',block.replace('BX0265','BX0266').replace('15kg','20kg')+'기내 수하물 :'))
        self.assertEqual([s['checked']['displayed_weight_kg'] for s in p['segments']],['15','20'])

    def test_extra_unparsed_segment_blocks_whole_parse(self):
        self.assertEqual(parse_policy(TEXT.replace('기내 수하물 :','다른 구간 미지원\n기내 수하물 :'))['status'],'unverified')
        self.assertEqual(parse_policy('수하물 정보 없음')['status'],'unverified')

    def test_access_stop_propagates_before_any_click(self):
        collector=Mock();collector.check.side_effect=ProbeStopped('access_stopped','blocked')
        with self.assertRaises(ProbeStopped):collect_policies(collector,{'url':'https://flight.naver.com','offers':[{'seller':'TEST'}]})
        collector.driver.find_elements.assert_not_called()

    def test_duplicate_seller_is_not_selected(self):
        c=Mock();c.driver.current_url='https://flight.naver.com'
        a=Mock();a.is_displayed.return_value=True;a.get_attribute.return_value='TEST에서 예약'
        c.driver.find_elements.side_effect=[[],[a,a]]
        d=collect_policies(c,{'url':c.driver.current_url,'offers':[{'seller':'TEST'}]})
        self.assertEqual(d['offers'][0]['fare_policy']['status'],'ambiguous_seller')
        a.find_element.assert_not_called()
