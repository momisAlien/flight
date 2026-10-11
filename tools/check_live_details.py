"""Explicit live acceptance: all supported observed cards, no truncation."""
import json
import argparse
import threading
from datetime import date
from pathlib import Path
from uuid import uuid4
from flightcore.browser_prices import BrowserCollector
from flightcore.browser_jobs import BrowserJobs
from flightcore.core import Request
from flightcore.serde import dumps
from flightcore.provider_probe import ProbeStopped


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='google-batch-details-20261007.json')
    parser.add_argument('--provider',choices=('google','naver'),default='google')
    parser.add_argument('--departure',type=date.fromisoformat,default=date(2026,12,10))
    parser.add_argument('--return-date',type=date.fromisoformat)
    parser.add_argument('--db',default='detail-stage-check.db')
    parser.add_argument('--resume-run',help='명시적으로 중단 작업의 pending 항목만 재개; 실패 항목 재시도 안 함')
    args=parser.parse_args()
    if Path(args.output).exists():parser.error('새 출력 파일명을 지정하세요')
    if args.resume_run:
        jobs=BrowserJobs(args.db)
        jobs.resume_pending_details(args.resume_run)
        return finish(jobs,args.resume_run,args.output)
    if args.return_date and (args.provider=='google' or args.return_date<=args.departure):
        parser.error('왕복 상세는 네이버에서 출발일 이후 귀국일로 실행하세요')
    request=Request('roundtrip' if args.return_date else 'outbound','ICN','NRT',args.departure,args.return_date)
    collector=BrowserCollector(args.provider,threading.Event())
    try:
        collector.open();result=collector.collect(request)
    except ProbeStopped as error:
        evidence={'status':error.status,'detail':error.detail,'phase':'initial_search','comparison_eligible':False}
        Path(args.output).write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        if collector.driver is not None:
            collector.driver.save_screenshot(str(Path(args.output).with_suffix('.png')))
        print(json.dumps({'status':error.status,'phase':'initial_search'}),flush=True)
        return 2
    finally:collector.close()
    jobs=BrowserJobs(args.db);id=uuid4().hex
    with jobs.db() as db:
        db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',(id,args.provider,'completed_observations',1,''))
        db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',(id,1,dumps(request),'observed_partial',dumps(result)))
    preview=jobs.detail_plan(id)
    print(json.dumps({'id':id,'detail_plan':{k:v for k,v in preview.items() if k not in ('candidates','skipped','notice')}}),flush=True)
    if not preview['count']:
        evidence=jobs.status(id)
        evidence['detail_plan']={k:v for k,v in preview.items() if k not in ('candidates','skipped')}
        Path(args.output).write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        return 2
    jobs.start_details(id)
    return finish(jobs,id,args.output)


def finish(jobs,id,output):
    previous=None
    try:
        while jobs.thread.is_alive():
            state=jobs.status(id)
            if state['detail_counts']!=previous:
                print(json.dumps(state['detail_counts']),flush=True);previous=state['detail_counts']
            jobs.thread.join(2)
    except KeyboardInterrupt:
        jobs.cancel(id)
        jobs.thread.join()
    state=jobs.status(id)
    Path(output).write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'id':id,'status':state['status'],'counts':state['detail_counts']}),flush=True)
    return 0 if state['status']=='completed_details' else 2


if __name__=='__main__':raise SystemExit(main())
