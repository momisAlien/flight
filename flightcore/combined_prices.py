"""Top 20 across current combined-run observations; cached MRT is labelled."""
from decimal import Decimal,InvalidOperation
from heapq import nsmallest,merge
from itertools import islice
from .core import plan


def amount(row):
    value=row.get('amount')
    if value is None or isinstance(value,bool) or row.get('currency')!='KRW':return None
    try:
        result=Decimal(str(value))
        return result if result.is_finite() and result>0 else None
    except InvalidOperation:return None


def ranking(c,browser_tasks,references):
    roundtrips=[];out={};back={};seen=set()
    slots={}
    for req in plan(c):
        if req.kind=='roundtrip':slots[(req.origin,req.destination,str(req.departure),req.return_origin or req.destination,req.return_destination or req.origin,str(req.return_date))]=req
    for provider,tasks in browser_tasks.items():
        for task in tasks:
            if task['status']!='observed_partial':continue
            req=task['request'];result=task.get('result') or {}
            for index,row in enumerate(result.get('observations',[])):
                price=amount(row)
                if price is None:continue
                key=(provider,req['kind'],req['origin'],req['destination'],req['departure'],req.get('return_date'),row.get('text'),str(price))
                if key in seen:continue
                seen.add(key)
                item={'source':provider,'amount':str(price),'currency':'KRW','basis':'search_display',
                      'request':req,'text':row.get('text',''),'conditional':row.get('conditional'),
                      'ticket_kind':row.get('ticket_kind','unverified'),'url':result.get('search_url'),
                      'observed_at':result.get('observed_at'),'task':task['number'],'row':index}
                if req['kind']=='roundtrip':
                    slot=(req['origin'],req['destination'],req['departure'],req.get('return_origin') or req['destination'],req.get('return_destination') or req['origin'],req.get('return_date'))
                    if slot in slots:roundtrips.append(item)
                elif req['kind'] in ('outbound','inbound'):
                    target=out if req['kind']=='outbound' else back
                    target.setdefault((req['origin'],req['destination'],req['departure']),[]).append(item)
    for response in references:
        if response.get('status')!='references_received':continue
        for index,row in enumerate(response.get('references',[])):
            price=amount({'amount':row.get('totalPrice'),'currency':'KRW'})
            slot=(row.get('fromCity'),row.get('toCity'),row.get('departureDate'),row.get('toCity'),row.get('fromCity'),row.get('returnDate'))
            if price is None or slot not in slots:continue
            key=('myrealtrip',slot,str(price),row.get('airline'))
            if key in seen:continue
            seen.add(key)
            roundtrips.append({'source':'myrealtrip','amount':str(price),'currency':'KRW','basis':'cached_reference',
                               'request':{'kind':'roundtrip','origin':slot[0],'destination':slot[1],'departure':slot[2],'return_date':slot[5]},
                               'text':str(row.get('airline') or '')+' · 저장 참고 가격 · 직항 캐시',
                               'conditional':None,'ticket_kind':'unverified','url':'https://flights.myrealtrip.com/',
                               'observed_at':None,'fetched_at':response.get('fetched_at'),'row':index})
    streams=[];pair_count=0
    def pairs(left,rights):
        for right in rights:
            yield (Decimal(left['amount'])+Decimal(right['amount']),left,right)
    if c.compare_oneways:
        for slot in slots:
            lefts=sorted(out.get(slot[:3],[]),key=lambda x:Decimal(x['amount']))
            rights=sorted(back.get(slot[3:],[]),key=lambda x:Decimal(x['amount']))
            pair_count+=len(lefts)*len(rights)
            streams.extend(pairs(left,rights) for left in lefts if rights)
    merged=merge(*streams,key=lambda x:x[0])
    combinations=[{'amount':str(value),'currency':'KRW','outbound':a,'inbound':b,'kind':'two_oneways'} for value,a,b in islice(merged,20)]
    return {'roundtrips':nsmallest(20,roundtrips,key=lambda x:Decimal(x['amount'])),
            'oneway_combinations':combinations,'roundtrip_total':len(roundtrips),'oneway_total':pair_count,
            'limit_per_category':20,'notice':'현재 로드된 검색 카드의 표시가 기준이며 전체 항공편 최저가 보장은 아닙니다. 수하물·좌석·시간 필터 제외 · 카드 할인 조건 포함 가능. 왕복 단일 발권 미확인, 편도 조합은 별도 구매입니다. 마이리얼트립은 저장 왕복 참고가이며 편도 미지원. 각 가격의 조회 시각이 다를 수 있습니다.'}
