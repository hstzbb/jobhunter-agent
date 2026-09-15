"""End-to-end smoke test with the dummy source and dry-run browser."""
import sys, pathlib, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from jobhunter.store.db import Store
from jobhunter.resume.master import MasterResume
from jobhunter.pipeline import Pipeline
from jobhunter.browser.base import DryRunBrowser


MASTER = MasterResume(
    name="Test Person", title="Backend Engineer",
    contact={"email": "test@example.com"},
    summary="6 years Python backend. Built systems serving 100 QPS. Team of 3.",
    experiences=[
        {"company": "A", "title": "Senior Eng", "period": "2022-now",
         "description": "Python FastAPI PostgreSQL Kubernetes."},
    ],
    skills=["python", "fastapi", "postgresql", "kubernetes"],
)


def test_dry_run_pipeline():
    with tempfile.TemporaryDirectory() as td:
        store = Store(os.path.join(td, "t.db"))
        pipe = Pipeline(
            store=store, master=MASTER,
            sources=[],  # empty; we inject jobs directly
            rules=[],
            browser=DryRunBrowser(),
            config={"min_score": 0, "daily_cap": 50,
                    "must_have_any": []},
        )
        # inject a job directly
        from jobhunter.store import models as m
        pipe.store.upsert_job(m.Job(
            id="dummy:0", source="dummy", company="Acme",
            title="Python Backend Engineer", url="https://example.com/0",
            description="Python FastAPI PostgreSQL Kubernetes",
        ))
        # hard filter -> score -> tailor
        pipe.hard_filter()
        pipe.score()
        tailored, rej = pipe.tailor_all()
        assert tailored >= 1, rej
        # submit
        from jobhunter.store import models as mm
        job = pipe.store.job("dummy:0")
        tr = pipe.store.conn.execute(
            "SELECT * FROM tailored_resumes WHERE job_id=?", (job.id,)).fetchone()
        status = pipe.submit_one(job, tr["rendered_markdown"],
                                 bool(tr["verified"]), [])
        assert status in ("submitted", "gate_fail", "awaiting_human"), status
        store.close()
