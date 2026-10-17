"""Durable per-query observation jobs, separate from verified fare comparison."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from uuid import uuid4
from datetime import date
from collections import Counter

from .browser_prices import BrowserCollector, validate, google_itinerary_key, naver_navigation_key, naver_payment_label
from .core import plan, Request
from .provider_probe import ProbeStopped
from .serde import dumps
from .observed_schedules import assess
from .comparison_readiness import audit
from .baggage_evidence import enrich_offer


def naver_key_or_none(label):
    try:
        return naver_navigation_key(label)
    except ValueError:
        return None


class BrowserJobs:
    def __init__(self, path, factory=BrowserCollector, recover_interrupted=True):
        self.path, self.factory = path, factory
        self.lock = threading.Lock()
        self.thread = None
        self.cancelled = threading.Event()
        self.active_id = None
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS browser_runs(id TEXT PRIMARY KEY,provider TEXT,status TEXT,total INTEGER,detail TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS browser_tasks(run TEXT,n INTEGER,request TEXT,status TEXT,result TEXT,PRIMARY KEY(run,n))')
            db.execute('CREATE TABLE IF NOT EXISTS browser_details(run TEXT,n INTEGER,row INTEGER,status TEXT,result TEXT,PRIMARY KEY(run,n,row))')
            if recover_interrupted:
                db.execute("UPDATE browser_runs SET status='interrupted',detail='서버 종료로 중단' WHERE status IN ('running','running_details')")
                db.execute("UPDATE browser_tasks SET status='interrupted' WHERE status='running'")
                db.execute("UPDATE browser_details SET status='interrupted' WHERE status='running'")

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self, c, provider):
        validate(c, provider)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("브라우저 조회가 이미 진행 중입니다")
            self.cancelled.clear()
            id = uuid4().hex
            with self.db() as db:
                total = 0
                for total, request in enumerate(plan(c), 1):
                    db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',
                               (id,total,dumps(request),'pending',None))
                db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',(id,provider,'running',total,''))
            self.active_id = id
            self.thread = threading.Thread(target=self.run,args=(id,c,provider),daemon=True)
            self.thread.start()
            return id

    def run(self, id, c, provider):
        collector = None
        status, detail, current = 'completed_observations', '', None
        try:
            collector = self.factory(provider,self.cancelled)
            collector.open()
            total = self.status(id)['total']
            for n, request in enumerate(plan(c), 1):
                if self.cancelled.is_set():
                    raise ProbeStopped('cancelled','사용자가 중단했습니다')
                current = n
                with self.db() as db:
                    db.execute("UPDATE browser_tasks SET status='running' WHERE run=? AND n=?",(id,n))
                item_status = 'observed_partial'
                try:
                    result = collector.collect(request)
                    result['evaluated_conditions'] = json.loads(dumps(c))
                    for observation in result['observations']:
                        observation['schedule'] = assess(provider, observation, request, c)
                    result['notice'] = '현재 로드된 카드만 관찰. 읽을 수 있는 일정의 시간·소요시간·귀국 마감 조건 점검. 중간 기착·판매처·수하물·확정 운임 및 전체 항공편 미검증.'
                except ProbeStopped as error:
                    if error.status not in ('unverified_response', 'schema_changed'):
                        raise
                    item_status = error.status
                    result = {'observations': [], 'error': error.detail, 'comparison_eligible': False}
                    status = 'completed_partial_observations'
                    detail = '조회 실패 조건은 미확인으로 보존했습니다. 항공편 없음이나 0원으로 처리하지 않습니다'
                with self.db() as db:
                    db.execute("UPDATE browser_tasks SET status=?,result=? WHERE run=? AND n=?",
                               (item_status,dumps(result),id,n))
                current = None
                if n < total and self.cancelled.wait(2):
                    raise ProbeStopped('cancelled','사용자가 중단했습니다')
        except ProbeStopped as error:
            status, detail = error.status, error.detail
        except Exception:
            status, detail = 'browser_error', 'Chrome·드라이버 설치 또는 브라우저 오류. 상세 인증정보는 기록하지 않습니다'
        finally:
            if collector is not None:
                try:
                    collector.close()
                except Exception:
                    pass
            with self.db() as db:
                if current is not None:
                    db.execute("UPDATE browser_tasks SET status=? WHERE run=? AND n=?",(status,id,current))
                db.execute('UPDATE browser_runs SET status=?,detail=? WHERE id=?',(status,detail,id))

    def cancel(self, id):
        self.status(id)
        with self.lock:
            if id == self.active_id:
                self.cancelled.set()

    def detail_plan(self, id):
        state = self.status(id)
        if state['provider'] not in ('google','naver') or state['status'] not in ('completed_observations','completed_partial_observations'):
            raise ValueError('조건별 관찰 종료 후 상세 조회를 실행하세요')
        with self.db() as db:
            if db.execute('SELECT COUNT(*) FROM browser_details WHERE run=?',(id,)).fetchone()[0]:
                raise ValueError('이 작업의 상세 조회는 이미 실행됐습니다. 실패 작업은 자동 재시도하지 않습니다')
            rows = db.execute("SELECT n,request,result FROM browser_tasks WHERE run=? AND status='observed_partial' ORDER BY n",(id,)).fetchall()
        candidates = []
        skipped = []
        roundtrip = 0
        conditional_cards = 0
        for n, request, result in rows:
            req, data = json.loads(request), json.loads(result)
            if req.get('return_date') and state['provider']=='google':
                roundtrip += len(data['observations'])
            else:
                identities=Counter(naver_key_or_none(row['text']) for row in data['observations']) if state['provider']=='naver' else {}
                for i,row in enumerate(data['observations']):
                    if state['provider']=='naver' and naver_key_or_none(row['text']) is None:
                        skipped.append((n,i,'unsupported_payment'))
                    elif state['provider']=='naver' and identities[naver_key_or_none(row['text'])]!=1:
                        skipped.append((n,i,'ambiguous_card'))
                    else:
                        candidates.append((n,i))
                        conditional_cards += int(state['provider']=='naver' and row.get('conditional') is True)
        skipped_counts=Counter(item[2] for item in skipped)
        return {'provider':state['provider'],'candidates': candidates, 'skipped':skipped,
                'failed_queries':state['failed_queries'],
                'conditional_cards':conditional_cards,
                'count': len(candidates), 'roundtrip_unsupported': roundtrip,
                'unsupported_payment':skipped_counts['unsupported_payment'],'ambiguous_card':skipped_counts['ambiguous_card'],
                'notice': 'Google은 편도, 네이버는 왕복·편도의 모든 결제수단 상세를 확인합니다. 네이버 조건부 검색 카드도 일반 결제 요금 선택지가 있는지 확인하며, 할인 가격을 일반 가격으로 사용하지 않습니다. 결제 조건 미해석·일정 중복은 보존합니다. 개별 식별 실패·시간 초과·구조 변경은 미확인으로 남기고 다음 카드를 조회합니다. 로그인·CAPTCHA·접근 차단·브라우저 오류에서는 전체를 중단합니다. 전체 재고·결제 총액·단일 왕복 발권은 미검증.'}

    def start_details(self, id):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('브라우저 조회가 이미 진행 중입니다')
            preview = self.detail_plan(id)
            if not preview['count']:
                raise ValueError('상세 조회할 지원 대상 카드가 없습니다')
            with self.db() as db:
                db.executemany('INSERT INTO browser_details VALUES(?,?,?,?,?)',
                               ((id,n,i,'pending',None) for n,i in preview['candidates']))
                db.executemany('INSERT INTO browser_details VALUES(?,?,?,?,?)',
                               ((id,n,i,status,None) for n,i,status in preview['skipped']))
                db.execute("UPDATE browser_runs SET status='running_details',detail='' WHERE id=?",(id,))
            self.cancelled.clear()
            self.active_id = id
            self.thread = threading.Thread(target=self.run_details,args=(id,),daemon=True)
            self.thread.start()
            return id

    def run_details(self, id):
        collector, current = None, None
        status, message = 'completed_details', ''
        try:
            with self.db() as db:
                tasks = db.execute("SELECT d.n,d.row,t.request,t.result FROM browser_details d JOIN browser_tasks t ON t.run=d.run AND t.n=d.n WHERE d.run=? AND d.status='pending' ORDER BY d.n,d.row",(id,)).fetchall()
                provider=db.execute('SELECT provider FROM browser_runs WHERE id=?',(id,)).fetchone()[0]
                if db.execute("SELECT COUNT(*) FROM browser_details WHERE run=? AND status NOT IN ('pending','observed')",(id,)).fetchone()[0]:
                    status='completed_partial_details'
                if db.execute("SELECT COUNT(*) FROM browser_tasks WHERE run=? AND status!='observed_partial'",(id,)).fetchone()[0]:
                    status='completed_partial_details'
            collector = self.factory(provider, self.cancelled)
            collector.open()
            for position, (n, index, req, result) in enumerate(tasks):
                if self.cancelled.is_set():
                    raise ProbeStopped('cancelled','사용자가 중단했습니다')
                current = (n,index)
                with self.db() as db:
                    db.execute("UPDATE browser_details SET status='running' WHERE run=? AND n=? AND row=?",(id,n,index))
                item_status='observed'
                try:
                    detail=self.collect_detail(collector,provider,req,result,index)
                except ProbeStopped as error:
                    if error.status not in ('unverified_response','schema_changed'):
                        raise
                    item_status=error.status
                    detail={'error':error.detail}
                    status='completed_partial_details'
                    message='미확인 항목을 보존하고 나머지 대상을 확인했습니다. 확정 운임 비교 완료가 아닙니다'
                with self.db() as db:
                    db.execute('UPDATE browser_details SET status=?,result=? WHERE run=? AND n=? AND row=?',(item_status,dumps(detail),id,n,index))
                current = None
                if position + 1 < len(tasks) and self.cancelled.wait(2):
                    raise ProbeStopped('cancelled','사용자가 중단했습니다')
        except ProbeStopped as error:
            status, message = error.status, error.detail
        except Exception:
            status, message = 'browser_error','브라우저 상세 조회 오류. 이전에 수집한 결과는 보존됩니다'
        finally:
            if collector is not None:
                try: collector.close()
                except Exception: pass
            with self.db() as db:
                if current is not None:
                    db.execute('UPDATE browser_details SET status=? WHERE run=? AND n=? AND row=?',(status,id,*current))
                db.execute('UPDATE browser_runs SET status=?,detail=? WHERE id=?',(status,message,id))

    def resume_pending_details(self, id):
        """Explicit resume of unattempted rows only; never retry failed rows.

        Access blocks cannot be resumed. This is opt-in, not startup behavior.
        """
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('브라우저 조회가 이미 진행 중입니다')
            state = self.status(id)
            if state['status'] not in ('interrupted','cancelled','browser_error'):
                raise ValueError('중단된 상세 작업의 미조회 항목만 명시적으로 재개할 수 있습니다')
            if not state['detail_counts'].get('pending'):
                raise ValueError('남은 미조회 상세 항목이 없습니다')
            with self.db() as db:
                db.execute("UPDATE browser_runs SET status='running_details',detail='' WHERE id=?",(id,))
            self.cancelled.clear()
            self.active_id = id
            self.thread = threading.Thread(target=self.run_details,args=(id,),daemon=True)
            self.thread.start()
            return id

    @staticmethod
    def collect_detail(collector,provider,req,result,index):
        request=json.loads(req)
        request['departure']=date.fromisoformat(request['departure'])
        if request.get('return_date'):request['return_date']=date.fromisoformat(request['return_date'])
        request=Request(**request)
        original=json.loads(result)['observations'][index]
        key=google_itinerary_key if provider=='google' else naver_key_or_none
        original_key=key(original['text'])
        if original_key is None:
            raise ProbeStopped('unverified_response','검색 카드의 결제 조건 미확인')
        fresh=collector.collect(request)
        matches=[row for row in fresh['observations'] if key(row['text'])==original_key]
        if len(matches)!=1:
            reason = '현재 목록에서 동일한 일정 문구를 찾지 못했습니다. 항공편 취소·매진을 뜻하지 않습니다' if not matches else f'동일한 일정 문구에 {len(matches)}개 카드가 일치해 선택하지 않았습니다'
            raise ProbeStopped('unverified_response',reason)
        selected=matches[0]
        detail=(collector.selected_google_details if provider=='google' else collector.selected_naver_details)(request,selected['text'])
        if provider=='naver':
            if detail.get('payment_condition') != '성인/모든 결제수단':
                raise ProbeStopped('unverified_response','상세에서 모든 결제수단 요금을 확인하지 못했습니다')
            detail['search_payment_transition']={
                'initial':naver_payment_label(original['text']),
                'latest':naver_payment_label(selected['text']),
                'selected':'성인/모든 결제수단',
                'same_search_condition':naver_payment_label(original['text'])==naver_payment_label(selected['text'])}
        detail['search_price_change']={'initial_amount':original.get('amount'),
                                       'latest_amount':selected.get('amount'),
                                       'changed':original.get('amount')!=selected.get('amount'),
                                       'latest_observed_at':fresh.get('observed_at'),
                                       'same_search_condition':detail.get('search_payment_transition',{}).get('same_search_condition',True)}
        return detail

    def price_summary(self,id):
        from .search_price_summary import summarize
        with self.db() as db:
            run=db.execute('SELECT provider FROM browser_runs WHERE id=?',(id,)).fetchone()
            if not run:raise ValueError('브라우저 조회 작업이 없습니다')
            tasks=[{'number':n,'request':json.loads(req),'status':status,'result':json.loads(raw) if raw else None}
                   for n,req,status,raw in db.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n',(id,))]
        return summarize(run[0],tasks)

    def candidate_comparisons(self, id, page=1):
        from .observed_comparisons import page as compare_page
        with self.db() as db:
            run=db.execute('SELECT provider FROM browser_runs WHERE id=?',(id,)).fetchone()
            if run is None:raise ValueError('브라우저 조회 작업이 없습니다')
            tasks=[{'number':n,'request':json.loads(req),'status':status,'result':json.loads(raw) if raw else None}
                   for n,req,status,raw in db.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n',(id,))]
            by_number={task['number']:task for task in tasks}
            for n,index,raw in db.execute("SELECT n,row,result FROM browser_details WHERE run=? AND status='observed'",(id,)):
                if raw:by_number[n]['result']['observations'][index]['seller_detail']=json.loads(raw)
        result=compare_page(run[0],tasks,page)
        result['query_counts']=dict(Counter(task['status'] for task in tasks))
        return result

    def status(self, id, page=1):
        if type(page) is not int or page < 1:
            raise ValueError('페이지 번호는 1 이상이어야 합니다')
        with self.db() as db:
            row = db.execute('SELECT provider,status,total,detail FROM browser_runs WHERE id=?',(id,)).fetchone()
            if row is None:
                raise ValueError('브라우저 조회 작업이 없습니다')
            counts = dict(db.execute('SELECT status,COUNT(*) FROM browser_tasks WHERE run=? GROUP BY status',(id,)))
            items = [{'number':n,'request':json.loads(req),'status':state,'result':json.loads(result) if result else None}
                     for n,req,state,result in db.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n LIMIT 10 OFFSET ?',
                                                         (id,(page-1)*10))]
            detail_counts = dict(db.execute('SELECT status,COUNT(*) FROM browser_details WHERE run=? GROUP BY status',(id,)))
            for item in items:
                for index, state, detail in db.execute('SELECT row,status,result FROM browser_details WHERE run=? AND n=?',(id,item['number'])):
                    observation = item['result']['observations'][index]
                    observation['detail_status'] = state
                    if detail:
                        parsed=json.loads(detail)
                        if 'error' in parsed:observation['detail_message']=parsed['error']
                        else:observation['seller_detail']=parsed
        for item in items:
            for observation in (item.get('result') or {}).get('observations', []):
                if observation.get('seller_detail'):
                    detail = observation['seller_detail']
                    detail['offers'] = [enrich_offer(offer) for offer in detail.get('offers', [])]
                observation['comparison_readiness'] = audit(row[0], item['request'], observation)
        return {'id':id,'provider':row[0],'status':row[1],'total':row[2],'detail':row[3],
                'observed':counts.get('observed_partial',0),'not_attempted':counts.get('pending',0),
                'failed_queries':sum(counts.get(s,0) for s in ('unverified_response','schema_changed')),
                'counts':counts,'page':page,'pages':max(1,(row[2]+9)//10),'items':items,
                'detail_counts':detail_counts,'detail_total':sum(detail_counts.values()),
                'comparison_eligible':False}
