import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from flightcore.server import create_app


class ReferenceApiTests(unittest.TestCase):
    def test_csrf_plan_start_status_and_cancel(self):
        c=json.loads((Path(__file__).parent.parent/'conditions.example.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            client=TestClient(create_app(folder+'/app.db'),base_url='http://127.0.0.1')
            token=client.get('/api/config').json()['csrf']
            self.assertEqual(client.post('/api/reference-plan',json={'conditions':c}).status_code,403)
            headers={'X-CSRF-Token':token}
            planned=client.post('/api/reference-plan',json={'conditions':c},headers=headers)
            self.assertEqual(planned.json()['requests'],6)
            with patch('flightcore.reference_jobs.myrealtrip.api_key',side_effect=ValueError('서버 키 미설정')):
                response=client.post('/api/reference-jobs',json={'conditions':c},headers=headers)
                self.assertEqual(response.status_code,422)
            with patch('flightcore.reference_jobs.ReferenceJobs.start',return_value='test-run'):
                self.assertEqual(client.post('/api/reference-jobs',json={'conditions':c},headers=headers).json()['id'],'test-run')
            with patch('flightcore.reference_jobs.ReferenceJobs.status',return_value={'status':'completed_references','comparison_eligible':False}):
                self.assertFalse(client.get('/api/reference-jobs/test-run').json()['comparison_eligible'])
                self.assertEqual(client.post('/api/reference-jobs/test-run/cancel',json={},headers=headers).status_code,200)
            c['passengers']['adults']=2
            self.assertEqual(client.post('/api/reference-plan',json={'conditions':c},headers=headers).status_code,422)
            client.close()
