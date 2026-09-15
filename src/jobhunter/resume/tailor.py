"""Tailor a one-page resume for a specific job.

Strategy: pick the most relevant experiences from the master by keyword
overlap with the JD, then render a compact markdown. This is a
deterministic stand-in; swap `render()` for an LLM call when you have
one. Whatever you swap in, it MUST go through FactChecker afterwards --
that gate is non-negotiable.
"""
from __future__ import annotations

import re
from pathlib import Path

from .fact_checker import FactChecker, FactCheckResult
from .master import MasterResume


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z+#.]+|[\u4e00-\u9fa5]{2,}", text.lower()))


def _score_experience(exp: dict, jd_tokens: set[str]) -> int:
    blob = " ".join(str(v) for v in exp.values()).lower()
    blob_tokens = _tokens(blob)
    return len(blob_tokens & jd_tokens)


class Tailor:
    def __init__(self, master: MasterResume):
        self.master = master
        self.checker = FactChecker(master.to_text())

    def tailor(self, job_title: str, job_description: str,
               max_experiences: int = 3) -> tuple[str, FactCheckResult]:
        """Return (rendered_markdown, fact_check_result).

        Caller must refuse to use the markdown unless result.verified is True.
        """
        jd_text = f"{job_title}\n{job_description}"
        jd_tokens = _tokens(jd_text)

        ranked = sorted(
            self.master.experiences,
            key=lambda e: _score_experience(e, jd_tokens),
            reverse=True,
        )[:max_experiences]

        lines = [
            f"# {self.master.name} — {self.master.title}",
            "",
            "## Applying for",
            f"**{job_title}**",
            "",
            "## Summary",
            self.master.summary,
            "",
            "## Selected experience",
        ]
        for exp in ranked:
            lines.append(f"### {exp.get('title', 'Role')} @ {exp.get('company', '')}")
            if exp.get("period"):
                lines.append(f"_{exp['period']}_")
            for k, v in exp.items():
                if k in ("title", "company", "period"):
                    continue
                lines.append(f"- {v}")
            lines.append("")

        lines.append("## Skills")
        lines.append(" · ".join(self.master.skills))

        rendered = "\n".join(lines)
        result = self.checker.check(rendered)
        return rendered, result

    def save(self, markdown: str, out_path: str | Path) -> Path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(markdown, encoding="utf-8")
        return p
