"""One explicitly requested real browser check; no automatic retries."""
import argparse
import json
import threading
from datetime import date
from pathlib import Path
from .browser_prices import BrowserCollector
from .core import Request,code
from .provider_probe import ProbeStopped
from .observed_schedules import assess


def main():
    p=argparse.ArgumentParser()
    p.add_argument('provider',choices=('google','naver'))
    p.add_argument('--origin',required=True,type=code)
    p.add_argument('--destination',required=True,type=code)
    p.add_argument('--departure',required=True,type=date.fromisoformat)
    p.add_argument('--return-date',type=date.fromisoformat)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--detail-index',type=int,help='카드 번호(0부터): Google 편도 또는 네이버 모든 결제수단 상세 확인')
    args=p.parse_args()
    if args.output.exists():p.error('새 출력 파일명을 지정하세요')
    if args.detail_index is not None and ((args.provider=='google' and args.return_date) or args.detail_index<0):
        p.error('0 이상 카드 번호를 지정하세요. Google 왕복 상세는 아직 지원하지 않습니다')
    if args.origin==args.destination or args.departure<date.today() or (args.return_date and args.return_date<=args.departure):
        p.error('공항·날짜를 확인하세요')
    c=BrowserCollector(args.provider,threading.Event())
    try:
        c.open()
        request=Request('roundtrip' if args.return_date else 'outbound',args.origin,args.destination,args.departure,args.return_date)
        result=c.collect(request)
        for row in result['observations']:
            row['schedule']=assess(args.provider,row,request)
        if args.detail_index is not None:
            if args.detail_index>=len(result['observations']):
                raise ProbeStopped('unverified_response','요청한 카드 번호가 결과 범위를 벗어납니다')
            row=result['observations'][args.detail_index]
            try:
                row['seller_detail']=(c.selected_google_details if args.provider=='google' else c.selected_naver_details)(request,row['text'])
            except ProbeStopped as error:
                result['detail_check']={'status':error.status,'detail':error.detail}
            except Exception as error:
                result['detail_check']={'status':'browser_error','exception_type':type(error).__name__}
    except ProbeStopped as error:
        result={'status':error.status,'detail':error.detail,'comparison_eligible':False}
    except Exception as error:
        result={'status':'browser_error','exception_type':type(error).__name__,'comparison_eligible':False}
    finally:
        if c.driver is not None:
            try:c.driver.save_screenshot(str(args.output.with_suffix('.png')))
            except Exception:pass
        try:c.close()
        except Exception:pass
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'observations':len(result.get('observations',[])),'output':str(args.output)}))
    return 0 if result['status']=='observed_partial' and 'detail_check' not in result else 2


if __name__=='__main__':raise SystemExit(main())
