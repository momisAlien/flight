from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from flightcore.server import create_app


class BrowserApiTests(unittest.TestCase):
    def test_plan_csrf_and_reject_unsupported_before_start(self):
        c=json.loads((Path(__file__).parent.parent/'conditions.example.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(folder+'/app.db'),base_url='http://127.0.0.1') as client:
                body={'conditions':c,'provider':'google'}
                self.assertEqual(client.post('/api/browser-plan',json=body).status_code,403)
                headers={'X-CSRF-Token':client.get('/api/config').json()['csrf']}
                self.assertEqual(client.post('/api/browser-plan',json=body,headers=headers).json()['queries'],396)
                body['provider']='naver'
                self.assertEqual(client.post('/api/browser-plan',json=body,headers=headers).json()['queries'],396)
                c['compare_oneways']=False
                self.assertEqual(client.post('/api/browser-plan',json=body,headers=headers).json()['queries'],132)
                with patch('flightcore.server.BrowserJobs.start',return_value='mock') as start:
                    self.assertEqual(client.post('/api/browser-jobs',json=body,headers=headers).json()['id'],'mock')
                    start.assert_called_once()
                self.assertEqual(client.get('/api/browser-jobs/nonexistent').status_code,422)
                self.assertEqual(client.post('/api/browser-jobs/mock/details',json={}).status_code,403)
                self.assertEqual(client.post('/api/browser-jobs/mock/resume-details',json={}).status_code,403)
                with patch('flightcore.server.BrowserJobs.resume_pending_details',return_value='mock') as resume:
                    self.assertEqual(client.post('/api/browser-jobs/mock/resume-details',json={},headers=headers).json()['id'],'mock')
                    resume.assert_called_once_with('mock')
                with patch('flightcore.server.BrowserJobs.start_details',return_value='mock') as detail_start:
                    self.assertEqual(client.post('/api/browser-jobs/mock/details',json={},headers=headers).json()['id'],'mock')
                    detail_start.assert_called_once_with('mock')
                with patch('flightcore.server.BrowserJobs.detail_plan',return_value={'count':2,'candidates':[(1,0),(1,1)]}):
                    self.assertEqual(client.get('/api/browser-jobs/mock/detail-plan').json(),{'count':2})


if __name__=='__main__':unittest.main()

class PriceSummaryApiTests(unittest.TestCase):
    def test_saved_search_prices_reach_api_without_detail_or_mutation(self):
        import sqlite3
        from contextlib import closing
        from test_search_price_summary import SearchPriceTests
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/app.db'
            with TestClient(create_app(path),base_url='http://127.0.0.1') as client:
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',('prices','google','completed_observations',3,''))
                    for task in SearchPriceTests().tasks():
                        db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',('prices',task['number'],json.dumps(task['request']),task['status'],json.dumps(task['result'])))
                response=client.get('/api/browser-jobs/prices/price-summary')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['comparisons'][0]['two_oneways'],'170.20')
                self.assertEqual(client.get('/api/browser-jobs/missing/price-summary').status_code,422)
                with closing(sqlite3.connect(path)) as db, db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_details').fetchone()[0],0)
