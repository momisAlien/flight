"""Persistent official reference-price jobs; never populate live/manual quotes."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4
from . import myrealtrip


def tasks(c):
    if set(c.origins) & set(c.destinations):
        raise ValueError("출발 공항과 목적지 공항이 겹칩니다")
    if not 2 <= c.nights <= 6:
        raise ValueError("마이리얼트립 참고 가격은 날짜 차이 2~6일만 지원합니다")
    if c.allow_origin_change or c.allow_destination_change or c.arrival_expansion:
        raise ValueError("참고 캘린더는 공항 변경·도착일 확장을 지원하지 않습니다")
    if c.passengers.adults != 1 or c.passengers.children or c.passengers.infants or c.cabin != "economy" or c.baggage != "none_requested":
        raise ValueError("이 API는 승객·좌석·수하물 조건을 받지 않습니다. 기본 조건에서 참고 가격으로만 조회하세요")
    for origin in c.origins:
        for destination in c.destinations:
            start = c.start
            while start <= c.end:
                end = min(start + timedelta(days=30), c.end)
                # Avoid a one-day tail without extending the user's requested range.
                if end == c.end - timedelta(days=1):
                    end -= timedelta(days=1)
                yield origin, destination, start, end, c.nights
                start = end + timedelta(days=1)


class ReferenceJobs:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.thread = None
        self.cancelled = threading.Event()
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reference_runs(id TEXT PRIMARY KEY,status TEXT,total INTEGER,completed INTEGER,payload TEXT)")
            db.execute("UPDATE reference_runs SET status='interrupted' WHERE status='running'")

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self, c):
        myrealtrip.api_key()  # Fail before creating a run when not configured.
        total = sum(1 for _ in tasks(c))
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("참고 가격 조회가 이미 진행 중입니다")
            self.cancelled.clear()
            id = uuid4().hex
            with self.db() as db:
                db.execute("INSERT INTO reference_runs VALUES(?,?,?,?,?)",(id,"running",total,0,"[]"))
            self.thread = threading.Thread(target=self.run,args=(id,c),daemon=True)
            self.thread.start()
            return id

    def run(self, id, c):
        results = []
        status = "completed_references"
        try:
            for args in tasks(c):
                if self.cancelled.is_set():
                    status = "cancelled_partial"
                    break
                result = myrealtrip.calendar(*args)
                results.append(result)
                with self.db() as db:
                    db.execute("UPDATE reference_runs SET completed=?,payload=? WHERE id=?",
                               (len(results),json.dumps(results,ensure_ascii=False),id))
                if result["status"] not in ("references_received","no_cached_reference"):
                    status = "failed_partial"
                    break  # No challenge/auth/rate-limit retries or continued load.
                if self.cancelled.wait(1):
                    status = "cancelled_partial"
                    break
        except Exception:
            status = "failed_partial"  # Never persist raw exception text containing secrets.
        finally:
            with self.db() as db:
                db.execute("UPDATE reference_runs SET status=? WHERE id=?",(status,id))

    def status(self, id):
        with self.db() as db:
            row = db.execute("SELECT status,total,completed,payload FROM reference_runs WHERE id=?",(id,)).fetchone()
        if not row:
            raise ValueError("조회 작업을 찾을 수 없습니다")
        return {"id":id,"status":row[0],"total":row[1],"completed":row[2],
                "not_attempted":row[1]-row[2],"results":json.loads(row[3]),"comparison_eligible":False}
