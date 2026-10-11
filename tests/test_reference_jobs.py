import tempfile
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from flightcore.core import Conditions
from flightcore.reference_jobs import tasks,ReferenceJobs


class ReferenceJobTests(unittest.TestCase):
    def condition(self,days=22):
        return Conditions(('ICN','GMP','CJJ'),('NRT','HND'),date(2026,12,10),date(2026,12,10)+timedelta(days=days-1),5)

    def test_all_routes_and_dates_without_tail_loss(self):
        for days in (2,22,31,32,62,63,94):
            c=self.condition(days)
            seen=[]
            for origin,dest,start,end,nights in tasks(c):
                self.assertTrue(1 <= (end-start).days <= 30)
                seen.extend((origin,dest,start+timedelta(days=i)) for i in range((end-start).days+1))
            self.assertEqual(len(seen),6*days)
            self.assertEqual(len(set(seen)),6*days)

    def test_failure_stops_and_preserves_unsearched(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=ReferenceJobs(folder+'/db.sqlite')
            with patch('flightcore.reference_jobs.myrealtrip.api_key',return_value='test'),patch('flightcore.reference_jobs.myrealtrip.calendar',return_value={'status':'rate_limited'}) as call:
                id=jobs.start(self.condition())
                jobs.thread.join(3)
                state=jobs.status(id)
                self.assertEqual(call.call_count,1)
                self.assertEqual(state['status'],'failed_partial')
                self.assertEqual(state['not_attempted'],5)

    def test_success_is_never_live_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=ReferenceJobs(folder+'/db.sqlite')
            c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,11),5)
            with patch('flightcore.reference_jobs.myrealtrip.api_key',return_value='test'),patch('flightcore.reference_jobs.myrealtrip.calendar',return_value={'status':'no_cached_reference'}):
                id=jobs.start(c);jobs.thread.join(3)
            state=jobs.status(id)
            self.assertEqual(state['status'],'completed_references')
            self.assertFalse(state['comparison_eligible'])

    def test_cancel_keeps_already_received_result(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=ReferenceJobs(folder+'/db.sqlite')
            def receive(*args):
                jobs.cancelled.set()
                return {'status':'references_received','references':[]}
            with patch('flightcore.reference_jobs.myrealtrip.api_key',return_value='test'),patch('flightcore.reference_jobs.myrealtrip.calendar',side_effect=receive):
                id=jobs.start(self.condition());jobs.thread.join(3)
            state=jobs.status(id)
            self.assertEqual(state['status'],'cancelled_partial')
            self.assertEqual(state['completed'],1)
            self.assertEqual(state['not_attempted'],5)
