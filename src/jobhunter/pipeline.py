"""The eight-step pipeline.

    $ jh submit --yes

    1. scrape   -- pull jobs from every configured source
    2. hard     -- drop anything that fails a hard requirement / rule
    3. score    -- score survivors by direction (keyword overlap + rules)
    4. tailor   -- render a one-page resume for the job
    5. fill     -- pre-fill the application form in a browser adapter
    6. gates    -- run all seven pre-submission gates
    7. submit   -- only when ALL gates pass
    8. verify   -- compare interface response; record an immutable record

Independent process: this file can be `nohup`'d. The chat session may
close. State lives in SQLite, so a restart resumes where it stopped.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .browser.base import DryRunBrowser, FilledForm, SubmissionResult
from .gates.gates import SEVEN_GATES, GateContext
from .loop.queue import HumanQueue
from .resume.master import MasterResume
from .resume.tailor import Tailor
from .rules.engine import Rule, evaluate, load_rules
from .sources.base import Source
from .sources.dummy import DummySource
from .store import models as m
from .store.db import Store


@dataclass
class PipelineResult:
    scraped: int = 0
    hard_rejected: int = 0
    scored: int = 0
    tailored: int = 0
    held_for_human: int = 0
    gate_blocked: int = 0
    submitted: int = 0
    facts_rejected: int = 0
    details: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.details is None:
            self.details = []


class Pipeline:
    def __init__(
        self,
        store: Store,
        master: MasterResume,
        sources: list[Source] | None = None,
        rules: list[Rule] | None = None,
        browser: Any | None = None,
        config: dict | None = None,
    ):
        self.store = store
        self.master = master
        self.sources = sources or [DummySource()]
        self.rules = rules or []
        self.browser = browser or DryRunBrowser()
        self.config = config or {}
        self.tailor = Tailor(master)
        self.queue = HumanQueue(store)

    # ---- step 1: scrape ----
    def scrape(self, query: str, limit_per_source: int = 50) -> int:
        n = 0
        for src in self.sources:
            for job in src.search(query, limit=limit_per_source):
                self.store.upsert_job(job)
                n += 1
        return n

    # ---- step 2: hard filter ----
    def hard_filter(self) -> int:
        rejected = 0
        for job in self.store.jobs_by_status(m.JobStatus.SCRAPED.value):
            jd = job.title + " " + job.description
            verdict = evaluate(self.rules, jd)
            if verdict["blocked_by"]:
                job.status = m.JobStatus.REJECTED.value
                job.hard_reason = verdict["blocked_by"]
                self.store.upsert_job(job)
                rejected += 1
                continue
            # default hard requirement: at least one of the must-have skills
            must_have = self.config.get("must_have_any", [])
            if must_have and not any(k.lower() in jd.lower() for k in must_have):
                job.status = m.JobStatus.REJECTED.value
                job.hard_reason = f"missing must-have: {must_have}"
                self.store.upsert_job(job)
                rejected += 1
                continue
            job.status = m.JobStatus.HARD_FILTERED.value
            self.store.upsert_job(job)
        return rejected

    # ---- step 3: score by direction ----
    def score(self) -> int:
        """Score each survivor 0-100 by how well JD matches our skills."""
        # flatten skills into individual tokens so "distributed systems"
        # matches "distributed" and "systems" in the JD
        skill_tokens: set[str] = set()
        for s in self.master.skills:
            for tok in s.lower().replace("+", " ").replace("#", " ").split():
                if len(tok) > 1:
                    skill_tokens.add(tok)
        n = 0
        for job in self.store.jobs_by_status(m.JobStatus.HARD_FILTERED.value):
            jd_text = (job.title + " " + job.description).lower()
            jd_tokens = set(t for t in jd_text.replace("/", " ").replace(",", " ").split()
                             if len(t) > 1)
            overlap = len(skill_tokens & jd_tokens)
            score = min(100, 40 + overlap * 10)
            if "senior" in job.title.lower() or "staff" in job.title.lower():
                score += 10
            job.score = float(score)
            job.score_breakdown = {"skill_overlap": overlap,
                                   "skills_hit": sorted(skill_tokens & jd_tokens)}
            job.status = m.JobStatus.SCORED.value
            self.store.upsert_job(job)
            n += 1
        return n

    # ---- step 4: tailor + fact-check ----
    def tailor_all(self) -> tuple[int, int]:
        """Returns (tailored_ok, fact_rejected)."""
        tailored = 0
        rejected = 0
        threshold = float(self.config.get("min_score", 80))
        for job in self.store.jobs_by_status(m.JobStatus.SCORED.value):
            if job.score < threshold:
                continue
            md, check = self.tailor.tailor(job.title, job.description)
            self.store.save_tailored(m.TailoredResume(
                job_id=job.id,
                rendered_markdown=md,
                sources_used=check.facts_used,
                untraceable=check.untraceable,
                verified=check.verified,
            ))
            if not check.verified:
                job.status = m.JobStatus.REJECTED.value
                job.hard_reason = f"fact-check failed: {check.untraceable}"
                self.store.upsert_job(job)
                rejected += 1
                continue
            job.status = m.JobStatus.TAILORED.value
            self.store.upsert_job(job)
            tailored += 1
        return tailored, rejected

    # ---- step 5: pre-fill form (dry-run by default) ----
    def prepare_form(self, job: m.Job) -> FilledForm:
        verdict = evaluate(self.rules, job.title + " " + job.description)
        fields = dict(verdict["fields"])
        # baseline fields that come straight from the master
        fields.setdefault("name", self.master.name)
        fields.setdefault("email", self.master.contact.get("email", ""))
        return FilledForm(fields=fields)

    # ---- step 6: seven gates ----
    def run_gates(self, job: m.Job, tailored_md: str,
                  fact_verified: bool, untraceable: list[str]) -> list[m.GateResult]:
        apps = self.store.applications()
        applied_urls = {a_id for a_id in
                        {self.store.job(a.job_id).url for a in apps if self.store.job(a.job_id)}}
        today = datetime.now(timezone.utc).date().isoformat()
        today_count = sum(1 for a in apps if a.submitted_at.startswith(today))
        ctx = GateContext(
            job=job,
            tailored_markdown=tailored_md,
            fact_verified=fact_verified,
            untraceable=untraceable,
            open_questions=self.store.open_questions(),
            already_applied_urls=applied_urls,
            today_submitted_count=today_count,
            config=self.config,
        )
        results = []
        for name, fn in SEVEN_GATES:
            outcome, detail = fn(ctx)
            g = m.GateResult(job_id=job.id, gate_name=name,
                             outcome=outcome, detail=detail)
            self.store.record_gate(g)
            results.append(g)
        return results

    # ---- step 7 + 8: submit and verify ----
    def submit_one(self, job: m.Job, tailored_md: str,
                   fact_verified: bool, untraceable: list[str]) -> str:
        """Returns a status string for the dashboard."""
        gates = self.run_gates(job, tailored_md, fact_verified, untraceable)
        outcomes = {g.gate_name: g.outcome for g in gates}

        if any(o == m.GateOutcome.FAIL.value for o in outcomes.values()):
            job.status = m.JobStatus.REJECTED.value
            job.hard_reason = "; ".join(
                f"{n}: {d}" for n, d in
                ((g.gate_name, g.detail) for g in gates
                 if g.outcome == m.GateOutcome.FAIL.value))
            self.store.upsert_job(job)
            return "gate_fail"

        if any(o == m.GateOutcome.NEEDS_HUMAN.value for o in outcomes.values()):
            job.status = m.JobStatus.AWAITING_HUMAN.value
            self.store.upsert_job(job)
            # raise a question the human must answer
            self.queue.ask(
                job.id,
                question="A gate needs your decision before I can submit.",
                context="; ".join(
                    f"{g.gate_name}: {g.detail}" for g in gates
                    if g.outcome == m.GateOutcome.NEEDS_HUMAN.value),
            )
            return "awaiting_human"

        # all seven pass -> submit
        form = self.prepare_form(job)
        self.browser.open(job.url)
        self.browser.fill(form)
        shot = Path(self.config.get("screenshot_dir", "data/shots")) / f"{job.id.replace(':','_')}.png"
        self.browser.screenshot(shot)
        result: SubmissionResult = self.browser.submit()

        app = m.Application(
            id=f"app_{uuid.uuid4().hex[:10]}",
            job_id=job.id,
            company=job.company,
            title=job.title,
            interface_ok=result.ok,
            interface_payload=result.response,
            screenshot_path=str(shot),
            fact_error=not fact_verified,
        )
        self.store.save_application(app)
        job.status = (m.JobStatus.INTERFACE_CONFIRMED.value
                      if result.ok else m.JobStatus.HELD.value)
        self.store.upsert_job(job)
        return "submitted" if result.ok else "held"

    # ---- one-shot end-to-end ----
    def run(self, query: str, limit_per_source: int = 50,
            dry_run: bool = True) -> PipelineResult:
        res = PipelineResult()
        res.scraped = self.scrape(query, limit_per_source)
        res.hard_rejected = self.hard_filter()
        res.scored = self.score()
        tailored, facts_rej = self.tailor_all()
        res.tailored = tailored
        res.facts_rejected = facts_rej

        # pull the tailored records
        for job in self.store.jobs_by_status(m.JobStatus.TAILORED.value):
            tr_row = self.store.conn.execute(
                "SELECT * FROM tailored_resumes WHERE job_id=?", (job.id,)).fetchone()
            md = tr_row["rendered_markdown"] if tr_row else ""
            verified = bool(tr_row["verified"]) if tr_row else False
            untraceable = []
            status = self.submit_one(job, md, verified, untraceable)
            res.details.append(f"{job.company} - {job.title}: {status}")
            if status == "submitted":
                res.submitted += 1
            elif status == "awaiting_human":
                res.held_for_human += 1
            elif status in ("gate_fail",):
                res.gate_blocked += 1
            elif status == "held":
                res.held_for_human += 1
        return res
