"""Offline comparisons in a worker; paginated results live on disk, not in RAM."""
import json
import threading
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from .store import Store
from .serde import dumps,quote_from_dict,conditions_from_dict
from .review import review_stream


def prepare(db):
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, status TEXT, conditions TEXT,
            processed INTEGER DEFAULT 0, eligible INTEGER DEFAULT 0, uncertain INTEGER DEFAULT 0,
            cancel INTEGER DEFAULT 0, error TEXT DEFAULT '', created TEXT);
        CREATE TABLE IF NOT EXISTS job_inputs(job TEXT, id TEXT, legs INTEGER, payload TEXT, PRIMARY KEY(job,id));
        CREATE TABLE IF NOT EXISTS job_results(job TEXT, seq INTEGER, bucket TEXT, currency TEXT,
            direct INTEGER, price TEXT, departure TEXT, duration REAL, day TEXT, payload TEXT, PRIMARY KEY(job,seq));
        CREATE INDEX IF NOT EXISTS result_job_bucket ON job_results(job,bucket);
    ''')


class Jobs:
    def __init__(self,path):
        self.path=path
        self.lock=threading.Lock()
        self.thread=None
        self.cancel_event=threading.Event()
        self.active_id=None
        with Store(path) as store:
            prepare(store.db)
            with store.db:
                store.db.execute("UPDATE jobs SET status='중단됨',error='서버 종료로 비교가 중단되었습니다. 다시 비교하세요' WHERE status='비교 중'")

    def start(self,conditions):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("진행 중인 비교를 취소하거나 완료 후 다시 실행하세요")
            id=uuid4().hex
            self.cancel_event.clear()
            self.active_id=id
            with Store(self.path) as store:
                with store.db:
                    store.db.execute("INSERT INTO jobs(id,status,conditions,created) VALUES (?,?,?,?)",
                                     (id,"비교 중",dumps(conditions),datetime.now(timezone.utc).isoformat()))
                    store.db.execute("INSERT INTO job_inputs SELECT ?,id,legs,payload FROM manual_quotes",(id,))
            self.thread=threading.Thread(target=self.run,args=(id,conditions),daemon=True)
            self.thread.start()
            return id

    def run(self,id,c):
        processed=eligible=uncertain=0
        try:
            with Store(self.path) as store, Store(self.path) as reader:
                def inputs(legs):
                    for row in reader.db.execute("SELECT payload FROM job_inputs WHERE job=? AND legs=? ORDER BY id",(id,legs)):
                        yield quote_from_dict(json.loads(row[0]))
                now=datetime.now(timezone.utc)
                for result in review_stream(inputs(2),lambda:inputs(1),c,now,self.cancel_event.is_set):
                    if store.db.execute("SELECT cancel FROM jobs WHERE id=?",(id,)).fetchone()[0]:
                        with store.db:
                            store.db.execute("UPDATE jobs SET status='비교 취소 · 일부 결과만 확인됨' WHERE id=?",(id,))
                        break
                    processed+=1
                    bucket="eligible" if result["rankable"] else "uncertain"
                    eligible+=int(result["rankable"])
                    uncertain+=int(not result["rankable"])
                    with store.db:
                        store.db.execute("INSERT INTO job_results VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (id,processed,bucket,result["currency"],int(result["direct"]),
                             str(result["total"]) if result["total"] is not None else "Infinity",
                             result["departure"],result["duration"],str(result["departure_date"]),dumps(result)))
                        store.db.execute("UPDATE jobs SET processed=?,eligible=?,uncertain=? WHERE id=?",(processed,eligible,uncertain,id))
                else:
                    with store.db:
                        status="비교 취소 · 일부 결과만 확인됨" if self.cancel_event.is_set() else "비교 완료"
                        store.db.execute("UPDATE jobs SET status=? WHERE id=?",(status,id))
        except Exception as exc:
            with Store(self.path) as store:
                with store.db:
                    store.db.execute("UPDATE jobs SET status='비교 실패',error=? WHERE id=?",(str(exc),id))

    def status(self,id):
        with Store(self.path) as store:
            row=store.db.execute("SELECT status,processed,eligible,uncertain,error,created,conditions FROM jobs WHERE id=?",(id,)).fetchone()
            if not row:
                raise KeyError(id)
            return dict(zip(("status","processed","eligible","uncertain","error","created","conditions"),row))

    def cancel(self,id):
        with Store(self.path) as store:
            with store.db:
                changed=store.db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND status='비교 중'",(id,)).rowcount
                if changed and id==self.active_id:
                    self.cancel_event.set()

    def results(self,id,bucket="eligible",page=1,mode="direct_first"):
        order={"direct_first":"direct DESC,price COLLATE EXACT_DECIMAL", "price":"price COLLATE EXACT_DECIMAL",
               "departure":"departure,price COLLATE EXACT_DECIMAL", "duration":"duration,price COLLATE EXACT_DECIMAL"}
        if mode not in order or bucket not in ("eligible","uncertain") or page<1:
            raise ValueError("결과 페이지 조건이 올바르지 않습니다")
        with Store(self.path) as store:
            store.db.create_collation("EXACT_DECIMAL",lambda a,b:(Decimal(a)>Decimal(b))-(Decimal(a)<Decimal(b)))
            count=store.db.execute("SELECT COUNT(*) FROM job_results WHERE job=? AND bucket=?",(id,bucket)).fetchone()[0]
            rows=store.db.execute("SELECT payload FROM job_results WHERE job=? AND bucket=? ORDER BY currency,"+order[mode]+",seq LIMIT 25 OFFSET ?",(id,bucket,(page-1)*25))
            return {"total":count,"page":page,"pages":max(1,(count+24)//25),"items":[json.loads(row[0]) for row in rows]}

    def daily(self,id):
        with Store(self.path) as store:
            store.db.create_collation("EXACT_DECIMAL",lambda a,b:(Decimal(a)>Decimal(b))-(Decimal(a)<Decimal(b)))
            rows=store.db.execute("SELECT payload FROM job_results WHERE job=? AND bucket='eligible' ORDER BY day,currency,direct DESC,price COLLATE EXACT_DECIMAL,seq",(id,))
            seen=set()
            result=[]
            for row in rows:
                value=json.loads(row[0]); key=(value["departure_date"],value["currency"])
                if key not in seen:
                    seen.add(key)
                    result.append({"date":key[0],"currency":key[1],"amount":value["total"],"direct":value["direct"]})
            return result
