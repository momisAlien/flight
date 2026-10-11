"""ALL synthetic flight/fare fixtures live in tests only. Never seeds application data."""
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from flightcore.core import *
from flightcore.catalog import CityAirports
from flightcore.serde import dumps, quote_from_dict, conditions_from_dict
from flightcore.store import Store

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 5, 17, tzinfo=TZ)


def leg(origin="ICN", destination="NRT", day=10, hour=8, duration=120, airline="TEST-A", stops=0):
    departure = datetime(2026, 12, day, hour, tzinfo=TZ)
    return Leg((Segment(origin, destination, departure, departure + timedelta(minutes=duration), airline, "TEST1", stops),))


def quote(id="out", legs=None, price="100", currency="KRW", **kwargs):
    return Quote(id, legs or (leg(),), Decimal(price), currency,
                 Provenance("TEST ONLY", "TEST SELLER", NOW, "https://example.invalid/source"),
                 baggage_confirmed=True, taxes_included=True, mandatory_fees_included=True, **kwargs)


def conditions(**kwargs):
    base = Conditions(("ICN", "GMP", "CJJ"), ("NRT", "HND"), date(2026, 12, 10), date(2026, 12, 31), 5)
    return replace(base, **kwargs)


def back(**kwargs):
    return quote("back", (leg("NRT", "ICN", 15, 17, airline="TEST-B"),), "120", **kwargs)


class PlanningTests(unittest.TestCase):
    def test_all_origins_destinations_dates_and_year_rollover(self):
        requests = list(plan(conditions()))
        rts = [r for r in requests if r.kind == "roundtrip"]
        self.assertEqual(len(rts), 132)
        self.assertEqual({r.origin for r in rts}, {"ICN", "GMP", "CJJ"})
        self.assertEqual({r.destination for r in rts}, {"NRT", "HND"})
        self.assertEqual(len({r.departure for r in rts}), 22)
        self.assertEqual(max(r.return_date for r in rts), date(2027, 1, 5))
        self.assertEqual(len(requests), 396)
        self.assertEqual(len(set(requests)), 396)

    def test_estimate_and_all_airport_change_combinations(self):
        for a, b, expected in ((False, False,396), (True,False,660), (False,True,528), (True,True,1056)):
            c = conditions(allow_origin_change=a, allow_destination_change=b)
            self.assertEqual(estimate(c)["base_total_per_provider"], expected)
            self.assertEqual(len(set(plan(c))), expected)

    def test_airport_duplicates_are_deduplicated_not_dropped(self):
        c = conditions(origins=("ICN","ICN","GMP","CJJ"))
        self.assertEqual(c.origins, ("ICN","GMP","CJJ"))

    def test_city_airports_selection(self):
        city = CityAirports("도쿄", ("NRT","HND"), "https://example.invalid/airport-source", date(2026,10,5))
        self.assertEqual(city.select(), ("NRT","HND"))
        self.assertEqual(city.select(exclude=("HND",)), ("NRT",))
        with self.assertRaises(ValueError):
            city.select(include=("KIX",))

    def test_natural_language_never_guesses_year_or_end(self):
        parsed = parse_korean("12월 10일 이후에 일본으로 5박 여행하고 싶어.")
        self.assertEqual(parsed["nights"], 5)
        self.assertIn("연도", parsed["missing"])
        self.assertIn("출발 마지막 날", parsed["missing"])
        self.assertFalse(parsed["executable"])

    def test_expansion_default_off_and_deduplicated_when_on(self):
        overnight = leg(hour=23, duration=120)
        self.assertEqual(list(expansion_requests([overnight], conditions())), [])
        requests = list(expansion_requests([overnight, overnight], conditions(arrival_expansion=True)))
        self.assertEqual(len(requests), 1)  # Dec 16 inbound already in base schedule.
        self.assertEqual(requests[0].return_date, date(2026,12,16))
        self.assertEqual(requests[0].kind, "roundtrip")

    def test_roundtrip_only(self):
        self.assertEqual(len(list(plan(conditions(compare_oneways=False)))), 132)

    def test_invalid_conditions(self):
        for changes in ({"origins": ()}, {"nights": 0}, {"end":date(2026,12,1)}, {"max_stops":-1}):
            with self.assertRaises(ValueError):
                conditions(**changes)


