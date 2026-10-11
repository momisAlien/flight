from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from itertools import product
from typing import Callable, Iterable, Iterator
from urllib.parse import urlsplit
import re


def code(value: str) -> str:
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("공항/통화 코드는 대문자 3자리여야 합니다")
    return value


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("시각에는 현지 UTC 오프셋이 필요합니다")
    return value


def money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("금액은 0 이상의 유한 Decimal이어야 합니다")
    return value


def link(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("출처 링크는 자격증명이 없는 HTTP(S) URL이어야 합니다")
    return value


@dataclass(frozen=True)
class TimeWindow:
    start: time
    end: time

    def __post_init__(self):
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("시간 필터에는 날짜/시간대 없이 현지 시각만 사용합니다")

    def contains(self, value: time) -> bool:
        value = value.replace(tzinfo=None)
        if self.start <= self.end:
            return self.start <= value <= self.end
        return value >= self.start or value <= self.end


@dataclass(frozen=True)
class Passengers:
    adults: int = 1
    children: int = 0
    infants: int = 0

    def __post_init__(self):
        if any(type(x) is not int or x < 0 for x in (self.adults, self.children, self.infants)) or self.adults < 1:
            raise ValueError("성인 1명 이상, 승객 수는 음수가 아닌 정수여야 합니다")


@dataclass(frozen=True)
class Conditions:
    origins: tuple[str, ...]
    destinations: tuple[str, ...]
    start: date
    end: date
    nights: int
    return_deadline: date | None = None
    passengers: Passengers = Passengers()
    cabin: str = "economy"
    baggage: str = "none_requested"
    direct_only: bool = True
    max_stops: int = 1
    max_duration_minutes: int | None = None
    outbound_window: TimeWindow | None = None
    inbound_window: TimeWindow | None = None
    allow_origin_change: bool = False
    allow_destination_change: bool = False
    compare_oneways: bool = True
    arrival_expansion: bool = False

    def __post_init__(self):
        for field in ("origins", "destinations"):
            values = tuple(dict.fromkeys(code(x) for x in getattr(self, field)))
            if not values:
                raise ValueError("출발 및 목적지 공항을 선택해야 합니다")
            object.__setattr__(self, field, values)
        if self.end < self.start or type(self.nights) is not int or self.nights < 1:
            raise ValueError("출발 기간 또는 숙박일수가 유효하지 않습니다")
        if type(self.max_stops) is not int or self.max_stops < 0 or (self.max_duration_minutes is not None and (type(self.max_duration_minutes) is not int or self.max_duration_minutes <= 0)):
            raise ValueError("경유 횟수/소요시간 제한이 유효하지 않습니다")
        if not self.cabin.strip() or not self.baggage.strip():
            raise ValueError("좌석/수하물 비교 조건이 필요합니다")


@dataclass(frozen=True)
class Request:
    kind: str
    origin: str
    destination: str
    departure: date
    return_date: date | None = None
    return_origin: str | None = None
    return_destination: str | None = None


def days(start: date, end: date) -> Iterator[date]:
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def plan(c: Conditions) -> Iterator[Request]:
    """One provider/one passenger-cabin-baggage set; no implicit date truncation."""
    for departure, origin, destination in product(days(c.start, c.end), c.origins, c.destinations):
        returning = departure + timedelta(days=c.nights)
        for return_origin, return_destination in product(
            c.destinations if c.allow_destination_change else (destination,),
            c.origins if c.allow_origin_change else (origin,),
        ):
            yield Request("roundtrip", origin, destination, departure, returning, return_origin, return_destination)
        if c.compare_oneways:
            yield Request("outbound", origin, destination, departure)
            yield Request("inbound", destination, origin, returning)


def estimate(c: Conditions) -> dict:
    routes = len(c.origins) * len(c.destinations) * ((c.end - c.start).days + 1)
    rt = routes * (len(c.origins) if c.allow_origin_change else 1) * (len(c.destinations) if c.allow_destination_change else 1)
    ow = routes * 2 if c.compare_oneways else 0
    return {"roundtrip": rt, "oneway": ow, "base_total_per_provider": rt + ow,
            "automatic_requests_now": 0, "automatic_cost_now": "0",
            "expansion_extra": "실제 도착 정보 확인 후 산정" if c.arrival_expansion else "disabled",
            "note": "수동 확인용 조건 수. 재시도·페이지·재확인·확장 조회는 별도. 마감일은 실제 한국 도착 후 판별."}


@dataclass(frozen=True)
class Segment:
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    airline: str
    flight_number: str | None = None
    intermediate_stops: int | None = None

    def __post_init__(self):
        code(self.origin)
        code(self.destination)
        aware(self.departure)
        aware(self.arrival)
        if self.arrival.astimezone(timezone.utc) <= self.departure.astimezone(timezone.utc):
            raise ValueError("도착은 출발 이후여야 합니다")
        if not self.airline.strip() or (self.intermediate_stops is not None and (type(self.intermediate_stops) is not int or self.intermediate_stops < 0)):
            raise ValueError("항공사 또는 기착 횟수가 유효하지 않습니다")


@dataclass(frozen=True)
class Leg:
    segments: tuple[Segment, ...]

    def __post_init__(self):
        if not self.segments:
            raise ValueError("구간이 필요합니다")
        for first, second in zip(self.segments, self.segments[1:]):
            if first.destination != second.origin or first.arrival.astimezone(timezone.utc) > second.departure.astimezone(timezone.utc):
                raise ValueError("연결 구간의 공항/시간이 맞지 않습니다")

    @property
    def origin(self):
        return self.segments[0].origin

    @property
    def destination(self):
        return self.segments[-1].destination

    @property
    def departure(self):
        return self.segments[0].departure

    @property
    def arrival(self):
        return self.segments[-1].arrival

    @property
    def stops(self) -> int | None:
        if any(s.intermediate_stops is None for s in self.segments):
            return None
        return len(self.segments) - 1 + sum(s.intermediate_stops for s in self.segments)

    @property
    def direct(self) -> bool | None:
        if len(self.segments) > 1 or any((s.intermediate_stops or 0) > 0 for s in self.segments):
            return False
        return True if self.stops == 0 else None

    @property
    def duration_minutes(self) -> float:
        return (self.arrival.astimezone(timezone.utc) - self.departure.astimezone(timezone.utc)).total_seconds() / 60


@dataclass(frozen=True)
class Provenance:
    source: str
    seller: str
    observed_at: datetime
    url: str
    kind: str = "manual"

    def __post_init__(self):
        if not self.source.strip() or not self.seller.strip() or self.kind not in ("manual", "live"):
            raise ValueError("출처·판매처·입력 구분이 필요합니다")
        aware(self.observed_at)
        link(self.url)


@dataclass(frozen=True)
class Quote:
    id: str
    legs: tuple[Leg, ...]
    amount: Decimal
    currency: str
    provenance: Provenance
    passengers: Passengers = Passengers()
    cabin: str = "economy"
    baggage: str = "none_requested"
    baggage_confirmed: bool = False
    taxes_included: bool | None = None
    mandatory_fees_included: bool | None = None
    extra_mandatory_fee: Decimal | None = None
    expires_at: datetime | None = None
    cached: bool = False
    baggage_details: str = ""

    def __post_init__(self):
        if not self.id or len(self.legs) not in (1, 2):
            raise ValueError("ID와 편도 또는 왕복 구간이 필요합니다")
        money(self.amount)
        code(self.currency)
        if self.extra_mandatory_fee is not None:
            money(self.extra_mandatory_fee)
        if self.mandatory_fees_included is True and self.extra_mandatory_fee not in (None, Decimal(0)):
            raise ValueError("필수비용 포함 금액에 추가 비용을 중복 가산할 수 없습니다")
        if self.expires_at:
            aware(self.expires_at)

    @property
    def confirmed_total(self) -> Decimal | None:
        if self.taxes_included is not True:
            return None
        if self.mandatory_fees_included is True:
            return self.amount
        if self.mandatory_fees_included is False and self.extra_mandatory_fee is not None:
            return self.amount + self.extra_mandatory_fee
        return None


@dataclass(frozen=True)
class ReferenceCandidate:
    """Cache-derived data never enters the Quote comparison pipeline."""
    id: str
    source: str
    url: str
    amount: Decimal
    currency: str
    fetched_at: datetime
    found_at: datetime | None = None
    expires_at: datetime | None = None
    note: str = ""
    label: str = "참고용 후보"

    def __post_init__(self):
        if not self.id or not self.source.strip() or self.label != "참고용 후보":
            raise ValueError("참고용 후보 출처가 필요합니다")
        link(self.url)
        money(self.amount)
        code(self.currency)
        aware(self.fetched_at)
        for value in (self.found_at, self.expires_at):
            if value:
                aware(value)


def leg_matches(leg: Leg, c: Conditions, outbound: bool) -> bool:
    if outbound:
        route_ok = leg.origin in c.origins and leg.destination in c.destinations
        date_ok = c.start <= leg.departure.date() <= c.end
        window = c.outbound_window
    else:
        route_ok = leg.origin in c.destinations and leg.destination in c.origins
        date_ok = True  # Exact return date checked against outbound leg below.
        window = c.inbound_window
    if not route_ok or not date_ok or (window and not window.contains(leg.departure.time())):
        return False
    if c.direct_only and leg.direct is not True:
        return False
    if not c.direct_only and (leg.stops is None or leg.stops > c.max_stops):
        return False
    return c.max_duration_minutes is None or leg.duration_minutes <= c.max_duration_minutes


@dataclass(frozen=True)
class Comparison:
    quotes: tuple[Quote, ...]
    actual_nights: int
    warnings: tuple[str, ...]
    total: Decimal | None
    currency: str
    rankable: bool

    @property
    def booking_type(self):
        return "왕복 예약" if len(self.quotes) == 1 else "편도 2건 별도 예약"

    @property
    def manual(self):
        return any(q.provenance.kind == "manual" for q in self.quotes)


def evaluate(quotes: tuple[Quote, ...], c: Conditions, now: datetime) -> Comparison | None:
    aware(now)
    if any(not isinstance(q, Quote) for q in quotes):
        raise TypeError("참고용 후보는 운임 비교에 사용할 수 없습니다")
    legs = tuple(leg for q in quotes for leg in q.legs)
    if len(legs) != 2 or not (len(quotes) == 1 and len(quotes[0].legs) == 2 or
                               len(quotes) == 2 and all(len(q.legs) == 1 for q in quotes)):
        raise ValueError("왕복 한 건 또는 편도 두 건이 필요합니다")
    out, back = legs
    if any(q.passengers != c.passengers or q.cabin != c.cabin or q.baggage != c.baggage for q in quotes):
        return None
    if not leg_matches(out, c, True) or not leg_matches(back, c, False):
        return None
    if not c.allow_origin_change and out.origin != back.destination:
        return None
    if not c.allow_destination_change and out.destination != back.origin:
        return None
    expected = out.departure.date() + timedelta(days=c.nights)
    expanded = out.arrival.date() + timedelta(days=c.nights)
    if back.departure.date() not in ({expected, expanded} if c.arrival_expansion else {expected}):
        return None
    if back.departure.astimezone(timezone.utc) <= out.arrival.astimezone(timezone.utc):
        return None
    korea_arrival_date = back.arrival.astimezone(timezone(timedelta(hours=9))).date()
    if c.return_deadline and korea_arrival_date > c.return_deadline:
        return None
    currencies = {q.currency for q in quotes}
    if len(currencies) != 1:  # No conversion or fake combined total.
        return None
    nights = (back.departure.date() - out.arrival.date()).days
    warnings = []
    if nights != c.nights:
        warnings.append("숙박일수 불일치")
    if out.origin != back.destination:
        warnings.append("한국 공항 변경")
    if out.destination != back.origin:
        warnings.append("현지 공항 변경")
    if len(quotes) == 2:
        warnings.append("변경·취소는 각 예약에서 별도 처리")
    if any(q.provenance.observed_at > now for q in quotes):
        warnings.append("조회 시각이 미래")
    reference = any(q.cached or (q.expires_at is not None and q.expires_at <= now) for q in quotes)
    if reference:
        warnings.append("참고용 후보")
    total = None if any(q.confirmed_total is None for q in quotes) else sum((q.confirmed_total for q in quotes), Decimal(0))
    if total is None:
        warnings.append("세금·필수 비용 미확인")
    bags_known = all(q.baggage_confirmed for q in quotes)
    if not bags_known:
        warnings.append("수하물 조건 미확인")
    eligible = total is not None and bags_known and not reference and nights == c.nights and not any(q.provenance.observed_at > now for q in quotes)
    return Comparison(quotes, nights, tuple(warnings), total, quotes[0].currency, eligible)


def comparisons(roundtrips: Iterable[Quote], outbound: Iterable[Quote],
                inbound_factory: Callable[[], Iterable[Quote]], c: Conditions,
                now: datetime) -> Iterator[Comparison]:
    """Stream cross-products without retaining combinations or pruning candidates."""
    for q in roundtrips:
        result = evaluate((q,), c, now)
        if result:
            yield result
    if c.compare_oneways:
        for out in outbound:
            if not leg_matches(out.legs[0], c, True):
                continue
            for back in inbound_factory():
                if not leg_matches(back.legs[0], c, False):
                    continue
                result = evaluate((out, back), c, now)
                if result:
                    yield result


def sort_key(result: Comparison, mode: str = "direct_first") -> tuple:
    if mode not in ("direct_first", "price", "departure", "duration"):
        raise ValueError("알 수 없는 정렬")
    legs = tuple(leg for q in result.quotes for leg in q.legs)
    price = result.total if result.total is not None else Decimal("Infinity")
    direct = 0 if all(leg.direct is True for leg in legs) else 1
    departure = legs[0].departure
    duration = sum(leg.duration_minutes for leg in legs)
    suffix = tuple(q.id for q in result.quotes)
    keys = {"direct_first": (direct, price), "price": (price,), "departure": (departure, price), "duration": (duration, price)}
    return (result.currency, not result.rankable, *keys[mode], suffix)


def lowest_per_date(results: Iterable[Comparison], mode="direct_first") -> dict:
    """Manual results get an input-only label; never claims external verification."""
    best = {}
    for result in results:
        if not result.rankable:
            continue
        day = result.quotes[0].legs[0].departure.date()
        key = (day, result.currency, "수동 입력 포함" if result.manual else "자동 조회")
        if key not in best or sort_key(result, mode) < sort_key(best[key], mode):
            best[key] = result
    return best


def local_time_details(leg: Leg) -> dict:
    """Preserve supplied local timestamps; elapsed time uses UTC instants."""
    offset = (leg.arrival.date() - leg.departure.date()).days
    return {"departure_local": leg.departure.isoformat(), "arrival_local": leg.arrival.isoformat(),
            "arrival_day_label": f"{offset:+d}일" if offset else "당일",
            "duration_minutes": leg.duration_minutes, "direct": leg.direct}


def manual_checklist(c: Conditions, request: Request, homepage: str) -> dict:
    link(homepage)
    return {"status": "직접 확인 필요", "url": homepage, "request": request,
            "passengers": c.passengers, "cabin": c.cabin, "baggage": c.baggage,
            "direct_only": c.direct_only, "max_stops": c.max_stops,
            "max_duration_minutes": c.max_duration_minutes,
            "outbound_window": c.outbound_window, "inbound_window": c.inbound_window,
            "nights": c.nights, "return_deadline_korea_arrival": c.return_deadline,
            "note": "조건을 서비스에서 직접 입력하세요. 링크 제공은 가격 조회 완료가 아닙니다."}


def expansion_requests(outbound: Iterable[Leg], c: Conditions) -> Iterator[Request]:
    """Additional requests based on observed arrivals; does not promise completeness."""
    if not c.arrival_expansion:
        return
    seen = set()
    for leg in outbound:
        if not leg_matches(leg, c, True):
            continue
        returning = leg.arrival.date() + timedelta(days=c.nights)
        baseline = leg.departure.date() + timedelta(days=c.nights)
        if returning == baseline:
            continue
        for ro, rd in product(c.destinations if c.allow_destination_change else (leg.destination,),
                              c.origins if c.allow_origin_change else (leg.origin,)):
            requests = [Request("roundtrip", leg.origin, leg.destination, leg.departure.date(), returning, ro, rd)]
            if c.compare_oneways and not c.start + timedelta(days=c.nights) <= returning <= c.end + timedelta(days=c.nights):
                requests.append(Request("inbound", ro, rd, returning))
            for request in requests:
                if request not in seen:
                    seen.add(request)
                    yield request


class Status(StrEnum):
    NOT_SEARCHED = "아직 검색하지 않음"
    RUNNING = "검색 중"
    NOT_CONNECTED = "연동되지 않음"
    NO_RESULTS = "정상 조회했지만 조건에 맞는 결과 없음"
    SUCCESS = "조회 완료"
    FAILED = "요청 제한 또는 조회 실패"
    PARTIAL = "일부 결과만 확인됨"
    CANCELLED = "검색 취소"


def progress(statuses: Iterable[Status]) -> dict:
    counts = {s: 0 for s in Status}
    for status in statuses:
        counts[status] += 1
    total = sum(counts.values())
    completed = counts[Status.SUCCESS] + counts[Status.NO_RESULTS]
    if counts[Status.RUNNING]:
        state = Status.RUNNING
    elif counts[Status.PARTIAL] or (0 < completed < total):
        state = Status.PARTIAL
    elif total and completed == total:
        state = Status.SUCCESS if counts[Status.SUCCESS] else Status.NO_RESULTS
    elif counts[Status.FAILED]:
        state = Status.FAILED
    elif counts[Status.CANCELLED]:
        state = Status.CANCELLED
    elif counts[Status.NOT_CONNECTED]:
        state = Status.NOT_CONNECTED
    else:
        state = Status.NOT_SEARCHED
    return {"state": state.value, "total": total, "completed": completed,
            "counts": {k.value: v for k, v in counts.items()}}


def parse_korean(text: str) -> dict:
    """Conservative proposal only: never executes or fills a missing year/end."""
    result = {"original": text, "requires_confirmation": True, "executable": False}
    year = re.search(r"(\d{4})년", text)
    nights = re.search(r"(\d+)박", text)
    dates = re.findall(r"(\d{1,2})월\s*(\d{1,2})일", text)
    result["year"] = int(year[1]) if year else None
    result["nights"] = int(nights[1]) if nights else None
    result["start_month_day"] = list(map(int, dates[0])) if dates else None
    result["end_month_day"] = list(map(int, dates[1])) if len(dates) == 2 and "까지" in text else None
    result["destination_hint"] = next((x for x in ("도쿄", "오사카", "일본") if x in text), None)
    result["missing"] = [label for key, label in (("year", "연도"), ("nights", "숙박일수"),
                          ("start_month_day", "출발 시작일"), ("end_month_day", "출발 마지막 날")) if result[key] is None]
    result["missing"].append("출발·목적지 공항 및 구조화된 조건 확인")
    return result
