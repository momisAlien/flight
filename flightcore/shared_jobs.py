"""Bounded FIFO for the explicitly shared PC instance; local jobs stay unchanged."""
import json
import threading
from collections import deque
from uuid import uuid4
from .combined_jobs import CombinedJobs
from .browser_prices import validate
from .serde import dumps
from .core import estimate


class SharedJobs(CombinedJobs):
    shared = True
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending = deque()
        self.active_id = None
        with self.db() as db:
            db.execute("UPDATE combined_runs SET status='interrupted' WHERE status='queued'")

    def start(self, conditions):
        validate(conditions, 'naver')
        validate(conditions, 'google')
        if estimate(conditions)['base_total_per_provider'] * 2 > 120:
            raise ValueError('공유 검색은 한 번에 최대 120개 브라우저 조건까지 가능합니다.')
        with self.lock:
            if len(self.pending) >= 5:
                raise ValueError('검색 대기열이 가득 찼습니다. 잠시 후 다시 시도하세요.')
            run_id = uuid4().hex
            payload = {'conditions': json.loads(dumps(conditions)), 'providers': {
                name: {'status': 'pending'} for name in ('naver', 'google', 'myrealtrip')}}
            with self.db() as db:
                db.execute('INSERT INTO combined_runs VALUES(?,?,?)',
                           (run_id, 'queued', dumps(payload)))
            self.pending.append((run_id, conditions, payload))
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._drain, daemon=True)
                self.thread.start()
            return run_id

    def _drain(self):
        while True:
            with self.lock:
                if not self.pending:
                    self.active_id = None
                    self.thread = None
                    return
                run_id, conditions, payload = self.pending.popleft()
                self.active_id = run_id
                self.cancelled.clear()
            try:
                self.save(run_id, 'running', payload)
                super().run(run_id, conditions, payload)
            except Exception:
                # Never persist provider exceptions, which can contain credentials.
                self.save(run_id, 'failed_partial', payload)

    def cancel(self, run_id):
        with self.lock:
            if run_id == self.active_id:
                self.cancelled.set()
                return
            for entry in list(self.pending):
                if entry[0] == run_id:
                    self.pending.remove(entry)
                    self.save(run_id, 'cancelled', entry[2])
                    return
        # Preserve unknown-job validation and no-op for finished jobs.
        with self.db() as db:
            if not db.execute('SELECT 1 FROM combined_runs WHERE id=?', (run_id,)).fetchone():
                raise ValueError('통합 조회 작업이 없습니다')

    def status(self, run_id):
        result = super().status(run_id)
        with self.lock:
            result['queue_position'] = next(
                (i + 1 for i, item in enumerate(self.pending) if item[0] == run_id), 0)
        return result
