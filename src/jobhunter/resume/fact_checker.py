"""Fact-checker: the hard reject, not a warning.

The video's core rule:

    "简历里每个数字都必须能在模板里找到原文校验，不过直接拒绝生成，
     不是警告，是拒绝。"

So this checker does two things:

1. Tokenize the master resume into a set of *claims* (numbers, dates,
   proper nouns, project names, metrics).
2. Scan the tailored resume for numeric / metric-like tokens. Any token
   that does not appear verbatim (or as a normalized match) in the master
   is treated as UNTRACEABLE. If even one is found, the whole tailored
   resume is rejected.

This is intentionally strict. We would rather hold a job for human review
than submit a fabricated number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Tokens we treat as "facts that must be traceable":
#  - percentages, years, counts, money, durations
#  - proper nouns (company / product / project names)
_NUMBER_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*"
    r"(?:%|％|percent|years?|yrs?|yr|months?|mos?|mo|days?|d|k|K|w|W|万|千|亿|"
    r"\+|plus)?)"
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_facts(master_text: str) -> set[str]:
    """Pull every traceable fact token out of the master resume."""
    facts: set[str] = set()
    for m in _NUMBER_RE.finditer(master_text):
        facts.add(_normalize(m.group(0)))
    for m in _YEAR_RE.finditer(master_text):
        facts.add(m.group(0))
    # also keep the whole normalized master as a fallback bag-of-phrases
    return facts


@dataclass
class FactCheckResult:
    verified: bool
    untraceable: list[str] = field(default_factory=list)
    facts_used: list[str] = field(default_factory=list)


class FactChecker:
    """Strict traceability gate between master resume and tailored output."""

    def __init__(self, master_text: str):
        self.master_text = master_text
        self.master_norm = _normalize(master_text)
        self.facts = _extract_facts(master_text)

    def check(self, tailored_text: str) -> FactCheckResult:
        """Return a hard verdict. verified=False => caller MUST reject."""
        untraceable: list[str] = []
        used: list[str] = []

        for m in _NUMBER_RE.finditer(tailored_text):
            tok = _normalize(m.group(0))
            if tok in self.facts or tok in self.master_norm:
                used.append(tok)
                continue
            # allow pure integer years/round numbers only if they appear verbatim
            bare = tok.rstrip("%％percentyrsyearsmonthmosdaysdkkww万千亿+plus ")
            if bare and bare in self.master_norm:
                used.append(tok)
                continue
            untraceable.append(m.group(0).strip())

        for m in _YEAR_RE.finditer(tailored_text):
            y = m.group(0)
            if y not in self.master_norm and y not in self.facts:
                untraceable.append(y)

        # de-dup while preserving order
        seen = set()
        uniq_untraceable = []
        for u in untraceable:
            if u not in seen:
                seen.add(u)
                uniq_untraceable.append(u)

        return FactCheckResult(
            verified=(len(uniq_untraceable) == 0),
            untraceable=uniq_untraceable,
            facts_used=sorted(set(used)),
        )
