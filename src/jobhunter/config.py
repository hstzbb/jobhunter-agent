"""Load config.yaml + rules/*.yaml + master resume."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .resume.master import MasterResume, load_master
from .rules.engine import Rule, load_rules


@dataclass
class Config:
    raw: dict
    rules: list[Rule]
    master: MasterResume

    @property
    def query(self) -> str:
        return self.raw.get("query", "python")

    @property
    def min_score(self) -> float:
        return float(self.raw.get("min_score", 80))

    @property
    def daily_cap(self) -> int:
        return int(self.raw.get("daily_cap", 30))

    @property
    def must_have_any(self) -> list[str]:
        return list(self.raw.get("must_have_any", []))


def load_config(project_root: str | Path) -> Config:
    root = Path(project_root)
    cfg_path = root / "config" / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"{cfg_path} not found. Copy config/config.example.yaml to config/config.yaml"
        )
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    master_path = root / "data" / "resume_master.yaml"
    master = load_master(master_path)

    rules = load_rules(root / "config" / "rules")

    return Config(raw=raw, rules=rules, master=master)
