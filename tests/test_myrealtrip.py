import unittest
from datetime import date
import httpx
from flightcore.myrealtrip import calendar


class MyRealTripTests(unittest.TestCase):
    def test_single_day_filters_extra_calendar_day(self):
        def handler(request):
            import json
            self.assertEqual(json.loads(request.content)['endDate'], '2027-01-19')
            return httpx.Response(200,json={'result':{'status':200,'code':'success'},'data':[
                {'fromCity':'ICN','toCity':'NRT','departureDate':f'2027-01-{day}',
                 'returnDate':f'2027-01-{day+5}','period':6,'totalPrice':123,
                 'airline':'TEST','transfer':0} for day in (18,19)]})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=calendar('ICN','NRT',date(2027,1,18),date(2027,1,18),5,client=client,key='test-key')
        self.assertEqual(len(result['references']),1)
        self.assertEqual(result['references'][0]['departureDate'],'2027-01-18')
        self.assertEqual(len(result['dates']),1)

    def query(self, handler):
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            return calendar("ICN", "NRT", date(2026,12,10), date(2026,12,11), 5,
                            client=client, key="test-key")

    def test_auth_header_and_period_and_missing_date(self):
        def handler(request):
            import json
            self.assertEqual(request.url.host, "partner-ext-api.myrealtrip.com")
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            self.assertEqual(json.loads(request.content)["period"], 6)
            return httpx.Response(200,json={"result":{"status":200,"code":"success"},"data":[
                {"fromCity":"ICN","toCity":"NRT","departureDate":"2026-12-10",
                 "returnDate":"2026-12-15","period":6,"totalPrice":123,"airline":"TEST","transfer":0}]})
        result = self.query(handler)
        self.assertFalse(result["comparison_eligible"])
        self.assertIsNone(result["source_observed_at"])
        self.assertEqual(result["dates"][1]["status"], "no_cached_reference")
        self.assertNotIn("test-key", str(result))

    def test_empty_cache_not_no_flights(self):
        result = self.query(lambda r: httpx.Response(200,json={"result":{"status":200,"code":"success"},"data":[]}))
        self.assertEqual(result["status"], "no_cached_reference")
        self.assertEqual(len(result["dates"]), 2)

    def test_error_response_does_not_leak_secret(self):
        for code, status in ((401,"authentication_failed"),(403,"permission_denied"),(429,"rate_limited"),(302,"http_error")):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(code,text="test-key",headers={"location":"https://other.invalid"})
            result = self.query(handler)
            self.assertEqual(result["status"], status)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("test-key", str(result))

    def test_wrong_schema_never_ranked(self):
        result = self.query(lambda r: httpx.Response(200,json={"result":{"status":200,"code":"success"},"data":[{}]}))
        self.assertEqual(result["status"], "unverified_response")
        self.assertNotIn("references", result)

    def test_unsupported_nights_rejected_without_request(self):
        with self.assertRaises(ValueError):
            calendar("ICN","NRT",date(2026,12,10),date(2026,12,11),7,key="test-key")


if __name__ == "__main__":
    unittest.main()
