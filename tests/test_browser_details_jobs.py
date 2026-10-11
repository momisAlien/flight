import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import date
from flightcore.browser_jobs import BrowserJobs
from flightcore.core import Request
from flightcore.serde import dumps
from flightcore.provider_probe import ProbeStopped


class DetailJobTests(unittest.TestCase):
    def seed(self,jobs):
        with jobs.db() as db:
            db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',('test','google','completed_observations',2,''))
            for n,req in enumerate([Request('roundtrip','ICN','NRT',date(2026,12,10),date(2026,12,15)),Request('outbound','ICN','NRT',date(2026,12,10))],1):
                db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',('test',n,dumps(req),'observed_partial',dumps({'observations':[{'text':'A'},{'text':'B'}]})))

    def test_all_oneway_cards_persist_and_results_survive_failure(self):
        collector=Mock()
        collector.collect.return_value={'observations':[{'text':'A'},{'text':'B'}]}
        collector.selected_google_details.side_effect=[{'offers':[]},ProbeStopped('access_stopped','blocked')]
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',lambda *a:collector);self.seed(jobs)
            self.assertEqual(jobs.detail_plan('test')['count'],2)
            self.assertEqual(jobs.detail_plan('test')['roundtrip_unsupported'],2)
            with patch.object(jobs.cancelled,'wait',return_value=False):
                jobs.start_details('test');jobs.thread.join(5)
            state=jobs.status('test')
            self.assertEqual(state['status'],'access_stopped')
            self.assertEqual(state['detail_counts'],{'access_stopped':1,'observed':1})
            self.assertIn('seller_detail',state['items'][1]['result']['observations'][0])
            self.assertEqual(state['observed'],2)
            with self.assertRaises(ValueError):jobs.start_details('test')

    def test_changed_itinerary_is_recorded_without_selecting_and_other_cards_attempted(self):
        collector=Mock();collector.collect.return_value={'observations':[{'text':'changed'}]}
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',lambda *a:collector);self.seed(jobs)
            with patch.object(jobs.cancelled,'wait',return_value=False):
                jobs.start_details('test');jobs.thread.join(5)
            self.assertEqual(jobs.status('test')['detail_counts'],{'unverified_response':2})
            self.assertEqual(jobs.status('test')['status'],'completed_partial_details')
            collector.selected_google_details.assert_not_called()
            self.assertIn('항공편 취소·매진을 뜻하지 않습니다',jobs.status('test')['items'][1]['result']['observations'][0]['detail_message'])

    def test_price_only_change_keeps_itinerary_and_records_both_prices(self):
        initial='최저가는 100000 대한민국 원입니다. 항공사 직항. 12월 10 오후 3:35 ICN NRT 항공편 선택'
        latest=initial.replace('100000','110000')
        collector=Mock()
        collector.collect.return_value={'observations':[{'text':latest,'amount':110000}],'observed_at':'TEST'}
        collector.selected_google_details.return_value={'offers':[]}
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',lambda *a:collector);self.seed(jobs)
            with jobs.db() as db:
                db.execute('UPDATE browser_tasks SET result=? WHERE n=2',(dumps({'observations':[{'text':initial,'amount':100000}]}),))
            jobs.start_details('test');jobs.thread.join(5)
            state=jobs.status('test')
            self.assertEqual(state['status'],'completed_details')
            change=state['items'][1]['result']['observations'][0]['seller_detail']['search_price_change']
            self.assertEqual((change['initial_amount'],change['latest_amount'],change['changed']),(100000,110000,True))
            collector.selected_google_details.assert_called_once()
            self.assertEqual(collector.selected_google_details.call_args.args[1],latest)

    def test_duplicate_itinerary_with_different_prices_is_not_guessed(self):
        from flightcore.browser_prices import google_itinerary_key
        first='최저가는 100 대한민국 원입니다. SAME SCHEDULE'
        second='최저가는 200 대한민국 원입니다. SAME SCHEDULE'
        self.assertEqual(google_itinerary_key(first),google_itinerary_key(second))
        collector=Mock();collector.collect.return_value={'observations':[{'text':first},{'text':second}]}
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',lambda *a:collector);self.seed(jobs)
            with jobs.db() as db:
                db.execute('UPDATE browser_tasks SET result=? WHERE n=2',(dumps({'observations':[{'text':first}]}),))
            jobs.start_details('test');jobs.thread.join(5)
            self.assertEqual(jobs.status('test')['status'],'completed_partial_details')
            collector.selected_google_details.assert_not_called()
            self.assertIn('2개 카드',jobs.status('test')['items'][1]['result']['observations'][0]['detail_message'])

    def test_restart_marks_detail_as_interrupted_without_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/test.db';jobs=BrowserJobs(path);self.seed(jobs)
            with jobs.db() as db:
                db.execute("UPDATE browser_runs SET status='running_details'")
                db.execute("INSERT INTO browser_details VALUES('test',2,0,'running',NULL)")
                db.execute("INSERT INTO browser_details VALUES('test',2,1,'pending',NULL)")
            recovered=BrowserJobs(path)
            self.assertEqual(recovered.status('test')['status'],'interrupted')
            self.assertEqual(recovered.status('test')['detail_counts'],{'interrupted':1,'pending':1})

    def test_timeout_is_preserved_for_each_card_without_claiming_success(self):
        collector=Mock();collector.collect.side_effect=ProbeStopped('unverified_response','timeout')
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',lambda *a:collector);self.seed(jobs)
            with patch.object(jobs.cancelled,'wait',return_value=False):
                jobs.start_details('test');jobs.thread.join(5)
            self.assertEqual(jobs.status('test')['detail_counts'],{'unverified_response':2})
            self.assertEqual(jobs.status('test')['status'],'completed_partial_details')
            self.assertEqual(collector.collect.call_count,2)

    def test_explicit_resume_only_pending_and_access_blocks_cannot_resume(self):
        collector=Mock()
        collector.collect.return_value={'observations':[{'text':'A'},{'text':'B'}]}
        collector.selected_google_details.return_value={'offers':[]}
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/test.db'
            jobs=BrowserJobs(path,lambda *a:collector);self.seed(jobs)
            with jobs.db() as db:
                db.execute("UPDATE browser_runs SET status='running_details'")
                db.execute("INSERT INTO browser_details VALUES('test',2,0,'running',NULL)")
                db.execute("INSERT INTO browser_details VALUES('test',2,1,'pending',NULL)")
            recovered=BrowserJobs(path,lambda *a:collector)
            collector.open.assert_not_called()
            recovered.resume_pending_details('test');recovered.thread.join(5)
            state=recovered.status('test')
            self.assertEqual(state['detail_counts'],{'interrupted':1,'observed':1})
            self.assertEqual(state['status'],'completed_partial_details')
            collector.selected_google_details.assert_called_once()
            self.assertEqual(collector.selected_google_details.call_args.args[1],'B')
            with recovered.db() as db:
                db.execute("UPDATE browser_runs SET status='access_stopped'")
                db.execute("UPDATE browser_details SET status='pending' WHERE row=0")
            with self.assertRaises(ValueError):recovered.resume_pending_details('test')
            self.assertEqual(collector.open.call_count,1)

    def test_naver_roundtrip_and_oneway_try_conditional_cards_but_keep_unknown_and_duplicates(self):
        normal='\n성인/모든 결제수단\n왕복\n100\n원'
        rows=[{'text':'unique'+normal,'conditional':False},{'text':'card\n성인/TEST카드\n왕복\n50\n원','conditional':True},
              {'text':'unknown','conditional':True},
              {'text':'duplicate'+normal,'conditional':False},{'text':'CO2 10%\nduplicate'+normal,'conditional':False}]
        collector=Mock();collector.collect.return_value={'observations':rows}
        collector.selected_naver_details.return_value={'offers':[],'payment_condition':'성인/모든 결제수단'}
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db',lambda *a:collector);self.seed(jobs)
            with jobs.db() as db:
                db.execute("UPDATE browser_runs SET provider='naver'")
                db.execute('UPDATE browser_tasks SET result=?',(dumps({'observations':rows}),))
            preview=jobs.detail_plan('test')
            self.assertEqual((preview['count'],preview['unsupported_payment'],preview['ambiguous_card']),(4,2,4))
            self.assertEqual(preview['conditional_cards'],2)
            with patch.object(jobs.cancelled,'wait',return_value=False):
                jobs.start_details('test');jobs.thread.join(5)
            state=jobs.status('test')
            self.assertEqual(state['detail_counts'],{'observed':4,'unsupported_payment':2,'ambiguous_card':4})
            self.assertEqual(state['status'],'completed_partial_details')
            collector.selected_google_details.assert_not_called()
            self.assertEqual(collector.selected_naver_details.call_args_list[0].args[0].return_date,date(2026,12,15))

    def test_naver_payment_change_is_navigation_only_and_records_noncomparable_prices(self):
        original='AIRLINE\n07:35ICN\n10:15NRT\n성인/모든 결제수단\n편도\n100\n원'
        latest=original.replace('모든 결제수단','TEST카드').replace('\n100\n','\n80\n')
        collector=Mock()
        collector.collect.return_value={'observations':[{'text':latest,'amount':80}],'observed_at':'TEST'}
        collector.selected_naver_details.return_value={'payment_condition':'성인/모든 결제수단','offers':[{'amount':110}]}
        req=dumps(Request('outbound','ICN','NRT',date(2026,12,10)))
        result=dumps({'observations':[{'text':original,'amount':100}]})
        detail=BrowserJobs.collect_detail(collector,'naver',req,result,0)
        self.assertFalse(detail['search_price_change']['same_search_condition'])
        self.assertEqual(detail['search_payment_transition']['latest'],'성인/TEST카드')
        self.assertEqual(detail['offers'][0]['amount'],110)
        collector.selected_naver_details.return_value={'payment_condition':'성인/TEST카드','offers':[{'amount':80}]}
        with self.assertRaises(ProbeStopped):BrowserJobs.collect_detail(collector,'naver',req,result,0)

    def test_naver_multiple_payment_cards_for_same_navigation_are_not_guessed(self):
        label='AIRLINE\n성인/모든 결제수단\n왕복\n100\n원'
        other=label.replace('모든 결제수단','TEST카드')
        collector=Mock();collector.collect.return_value={'observations':[{'text':label},{'text':other}]}
        req=dumps(Request('roundtrip','ICN','NRT',date(2026,12,10),date(2026,12,15)))
        with self.assertRaises(ProbeStopped):
            BrowserJobs.collect_detail(collector,'naver',req,dumps({'observations':[{'text':label}]}),0)
        collector.selected_naver_details.assert_not_called()
