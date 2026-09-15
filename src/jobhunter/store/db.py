"""SQLite persistence.

A single file under data/applied.db. No ORM, just stdlib sqlite3, so the
project stays dependency-light and the schema is easy to read.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from . import models as m


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT, company TEXT, title TEXT, url TEXT,
    location TEXT, salary TEXT, posted_at TEXT,
    description TEXT,
    raw TEXT,
    status TEXT, hard_reason TEXT,
    score REAL, score_breakdown TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);

CREATE TABLE IF NOT EXISTS tailored_resumes (
    job_id TEXT PRIMARY KEY,
    rendered_markdown TEXT,
    sources_used TEXT,
    untraceable TEXT,
    verified INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    job_id TEXT, question TEXT, context TEXT, options TEXT,
    status TEXT, answer TEXT,
    created_at TEXT, answered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_q_open ON questions(status);

CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT, gate_name TEXT, outcome TEXT, detail TEXT, at TEXT
);
CREATE INDEX IF NOT EXISTS idx_gate_job ON gate_results(job_id);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT, company TEXT, title TEXT,
    submitted_at TEXT, interface_ok INTEGER,
    interface_payload TEXT, screenshot_path TEXT,
    fact_error INTEGER
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- jobs ----------
    def upsert_job(self, job: m.Job) -> None:
        self.conn.execute(
            """INSERT INTO jobs VALUES (
               :id,:source,:company,:title,:url,:location,:salary,:posted_at,
               :description,:raw,:status,:hard_reason,:score,:score_breakdown,
               :created_at,:updated_at
            ) ON CONFLICT(id) DO UPDATE SET
               status=excluded.status, hard_reason=excluded.hard_reason,
               score=excluded.score, score_breakdown=excluded.score_breakdown,
               updated_at=excluded.updated_at""",
            job.to_row(),
        )
        self.conn.commit()

    def jobs_by_status(self, status: str) -> list[m.Job]:
        cur = self.conn.execute("SELECT * FROM jobs WHERE status=?", (status,))
        return [self._row_to_job(r) for r in cur.fetchall()]

    def job(self, job_id: str) -> m.Job | None:
        cur = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        return self._row_to_job(row) if row else None

    def all_jobs(self) -> list[m.Job]:
        cur = self.conn.execute("SELECT * FROM jobs ORDER BY score DESC")
        return [self._row_to_job(r) for r in cur.fetchall()]

    def count_by_status(self) -> dict[str, int]:
        cur = self.conn.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status")
        return {r["status"]: r["c"] for r in cur.fetchall()}

    # ---------- tailored resumes ----------
    def save_tailored(self, tr: m.TailoredResume) -> None:
        self.conn.execute(
            """INSERT INTO tailored_resumes VALUES (?,?,?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET
               rendered_markdown=excluded.rendered_markdown,
               sources_used=excluded.sources_used,
               untraceable=excluded.untraceable,
               verified=excluded.verified""",
            (
                tr.job_id, tr.rendered_markdown,
                json.dumps(tr.sources_used, ensure_ascii=False),
                json.dumps(tr.untraceable, ensure_ascii=False),
                int(tr.verified), tr.created_at,
            ),
        )
        self.conn.commit()

    # ---------- questions / human loop ----------
    def add_question(self, q: m.Question) -> None:
        self.conn.execute(
            """INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?)""",
            (q.id, q.job_id, q.question, q.context,
             json.dumps(q.options, ensure_ascii=False),
             q.status, q.answer, q.created_at, q.answered_at),
        )
        self.conn.commit()

    def open_questions(self) -> list[m.Question]:
        cur = self.conn.execute("SELECT * FROM questions WHERE status='open'")
        out = []
        for r in cur.fetchall():
            out.append(m.Question(
                id=r["id"], job_id=r["job_id"], question=r["question"],
                context=r["context"] or "",
                options=json.loads(r["options"] or "[]"),
                status=r["status"], answer=r["answer"] or "",
                created_at=r["created_at"], answered_at=r["answered_at"] or "",
            ))
        return out

    def answer_question(self, qid: str, answer: str) -> None:
        from datetime import datetime, timezone
        self.conn.execute(
            "UPDATE questions SET status='answered', answer=?, answered_at=? WHERE id=?",
            (answer, datetime.now(timezone.utc).isoformat(timespec="seconds"), qid),
        )
        self.conn.commit()

    # ---------- gates ----------
    def record_gate(self, g: m.GateResult) -> None:
        self.conn.execute(
            "INSERT INTO gate_results (job_id,gate_name,outcome,detail,at) VALUES (?,?,?,?,?)",
            (g.job_id, g.gate_name, g.outcome, g.detail, g.at),
        )
        self.conn.commit()

    def gates_for(self, job_id: str) -> list[m.GateResult]:
        cur = self.conn.execute(
            "SELECT * FROM gate_results WHERE job_id=? ORDER BY id", (job_id,))
        return [m.GateResult(job_id=r["job_id"], gate_name=r["gate_name"],
                             outcome=r["outcome"], detail=r["detail"], at=r["at"])
                for r in cur.fetchall()]

    # ---------- applications ----------
    def save_application(self, app: m.Application) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO applications VALUES (?,?,?,?,?,?,?,?,?)""",
            (app.id, app.job_id, app.company, app.title, app.submitted_at,
             int(app.interface_ok),
             json.dumps(app.interface_payload, ensure_ascii=False),
             app.screenshot_path, int(app.fact_error)),
        )
        self.conn.commit()

    def applications(self) -> list[m.Application]:
        cur = self.conn.execute("SELECT * FROM applications ORDER BY submitted_at DESC")
        return [m.Application(
            id=r["id"], job_id=r["job_id"], company=r["company"],
            title=r["title"], submitted_at=r["submitted_at"],
            interface_ok=bool(r["interface_ok"]),
            interface_payload=json.loads(r["interface_payload"] or "{}"),
            screenshot_path=r["screenshot_path"] or "",
            fact_error=bool(r["fact_error"]),
        ) for r in cur.fetchall()]

    # ---------- helpers ----------
    @staticmethod
    def _row_to_job(r: sqlite3.Row) -> m.Job:
        return m.Job(
            id=r["id"], source=r["source"], company=r["company"],
            title=r["title"], url=r["url"], location=r["location"] or "",
            salary=r["salary"] or "", posted_at=r["posted_at"] or "",
            description=r["description"] or "",
            raw=json.loads(r["raw"] or "{}"),
            status=r["status"], hard_reason=r["hard_reason"] or "",
            score=r["score"] or 0.0,
            score_breakdown=json.loads(r["score_breakdown"] or "{}"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def close(self) -> None:
        self.conn.close()
