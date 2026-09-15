"""Core data models.

Everything the pipeline touches is a dataclass here. The point is that a
Job / Application / GateResult can be serialized to SQLite without losing
the audit trail the video promises: every submitted application must
trace back to (a) a real JD, (b) a fact-verified tailored resume,
(c) seven passing gates, (d) a human decision when anything was uncertain.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStatus(str, Enum):
    SCRAPED = "scraped"            # seen by a source adapter
    HARD_FILTERED = "hard_filtered"  # passed hard gates
    SCORED = "scored"               # scored by direction; score>=threshold
    TAILORED = "tailored"           # resume tailored, fact-checked
    QUESTIONS_READY = "questions_ready"  # questions for the human
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    INTERFACE_CONFIRMED = "interface_confirmed"
    REJECTED = "rejected"           # hard filter / fact-check / gate failed
    HELD = "held"                   # unclear result, never resubmit blindly
    AWAITING_HUMAN = "awaiting_human"  # needs a human decision / code


class GateOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN = "needs_human"


@dataclass
class Job:
    """One scraped job posting."""
    id: str
    source: str                  # e.g. "dummy", "linkedin", "boss"
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    salary: str = ""
    posted_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    status: str = JobStatus.SCRAPED.value
    hard_reason: str = ""        # why hard-filter rejected
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["raw"] = _dumps(self.raw)
        d["score_breakdown"] = _dumps(self.score_breakdown)
        return d


@dataclass
class TailoredResume:
    """A resume tailored for one specific job.

    The video's hard rule: every number / claim in the rendered resume
    MUST be traceable to a verbatim fact in the master resume. The
    FactChecker enforces this; a single untraceable token rejects the
    whole resume instead of emitting a warning.
    """
    job_id: str
    rendered_markdown: str
    sources_used: list[str]      # which master facts were used
    untraceable: list[str]       # tokens that could NOT be traced -> hard reject
    verified: bool = False
    created_at: str = field(default_factory=_now)


@dataclass
class Question:
    """A question the agent could not answer from the resume master.

    The agent does NOT guess. It pastes the original question and waits
    for the human to decide. This is the "拍板" step.
    """
    id: str
    job_id: str
    question: str
    context: str = ""
    options: list[str] = field(default_factory=list)
    status: str = "open"         # open / answered / dismissed
    answer: str = ""
    created_at: str = field(default_factory=_now)
    answered_at: str = ""


@dataclass
class GateResult:
    """One of the seven pre-submission gates."""
    job_id: str
    gate_name: str
    outcome: str                 # GateOutcome value
    detail: str = ""
    at: str = field(default_factory=_now)


@dataclass
class Application:
    """A submission record, immutable after SUBMITTED."""
    id: str
    job_id: str
    company: str
    title: str
    submitted_at: str = field(default_factory=_now)
    interface_ok: bool = False   # did the POST return success?
    interface_payload: dict[str, Any] = field(default_factory=dict)
    screenshot_path: str = ""
    fact_error: bool = False      # any fact that failed tracing? -> MUST stay False

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["interface_payload"] = _dumps(self.interface_payload)
        return d


def _dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
