"""Persistent parent jobs coordinating the existing provider collectors."""
import json,sqlite3,threading
from contextlib import contextmanager
from uuid import uuid4
from .serde import dumps,conditions_from_dict
from .browser_prices import validate
from .combined_prices import ranking
from .browser_jobs import BrowserJobs
from .reference_jobs import tasks as reference_tasks

def reference_reason(c):
    try:
        list(reference_tasks(c))
    except ValueError as error:
        return str(error)  # Only local condition validation, never API exceptions.
    return 'API 키 설정 또는 다른 참고가 조회의 실행 상태를 확인하세요.'

class CombinedJobs:
    def __init__(self,path,browser,reference):
        self.path=path;self.browser=browser;self.reference=reference
        # Independent browser/session/cancellation state; shared durable result store.
        self.google=BrowserJobs(path,factory=lambda *args:browser.factory(*args),recover_interrupted=False)
        self.lock=threading.Lock();self.thread=None;self.cancelled=threading.Event()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS combined_runs(id TEXT PRIMARY KEY,status TEXT,payload TEXT)')
            db.execute("UPDATE combined_runs SET status='interrupted' WHERE status='running'")

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:yield db
        finally:db.close()

    def start(self,c):
        validate(c,'naver');validate(c,'google')
        with self.lock:
            if any(obj.thread and obj.thread.is_alive() for obj in (self,self.browser,self.google,self.reference)):
                raise ValueError('진행 중인 조회가 끝난 뒤 통합 검색을 시작하세요')
            self.cancelled.clear();id=uuid4().hex
            payload={'conditions':json.loads(dumps(c)),'providers':{name:{'status':'pending'} for name in ('naver','google','myrealtrip')}}
            with self.db() as db:db.execute('INSERT INTO combined_runs VALUES(?,?,?)',(id,'running',dumps(payload)))
            self.thread=threading.Thread(target=self.run,args=(id,c,payload),daemon=True);self.thread.start()
            return id

    def save(self,id,status,payload):
        with self.db() as db:db.execute('UPDATE combined_runs SET status=?,payload=? WHERE id=?',(status,dumps(payload),id))

    def run(self,id,c,payload):
        final='completed'
        active={}
        for name,child in (('naver',self.browser),('google',self.google),('myrealtrip',self.reference)):
            if self.cancelled.is_set():final='cancelled';break
            try:
                run=child.start(c) if name=='myrealtrip' else child.start(c,name)
                active[name]=(child,run)
                payload['providers'][name]={'id':run,'status':'running'};self.save(id,'running',payload)
            except ValueError:
                payload['providers'][name]={'status':'setup_or_conditions_unsupported','notice':reference_reason(c) if name=='myrealtrip' else '조회 설정 또는 다른 검색의 실행 상태를 확인하세요.'};final='completed_partial'
            except Exception:
                payload['providers'][name]={'status':'provider_error','notice':'공급사 조회 실행 실패 · 인증정보를 포함할 수 있는 원본 오류는 기록하지 않음'};final='completed_partial'
            self.save(id,'running',payload)
        while active:
            # Signal all collectors before waiting for any one of them to exit.
            if self.cancelled.is_set():
                for child,run in active.values():child.cancelled.set()
            for name,(child,run) in list(active.items()):
                child.thread.join(.1)
                if child.thread.is_alive():continue
                state=child.status(run);payload['providers'][name]['status']=state['status']
                if state['status'] not in ('completed_references','completed_observations'):final='completed_partial'
                del active[name]
                self.save(id,'running',payload)
        if self.cancelled.is_set():final='cancelled'
        self.save(id,final,payload)

    def cancel(self,id):
        with self.db() as db:row=db.execute('SELECT status FROM combined_runs WHERE id=?',(id,)).fetchone()
        if not row:raise ValueError('통합 조회 작업이 없습니다')
        if row[0]=='running':self.cancelled.set()

    def history(self):
        with self.db() as db:
            rows=db.execute('SELECT id,status,payload FROM combined_runs ORDER BY rowid DESC LIMIT 20').fetchall()
        return [{'id':id,'status':status,'conditions':json.loads(payload)['conditions']} for id,status,payload in rows]

    def status(self,id):
        with self.db() as db:
            row=db.execute('SELECT status,payload FROM combined_runs WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('통합 조회 작업이 없습니다')
            payload=json.loads(row[1]);tasks={};references=[]
            for name,provider in payload['providers'].items():
                if name=='myrealtrip' and provider['status']=='setup_or_conditions_unsupported':
                    provider['notice']=reference_reason(conditions_from_dict(payload['conditions']))
                if not provider.get('id'):continue
                if name=='myrealtrip':
                    state=self.reference.status(provider['id']);references=state['results']
                    provider.update(status=state['status'],completed=state['completed'],total=state['total'])
                else:
                    state=self.browser.status(provider['id']);provider.update(status=state['status'],completed=state['observed'],total=state['total'],failed_queries=state['failed_queries'])
                    tasks[name]=[{'number':n,'request':json.loads(req),'status':s,'result':json.loads(raw) if raw else None} for n,req,s,raw in db.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n',(provider['id'],))]
        return {'id':id,'status':row[0],**payload,'ranking':ranking(conditions_from_dict(payload['conditions']),tasks,references)}
