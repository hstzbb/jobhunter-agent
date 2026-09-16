"""国聘行动 (iguopin.com) source adapter.

国聘网 is the SASAC-backed central state-owned-enterprise job board. Job
listings require a logged-in session, so like the BOSS adapter this uses
a persistent Playwright context under data/browser_profile_iguopin/.

Run `jh login iguopin` once, log in with your phone number, then the
pipeline can search. This adapter only scrapes the list; it does not
auto-submit.
"""
from __future__ import annotations

import time
from pathlib import Path

from .base import make_id
from ..store import models as m


# Job card selectors observed on iguopin job-center. Tried in order.
CARD_SELECTORS = [
    ".job-list .job-item",
    ".job-list-item",
    "[class*='job-card']",
    "[class*='position-item']",
    ".el-card",
]


class IguopinSource:
    name = "iguopin"

    def __init__(self, profile_dir: str | Path):
        self.profile_dir = str(Path(profile_dir))
        self._pw = None
        self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        launch = dict(
            headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        for channel in ("msedge", "chrome"):
            try:
                self._ctx = self._pw.chromium.launch_persistent_context(
                    self.profile_dir, channel=channel, **launch)
                break
            except Exception:
                continue
        else:
            self._ctx = self._pw.chromium.launch_persistent_context(
                self.profile_dir, **launch)
        return self

    def __exit__(self, *exc):
        self._ctx.close()
        self._pw.stop()

    def ensure_logged_in(self) -> None:
        """Open the job center and wait for the user to log in manually."""
        page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        try:
            page.goto("https://www.iguopin.com/job-center",
                      wait_until="commit", timeout=15000)
        except Exception:
            pass
        print("=" * 60)
        print("国聘网已打开。请在浏览器中：")
        print("  1. 右上角点「登录/注册」，用手机号登录")
        print("  2. 能看到岗位列表后，回到这里按回车")
        print("=" * 60)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

    def search(self, query: str, *, limit: int = 50) -> list[m.Job]:
        page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        page.goto(f"https://www.iguopin.com/job-center?keyword={query}",
                  wait_until="domcontentloaded", timeout=20000)
        time.sleep(6)

        cards = []
        for sel in CARD_SELECTORS:
            cards = page.query_selector_all(sel)
            if cards:
                break

        jobs: list[m.Job] = []
        seen: set[str] = set()
        for card in cards[:limit]:
            try:
                text = (card.inner_text() or "").strip()
                href = card.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://www.iguopin.com" + href
                if href in seen or not text:
                    continue
                seen.add(href)
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                title = lines[0] if lines else ""
                company = lines[1] if len(lines) > 1 else ""
                jobs.append(m.Job(
                    id=make_id(self.name, href.rsplit("/", 1)[-1]),
                    source=self.name,
                    company=company or "国聘岗位",
                    title=title,
                    url=href,
                    location="全国",
                    description=text,
                ))
            except Exception:
                continue
        return jobs
