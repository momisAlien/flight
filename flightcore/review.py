"""Transparent diagnostic layer: excludes from ranking, never hides the input."""
from dataclasses import asdict
from datetime import timedelta, timezone
from decimal import Decimal
from .core import Request, Quote, Conditions, plan, expansion_requests, days


def role(leg, c):
    if leg.origin in c.origins and leg.destination in c.destinations:
        return "outbound"
    if leg.origin in c.destinations and leg.destination in c.origins:
        return "inbound"
    return "outside"


def quote_reasons(q, c, now):
    reasons = []
    if q.passengers != c.passengers:
        reasons.append("승객 구성 불일치")
    if q.cabin != c.cabin:
        reasons.append("좌석 등급 불일치")
    if q.baggage != c.baggage:
        reasons.append("수하물 요구 조건 불일치")
    if not q.baggage_confirmed:
        reasons.append("수하물 미확인")  # Keep strict policy until user's approval.
    if q.taxes_included is not True:
        reasons.append("세금 미확인 또는 미포함")
    if q.confirmed_total is None and q.taxes_included is True:
        reasons.append("필수 수수료 미확인")
    elif q.mandatory_fees_included is None or (q.mandatory_fees_included is False and q.extra_mandatory_fee is None):
        reasons.append("필수 수수료 미확인")
    if q.cached or q.expires_at and q.expires_at <= now:
        reasons.append("참고용 후보 · 캐시 또는 만료")
    if q.provenance.observed_at > now:
        reasons.append("조회 시각이 미래")
    for index, leg in enumerate(q.legs):
        direction = ("outbound" if index == 0 else "inbound") if len(q.legs) == 2 else role(leg,c)
        prefix = "가는 편" if direction == "outbound" else "오는 편" if direction == "inbound" else "입력 구간"
        if role(leg,c) != direction or direction == "outside":
            reasons.append(f"{prefix}: 선택 공항 범위 밖")
        if direction == "outbound" and not c.start <= leg.departure.date() <= c.end:
            reasons.append("출발 기간 불일치")
        if direction == "inbound":
            minimum = c.start + timedelta(days=c.nights)
            maximum = c.end + timedelta(days=c.nights)
            if not c.arrival_expansion and not minimum <= leg.departure.date() <= maximum:
                reasons.append("귀국 날짜 범위 불일치")
            if c.return_deadline and leg.arrival.astimezone(timezone(timedelta(hours=9))).date() > c.return_deadline:
                reasons.append("한국 도착 귀국 마감일 초과")
        window = c.outbound_window if direction == "outbound" else c.inbound_window
        if window and not window.contains(leg.departure.time()):
            reasons.append(f"{prefix}: 출발 시간 조건 불일치")
        if c.direct_only:
            if leg.direct is None:
                reasons.append(f"{prefix}: 직항 미확인 (중간 기착 미확인)")
            elif leg.direct is False:
                reasons.append(f"{prefix}: 직항 조건 불일치")
        elif leg.stops is None:
            reasons.append(f"{prefix}: 경유 횟수 미확인")
        elif leg.stops > c.max_stops:
            reasons.append(f"{prefix}: 최대 경유 횟수 초과")
        if c.max_duration_minutes is not None and leg.duration_minutes > c.max_duration_minutes:
            reasons.append(f"{prefix}: 최대 소요시간 초과")
    return list(dict.fromkeys(reasons))


def assess(quotes, c, now, extra_reasons=()):
    reasons = [r for q in quotes for r in quote_reasons(q,c,now)] + list(extra_reasons)
    legs = [leg for q in quotes for leg in q.legs]
    notes = []
    actual_nights = None
    if len(legs) == 2:
        out,back = legs
        if role(out,c) != "outbound" or role(back,c) != "inbound":
            reasons.append("출국·귀국 방향 불일치")
        if out.origin != back.destination:
            notes.append("한국 공항 변경")
            if not c.allow_origin_change:
                reasons.append("한국 공항 변경 허용 안 됨")
        if out.destination != back.origin:
            notes.append("현지 공항 변경")
            if not c.allow_destination_change:
                reasons.append("현지 공항 변경 허용 안 됨")
        expected = out.departure.date() + timedelta(days=c.nights)
        permitted = {expected}
        if c.arrival_expansion:
            permitted.add(out.arrival.date() + timedelta(days=c.nights))
        if back.departure.date() not in permitted:
            reasons.append("귀국 날짜 불일치")
        actual_nights=(back.departure.date()-out.arrival.date()).days
        if actual_nights != c.nights:
            reasons.append("숙박일수 불일치")
        if back.departure.astimezone(timezone.utc) <= out.arrival.astimezone(timezone.utc):
            reasons.append("출국 도착 이후 귀국 출발 조건 불일치")
    else:
        reasons.append("왕복 일정 미완성 · 반대 방향 입력 필요")
    currencies = set(q.currency for q in quotes)
    if len(currencies)>1:
        reasons.append("통화 불일치 · 합산 안 함")
    amounts = [q.confirmed_total for q in quotes]
    total = sum(amounts,Decimal(0)) if len(currencies)==1 and all(a is not None for a in amounts) else None
    reasons = list(dict.fromkeys(reasons))
    kind = "왕복 예약 입력" if len(quotes)==1 and len(legs)==2 else "편도 2건 별도 예약 입력" if len(quotes)==2 else "편도 단독 입력"
    if len(quotes)==2:
        notes.append("변경·취소는 각 예약에서 별도 처리")
    return {"quotes":quotes, "reasons":reasons, "notes":notes, "actual_nights":actual_nights,
            "requested_nights":c.nights,"total":total, "currency":quotes[0].currency if len(currencies)==1 else "혼합",
            "rankable":not reasons,"booking_type":kind,"label":"수동 입력 · 외부 검증 안 됨",
            "departure_date":legs[0].departure.date(),"departure":legs[0].departure.isoformat(),
            "duration":sum(l.duration_minutes for l in legs),"direct":all(l.direct is True for l in legs)}


