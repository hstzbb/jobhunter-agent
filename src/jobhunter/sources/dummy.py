"""A built-in dummy source for offline demos / tests.

It emits a hand-crafted mix of jobs: some obviously qualified, some
missing required skills, some with invented-sounding numbers. This lets
you run the whole pipeline end-to-end without a real account.
"""
from __future__ import annotations

from .base import make_id
from ..store import models as m


_SAMPLE_JOBS = [
    {
        "company": "Acme", "title": "Senior Backend Engineer",
        "location": "Remote", "salary": "40k",
        "description": (
            "Build distributed systems in Python and Go. "
            "5+ years experience, PostgreSQL, Kubernetes. "
            "We process billions of requests per day."
        ),
    },
    {
        "company": "Globex", "title": "Python Developer",
        "location": "Shanghai", "salary": "25-35k",
        "description": (
            "Backend services in Python / FastAPI. "
            "Experience with asyncio, PostgreSQL, Docker. "
            "2+ years required."
        ),
    },
    {
        "company": "Initech", "title": "Data Analyst",
        "location": "Beijing", "salary": "15-20k",
        "description": (
            "SQL and Tableau. Reporting and dashboards. "
            "No engineering work."
        ),
    },
    {
        "company": "Umbrella", "title": "ML Engineer",
        "location": "Shenzhen", "salary": "50k",
        "description": (
            "Train and deploy LLMs. PyTorch, distributed training. "
            "PhD preferred. CUDA experience required."
        ),
    },
    {
        "company": "Hooli", "title": "Staff Software Engineer",
        "location": "Remote", "salary": "60k",
        "description": (
            "Design large-scale systems. Python, Go, Rust. "
            "10+ years. Mentorship experience."
        ),
    },
    {
        "company": "Stark", "title": "Frontend Engineer",
        "location": "Hangzhou", "salary": "30k",
        "description": (
            "React, TypeScript, WebGL. "
            "Build rich visual dashboards."
        ),
    },
]


class DummySource:
    name = "dummy"

    def search(self, query: str, *, limit: int = 50) -> list[m.Job]:
        q = query.lower()
        out: list[m.Job] = []
        for i, j in enumerate(_SAMPLE_JOBS):
            # crude relevance: include everything so the demo pipeline
            # has enough candidates to filter/score
            text = (j["title"] + " " + j["description"]).lower()
            if q and q not in text and q.split() and not any(w in text for w in q.split()):
                continue
            out.append(m.Job(
                id=make_id(self.name, str(i)),
                source=self.name,
                company=j["company"],
                title=j["title"],
                url=f"https://example.com/jobs/{i}",
                location=j["location"],
                salary=j["salary"],
                description=j["description"],
            ))
            if len(out) >= limit:
                break
        return out
