"""Rules engine: every pit you hit becomes one rule.

The video: "约 8400 行 Python，每个坑都沉淀成一条规则。"

Rules live as small YAML files under config/rules/. Each rule can:
  - block a job by a regex on JD text (e.g. "needs PhD", "requires clearance")
  - inject extra questions for the human when a pattern matches
  - rewrite a field value (e.g. always answer "visa_sponsorship": "No")

This is intentionally trivial on purpose: a flat, human-editable list.
If a rule needs code, it is a bug -- write it in YAML.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Rule:
    name: str
    reason: str = ""
    block_if_matches: str | None = None   # regex; if JD matches, reject
    ask_human_when: str | None = None     # regex; if JD matches, ask human
    set_field: dict[str, str] | None = None  # always set these form fields


def load_rules(rules_dir: str | Path) -> list[Rule]:
    rules: list[Rule] = []
    p = Path(rules_dir)
    if not p.exists():
        return rules
    for f in sorted(p.glob("*.yaml")) + sorted(p.glob("*.yml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        rules.append(Rule(
            name=data.get("name", f.stem),
            reason=data.get("reason", ""),
            block_if_matches=data.get("block_if_matches"),
            ask_human_when=data.get("ask_human_when"),
            set_field=data.get("set_field"),
        ))
    return rules


def evaluate(rules: list[Rule], jd_text: str) -> dict:
    """Return {blocked_by, questions_to_ask, fields}."""
    import re
    out = {"blocked_by": None, "questions_to_ask": [], "fields": {}}
    for r in rules:
        if r.block_if_matches and re.search(r.block_if_matches, jd_text, re.I):
            out["blocked_by"] = f"{r.name}: {r.reason}"
            return out
        if r.ask_human_when and re.search(r.ask_human_when, jd_text, re.I):
            out["questions_to_ask"].append(
                f"[{r.name}] {r.reason or r.ask_human_when}")
        if r.set_field:
            out["fields"].update(r.set_field)
    return out
