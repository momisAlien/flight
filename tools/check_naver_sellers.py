"""Explicit single-itinerary all-payment seller audit, without booking."""
import json
import argparse
import threading
from collections import Counter
from datetime import date
from pathlib import Path
from flightcore.browser_prices import BrowserCollector,naver_navigation_key
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped
from flightcore.browser_jobs import BrowserJobs
from flightcore.serde import dumps


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='naver-seller-audit-20261007.json')
    parser.add_argument('--outbound-time')
    parser.add_argument('--inbound-time')
    parser.add_argument('--conditional',action='store_true',help='조건부 검색 카드에서 모든 결제수단 상세로 이동하는 경로 검증')
    parser.add_argument('--kind',choices=('roundtrip','outbound','inbound'),default='roundtrip')
    parser.add_argument('--refresh-before-detail',action='store_true',help='웹 작업과 같은 재검색·일정 식별·결제 조건 기록 경로 사용')
    args=parser.parse_args()
    output=Path(args.output)
    if output.exists():parser.error('새 출력 파일명을 지정하세요')
    c=BrowserCollector('naver',threading.Event())
    result={}
    try:
        c.open()
        request=(Request('inbound','NRT','ICN',date(2026,12,15)) if args.kind=='inbound' else
                 Request(args.kind,'ICN','NRT',date(2026,12,10),date(2026,12,15) if args.kind=='roundtrip' else None))
        result=c.collect(request)
        counts=Counter(naver_navigation_key(row['text']) for row in result['observations'])
        index=next(i for i,row in enumerate(result['observations']) if row['conditional']==args.conditional and counts[naver_navigation_key(row['text'])]==1
                   and (not args.outbound_time or args.outbound_time+'ICN' in row['text'])
                   and (not args.inbound_time or args.inbound_time+'NRT' in row['text']))
        row=result['observations'][index]
        result['selected_index']=index
        row['seller_detail']=(BrowserJobs.collect_detail(c,'naver',dumps(request),dumps(result),index)
                              if args.refresh_before_detail else c.selected_naver_details(request,row['text']))
        result['detail_status']='observed'
    except ProbeStopped as error:
        result['detail_status']=error.status;result['detail_error']=error.detail
    except StopIteration:
        result['detail_status']='candidate_unavailable'
        result['detail_error']='현재 관찰에서 조건에 맞는 유일한 카드를 찾지 못했습니다'
    finally:
        if c.driver is not None:
            try:
                output.with_suffix('.txt').write_text(c.check(),encoding='utf-8')
                c.driver.save_screenshot(str(output.with_suffix('.png')))
            except Exception:pass
        c.close()
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    detail=result.get('observations',[{}])[result.get('selected_index',0)].get('seller_detail',{})
    print(json.dumps({'status':result.get('detail_status'),'seller_count':len(detail.get('offers',[]))}),flush=True)
    return 0 if result.get('detail_status')=='observed' else 2


if __name__=='__main__':raise SystemExit(main())
