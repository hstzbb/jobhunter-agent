"""The seven pre-submission gates.

    "提交前七道闸任何一道不过就不交，拿不准的一律不投，
     结果不明的单独挂起，绝不重投。"

Each gate returns PASS / FAIL / NEEDS_HUMAN. The pipeline only submits
when ALL SEVEN return PASS. A single FAIL or NEEDS_HUMAN blocks the
submission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..store import models as m


@dataclass
class GateContext:
    job: m.Job
    tailored_markdown: str
    fact_verified: bool
    untraceable: list[str]
    open_questions: list[m.Question]
    already_applied_urls: set[str]
    today_submitted_count: int
    config: dict


GateFn = Callable[[GateContext], tuple[str, str]]  # -> (outcome, detail)


# --- the seven gates, in order -------------------------------------------

def g1_facts_traceable(ctx: GateContext) -> tuple[str, str]:
    """1. Every number in the tailored resume traces to the master."""
    if not ctx.fact_verified:
        return m.GateOutcome.FAIL.value, \
            f"untraceable facts: {ctx.untraceable}"
    return m.GateOutcome.PASS.value, "all facts traceable"


def g2_no_open_questions(ctx: GateContext) -> tuple[str, str]:
    """2. Nothing left unanswered by the human."""
    open_q = [q for q in ctx.open_questions if q.status == "open"]
    if open_q:
        return m.GateOutcome.NEEDS_HUMAN.value, \
            f"{len(open_q)} unanswered question(s)"
    return m.GateOutcome.PASS.value, "all questions answered"


def g3_not_already_applied(ctx: GateContext) -> tuple[str, str]:
    """3. Never resubmit the same posting."""
    if ctx.job.url in ctx.already_applied_urls:
        return m.GateOutcome.FAIL.value, "already applied to this URL"
    return m.GateOutcome.PASS.value, "not previously applied"


def g4_score_above_threshold(ctx: GateContext) -> tuple[str, str]:
    """4. Score above the configured cut-off (default 80)."""
    threshold = float(ctx.config.get("min_score", 80))
    if ctx.job.score < threshold:
        return m.GateOutcome.FAIL.value, \
            f"score {ctx.job.score:.1f} < {threshold}"
    return m.GateOutcome.PASS.value, f"score {ctx.job.score:.1f}"


def g5_daily_quota(ctx: GateContext) -> tuple[str, str]:
    """5. Respect the per-day cap so we don't get banned."""
    cap = int(ctx.config.get("daily_cap", 30))
    if ctx.today_submitted_count >= cap:
        return m.GateOutcome.FAIL.value, \
            f"daily cap {cap} reached ({ctx.today_submitted_count})"
    return m.GateOutcome.PASS.value, \
        f"{ctx.today_submitted_count}/{cap} submitted today"


def g6_resume_renders(ctx: GateContext) -> tuple[str, str]:
    """6. The tailored resume is non-empty and has a summary + bullets."""
    body = ctx.tailored_markdown.strip()
    if len(body) < 200:
        return m.GateOutcome.FAIL.value, "tailored resume too short"
    if "## Summary" not in body or "## Selected experience" not in body:
        return m.GateOutcome.FAIL.value, "tailored resume missing sections"
    return m.GateOutcome.PASS.value, "resume renders"


def g7_hard_requirements_still_match(ctx: GateContext) -> tuple[str, str]:
    """7. Re-check that the JD still meets hard requirements right before submit.

    This catches postings that get edited after we scraped them.
    """
    must_have_any = ctx.config.get("must_have_any", [])
    jd = (ctx.job.title + " " + ctx.job.description).lower()
    if must_have_any and not any(k.lower() in jd for k in must_have_any):
        return m.GateOutcome.FAIL.value, \
            f"JD no longer matches any of {must_have_any}"
    return m.GateOutcome.PASS.value, "hard requirements still match"


SEVEN_GATES: list[tuple[str, GateFn]] = [
    ("facts_traceable", g1_facts_traceable),
    ("no_open_questions", g2_no_open_questions),
    ("not_already_applied", g3_not_already_applied),
    ("score_above_threshold", g4_score_above_threshold),
    ("daily_quota", g5_daily_quota),
    ("resume_renders", g6_resume_renders),
    ("hard_requirements_still_match", g7_hard_requirements_still_match),
]
