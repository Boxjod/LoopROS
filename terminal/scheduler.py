"""Persistent, serial foreground timers. No catch-up replay after restart."""
import math
import sqlite3
import time


class Scheduler:
    def __init__(self, path, recover=True):
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, due REAL, "
                        "period REAL, command TEXT, state TEXT, result TEXT)")
        if recover:
            with self.db:
                self.db.execute("UPDATE jobs SET state='interrupted' WHERE state='running'")

    def add(self, seconds, command, repeat=False):
        if not math.isfinite(seconds) or seconds < 1 or not command.strip():
            raise ValueError("定时秒数必须 >=1，任务不能为空")
        if self.db.execute("SELECT COUNT(*) FROM jobs WHERE state='pending'").fetchone()[0] >= 100:
            raise ValueError("最多 100 个等待任务")
        with self.db:
            row = self.db.execute("INSERT INTO jobs(due,period,command,state,result) VALUES(?,?,?,'pending','')",
                                  (time.time() + seconds, seconds if repeat else 0, command))
        return row.lastrowid

    def list(self):
        return self.db.execute("SELECT id,due,period,command,state,result FROM jobs ORDER BY id").fetchall()

    def cancel(self, job_id):
        with self.db:
            return self.db.execute("UPDATE jobs SET state='cancelled' WHERE id=? AND state='pending'",
                                   (job_id,)).rowcount

    def claim(self):
        row = self.db.execute("SELECT id,period,command FROM jobs WHERE state='pending' AND due<=? "
                              "ORDER BY due LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return None
        job_id, period, command = row
        with self.db:
            self.db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
        return job_id, period, command

    def finish(self, job_id, period, result, failed=False):
        state = "failed" if failed else ("pending" if period else "done")
        with self.db:
            self.db.execute("UPDATE jobs SET state=?,result=?,due=? WHERE id=?",
                            (state, result[:8000], time.time() + period, job_id))
        return job_id, result

    def tick(self, dispatch):
        row = self.claim()
        if not row:
            return None
        job_id, period, command = row
        try:
            result, state = str(dispatch(command)), "pending" if period else "done"
        except Exception as exc:
            result, state = "执行失败: " + type(exc).__name__, "failed"
        with self.db:
            self.db.execute("UPDATE jobs SET state=?,result=?,due=? WHERE id=?",
                            (state, result[:8000], time.time() + period, job_id))
        return job_id, result

    def close(self):
        self.db.close()
