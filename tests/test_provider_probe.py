import unittest
from datetime import date, timedelta
from unittest.mock import patch
import httpx
from flightcore.provider_probe import DirectTransport, ProbeStopped, run


class ProbeTests(unittest.TestCase):
    def transport(self, handler):
        return DirectTransport(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))

    def test_block_prevents_second_request(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429)
        transport = self.transport(handler)
        for _ in range(2):
            with self.assertRaises(ProbeStopped):
                transport.request("GET", "https://www.google.com/travel/flights")
        self.assertEqual(len(calls), 1)

    def test_redirect_not_followed(self):
        transport = self.transport(lambda r: httpx.Response(302, headers={"location": "https://accounts.google.com"}))
        with self.assertRaises(ProbeStopped) as error:
            transport.request("GET", "https://www.google.com/travel/flights")
        self.assertEqual(error.exception.status, "redirect_stopped")
        self.assertEqual(transport.requests, 1)

    def test_challenge_200_stops(self):
        transport = self.transport(lambda r: httpx.Response(200, text="Our systems have detected unusual traffic"))
        with self.assertRaises(ProbeStopped) as error:
            transport.request("GET", "https://www.google.com/travel/flights")
        self.assertEqual(error.exception.status, "challenge")

    def test_cookie_not_reused(self):
        cookies = []
        def handler(request):
            cookies.append(request.headers.get("cookie"))
            return httpx.Response(200, text="ok", headers={"set-cookie": "session=secret"})
        transport = self.transport(handler)
        for _ in range(2):
            transport.request("GET", "https://www.google.com/travel/flights")
        self.assertEqual(cookies, [None, None])

    def test_naver_error_never_polled(self):
        transport = self.transport(lambda r: httpx.Response(200, json={"errors": [{"message": "denied"}]}))
        result = run("naver", "ICN", "NRT", date.today() + timedelta(days=30), transport=transport)
        self.assertEqual(result["status"], "api_error")
        self.assertEqual(transport.requests, 1)
        self.assertFalse(result["comparison_eligible"])

    def test_naver_poll_uses_only_returned_keys_and_does_not_persist_them(self):
        calls = []
        def handler(request):
            import json
            calls.append(json.loads(request.content))
            data = {"galileoKey": "temporary-key", "travelBizKey": "", "results": {}}
            if len(calls) == 2:
                data["results"] = {"fares": {"unparsed": {}}}
            return httpx.Response(200, json={"data": {"internationalList": data}})
        transport = self.transport(handler)
        with patch("flightcore.provider_probe.time.sleep"):
            result = run("naver", "ICN", "NRT", date.today() + timedelta(days=30), transport=transport)
        self.assertEqual(calls[1]["variables"]["galileoKey"], "temporary-key")
        self.assertNotIn("temporary-key", str(result))
        self.assertEqual(result["status"], "unparsed_fares")

    def test_google_schema_failure_not_sold_out(self):
        transport = self.transport(lambda r: httpx.Response(200, text="<html></html>"))
        result = run("google", "ICN", "NRT", date.today() + timedelta(days=30), transport=transport)
        self.assertEqual(result["status"], "unverified_response")
        self.assertNotIn("observations", result)

    def test_google_roundtrip_query_without_library_fetcher(self):
        transport = self.transport(lambda r: httpx.Response(200, text="fixture"))
        with patch("fast_flights.parser.parse", return_value=[]), patch("fast_flights.get_flights", side_effect=AssertionError):
            result = run("google", "ICN", "NRT", date.today() + timedelta(days=30),
                         date.today() + timedelta(days=35), transport=transport)
        self.assertEqual(result["status"], "unverified_empty")
        self.assertIn("curr=KRW", result["search_url"])
        self.assertFalse(result["comparison_eligible"])


if __name__ == "__main__":
    unittest.main()
