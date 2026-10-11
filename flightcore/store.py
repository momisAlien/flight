"""SQLite persistence with no seeded results and no external data ingestion."""
import json
import sqlite3

from .core import Quote, ReferenceCandidate, Status, progress
from .serde import dumps, quote_from_dict, reference_from_dict


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS manual_quotes (id TEXT PRIMARY KEY, legs INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reference_candidates (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (job TEXT NOT NULL, provider TEXT NOT NULL, request TEXT NOT NULL,
                status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', PRIMARY KEY(job,provider,request));
        ''')

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def add_manual(self, quote: Quote):
        if not isinstance(quote, Quote) or quote.provenance.kind != "manual":
            raise ValueError("수동 입력만 저장할 수 있습니다. 자동 검증 상태로 승격할 수 없습니다")
        with self.db:
            self.db.execute("INSERT INTO manual_quotes VALUES (?, ?, ?)", (quote.id, len(quote.legs), dumps(quote)))

    def all_quotes(self):
        for row in self.db.execute("SELECT payload FROM manual_quotes ORDER BY id"):
            yield quote_from_dict(json.loads(row[0]))

    def add_batch(self, quotes):
        quotes = tuple(quotes)
        if any(q.provenance.kind != "manual" for q in quotes):
            raise ValueError("수동 입력만 저장할 수 있습니다")
        with self.db:
            self.db.executemany("INSERT INTO manual_quotes VALUES (?,?,?)",
                                ((q.id, len(q.legs), dumps(q)) for q in quotes))

    def delete_manual(self, id):
        with self.db:
            self.db.execute("DELETE FROM manual_quotes WHERE id=?", (id,))

    def quotes(self, legs: int):
        for row in self.db.execute("SELECT payload FROM manual_quotes WHERE legs=? ORDER BY id", (legs,)):
            yield quote_from_dict(json.loads(row[0]))

    def add_reference(self, candidate: ReferenceCandidate):
        if not isinstance(candidate, ReferenceCandidate):
            raise TypeError("참고용 후보 모델이 필요합니다")
        with self.db:
            self.db.execute("INSERT INTO reference_candidates VALUES (?,?)", (candidate.id, dumps(candidate)))

    def references(self):
        for row in self.db.execute("SELECT payload FROM reference_candidates ORDER BY id"):
            yield reference_from_dict(json.loads(row[0]))

    def seed_tasks(self, job, provider, requests, connected=False):
        state = Status.NOT_SEARCHED if connected else Status.NOT_CONNECTED
        with self.db:
            self.db.executemany("INSERT OR IGNORE INTO tasks VALUES (?,?,?,?,?)",
                                ((job, provider, dumps(r), state.value, "") for r in requests))

    def transition(self, job, provider, request, status: Status, reason=""):
        key = (job, provider, dumps(request))
        row = self.db.execute("SELECT status FROM tasks WHERE job=? AND provider=? AND request=?", key).fetchone()
        if row is None:
            raise KeyError("등록되지 않은 검색 조건")
        old = Status(row[0])
        allowed = {
            Status.NOT_CONNECTED: set(),
            Status.NOT_SEARCHED: {Status.RUNNING, Status.CANCELLED},
            Status.RUNNING: {Status.SUCCESS, Status.NO_RESULTS, Status.FAILED, Status.PARTIAL, Status.CANCELLED},
            Status.FAILED: {Status.NOT_SEARCHED},
            Status.PARTIAL: {Status.NOT_SEARCHED},
            Status.CANCELLED: {Status.NOT_SEARCHED},
            Status.SUCCESS: set(), Status.NO_RESULTS: set(),
        }
        if status not in allowed[old]:
            raise ValueError(f"허용되지 않은 상태 변경: {old} -> {status}")
        if status in (Status.FAILED, Status.PARTIAL) and not reason.strip():
            raise ValueError("실패/일부 결과 사유가 필요합니다")
        with self.db:
            self.db.execute("UPDATE tasks SET status=?,reason=? WHERE job=? AND provider=? AND request=?",
                            (status.value, reason, *key))

    def task_progress(self, job):
        return progress(Status(row[0]) for row in self.db.execute("SELECT status FROM tasks WHERE job=?", (job,)))

    def unfinished(self, job):
        for provider, request, status, reason in self.db.execute(
            "SELECT provider,request,status,reason FROM tasks WHERE job=? AND status NOT IN (?,?)",
            (job, Status.SUCCESS.value, Status.NO_RESULTS.value)):
            yield {"provider": provider, "request": json.loads(request), "status": status, "reason": reason}