class ComparisonTests(unittest.TestCase):
    def test_actual_roundtrip_and_different_airline_oneways(self):
        rt = quote("rt", (leg(), back().legs[0]), "300")
        values = list(comparisons([rt], [quote()], lambda: iter([back()]), conditions(), NOW))
        self.assertEqual([r.total for r in values], [Decimal(300),Decimal(220)])
        self.assertEqual(values[1].booking_type, "편도 2건 별도 예약")
        self.assertNotEqual(values[1].quotes[0].legs[0].segments[0].airline, values[1].quotes[1].legs[0].segments[0].airline)
        self.assertEqual(next(iter(lowest_per_date(values).values())).total, Decimal(220))

    def test_different_sellers_keep_individual_provenance_and_prices(self):
        incoming = replace(back(), provenance=Provenance("TEST OTHER", "TEST SELLER B", NOW, "https://example.invalid/b"))
        value = evaluate((quote(), incoming), conditions(), NOW)
        self.assertEqual(value.total, Decimal(220))
        self.assertEqual(len({q.provenance.seller for q in value.quotes}), 2)

    def test_nights_mismatch_visible_but_not_ranked(self):
        out = quote(legs=(leg(hour=23),))
        value = evaluate((out, back()), conditions(), NOW)
        self.assertEqual(value.actual_nights, 4)
        self.assertIn("숙박일수 불일치", value.warnings)
        self.assertFalse(value.rankable)
        self.assertEqual(lowest_per_date([value]), {})

    def test_arrival_expansion_option(self):
        out = quote(legs=(leg(hour=23),))
        incoming = quote("b16", (leg("NRT","ICN",16,17),))
        self.assertIsNone(evaluate((out,incoming), conditions(),NOW))
        self.assertTrue(evaluate((out,incoming), conditions(arrival_expansion=True),NOW).rankable)

    def test_deadline_uses_korea_arrival_not_return_departure(self):
        incoming = quote("b", (leg("NRT","ICN",15,23),))
        self.assertIsNone(evaluate((quote(),incoming),conditions(return_deadline=date(2026,12,15)),NOW))
        self.assertIsNotNone(evaluate((quote(),incoming),conditions(return_deadline=date(2026,12,16)),NOW))

    def test_unknown_stops_never_marked_direct(self):
        self.assertIsNone(leg(stops=None).direct)
        self.assertIsNone(evaluate((quote(legs=(leg(stops=None),)),back()),conditions(),NOW))

    def test_same_flight_intermediate_landing_is_not_direct(self):
        self.assertFalse(leg(stops=1).direct)
        self.assertIsNone(evaluate((quote(legs=(leg(stops=1),)),back()),conditions(),NOW))

    def test_connections_stop_count_and_duration(self):
        first = leg(destination="KIX").segments[0]
        second = replace(first, origin="KIX", destination="NRT", departure=first.arrival+timedelta(hours=1), arrival=first.arrival+timedelta(hours=2))
        connected = Leg((first,second))
        self.assertFalse(connected.direct)
        self.assertEqual(connected.stops,1)
        self.assertEqual(connected.duration_minutes,240)
        q = quote(legs=(connected,))
        self.assertIsNotNone(evaluate((q,back()),conditions(direct_only=False),NOW))
        self.assertIsNone(evaluate((q,back()),conditions(direct_only=False,max_duration_minutes=180),NOW))

    def test_both_direction_time_filters(self):
        good = conditions(outbound_window=TimeWindow(time(6),time(12)), inbound_window=TimeWindow(time(15),time(23)))
        self.assertIsNotNone(evaluate((quote(),back()),good,NOW))
        self.assertIsNone(evaluate((quote(),back()),replace(good,inbound_window=TimeWindow(time(6),time(12))),NOW))
        self.assertIsNone(evaluate((quote(),back()),replace(good,outbound_window=TimeWindow(time(9),time(12))),NOW))

    def test_midnight_window(self):
        w = TimeWindow(time(22),time(2))
        self.assertTrue(w.contains(time(23)))
        self.assertTrue(w.contains(time(1)))
        self.assertFalse(w.contains(time(12)))

    def test_airport_changes_require_options_and_are_labelled(self):
        incoming = quote("b", (leg("HND","GMP",15,17),))
        self.assertIsNone(evaluate((quote(),incoming),conditions(),NOW))
        result = evaluate((quote(),incoming),conditions(allow_origin_change=True,allow_destination_change=True),NOW)
        self.assertIn("한국 공항 변경",result.warnings)
        self.assertIn("현지 공항 변경",result.warnings)

    def test_currencies_not_combined_or_converted(self):
        self.assertIsNone(evaluate((quote(),replace(back(),currency="JPY")),conditions(),NOW))

    def test_daily_prices_grouped_by_currency(self):
        krw = evaluate((quote(),back()),conditions(),NOW)
        jpy = evaluate((replace(quote(),currency="JPY"),replace(back(),currency="JPY")),conditions(),NOW)
        self.assertEqual(len(lowest_per_date([krw,jpy])),2)

    def test_passengers_cabin_and_baggage_must_match(self):
        for changes in ({"passengers":Passengers(2)}, {"cabin":"business"}, {"baggage":"checked20kg"}):
            self.assertIsNone(evaluate((replace(quote(),**changes),back()),conditions(),NOW))

    def test_unknown_fees_taxes_baggage_are_not_free_or_ranked(self):
        for changes in ({"taxes_included":None}, {"mandatory_fees_included":None}, {"baggage_confirmed":False}):
            result = evaluate((replace(quote(),**changes),back()),conditions(),NOW)
            self.assertFalse(result.rankable)
            self.assertTrue(result.warnings)

    def test_confirmed_fee_is_added_exactly(self):
        q = replace(quote(price="0.10"),mandatory_fees_included=False,extra_mandatory_fee=Decimal("0.20"))
        self.assertEqual(q.confirmed_total,Decimal("0.30"))
        with self.assertRaises(ValueError):
            replace(q,mandatory_fees_included=True)

    def test_cache_and_expired_results_never_enter_lowest(self):
        for q in (replace(quote(),cached=True),replace(quote(),expires_at=NOW)):
            result = evaluate((q,back()),conditions(),NOW)
            self.assertIn("참고용 후보",result.warnings)
            self.assertEqual(lowest_per_date([result]),{})

    def test_reference_model_rejected_by_comparison(self):
        r = ReferenceCandidate("ref","TEST","https://example.invalid",Decimal(1),"KRW",NOW)
        with self.assertRaises(TypeError):
            evaluate((r,back()),conditions(),NOW)

    def test_future_provenance_not_ranked(self):
        q = replace(quote(),provenance=replace(quote().provenance,observed_at=NOW+timedelta(days=1)))
        self.assertFalse(evaluate((q,back()),conditions(),NOW).rankable)

    def test_every_quote_needs_source_seller_timestamp_url(self):
        for changes in ({"source":""}, {"seller":""}, {"observed_at":datetime(2026,1,1)}, {"url":"javascript:alert(1)"}):
            with self.assertRaises(ValueError):
                replace(quote().provenance,**changes)

    def test_streaming_does_not_read_all_before_first_result(self):
        calls=[]
        def incoming():
            calls.append(1)
            yield back()
            raise RuntimeError("should not be reached for first result")
        results=comparisons([],iter([quote()]),incoming,conditions(),NOW)
        self.assertEqual(next(results).total,Decimal(220))
        self.assertEqual(len(calls),1)

    def test_no_candidate_truncation(self):
        outs=[replace(quote(),id=f"o{i}") for i in range(13)]
        backs=[replace(back(),id=f"b{i}") for i in range(17)]
        self.assertEqual(sum(1 for _ in comparisons([],outs,lambda:iter(backs),conditions(),NOW)),221)

    def test_sort_direct_first_or_overall_price(self):
        direct=evaluate((quote(),back()),conditions(direct_only=False),NOW)
        stop=evaluate((quote(legs=(leg(stops=1),),price="1"),back()),conditions(direct_only=False),NOW)
        self.assertLess(sort_key(direct),sort_key(stop))
        self.assertLess(sort_key(stop,"price"),sort_key(direct,"price"))

    def test_nonfinite_money_and_naive_time_rejected(self):
        for bad in (Decimal("NaN"),Decimal("Infinity"),Decimal(-1),1.1):
            with self.assertRaises(ValueError):
                replace(quote(),amount=bad)
        with self.assertRaises(ValueError):
            replace(leg().segments[0],departure=datetime(2026,12,10,8))

    def test_timezone_elapsed_and_day_label(self):
        s=Segment("ICN","NRT",datetime(2026,12,10,23,tzinfo=TZ),datetime(2026,12,10,17,tzinfo=timezone(timedelta(hours=-5))),"TEST",intermediate_stops=0)
        self.assertEqual(Leg((s,)).duration_minutes,480)
        self.assertEqual(local_time_details(leg(hour=23))["arrival_day_label"],"+1일")

    def test_deadline_normalizes_arrival_to_korea_date(self):
        b=back()
        s=b.legs[0].segments[0]
        # 15:30 UTC on Dec 15 is Dec 16 00:30 in Korea.
        s=replace(s,arrival=datetime(2026,12,15,15,30,tzinfo=timezone.utc))
        b=replace(b,legs=(Leg((s,)),))
        self.assertIsNone(evaluate((quote(),b),conditions(return_deadline=date(2026,12,15)),NOW))

    def test_filters_run_before_opening_inbound_stream(self):
        def incoming():
            raise AssertionError("invalid outbound should be filtered first")
        bad=quote(legs=(leg(stops=None),))
        self.assertEqual(list(comparisons([], [bad],incoming,conditions(),NOW)),[])

    def test_oneway_disabled_does_not_compare_separate_bookings(self):
        self.assertEqual(list(comparisons([], [quote()],lambda:iter([back()]),conditions(compare_oneways=False),NOW)),[])

    def test_checklist_does_not_claim_price_lookup(self):
        checklist=manual_checklist(conditions(),next(plan(conditions())),"https://example.invalid")
        self.assertEqual(checklist["status"],"직접 확인 필요")
        self.assertNotIn("price",checklist)


