"""Load the resume master (the only source of truth for facts).

The master is a YAML file that the human writes once. Every tailored
resume is assembled ONLY from these facts. The FactChecker guarantees
no invented numbers slip through.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MasterResume:
    name: str
    title: str
    contact: dict[str, str]
    summary: str
    experiences: list[dict[str, Any]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        """Flatten to plain text for fact extraction.

        Every number / project / company in here is a *claim* the agent is
        allowed to reuse. Nothing outside this text may appear in a
        tailored resume.
        """
        parts = [self.name, self.title, self.summary]
        for k, v in self.contact.items():
            parts.append(f"{k}: {v}")
        for exp in self.experiences:
            for k, v in exp.items():
                parts.append(f"{k}: {v}")
        parts.append(" ".join(self.skills))
        return "\n".join(parts)


def load_master(path: str | Path) -> MasterResume:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return MasterResume(
        name=data["name"],
        title=data["title"],
        contact=data.get("contact", {}),
        summary=data["summary"],
        experiences=data.get("experiences", []),
        skills=data.get("skills", []),
        extra=data.get("extra", {}),
    )
