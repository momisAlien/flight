import unittest
from dataclasses import replace
from datetime import date, time
from flightcore.core import Conditions, Request, TimeWindow
from flightcore.observed_schedules import assess

TEXT = '에어부산\n15:35ICN\n18:10NRT\n직항, 02시간 35분\n피치항공\n08:30NRT\n11:50ICN\n직항, 03시간 20분\n성인/모든 결제수단\n왕복\n273,892\n원~'
GOOGLE = '왕복 총 가격은 최저 270497 대한민국 원입니다. 에어부산의 직항 항공편입니다. 목요일, 12월 10 오후 3:35에 인천국제공항에서 출발하여 목요일, 12월 10 오후 6:10에 나리타 국제 공항에 도착합니다. 총 비행 시간은 2시간 35분입니다. 항공편 선택'


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.req = Request('roundtrip', 'ICN', 'NRT', date(2026,12,10), date(2026,12,15))
        self.c = Conditions(('ICN',), ('NRT',), date(2026,12,10), date(2026,12,10), 5)

    def test_naver_roundtrip_actual_nights_and_unknown_technical_stop(self):
        result = assess('naver', {'text': TEXT}, self.req, self.c)
        self.assertEqual(result['actual_nights'], 5)
        self.assertEqual(len(result['legs']), 2)
        self.assertEqual(result['legs'][0]['departure'], '2026-12-10T15:35:00+09:00')
        self.assertFalse(result['comparison_eligible'])
        self.assertEqual(result['status'], 'unverified')

    def test_cheongju_example_origin_can_be_parsed_for_both_sources(self):
        req=replace(self.req,origin='CJJ',return_destination='CJJ')
        c=replace(self.c,origins=('CJJ',))
        self.assertEqual(len(assess('naver',{'text':TEXT.replace('ICN','CJJ')},req,c)['legs']),2)
        result=assess('google',{'text':GOOGLE.replace('인천국제공항','청주국제공항')},req,c)
        self.assertEqual(result['legs'][0]['origin'],'CJJ')
        self.assertFalse(result['comparison_eligible'])

    def test_time_duration_and_return_deadline_rejections(self):
        c = replace(self.c, outbound_window=TimeWindow(time(6),time(12)),
                    max_duration_minutes=180, return_deadline=date(2026,12,14))
        result = assess('naver', {'text': TEXT}, self.req, c)
        self.assertEqual(result['status'], 'excluded')
        self.assertEqual(len(result['reasons']), 3)

    def test_google_roundtrip_is_not_a_complete_itinerary(self):
        result = assess('google', {'text': GOOGLE}, self.req, self.c)
        self.assertEqual(len(result['legs']), 1)
        self.assertTrue(any('귀국편 선택 전' in x for x in result['unknown']))
        self.assertNotIn('actual_nights', result)

    def test_unknown_airport_wrong_route_and_duration_fail_closed(self):
        for text in [TEXT.replace('NRT','LAX'), TEXT.replace('18:10','17:10'),TEXT.replace('15:35','25:35')]:
            result = assess('naver', {'text':text}, self.req, self.c)
            self.assertEqual(result['status'], 'unverified')
            self.assertEqual(result['legs'], [])

    def test_overnight_arrival_changes_nights(self):
        text = TEXT.replace('15:35ICN\n18:10NRT','23:35ICN\n02:10NRT\n+1일')
        result = assess('naver', {'text':text}, self.req, self.c)
        self.assertEqual(result['actual_nights'], 4)
        self.assertEqual(result['status'], 'excluded')

    def test_google_new_year_and_midnight(self):
        text = GOOGLE.replace('12월 10 오후 3:35','12월 31 오후 9:35').replace('12월 10 오후 6:10','1월 1 오전 12:10')
        req = replace(self.req, departure=date(2026,12,31))
        result = assess('google', {'text':text}, req)
        self.assertEqual(result['legs'][0]['arrival'], '2027-01-01T00:10:00+09:00')

    def test_missing_offset_is_not_invented(self):
        text = TEXT.replace('15:35ICN\n18:10NRT','23:35ICN\n02:10NRT')
        self.assertEqual(assess('naver', {'text':text}, self.req)['legs'], [])


if __name__ == '__main__': unittest.main()