class PersistenceTests(unittest.TestCase):
    def test_empty_db_has_no_results(self):
        with Store(":memory:") as s:
            self.assertEqual(list(s.quotes(1)),[])
            self.assertEqual(list(s.references()),[])

    def test_manual_roundtrip_persists_source_and_decimal(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/"test.db"
            with Store(db) as s:
                s.add_manual(quote())
            with Store(db) as s:
                self.assertEqual(next(s.quotes(1)),quote())

    def test_manual_cannot_claim_live_verification(self):
        with Store(":memory:") as s:
            with self.assertRaises(ValueError):
                s.add_manual(replace(quote(),provenance=replace(quote().provenance,kind="live")))

    def test_reference_storage_is_separate(self):
        with Store(":memory:") as s:
            r=ReferenceCandidate("ref","TEST","https://example.invalid",Decimal(10),"KRW",NOW)
            s.add_reference(r)
            self.assertEqual(list(s.quotes(1)),[])
            self.assertEqual(next(s.references()),r)

    def test_task_failure_empty_and_partial_differ(self):
        with Store(":memory:") as s:
            requests=list(plan(conditions(compare_oneways=False)))[:2]
            s.seed_tasks("job","TEST",requests,connected=True)
            for r in requests:
                s.transition("job","TEST",r,Status.RUNNING)
            s.transition("job","TEST",requests[0],Status.NO_RESULTS)
            s.transition("job","TEST",requests[1],Status.FAILED,"429")
            p=s.task_progress("job")
            self.assertEqual(p["state"],Status.PARTIAL.value)
            self.assertEqual(p["completed"],1)
            self.assertEqual(list(s.unfinished("job"))[0]["reason"],"429")
            s.transition("job","TEST",requests[1],Status.NOT_SEARCHED)

    def test_unconnected_tasks_cannot_claim_results(self):
        with Store(":memory:") as s:
            r=next(plan(conditions()))
            s.seed_tasks("job","TEST",[r,r])
            self.assertEqual(s.task_progress("job")["total"],1)
            with self.assertRaises(ValueError):
                s.transition("job","TEST",r,Status.SUCCESS)

    def test_statuses_not_conflated(self):
        for status in (Status.NOT_SEARCHED,Status.RUNNING,Status.NOT_CONNECTED,Status.NO_RESULTS,Status.FAILED,Status.PARTIAL,Status.CANCELLED):
            self.assertEqual(progress([status])["state"],status.value)

    def test_json_rejects_string_boolean_and_float_price(self):
        d=json.loads(dumps(quote()))
        d["amount"]=1.1
        with self.assertRaises(ValueError):
            quote_from_dict(d)
        d=json.loads(dumps(quote()))
        d["cached"]="false"
        with self.assertRaises(ValueError):
            quote_from_dict(d)

    def test_no_network_for_offline_workflow(self):
        with patch("socket.socket",side_effect=AssertionError("network forbidden")):
            with Store(":memory:") as s:
                s.add_manual(quote())
                s.add_manual(back())
                results=list(comparisons(s.quotes(2),s.quotes(1),lambda:s.quotes(1),conditions(),NOW))
                self.assertEqual(len(results),1)


if __name__ == "__main__":
    unittest.main()
