"""Explicit, single-condition unofficial connectivity probe; never a fare comparison.

No proxy, browser impersonation, login, cookie reuse, redirects or retries.
Only query construction/parser from fast-flights is used, never its fetcher.
"""
import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import time

import httpx

from .core import code

GOOGLE = "https://www.google.com/travel/flights"
NAVER = "https://airline-api.naver.com/graphql"
MAX_BYTES = 8 * 1024 * 1024
BLOCK_MARKERS = ("unusual traffic", "our systems have detected", "access denied",
                 "verify you are human", "비정상적인 접근", "접근이 제한",
                 "자동입력 방지", "recaptcha/api.js", "hcaptcha.com/1/api.js")


class ProbeStopped(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(detail)


class DirectTransport:
    def __init__(self, client=None):
        self.client = client or httpx.Client(
            timeout=30, follow_redirects=False, trust_env=False,
            headers={"User-Agent": "PersonalFlightProbe/0.1"})
        self.requests = 0
        self.stopped = False

    def close(self):
        self.client.close()

    def request(self, method, url, **kwargs):
        if self.stopped:
            raise ProbeStopped("stopped", "이미 중단된 연결입니다")
        if url not in (GOOGLE, NAVER):
            raise ValueError("허용된 조회 주소가 아닙니다")
        self.requests += 1
        # Never accept cookies set by a previous response, even for Naver polling.
        self.client.cookies.clear()
        try:
            with self.client.stream(method, url, **kwargs) as response:
                status = response.status_code
                if status in (401, 403, 407, 429):
                    raise ProbeStopped("blocked", f"HTTP {status}; 재시도하지 않음")
                if 300 <= status < 400:
                    raise ProbeStopped("redirect_stopped", f"HTTP {status}; 이동을 따라가지 않음")
                if status != 200:
                    raise ProbeStopped("http_error", f"HTTP {status}")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ProbeStopped("response_too_large", "응답 크기 제한 초과")
                    chunks.append(chunk)
                text = b"".join(chunks).decode("utf-8", errors="replace")
                lower = text.lower()
                if any(marker in lower for marker in BLOCK_MARKERS):
                    raise ProbeStopped("challenge", "차단/사람 확인 페이지 감지; 재시도하지 않음")
                if "accounts.google.com/servicelogin" in lower and "ds:1" not in lower:
                    raise ProbeStopped("login_required", "로그인이 필요한 응답")
                return text
        except ProbeStopped:
            self.stopped = True
            raise
        except httpx.HTTPError:
            self.stopped = True
            raise ProbeStopped("network_error", "네트워크 오류; 재시도하지 않음") from None


def google_probe(transport, origin, destination, departure, returning=None):
    from fast_flights import FlightQuery, Passengers, create_query
    from fast_flights.parser import parse
    flights = [FlightQuery(date=departure.isoformat(), from_airport=origin, to_airport=destination)]
    if returning:
        flights.append(FlightQuery(date=returning.isoformat(), from_airport=destination, to_airport=origin))
    query = create_query(flights=flights, passengers=Passengers(adults=1), seat="economy",
                         trip="round-trip" if returning else "one-way", language="ko", currency="KRW")
    text = transport.request("GET", GOOGLE, params=query.params())
    try:
        rows = parse(text)
    except Exception:
        # Parser's FlightsNotFound can also mean upstream schema/error, not sold out.
        raise ProbeStopped("unverified_response", "Google 가격 구조를 확인하지 못함; 매진으로 처리하지 않음") from None
    return {"status": "observations" if rows else "unverified_empty",
            "search_url": query.url(), "observations": [asdict(row) for row in rows],
            "currency_requested": "KRW", "currency_verified": False,
            "comparison_eligible": False,
            "limitations": ["검색에 표시된 가격 관찰값; 전체 재고·결제 총액 미검증",
                            "판매처·수하물·시간대·왕복 귀국편 상세 미검증"]}


def naver_probe(transport, origin, destination, departure, returning=None):
    # Public search protocol described in the supplied blog; no copied session keys.
    # Request only fields necessary to assess availability, not assumed fare totals.
    itinerary = [{"departureAirport": origin, "arrivalAirport": destination,
                  "departureDate": departure.strftime("%Y%m%d")}]
    if returning:
        itinerary.append({"departureAirport": destination, "arrivalAirport": origin,
                          "departureDate": returning.strftime("%Y%m%d")})
    variables = {"trip": "RT" if returning else "OW", "itinerary": itinerary,
                 "galileoKey": "", "travelBizKey": ""}
    query = """query Probe($trip: InternationalList_TripType!,
      $itinerary: [InternationalList_itinerary]!, $galileoKey: String, $travelBizKey: String) {
      internationalList(input: {trip: $trip, itinerary: $itinerary,
        person: {adult: 1, child: 0, infant: 0}, fareType: Y, where: pc,
        isDirect: false, galileoKey: $galileoKey, travelBizKey: $travelBizKey,
        galileoFlag: true, travelBizFlag: true}) {
          galileoKey travelBizKey galileoFlag travelBizFlag totalResCnt resCnt
          results { schedules fares errors }
      }
    }"""
    for attempt in range(2):
        text = transport.request("POST", NAVER,
                                 json={"operationName": "Probe", "query": query, "variables": variables})
        try:
            payload = json.loads(text)
            if payload.get("errors"):
                raise ProbeStopped("api_error", "GraphQL 오류; 헤더·키 변경 재시도 없음")
            data = payload["data"]["internationalList"]
            results = data.get("results") or {}
            if results.get("errors"):
                raise ProbeStopped("upstream_error", "네이버 공급사 오류; 결과를 확정하지 않음")
            if results.get("fares"):
                # Preserve counts only until the real schema is reviewed. No tokens saved.
                return {"status": "unparsed_fares", "comparison_eligible": False,
                        "result_fields": sorted(results), "returned_count": data.get("resCnt"),
                        "total_count": data.get("totalResCnt"),
                        "limitations": ["운임 응답 존재; 가격·판매처·완전성 해석 미완료"]}
            keys = {key: data.get(key) for key in ("galileoKey", "travelBizKey")}
            if attempt or not any(keys.values()):
                return {"status": "pending_or_unverified_empty", "comparison_eligible": False,
                        "limitations": ["조회 미완료와 실제 항공편 없음을 구분하지 못함"]}
            if any(value is not None and not isinstance(value, str) for value in keys.values()):
                raise ValueError("unexpected key schema")
            variables.update({key: value or "" for key, value in keys.items()})
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProbeStopped("unverified_response", "네이버 응답 구조 미확인; 매진으로 처리하지 않음") from None
        time.sleep(2)  # One normal completion poll, never an error/challenge retry.


def run(provider, origin, destination, departure, returning=None, transport=None):
    code(origin); code(destination)
    if origin == destination or departure < date.today() or (returning and returning <= departure):
        raise ValueError("공항 또는 출발/귀국 날짜를 확인하세요")
    own = transport is None
    transport = transport or DirectTransport()
    report = {"provider": provider, "observed_at": datetime.now(timezone.utc).isoformat(),
              "origin": origin, "destination": destination, "departure": departure.isoformat(),
              "return_date": returning.isoformat() if returning else None,
              "passengers": {"adults": 1}, "cabin": "economy", "comparison_eligible": False}
    try:
        fn = {"google": google_probe, "naver": naver_probe}[provider]
        report.update(fn(transport, origin, destination, departure, returning))
    except ProbeStopped as error:
        report.update(status=error.status, detail=error.detail)
    finally:
        report["external_requests"] = transport.requests
        if own:
            transport.close()
    return report


def main():
    parser = argparse.ArgumentParser(description="우회 없는 단일 조건 연결 검증; 웹 가격 비교와 미연결")
    parser.add_argument("provider", choices=("google", "naver"))
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--departure", type=date.fromisoformat, required=True)
    parser.add_argument("--return-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("출력 파일이 이미 있습니다. 새 파일명을 사용하세요")
    result = run(args.provider, args.origin, args.destination, args.departure, args.return_date)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("provider", "status", "external_requests")}, ensure_ascii=False))
    return 0 if result["status"] == "observations" else 2


if __name__ == "__main__":
    raise SystemExit(main())
