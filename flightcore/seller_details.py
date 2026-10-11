"""Read Google booking-option statements, without opening a seller checkout."""
import re
from .baggage_evidence import enrich_offer


def naver_offer(label, text):
    """One visible seller wrapper, not a page-wide minimum or graph price."""
    if not label.endswith('에서 예약'):
        raise ValueError('판매처 이름 미확인')
    seller = label.removesuffix('에서 예약')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    prices = re.findall(r'^([\d,]+)\s*\n원$', text.strip(), re.MULTILINE)
    if not seller or not lines or lines[0] != seller or len(prices) != 1:
        raise ValueError('판매처와 가격 연결 미확인')
    amount = int(prices[0].replace(',',''))
    if amount <= 0:
        raise ValueError('판매처 가격 오류')
    return enrich_offer({'seller':seller,'amount':amount,'currency':'KRW','price_status':'observed',
            'seller_statements':lines[1:-2], 'comparison_eligible':False})


def google_details(body):
    if '예약 옵션\n' not in body or '통화KRW' not in body:
        raise ValueError('예약 옵션·통화 미확인')
    section = body.split('예약 옵션\n', 1)[1].split('가격에는', 1)[0]
    pattern = r'^([^\n]+?)에서 예약(?:항공사)?$'
    matches = list(re.finditer(pattern, section, re.MULTILINE))
    if not matches or len(matches) != section.count('에서 예약'):
        raise ValueError('판매처별 가격 구조 미확인')
    offers = []
    for index, match in enumerate(matches):
        end = matches[index+1].start() if index+1 < len(matches) else len(section)
        block = section[match.end():end]
        options = re.split(r'^계속$', block, flags=re.MULTILINE)
        if len(options) < 2:
            raise ValueError('판매처 예약 선택지 미확인')
        # Each Continue closes one fare option, including its own baggage and
        # change restrictions. Do not combine fare families under one price.
        for option in options[:-1]:
            lines = [line.strip() for line in option.splitlines() if line.strip()]
            prices = re.findall(r'^₩([\d,]+)$', option, re.MULTILINE)
            unpriced = '사이트에서 가격을 확인하세요.' in lines
            if len(prices) > 1 or bool(prices) == unpriced:
                raise ValueError('선택지별 금액 미확인')
            amount = int(prices[0].replace(',','')) if prices else None
            offers.append({'seller':match[1], 'amount':amount,
                           'currency':'KRW' if prices else None,
                           'price_status':'observed' if prices else 'not_provided',
                           'seller_statements':[line for line in lines if not re.fullmatch(r'₩[\d,]+',line)],
                           'comparison_eligible':False})
        if re.search(r'^₩[\d,]+$', options[-1], re.MULTILINE):
            raise ValueError('마지막 예약 선택지 구조 미확인')
    if any(offer['amount'] is not None and offer['amount'] <= 0 for offer in offers):
        raise ValueError('판매처 가격 오류')
    taxes = '가격에는 성인 1명의 필수 세금과 수수료가 포함됩니다.' in body
    bags = [line for line in body.splitlines() if '수하물' in line]
    return {'offers': [enrich_offer(offer) for offer in offers], 'baggage_statements': bags,
            'taxes_and_mandatory_fees_stated_included': True if taxes else None,
            'passenger_and_cabin_stated': '성인 1명·일반석' if taxes and '편도이코노미' in body else None,
            'baggage_allowance_verified': False, 'checkout_verified': False,
            'comparison_eligible': False,
            'notice': 'Google 예약 옵션 표시만 확인. 수하물 무게·구매 조건·판매처 결제 총액 미확인.'}
