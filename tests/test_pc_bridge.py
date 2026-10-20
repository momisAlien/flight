import tempfile
import threading
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from flightcore.pc_bridge import Bridge
from flightcore.server import create_app
from flightcore.shared_jobs import SharedJobs
from flightcore.combined_jobs import CombinedJobs
from flightcore.browser_jobs import BrowserJobs
from flightcore.reference_jobs import ReferenceJobs
from flightcore.core import Conditions


class PCBridgeTests(unittest.TestCase):
    def test_bridge_secret_and_csrf_are_both_required(self):
        with tempfile.TemporaryDirectory() as folder:
            client = TestClient(Bridge(create_app(folder+'/shared.db'), 'x'*40))
            self.assertEqual(client.get('/api/config').status_code, 401)
            headers = {'x-flight-bridge': 'x'*40, 'host': 'test.trycloudflare.com'}
            self.assertEqual(client.get('/healthz', headers=headers).json()['status'], 'online')
            config = client.get('/api/config', headers=headers)
            self.assertEqual(config.status_code, 200)
            self.assertEqual(client.post('/api/parse', json={'text': 'test'}, headers=headers).status_code, 403)
            headers['x-csrf-token'] = config.json()['csrf']
            self.assertNotEqual(client.post('/api/parse', json={'text': 'test'}, headers=headers).status_code, 403)
            self.assertEqual(client.post('/api/browser-jobs', json={}, headers=headers).status_code, 409)

    def test_fifo_cancellation_and_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            path = folder+'/shared.db'
            jobs = SharedJobs(path, BrowserJobs(path), ReferenceJobs(path))
            entered, release, second_done = threading.Event(), threading.Event(), threading.Event()
            seen = []
            def run(instance, run_id, conditions, payload):
                seen.append(run_id)
                if len(seen) == 1:
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError('test timeout')
                instance.save(run_id, 'completed', payload)
                if len(seen) == 2:
                    second_done.set()
            start = date.today()+timedelta(days=30)
            c = Conditions(('ICN',), ('NRT',), start, start, 3)
            with patch.object(CombinedJobs, 'run', run):
                first = jobs.start(c)
                self.assertTrue(entered.wait(2))
                second = jobs.start(c)
                cancelled = jobs.start(c)
                self.assertEqual(jobs.status(second)['status'], 'queued')
                self.assertEqual(jobs.status(second)['queue_position'], 1)
                jobs.cancel(cancelled)
                self.assertEqual(jobs.status(cancelled)['status'], 'cancelled')
                worker = jobs.thread
                release.set()
                self.assertTrue(second_done.wait(3))
                worker.join(3)
            self.assertEqual(seen, [first, second])
            self.assertIsNone(jobs.thread)
            with jobs.db() as db:
                db.execute("UPDATE combined_runs SET status='queued' WHERE id=?", (second,))
            restarted = SharedJobs(path, BrowserJobs(path), ReferenceJobs(path))
            self.assertEqual(restarted.status(second)['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
