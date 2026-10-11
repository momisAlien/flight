import tempfile
import threading
import unittest
from datetime import date,timedelta
from unittest.mock import Mock,patch

from flightcore.browser_prices import BrowserCollector,google_row,naver_row,validate,search_url,naver_itinerary_key,naver_navigation_key,naver_card_header
from flightcore.browser_jobs import BrowserJobs
from flightcore.core import Conditions,Request,plan
from flightcore.provider_probe import ProbeStopped


GOOGLE='왕복 총 가격은 최저 270497 대한민국 원입니다. 에어부산의 직항 항공편입니다. 다구간 항공권. 이 운항 일정의 각 항공권을 따로 구입합니다.. 항공편 선택'
NAVER='에어부산\n15:35ICN\n18:10NRT\n직항, 02시간 35분\n피치항공\n08:30NRT\n11:50ICN\n직항, 03시간 20분\n성인/모든 결제수단\n왕복\n273,892\n원~'


class BrowserPriceTests(unittest.TestCase):
    def test_google_error_page_is_not_waited_on_or_treated_as_no_flights(self):
        collector=BrowserCollector('google',threading.Event(),Mock())
        collector.check=Mock(return_value='죄송합니다. 오류가 발생했습니다.\n새로고침')
        collector.visible_cards=Mock(return_value=[])
        with self.assertRaises(ProbeStopped) as error:
            collector.collect(Request('outbound','ICN','NRT',date(2026,12,10)))
        self.assertEqual(error.exception.status,'unverified_response')
        self.assertIn('Google 검색 화면에서 오류',error.exception.detail)
        collector.check.assert_called_once_with(fast=True)

    def test_google_completed_results_override_stale_loading_announcement_only(self):
        from flightcore.browser_prices import search_loading
        body='결과 로드 중\n검색 결과\n결과 33개가 반환되었습니다.'
        self.assertFalse(search_loading('google',body))
        self.assertTrue(search_loading('google','결과 로드 중'))
        self.assertTrue(search_loading('google','결과 로드 중\n결과 0개가 반환되었습니다.'))
        self.assertTrue(search_loading('naver',body))
        self.assertFalse(search_loading('google','결과 로드 중',has_cards=True))
        self.assertTrue(search_loading('naver','항공편 검색중',has_cards=True))

    def condition(self):
        start=date.today()+timedelta(days=30)
        return Conditions(('ICN','GMP'),('NRT','HND'),start,start+timedelta(days=1),5)

    def test_separate_tickets_not_single_roundtrip(self):
        row=google_row(GOOGLE)
        self.assertEqual(row['amount'],270497)
        self.assertEqual(row['ticket_kind'],'separate_tickets')
        self.assertFalse(row['comparison_eligible'])
        self.assertEqual(google_row(GOOGLE.replace('다구간 항공권. 이 운항 일정의 각 항공권을 따로 구입합니다.. ',''))['ticket_kind'],'unverified')

    def test_naver_card_conditions_preserved(self):
        ordinary=naver_row(NAVER)
        conditional=naver_row(NAVER.replace('모든 결제수단','하나카드(이용실적 충족시)'))
        self.assertFalse(ordinary['conditional'])
        self.assertTrue(conditional['conditional'])
        self.assertEqual(ordinary['ticket_kind'],'unverified')
        self.assertFalse(ordinary['comparison_eligible'])
        with self.assertRaises(ValueError):naver_row(NAVER+'\n왕복\n1,000\n원~')

    def test_co2_badge_is_not_identity_but_airline_schedule_payment_and_stops_are(self):
        decorated=NAVER.replace('피치항공','CO2 36%\n피치항공')
        self.assertEqual(naver_itinerary_key(NAVER),naver_itinerary_key(decorated))
        self.assertEqual(naver_itinerary_key(NAVER),naver_itinerary_key(decorated.replace('273,892','300,000')))
        for before,after in [('피치항공','다른항공사'),('08:30NRT','08:40NRT'),('모든 결제수단','카드 할인'),('직항','경유 1')]:
            self.assertNotEqual(naver_itinerary_key(NAVER),naver_itinerary_key(decorated.replace(before,after)))

    def test_navigation_can_ignore_payment_but_never_proves_equal_fares(self):
        discounted=NAVER.replace('모든 결제수단','TEST카드').replace('273,892','200,000')
        self.assertEqual(naver_navigation_key(NAVER),naver_navigation_key(discounted))
        self.assertNotEqual(naver_itinerary_key(NAVER),naver_itinerary_key(discounted))
        for before,after in [('피치항공','다른항공사'),('08:30NRT','08:40NRT'),('직항','경유 1')]:
            self.assertNotEqual(naver_navigation_key(NAVER),naver_navigation_key(discounted.replace(before,after)))
        with self.assertRaises(ValueError):naver_navigation_key(NAVER+'\n성인/TEST카드')

    def test_expanded_header_drops_options_and_transient_hint_without_losing_route(self):
        original='예약 많은\n'+NAVER.replace('피치항공','상세 여정을 확인해보세요\n피치항공')
        expanded=NAVER+'\n성인/TEST카드\n왕복\n100,000\n원~'
        self.assertEqual(naver_navigation_key(original),naver_navigation_key(naver_card_header(expanded)))
        self.assertEqual(naver_navigation_key(original+'\n로그인 후 특가확인'),naver_navigation_key(naver_card_header(expanded)))

    def test_discount_detail_is_never_read_as_all_payment_seller_prices(self):
        req=Request('outbound','ICN','NRT',date(2026,12,10))
        driver=Mock();driver.current_url=search_url('naver',req).replace('/international/','/international/detail/')
        cancel=Mock();cancel.wait.return_value=False
        collector=BrowserCollector('naver',cancel,driver,timeout=1)
        collector.check=Mock(return_value='항공권 판매사 선택\n성인/TEST카드\n100,000원')
        with patch('flightcore.browser_prices.time.monotonic',side_effect=[0,0,2]):
            with self.assertRaises(ProbeStopped) as failure:collector.read_naver_sellers(req,NAVER)
        self.assertEqual(failure.exception.status,'unverified_response')
        driver.find_elements.assert_not_called()

    def test_general_payment_option_can_be_beyond_more_without_selecting_discount(self):
        req=Request('roundtrip','ICN','NRT',date(2026,12,10),date(2026,12,15))
        label=NAVER.replace('모든 결제수단','TEST카드')
        driver=Mock();driver.current_url=search_url('naver',req)
        cancel=Mock();cancel.wait.return_value=False
        collector=BrowserCollector('naver',cancel,driver)
        collector.check=Mock(return_value='')
        card=Mock();collector.visible_cards=Mock(return_value=[{'element':card,'text':label}])
        discount=Mock();discount.is_displayed.return_value=True
        discount.find_element.return_value.text='성인/TEST카드\n왕복\n100\n원'
        regular=Mock();regular.is_displayed.return_value=True
        regular.find_element.return_value.text='성인/모든 결제수단\n왕복\n120\n원'
        more=Mock();more.is_displayed.return_value=True;more.text='5개요금조건 더보기'
        expanded=[]
        more.send_keys.side_effect=lambda *args:expanded.append(True)
        card.find_elements.side_effect=lambda how,selector: ([more] if how=='tag name' else [discount,regular] if expanded else [discount])
        collector.read_naver_sellers=Mock(return_value={'payment_condition':'성인/모든 결제수단'})
        result=collector.selected_naver_details(req,label)
        more.send_keys.assert_called_once();regular.send_keys.assert_called_once();discount.send_keys.assert_not_called()
        self.assertEqual(result['search_payment_condition'],'성인/TEST카드')

    def test_unsupported_options_rejected_before_requests(self):
        c=self.condition()
        validate(c,'naver')
        from dataclasses import replace
        for c in (replace(c,arrival_expansion=True),replace(c,baggage='20kg'),replace(c,destinations=('ICN',))):
            with self.assertRaises(ValueError):validate(c,'google')

    def test_google_ow_and_rt_have_different_queries(self):
        rt,ow,_=list(plan(self.condition()))[:3]
        self.assertNotEqual(search_url('google',rt),search_url('google',ow))
        self.assertIn('curr=KRW',search_url('google',rt))
        self.assertNotEqual(search_url('naver',rt),search_url('naver',ow))
        self.assertEqual(naver_row(NAVER.replace('왕복','편도'))['price_scope'],'oneway_from')

    def test_access_screen_stops_without_interaction(self):
        driver=Mock();driver.current_url='https://www.google.com/sorry/index'
        collector=BrowserCollector('google',threading.Event(),driver)
        with self.assertRaises(ProbeStopped):collector.check()
        driver.find_element.assert_not_called()

    def test_login_link_alone_is_not_a_block(self):
        driver=Mock();driver.current_url='https://www.google.com/travel/flights/search'
        driver.find_element.return_value.text='로그인\n검색 결과'
        driver.find_elements.return_value=[]
        self.assertIn('검색 결과',BrowserCollector('google',threading.Event(),driver).check())

    def test_fast_naver_control_read_still_stops_block_text_and_visible_captcha(self):
        driver=Mock();driver.current_url='https://flight.naver.com/flights/international/ICN-NRT-20261210'
        driver.execute_script.return_value='access denied'
        driver.find_elements.return_value=[]
        collector=BrowserCollector('naver',threading.Event(),driver)
        with self.assertRaises(ProbeStopped) as failure:collector.check(fast=True)
        self.assertEqual(failure.exception.status,'access_stopped')
        driver.find_element.assert_not_called()
        driver.execute_script.return_value='검색 결과'
        captcha=Mock();captcha.is_displayed.return_value=True
        driver.find_elements.return_value=[captcha]
        with self.assertRaises(ProbeStopped) as failure:collector.check(fast=True)
        self.assertEqual(failure.exception.status,'access_stopped')
        self.assertIn('input[type="password"]',driver.find_elements.call_args.args[1])

    def test_navigation_timeout_is_local_but_access_block_has_priority(self):
        from selenium.common.exceptions import TimeoutException
        driver=Mock();driver.get.side_effect=TimeoutException('TEST')
        driver.current_url='https://flight.naver.com/flights/international/ICN-NRT-20261210'
        driver.find_element.return_value.text='검색 중'
        driver.find_elements.return_value=[]
        collector=BrowserCollector('naver',threading.Event(),driver)
        with self.assertRaises(ProbeStopped) as failure:collector.collect(next(plan(self.condition())))
        self.assertEqual(failure.exception.status,'unverified_response')
        driver.find_element.return_value.text='access denied'
        with self.assertRaises(ProbeStopped) as failure:collector.collect(next(plan(self.condition())))
        self.assertEqual(failure.exception.status,'access_stopped')

    def test_price_collection_is_partial_even_after_stable_rows(self):
        driver=Mock();driver.current_url='https://www.google.com/travel/flights/search'
        driver.find_element.return_value.text='검색 결과'
        row=Mock();row.is_displayed.return_value=True;row.get_attribute.return_value=GOOGLE
        driver.find_elements.side_effect=lambda how,selector: [] if 'iframe' in selector else [row]
        driver.execute_script.side_effect=lambda script,*args: '검색 결과' if script=='return document.body.innerText' else [{'element':row,'text':GOOGLE}]
        cancel=Mock();cancel.is_set.return_value=False;cancel.wait.return_value=False
        collector=BrowserCollector('google',cancel,driver)
        result=collector.collect(next(plan(self.condition())))
        self.assertFalse(result['inventory_complete'])
        self.assertFalse(result['comparison_eligible'])
        self.assertEqual(len(result['observations']),1)

    def test_google_fast_body_still_stops_at_access_block(self):
        driver=Mock();driver.current_url='https://www.google.com/travel/flights/search'
        driver.execute_script.return_value='access denied'
        c=BrowserCollector('google',threading.Event(),driver)
        with self.assertRaises(ProbeStopped) as failure:c.check(fast=True)
        self.assertEqual(failure.exception.status,'access_stopped')

    def test_all_queries_persisted_and_failed_job_does_not_skip_to_next_date(self):
        collector=Mock();collector.collect.side_effect=ProbeStopped('access_stopped','중단')
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',factory=lambda *a:collector)
            id=jobs.start(self.condition(),'google');jobs.thread.join(3)
            state=jobs.status(id)
            self.assertEqual(state['total'],24)
            self.assertEqual(state['not_attempted'],23)
            self.assertEqual(state['observed'],0)
            self.assertEqual(state['status'],'access_stopped')
            self.assertEqual(collector.collect.call_count,1)
            collector.close.assert_called_once()
            pages=[jobs.status(id,page)['items'] for page in (1,2,3)]
            self.assertEqual(sum(len(p) for p in pages),24)

    def test_cancellation_retains_observation_and_old_cancel_does_not_cancel_new_job(self):
        with tempfile.TemporaryDirectory() as folder:
            collector=Mock()
            jobs=BrowserJobs(folder+'/test.db',factory=lambda *a:collector)
            def collect(request):
                jobs.cancelled.set()
                return {'observations':[google_row(GOOGLE)]}
            collector.collect.side_effect=collect
            id=jobs.start(self.condition(),'google');jobs.thread.join(3)
            self.assertEqual(jobs.status(id)['observed'],1)
            self.assertEqual(jobs.status(id)['not_attempted'],23)
            jobs.cancelled.clear();jobs.active_id='new-job'
            jobs.cancel(id)
            self.assertFalse(jobs.cancelled.is_set())

    def test_search_failure_keeps_all_dates_and_successful_details_available(self):
        collector=Mock()
        results=[{'observations':[google_row(GOOGLE)]} for _ in range(22)]
        collector.collect.side_effect=[ProbeStopped('unverified_response','search timeout'),
                                       ProbeStopped('schema_changed','changed card'),*results]
        collector.selected_google_details.return_value={'offers':[]}
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',factory=lambda *a:collector)
            with patch.object(jobs.cancelled,'wait',return_value=False):
                id=jobs.start(self.condition(),'google');jobs.thread.join(5)
            state=jobs.status(id)
            self.assertEqual(state['status'],'completed_partial_observations')
            self.assertEqual((state['observed'],state['failed_queries'],state['not_attempted']),(22,2,0))
            self.assertEqual(collector.collect.call_count,24)
            self.assertEqual(state['items'][0]['result']['error'],'search timeout')
            self.assertEqual(state['items'][0]['result']['observations'],[])
            preview=jobs.detail_plan(id)
            self.assertEqual((preview['count'],preview['failed_queries']),(15,2))
            collector.collect.side_effect=None
            collector.collect.return_value={'observations':[google_row(GOOGLE)]}
            with patch.object(jobs.cancelled,'wait',return_value=False):
                jobs.start_details(id);jobs.thread.join(5)
            self.assertEqual(jobs.status(id)['status'],'completed_partial_details')
            self.assertEqual(jobs.status(id)['detail_counts'],{'observed':15})

    def test_access_block_after_timeout_still_stops_remaining_queries(self):
        collector=Mock()
        collector.collect.side_effect=[ProbeStopped('unverified_response','timeout'),ProbeStopped('access_stopped','blocked')]
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',factory=lambda *a:collector)
            with patch.object(jobs.cancelled,'wait',return_value=False):
                id=jobs.start(self.condition(),'naver');jobs.thread.join(5)
            state=jobs.status(id)
            self.assertEqual(state['status'],'access_stopped')
            self.assertEqual(state['not_attempted'],22)
            self.assertEqual(collector.collect.call_count,2)
            with self.assertRaises(ValueError):jobs.detail_plan(id)

    def test_restart_retains_results_and_reports_interrupted_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/test.db';jobs=BrowserJobs(path)
            with jobs.db() as db:
                db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',('old','google','running',1,''))
                db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',('old',1,'{}','running',None))
            recovered=BrowserJobs(path).status('old')
            self.assertEqual(recovered['status'],'interrupted')
            self.assertEqual(recovered['items'][0]['status'],'interrupted')


if __name__=='__main__':unittest.main()
