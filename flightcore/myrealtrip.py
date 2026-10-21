"""Official stored calendar prices, explicitly separate from live quotes."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path

import httpx
from .core import code

BASE = "https://partner-ext-api.myrealtrip.com/v1/products/flight/"


def api_key():
    value = os.environ.get("MYREALTRIP_API_KEY", "").strip()
    if not value:
        path = Path(__file__).resolve().parent.parent / ".env"
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                name, sep, candidate = line.partition("=")
                if sep and name.strip() == "MYREALTRIP_API_KEY":
                    value = candidate.strip().strip("\"'")
                    break
    if not value:
        raise ValueError("서버 .env에 MYREALTRIP_API_KEY를 설정하세요")
    return value


def calendar(origin, destination, start, end, nights, *, client=None, key=None):
    code(origin); code(destination)
    if origin == destination or not 0 <= (end-start).days <= 30:
        raise ValueError("서로 다른 공항과 1~31일의 출발일 범위를 지정하세요")
    if type(nights) is not int or not 2 <= nights <= 6:
        raise ValueError("이 공식 API는 period 3~7만 지원합니다(날짜 차이 2~6일)")
    query_end = end if end > start else end + timedelta(days=1)
    payload = {"depCityCd": origin, "arrCityCd": destination,
               "startDate": start.isoformat(), "endDate": query_end.isoformat(), "period": nights+1}
    secret = key or api_key()
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
    result = {"source": "MyRealTrip", "kind": "cached_reference", "request": payload,
              "fetched_at": datetime.now(timezone.utc).isoformat(), "source_observed_at": None,
              "comparison_eligible": False, "external_requests": 1, "currency": "KRW",
              "notice": "저장된 참고 가격. 실시간 운임·갱신시각·승객/수하물 조건 미확인"}
    try:
        response = client.post(BASE+"calendar", json=payload,
                               headers={"Authorization": "Bearer "+secret})
        result["http_status"] = response.status_code
        if response.status_code != 200:
            result["status"] = {401: "authentication_failed", 403: "permission_denied",
                                429: "rate_limited"}.get(response.status_code, "http_error")
            return result
        try:
            body = response.json()
            if body["result"]["status"] != 200 or body["result"]["code"] != "success":
                result["status"] = "api_error"
                return result
            rows = body["data"]
            if not isinstance(rows, list):
                raise ValueError()
            references = []
            for row in rows:
                departure = date.fromisoformat(row["departureDate"])
                returning = date.fromisoformat(row["returnDate"])
                if (row["fromCity"] != origin or row["toCity"] != destination
                    or row["period"] != nights+1 or not start <= departure <= query_end
                    or returning != departure+timedelta(days=nights)
                    or type(row["totalPrice"]) is not int or row["totalPrice"] <= 0
                    or row["transfer"] != 0):
                    raise ValueError()
                if departure > end:
                    continue  # Calendar requires two days; only retain the requested day.
                # Whitelist fields; never write response headers, tokens or raw error text.
                references.append({name: row.get(name) for name in
                                   ("fromCity", "toCity", "departureDate", "returnDate",
                                    "period", "totalPrice", "airline", "transfer")})
            result["references"] = references
            present = {row["departureDate"] for row in references}
            result["dates"] = [{"date": (start+timedelta(days=i)).isoformat(),
                                 "status": "reference_available" if (start+timedelta(days=i)).isoformat() in present
                                 else "no_cached_reference"} for i in range((end-start).days+1)]
            result["status"] = "references_received" if references else "no_cached_reference"
        except (ValueError, KeyError, TypeError):
            result["status"] = "unverified_response"
        return result
    except httpx.HTTPError:
        result["status"] = "network_error"
        return result
    finally:
        if own:
            client.close()


def main():
    parser = argparse.ArgumentParser(description="마이리얼트립 저장 참고 가격 조회 (실시간 비교 아님)")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--nights", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("출력 파일이 존재합니다. 새 파일명을 사용하세요")
    try:
        result = calendar(args.origin, args.destination, args.start, args.end, args.nights)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "http_status": result.get("http_status"),
                      "references": len(result.get("references", []))}, ensure_ascii=False))
    return 0 if result["status"] in ("references_received", "no_cached_reference") else 2


if __name__ == "__main__":
    raise SystemExit(main())