def review_stream(roundtrips, oneways_factory, c, now, should_cancel=lambda:False):
    for q in roundtrips:
        if should_cancel():
            return
        yield assess((q,),c,now)
    used = set()
    def time_allowed(leg, direction):
        window=c.outbound_window if direction=="outbound" else c.inbound_window
        return window is None or window.contains(leg.departure.time())
    if c.compare_oneways:
        for out in oneways_factory():
            if should_cancel():
                return
            leg=out.legs[0]
            if role(leg,c)!="outbound" or not time_allowed(leg,"outbound"):
                continue
            dates={leg.departure.date()+timedelta(days=c.nights)}
            if c.arrival_expansion:
                dates.add(leg.arrival.date()+timedelta(days=c.nights))
            for back in oneways_factory():
                if should_cancel():
                    return
                if role(back.legs[0],c)=="inbound" and time_allowed(back.legs[0],"inbound") and back.legs[0].departure.date() in dates:
                    used.update((out.id,back.id))
                    yield assess((out,back),c,now)
    for q in oneways_factory():
        if should_cancel():
            return
        if q.id not in used:
            reason="편도 조합 비교 꺼짐" if not c.compare_oneways else "귀국 날짜·출발 시간 조건을 만족하는 반대 방향 조합 없음"
            yield assess((q,),c,now,(reason,))


def input_requests(q,c):
    if q.cached or q.passengers!=c.passengers or q.cabin!=c.cabin or q.baggage!=c.baggage:
        return []
    if len(q.legs)==2:
        out,back=q.legs
        return [Request("roundtrip",out.origin,out.destination,out.departure.date(),back.departure.date(),back.origin,back.destination)]
    leg=q.legs[0]
    return [Request(role(leg,c),leg.origin,leg.destination,leg.departure.date())]


def coverage(quotes_factory,c):
    expected=set(plan(c))
    base=len(expected)
    if c.arrival_expansion:
        legs=(q.legs[0] for q in quotes_factory() if role(q.legs[0],c)=="outbound" and not q.cached)
        expected.update(expansion_requests(legs,c))
    entered=set()
    for q in quotes_factory():
        entered.update(r for r in input_requests(q,c) if r in expected)
    calendar=[]
    for d in days(c.start,c.end):
        day_requests=set(r for r in expected if r.kind!="inbound" and r.departure==d)
        for r in tuple(day_requests):
            if r.kind=="roundtrip" and c.compare_oneways:
                incoming=Request("inbound",r.return_origin,r.return_destination,r.return_date)
                if incoming in expected:
                    day_requests.add(incoming)
        count=len(day_requests & entered)
        calendar.append({"date":d.isoformat(),"entered":count,"expected":len(day_requests),
                         "state":"미입력" if count==0 else "입력 있음"})
    return {"expected":len(expected),"base_expected":base,"entered":len(entered),"remaining":len(expected-entered),
            "label":f"예상 조건 {len(expected):,}건 중 {len(entered):,}건 입력됨", "calendar":calendar,
            "note":"공항·날짜·예약형태·승객·좌석·수하물 요구가 같은 조건의 중복 입력은 1건. 확인 항목 미상/시간 제외 입력도 입력률에는 포함. 가격 조회 완료율이 아닙니다.",
            "expansion_note":"관찰된 도착일 기준 확장만 포함 · 전체 운항 보장 아님" if c.arrival_expansion else "기본 귀국일 기준"}
