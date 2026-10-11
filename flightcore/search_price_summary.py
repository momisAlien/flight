"""Lowest observed search prices; no baggage/cabin equivalence certification."""
from decimal import Decimal,InvalidOperation


def minimum(rows):
    best=None;amount=None
    for index,row in enumerate(rows):
        try:
            value=row.get('amount')
            if value is None or isinstance(value,bool) or row.get('currency')!='KRW':continue
            price=Decimal(str(value))
            if not price.is_finite() or price<=0:continue
        except InvalidOperation:continue
        if amount is None or price<amount:
            amount=price;best={'row':index,'amount':str(price),'currency':'KRW',
                              'conditional':row.get('conditional'),'text':row.get('text',''),
                              'ticket_kind':row.get('ticket_kind','unverified')}
    return best


def summarize(provider,tasks):
    queries=[];comparisons=[]
    known=[(t.get('result') or {}).get('evaluated_conditions') for t in tasks]
    known=[c for c in known if c is not None]
    run_conditions=known[0] if known and all(c==known[0] for c in known) else None
    for task in tasks:
        data=task.get('result') or {}
        rows=data.get('observations') or []
        best=minimum(rows) if task['status']=='observed_partial' else None
        queries.append({'number':task['number'],'request':task['request'],'status':task['status'],
                        'observed_cards':len(rows),'minimum':best,'source':provider,
                        'url':data.get('search_url'),'observed_at':data.get('observed_at'),
                        'error':data.get('error'), 'conditions':data.get('evaluated_conditions') or run_conditions})
    for rt in queries:
        req=rt['request'];c=rt['conditions'] or {}
        if req.get('kind')!='roundtrip':continue
        out=[q for q in queries if q['conditions']==rt['conditions'] and q['request'].get('kind')=='outbound'
             and (q['request'].get('origin'),q['request'].get('destination'),q['request'].get('departure'))==(req['origin'],req['destination'],req['departure'])]
        back=[q for q in queries if q['conditions']==rt['conditions'] and q['request'].get('kind')=='inbound'
              and (q['request'].get('origin'),q['request'].get('destination'),q['request'].get('departure'))==(req.get('return_origin') or req['destination'],req.get('return_destination') or req['origin'],req.get('return_date'))]
        # Duplicate planned requests can share the same route; pick the lowest
        # observed query result, preserving its provenance and every raw query.
        def pick(items):return min((q for q in items if q['minimum']),key=lambda q:Decimal(q['minimum']['amount']),default=None)
        a,b=pick(out),pick(back)
        rt_amount=rt['minimum']['amount'] if rt['minimum'] else None
        ow_amount=str(Decimal(a['minimum']['amount'])+Decimal(b['minimum']['amount'])) if a and b and c.get('compare_oneways',True) else None
        winner=None;saving=None
        if rt_amount is not None and ow_amount is not None:
            difference=Decimal(rt_amount)-Decimal(ow_amount)
            winner='two_oneways' if difference>0 else 'roundtrip' if difference<0 else 'equal'
            saving=str(abs(difference))
        comparisons.append({'request':req,'roundtrip':rt_amount,'two_oneways':ow_amount,'currency':'KRW',
                            'lower_displayed':winner,'displayed_difference':saving,
                            'roundtrip_query':rt['number'],'outbound_query':a['number'] if a else None,
                            'inbound_query':b['number'] if b else None,
                            'conditional':any(q and q['minimum'] and q['minimum']['conditional'] is True for q in (rt,a,b))})
    comparisons.sort(key=lambda x:(min((Decimal(v) for v in (x['roundtrip'],x['two_oneways']) if v is not None),default=Decimal('Infinity')),x['request']['departure']))
    return {'source':provider,'mode':'search_display_price','queries':queries,'comparisons':comparisons,
            'total_queries':len(queries),'queries_with_price':sum(q['minimum'] is not None for q in queries),
            'label':'검색 화면 최저 표시가 · 왕복 vs 편도 두 장',
            'notice':'수하물·좌석 조건 비교 제외. 각 검색에서 관찰한 카드의 최저 표시가이며 카드 할인 조건이 포함될 수 있습니다. 검색 날짜 기준 조합이며 실제 도착 기준 숙박·시간 필터·결제 총액은 검증하지 않습니다.'}
