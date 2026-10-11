"""Read-only readiness diagnostics; observations never become verified Quotes here."""
from decimal import Decimal, InvalidOperation
from datetime import datetime
from urllib.parse import urlsplit


def priced(offer):
    value = offer.get('amount')
    if isinstance(value, bool) or value is None:
        return False
    try:
        amount = Decimal(str(value))
        return amount.is_finite() and amount > 0 and offer.get('currency') == 'KRW' and bool(str(offer.get('seller') or '').strip())
    except InvalidOperation:
        return False


def audit(provider, request, observation):
    detail = observation.get('seller_detail') or {}
    schedule = observation.get('schedule') or {}
    checks = []

    def add(code, state, label):
        checks.append({'code': code, 'state': state, 'label': label})

    add('seller_detail', 'observed' if detail else 'missing',
        '판매처 상세 표시 확인' if detail else '판매처 상세 미조회 또는 확인 실패')
    offers = detail.get('offers') or []
    price_count = sum(priced(offer) for offer in offers)
    add('seller_prices', 'observed' if price_count else 'missing',
        f'판매처·양수 KRW 표시 가격 {price_count}개 확인' if price_count else '판매처·양수 KRW 가격 미확인')
    valid_source = False
    try:
        stamp = datetime.fromisoformat(detail.get('observed_at', ''))
        url = urlsplit(detail.get('url', ''))
        valid_source = stamp.utcoffset() is not None and url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password
    except (ValueError, TypeError):
        pass
    add('provenance', 'observed' if valid_source else 'missing',
        '상세 출처·관찰 시각 기록 있음 · 현재 가격 재확인 필요' if valid_source else '상세 출처·관찰 시각 미확인')
    payment = provider == 'naver' and detail.get('payment_condition') == '성인/모든 결제수단'
    add('payment', 'observed' if payment else 'missing',
        '모든 결제수단 표시 확인' if payment else '판매처별 적용 결제 조건 미확인')
    expected = 2 if request.get('return_date') else 1
    legs = schedule.get('legs') or []
    reasons = schedule.get('reasons') or []
    add('schedule', 'excluded' if reasons else 'observed' if len(legs) == expected else 'missing',
        '일정 조건 제외: ' + ' / '.join(reasons) if reasons else
        '표시 일정 읽기 완료 · 상세 기착 검증 별도' if len(legs) == expected else '전체 구간 일정·시간대 미확인')
    # Current collectors do not provide per-offer normalized evidence for these
    # requirements. Page-wide text/booleans cannot certify individual fares.
    add('passenger_cabin', 'missing', '판매처 운임의 인원·좌석 조건 일치 미검증')
    add('baggage', 'missing', '판매처 운임별 수하물 허용량·추가 비용 미검증')
    add('total_fees', 'missing', '판매처 운임별 세금·필수 수수료 포함 총액 미검증')
    add('intermediate_stops', 'missing', '전체 구간의 중간 기착 여부 미검증')
    add('journey', 'missing', '단일 왕복 발권 여부 미검증' if expected == 2 else '편도 단독 결과 · 숙박일수·귀국 마감은 표시가 후보 조합에서 별도 판정')
    add('comparison_adapter', 'missing', '자동 수집 운임의 확정 비교 연결 미완료')
    return {'status': 'excluded' if reasons else 'unverified', 'comparison_eligible': False,
            'checks': checks, 'priced_seller_options': price_count,
            'unpriced_seller_options': len(offers) - price_count,
            'notice': '표시 정보 진단이며 완성률·현재 구매 가능 가격·전체 재고 확인을 뜻하지 않습니다.'}
