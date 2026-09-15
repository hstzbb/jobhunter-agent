"""Text dashboard: the single panel the video opens.

    今天投了多少？还有多少在排队？哪几件必须我拍板？

A `$ jh status` prints a compact, always-readable summary. No web server
required -- this is the panel. Swap in a TUI / web UI later if you want
the screenshot in the video.
"""
from __future__ import annotations

from ..store.db import Store


def render(store: Store) -> str:
    counts = store.count_by_status()
    apps = store.applications()
    open_q = store.open_questions()

    total = sum(counts.values()) or 1
    submitted_ok = sum(1 for a in apps if a.interface_ok)
    fact_errors = sum(1 for a in apps if a.fact_error)

    lines = []
    lines.append("=== jobhunter-agent - daily panel ===")
    lines.append(f"  jobs in pool        : {total}")
    lines.append(f"  scraped             : {counts.get('scraped', 0)}")
    lines.append(f"  rejected (hard)     : {counts.get('rejected', 0)}")
    lines.append(f"  scored (>=threshold): {counts.get('scored', 0)}")
    lines.append(f"  tailored            : {counts.get('tailored', 0)}")
    lines.append(f"  awaiting human      : {counts.get('awaiting_human', 0)}")
    lines.append(f"  submitted (total)   : {len(apps)}")
    lines.append(f"  interface confirmed : {submitted_ok}")
    lines.append(f"  held (unclear)      : {counts.get('held', 0)}")
    lines.append(f"  FACT ERRORS         : {fact_errors}   (must be 0)")
    lines.append("")

    if open_q:
        lines.append("--- needs your decision ---")
        for q in open_q:
            lines.append(f"  [{q.id}] job={q.job_id}")
            lines.append(f"      Q: {q.question}")
            if q.context:
                lines.append(f"      context: {q.context}")
            if q.options:
                lines.append(f"      options: {q.options}")
        lines.append("")

    lines.append("--- recent submissions ---")
    for a in apps[:10]:
        mark = "OK  " if a.interface_ok else "HELD"
        lines.append(f"  [{mark}] {a.submitted_at[:10]}  {a.company} - {a.title}")

    return "\n".join(lines)
