import json
import tempfile
import threading
import unittest
from datetime import date
from unittest.mock import patch
from fastapi.testclient import TestClient
from flightcore.core import Conditions
from flightcore.serde import dumps
from flightcore.browser_jobs import BrowserJobs
from flightcore.reference_jobs import ReferenceJobs
from flightcore.combined_jobs import CombinedJobs
from flightcore.server import create_app


class Collector:
    def __init__(self,provider,event):self.provider=provider
    def open(self):pass
    def close(self):pass
    def collect(self,request):
        return {'observations':[{'amount':100,'currency':'KRW','text':'TEST ONLY'}]}


class CombinedJobsTests(unittest.TestCase):
    def test_three_providers_overlap_and_cancel_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            entered={name:threading.Event() for name in ('naver','google','myrealtrip')}
            release=threading.Event()
            class BlockingCollector(Collector):
                def collect(self,request):
                    entered[self.provider].set()
                    if not release.wait(5):raise RuntimeError('concurrent start timed out')
                    return super().collect(request)
            def calendar(*args):
                entered['myrealtrip'].set()
                if not release.wait(5):raise RuntimeError('concurrent start timed out')
                return {'status':'no_cached_reference'}
            path=folder+'/test.db';browser=BrowserJobs(path,factory=BlockingCollector);reference=ReferenceJobs(path)
            jobs=CombinedJobs(path,browser,reference)
            c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,11),5)
            with patch('flightcore.myrealtrip.api_key',return_value='TEST'),patch('flightcore.myrealtrip.calendar',side_effect=calendar):
                id=jobs.start(c)
                try:
                    for name,event in entered.items():self.assertTrue(event.wait(3),name+' never started concurrently')
                    self.assertIsNot(browser.cancelled,jobs.google.cancelled)
                    self.assertIsNot(browser.thread,jobs.google.thread)
                    state=jobs.status(id)
                    for name in entered:self.assertEqual(state['providers'][name]['status'],'running')
                    jobs.cancel(id)
                finally:
                    release.set();jobs.thread.join(10)
            self.assertFalse(jobs.thread.is_alive())
            self.assertFalse(browser.thread.is_alive());self.assertFalse(jobs.google.thread.is_alive())
            state=jobs.status(id)
            self.assertEqual(state['status'],'cancelled')
            self.assertGreaterEqual(state['ranking']['roundtrip_total'],2)

    def test_cancel_keeps_received_rows_and_stops_active_suppliers(self):
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/test.db'
            class CancelCollector(Collector):
                def collect(self,request):
                    jobs.cancelled.set()
                    return super().collect(request)
            browser=BrowserJobs(path,factory=CancelCollector);reference=ReferenceJobs(path)
            jobs=CombinedJobs(path,browser,reference)
            c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,11),5)
            with patch.object(reference,'start',side_effect=ValueError('not configured')):
                id=jobs.start(c);jobs.thread.join(5)
            state=jobs.status(id)
            self.assertEqual(state['status'],'cancelled')
            self.assertIn(state['providers']['google']['status'],('pending','cancelled'))
            self.assertGreaterEqual(state['ranking']['roundtrip_total'],1)
            browser.factory=Collector
            with patch.object(reference,'start',side_effect=ValueError('not configured')),patch.object(browser.cancelled,'wait',return_value=False),patch.object(jobs.google.cancelled,'wait',return_value=False):
                next_id=jobs.start(c);jobs.thread.join(5)
            self.assertNotEqual(id,next_id)
            self.assertEqual(jobs.status(id)['ranking'],state['ranking'])
            self.assertEqual(jobs.status(next_id)['providers']['google']['completed'],6)
            self.assertEqual([x['id'] for x in jobs.history()],[next_id,id])

    def test_reference_setup_failure_preserves_both_browser_results_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/test.db';browser=BrowserJobs(path,factory=Collector);reference=ReferenceJobs(path)
            jobs=CombinedJobs(path,browser,reference)
            c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,11),5)
            with patch.object(reference,'start',side_effect=ValueError('SECRET MUST NOT LEAK')),patch.object(browser.cancelled,'wait',return_value=False),patch.object(jobs.google.cancelled,'wait',return_value=False):
                id=jobs.start(c);jobs.thread.join(10)
            self.assertFalse(jobs.thread.is_alive())
            state=jobs.status(id)
            self.assertEqual(state['status'],'completed_partial')
            self.assertEqual(state['providers']['naver']['completed'],6)
            self.assertEqual(state['providers']['google']['completed'],6)
            self.assertEqual(state['ranking']['roundtrip_total'],4)
            self.assertEqual(state['ranking']['oneway_total'],8)
            self.assertNotIn('SECRET',json.dumps(state))
            self.assertEqual(CombinedJobs(path,browser,reference).status(id)['ranking'],state['ranking'])
            with jobs.db() as db:db.execute("UPDATE combined_runs SET status='running' WHERE id=?",(id,))
            self.assertEqual(CombinedJobs(path,browser,reference).status(id)['status'],'interrupted')

    def test_preview_counts_and_csrf_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(folder+'/test.db'),base_url='http://127.0.0.1') as client:
                c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,11),5)
                body={'conditions':json.loads(dumps(c))}
                self.assertEqual(client.post('/api/combined-jobs',json=body).status_code,403)
                headers={'X-CSRF-Token':client.get('/api/config').json()['csrf']}
                self.assertEqual(client.get('/api/combined-history').json(),{'items':[]})
                preview=client.post('/api/combined-plan',json=body,headers=headers).json()
                self.assertEqual((preview['browser_queries'],preview['reference_queries']),(12,1))
                body['conditions']['end']='2026-12-10'
                preview=client.post('/api/combined-plan',json=body,headers=headers).json()
                self.assertEqual(preview['reference_queries'],1)
                self.assertEqual(preview['browser_queries'],6)
                with patch('flightcore.server.CombinedJobs.start',return_value='test') as start:
                    response=client.post('/api/combined-jobs',json={'conditions':json.loads(dumps(c))},headers=headers)
                    self.assertEqual(response.json(),{'id':'test'});start.assert_called_once()
                self.assertEqual(client.post('/api/combined-jobs/test/cancel',json={}).status_code,403)
                self.assertEqual(client.get('/api/combined-jobs/missing').status_code,422)

    def test_history_survives_restart_and_limits_listing_without_deleting_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/test.db';browser=BrowserJobs(path,factory=Collector);reference=ReferenceJobs(path)
            jobs=CombinedJobs(path,browser,reference)
            c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,11),5)
            with jobs.db() as db:
                for i in range(25):
                    db.execute('INSERT INTO combined_runs VALUES(?,?,?)',(str(i),'completed',dumps({'conditions':json.loads(dumps(c)),'providers':{}})))
            restored=CombinedJobs(path,browser,reference)
            self.assertEqual([x['id'] for x in restored.history()],[str(i) for i in range(24,4,-1)])
            self.assertEqual(restored.status('0')['status'],'completed')
