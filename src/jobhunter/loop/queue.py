"""Human-in-the-loop queue.

The agent never guesses. When a question cannot be answered from the
master resume, it is pushed here. The CLI surfaces it with `jh ask` and
waits for the human's decision. The pipeline pauses the affected job
until the question is answered.

Humans only do three things (per the video):
  1. 拍板 — decide on facts/intent the master doesn't cover
  2. 注册账号 — register a new company account
  3. 交验证码 — hand over the SMS / email code
"""
from __future__ import annotations

import uuid
from typing import Iterable

from ..store import models as m
from ..store.db import Store


class HumanQueue:
    def __init__(self, store: Store):
        self.store = store

    def ask(self, job_id: str, question: str, *,
            context: str = "", options: Iterable[str] = ()) -> m.Question:
        q = m.Question(
            id=f"q_{uuid.uuid4().hex[:10]}",
            job_id=job_id,
            question=question,
            context=context,
            options=list(options),
            status="open",
        )
        self.store.add_question(q)
        return q

    def open(self) -> list[m.Question]:
        return self.store.open_questions()

    def answer(self, qid: str, answer: str) -> None:
        self.store.answer_question(qid, answer)
