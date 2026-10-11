import unittest
import tempfile
import json
from copy import deepcopy
from flightcore.comparison_readiness import audit
from flightcore.browser_jobs import BrowserJobs


class ReadinessTests(unittest.TestCase):
    def row(self):
        return {'schedule': {'legs': [{}], 'reasons': []}, 'seller_detail': {
            'offers': [{'seller': 'TEST ONLY', 'currency': 'KRW', 'amount': 100}],
            'observed_at': '2026-10-09T06:33:29+00:00', 'url': 'https://example.invalid',
            'payment_condition': '성인/모든 결제수단'}}

    def codes(self, result):
        return {x['code']: x['state'] for x in result['checks']}

    def test_search_price_alone_is_not_seller_price(self):
        result = audit('naver', {}, {'amount': 123, 'conditional': False})
        self.assertEqual(result['priced_seller_options'], 0)
        self.assertEqual(self.codes(result)['payment'], 'missing')
        self.assertFalse(result['comparison_eligible'])

    def test_page_wide_confirmations_cannot_certify_fares(self):
        row = self.row()
        row['seller_detail'].update(baggage_allowance_verified=True,
            taxes_and_mandatory_fees_stated_included=True, comparison_eligible=True)
        row['seller_detail']['baggage_statements'] = ['무료 수하물']
        before = deepcopy(row)
        result = audit('naver', {}, row)
        self.assertEqual(result['priced_seller_options'], 1)
        for code in ('baggage', 'total_fees', 'passenger_cabin', 'intermediate_stops', 'comparison_adapter'):
            self.assertEqual(self.codes(result)[code], 'missing')
        self.assertFalse(result['comparison_eligible'])
        self.assertEqual(row, before)

    def test_invalid_prices_not_counted_and_no_top_n(self):
        row = self.row()
        row['seller_detail']['offers'] *= 121
        row['seller_detail']['offers'] += [{'seller':'TEST', 'currency':'KRW', 'amount':x} for x in (None, True, 0, -1, 'NaN', 'Infinity', 'bad')]
        row['seller_detail']['offers'] += [{'seller':'TEST','currency':'USD','amount':1}, {'currency':'KRW','amount':1}]
        result = audit('naver', {}, row)
        self.assertEqual(result['priced_seller_options'], 121)
        self.assertEqual(result['unpriced_seller_options'], 9)

    def test_excluded_schedule_overrides_observed_price(self):
        row = self.row(); row['schedule']['reasons'] = ['한국 도착 마감 초과']
        result = audit('naver', {}, row)
        self.assertEqual(result['status'], 'excluded')
        self.assertEqual(self.codes(result)['schedule'], 'excluded')

    def test_return_requires_two_legs_and_journey_reason_differs(self):
        one = audit('naver', {}, self.row())
        two = audit('naver', {'return_date':'2026-12-15'}, self.row())
        self.assertEqual(self.codes(two)['schedule'], 'missing')
        self.assertNotEqual(one['checks'][-2]['label'], two['checks'][-2]['label'])

    def test_provenance_requires_timezone_and_safe_url(self):
        for field, value in [('observed_at','2026-10-09T06:33:29'), ('url','https://user:pass@example.invalid'), ('url','javascript:alert(1)')]:
            row=self.row(); row['seller_detail'][field]=value
            self.assertEqual(self.codes(audit('naver',{},row))['provenance'],'missing')

    def test_google_does_not_inherit_naver_payment_confirmation(self):
        self.assertEqual(self.codes(audit('google',{},self.row()))['payment'],'missing')

    def test_saved_job_diagnostic_does_not_rewrite_database(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=BrowserJobs(folder+'/test.db')
            raw=json.dumps({'observations':[self.row()]})
            with jobs.db() as db:
                db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',('test','naver','completed_observations',1,''))
                db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',('test',1,'{}','observed_partial',raw))
            result=jobs.status('test')['items'][0]['result']['observations'][0]
            self.assertEqual(result['comparison_readiness']['priced_seller_options'],1)
            with jobs.db() as db:
                self.assertEqual(db.execute('SELECT result FROM browser_tasks').fetchone()[0],raw)

if __name__ == '__main__':
    unittest.main()
