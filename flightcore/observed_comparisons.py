"""Unverified displayed-fare combinations, strictly separate from Quote ranking."""
from datetime import datetime, timezone, timedelta
from .comparison_readiness import priced
from .observed_schedules import assess
from .serde import conditions_from_dict
from .core import Request
from datetime import date
from decimal import Decimal
from heapq import merge
from itertools import islice


def groups(provider, tasks):
    rt, out, back = [], [], []
    for task in tasks:
        data=task.get('result') or {}
        raw_conditions=data.get('evaluated_conditions')
        if task['status']!='observed_partial' or not raw_conditions:
            continue
        c=conditions_from_dict(raw_conditions)
        req=dict(task['request'])
        req['departure']=date.fromisoformat(req['departure'])
        if req.get('return_date'):req['return_date']=date.fromisoformat(req['return_date'])
        request=Request(**req)
        if request.kind in ('outbound','roundtrip') and not (c.start<=request.departure<=c.end and request.origin in c.origins and request.destination in c.destinations):continue
        if request.kind=='inbound' and not (request.origin in c.destinations and request.destination in c.origins):continue
        for index,row in enumerate(data.get('observations',[])):
            detail=row.get('seller_detail') or {}
            if provider=='naver' and detail.get('payment_condition')!='성인/모든 결제수단':continue
            schedule=assess(provider,row,request,c)
            if schedule['reasons'] or len(schedule['legs'])!=(2 if request.return_date else 1):continue
            offers=[o for o in detail.get('offers',[]) if priced(o)]
            if not offers:continue
            item={'task':task['number'],'row':index,'conditions':raw_conditions,'legs':schedule['legs'],
                  'offers':offers,'observed_at':detail.get('observed_at'),'url':detail.get('url'),
                  'source':provider,'payment_condition':detail.get('payment_condition','미확인')}
            if request.kind=='roundtrip' and schedule.get('actual_nights')==c.nights:rt.append(item)
            elif request.kind=='outbound':out.append(item)
            elif request.kind=='inbound':back.append(item)
    for item in rt:
        yield (item,)
    for first in out:
        c=conditions_from_dict(first['conditions'])
        if not c.compare_oneways:continue
        for second in back:
            if first['conditions']!=second['conditions']:continue
            a,b=first['legs'][0],second['legs'][0]
            if a['origin'] not in c.origins or a['destination'] not in c.destinations:continue
            if b['origin'] not in c.destinations or b['destination'] not in c.origins:continue
            if not c.allow_origin_change and a['origin']!=b['destination']:continue
            if not c.allow_destination_change and a['destination']!=b['origin']:continue
            arrival=datetime.fromisoformat(a['arrival']); departure=datetime.fromisoformat(b['departure'])
            if departure<=arrival or (departure.date()-arrival.date()).days!=c.nights:continue
            if c.return_deadline and datetime.fromisoformat(b['arrival']).astimezone(timezone(timedelta(hours=9))).date()>c.return_deadline:continue
            yield (first,second)


def ordered_group(group):
    """Merge all seller pairs in displayed-price order without materializing them."""
    prices=[sorted(enumerate(item['offers']),key=lambda pair:(Decimal(str(pair[1]['amount'])),pair[0])) for item in group]
    if len(group)==1:
        for index,offer in prices[0]:
            yield Decimal(str(offer['amount'])),(index,)
    else:
        def row(left_index,left_offer):
            for right_index,right_offer in prices[1]:
                yield Decimal(str(left_offer['amount']))+Decimal(str(right_offer['amount'])),(left_index,right_index)
        yield from merge(*(row(index,offer) for index,offer in prices[0]))


def page(provider,tasks,number=1):
    if type(number) is not int or number<1:raise ValueError('페이지 번호는 1 이상이어야 합니다')
    all_groups=list(groups(provider,tasks))
    total=sum(len(g[0]['offers'])*(len(g[1]['offers']) if len(g)==2 else 1) for g in all_groups)
    def stream(index,group):
        for amount,indices in ordered_group(group):yield amount,index,indices
    ordered=merge(*(stream(index,g) for index,g in enumerate(all_groups)))
    items=[]
    for amount,index,indices in islice(ordered,(number-1)*10,number*10):
        group=all_groups[index];parts=[]
        for item,offer_index in zip(group,indices):
            parts.append({k:v for k,v in item.items() if k not in ('offers','conditions')})
            parts[-1]['offer']=item['offers'][offer_index]
        items.append({'kind':'two_oneways' if len(group)==2 else 'roundtrip',
                      'displayed_sum':str(amount),'currency':'KRW','parts':parts,'rankable':False,
                      'notice':'표시가 합계 후보 · 세금·필수 비용·수하물·기착·발권 조건 미검증 · 구매 가능 총액 아님'})
    return {'items':items,'total':total,'page':number,'pages':max(1,(total+9)//10),
            'sort':'displayed_price_ascending',
            'rankable':False,'label':'저장된 표시가 후보 비교 · 표시가 낮은 순 · 확정 최저가 순위 아님',
            'notice':'모든 관찰 판매처 조합을 표시가 합계 순으로 제공합니다. 상세 미조회·실패·일정 미확인·조건 누락 항목은 조합할 수 없으며 전체 재고나 현재 결제 최저가를 뜻하지 않습니다.'}
