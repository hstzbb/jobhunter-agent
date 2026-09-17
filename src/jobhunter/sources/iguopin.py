"""国聘行动 (iguopin.com) source adapter.

State-owned / central enterprise job board. Requires a one-time login
(`jh login iguopin`). Cookies are saved to data/iguopin_cookies.json.
The real search page is /job?channel=social&keyword=..., and each result
is a <div class="job-card">.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .base import make_id
from ..store import models as m


class IguopinSource:
    name = "iguopin"

    def __init__(self, cookies_path: str | Path):
        self.cookies_path = Path(cookies_path)
        self._pw = None
        self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        browser = self._pw.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
        ])
        storage_state = str(self.cookies_path) if self.cookies_path.exists() else None
        self._ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            storage_state=storage_state,
        )
        return self

    def __exit__(self, *exc):
        try:
            self._ctx.storage_state(path=str(self.cookies_path))
        except Exception:
            pass
        self._ctx.close()
        self._pw.stop()

    def ensure_logged_in(self, wait_seconds: int = 180) -> None:
        """Open a non-headless browser so the user can log in."""
        from playwright.sync_api import sync_playwright
        # relaunch headless=False just for the login step
        browser = self._pw.chromium.launch(headless=False, args=[
            "--disable-blink-features=AutomationControlled",
        ])
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto("https://www.iguopin.com/job?channel=social",
                  wait_until="domcontentloaded", timeout=20000)
        print(f"浏览器已打开，{wait_seconds} 秒内请在浏览器里登录国聘网...")
        time.sleep(wait_seconds)
        ctx.storage_state(path=str(self.cookies_path))
        ctx.close()
        browser.close()

    def search(self, query: str, *, limit: int = 50) -> list[m.Job]:
        page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        url = f"https://www.iguopin.com/job?channel=social&keyword={query}"
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(5)

        cards = page.query_selector_all(".job-card")
        jobs: list[m.Job] = []
        seen: set[str] = set()

        for card in cards[:limit]:
            try:
                name_el = card.query_selector(".job-name")
                title_el = card.query_selector(".job-title")
                comp_el = card.query_selector(".company-name")
                tag_els = card.query_selector_all(".tag-item")
                ant_tag_els = card.query_selector_all(".ant-tag")

                title = (name_el.inner_text() or "").strip() if name_el else ""
                # location is embedded in the job-title attribute:
                # e.g. "java后端 「北京-东城区」"
                title_attr = (title_el.get_attribute("title") or "") if title_el else ""
                loc_match = re.search(r"[「【](.+?)[」】]", title_attr)
                location = loc_match.group(1) if loc_match else "全国"

                company = (comp_el.get_attribute("title")
                           or (comp_el.inner_text() if comp_el else "") or "").strip()
                tags = [t.inner_text().strip() for t in tag_els if t.inner_text().strip()]
                ant_tags = [t.inner_text().strip() for t in ant_tag_els if t.inner_text().strip()]

                # job detail link: look for an <a> with href inside the card
                link_el = card.query_selector("a[href]")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.iguopin.com" + href

                if not title or title in seen:
                    continue
                seen.add(title)

                jobs.append(m.Job(
                    id=make_id(self.name, f"{company}-{title}-{location}"),
                    source=self.name,
                    company=company or "国聘岗位",
                    title=title,
                    url=href or url,
                    location=location,
                    salary=" ".join(tags),
                    description=" ".join(ant_tags + tags),
                ))
            except Exception:
                continue
        return jobs
