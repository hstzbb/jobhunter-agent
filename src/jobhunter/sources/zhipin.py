"""BOSS直聘 (zhipin.com) source adapter.

Design notes
------------
* Uses a persistent Playwright context under ``data/browser_profile/`` so
  that the login cookie survives across runs. Run ``jh login`` once and
  log in with your phone-number/QR code; afterwards this adapter runs
  unattended.
* This adapter ONLY scrapes the job list. It does NOT apply to jobs --
  applying still goes through your browser adapter of choice (dry-run
  by default). Boss's anti-bot is aggressive, so we keep this minimal
  and polite.
* Selectors drift. If scraping returns zero jobs, open the browser
  yourself (``jh login``), inspect a job card, and update
  ``JOB_CARD_SELECTORS`` below.

City codes (Beijing/Shanghai/Hangzhou/Anqing ...):
    https://www.zhipin.com/wapi/zpgeek/common/config/city.json
    Common ones:
      101010100 北京
      101020100 上海
      101210100 杭州
      101220100 合肥
      101220800 安庆
      101190400 南京
      101280100 广州
"""
from __future__ import annotations

import re
import time
import urllib.parse
from pathlib import Path

from .base import make_id
from ..store import models as m


# BOSS直聘 2024-2026 年常用的岗位卡片选择器。按顺序尝试，第一个命中的用。
JOB_CARD_SELECTORS = [
    ".job-card-wrapper",
    ".search-job-result .job-card-box",
    "[class*='job-card-']",
    ".job-list-box li",
]

# Inside each card, the fields we want.
CARD_TITLE = [".job-name", ".job-title", "[class*='job-title']", ".name"]
CARD_COMPANY = [".company-name a", ".company-name", "[class*='company']"]
CARD_SALARY = [".salary", ".job-salary", "[class*='salary']"]
CARD_LOCATION = [".job-area", ".company-location", "[class*='area']"]
CARD_LINK = ["a.job-card-left", "a", ".job-left a"]


class ZhipinSource:
    name = "zhipin"

    def __init__(self, profile_dir: str | Path, city_code: str = "101220800"):
        self.profile_dir = str(Path(profile_dir))
        self.city_code = city_code
        self._pw = None
        self._ctx = None

    # ---- context lifecycle ----
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir,
            headless=False,  # keep visible so you can solve captchas
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        return self

    def __exit__(self, *exc):
        self._ctx.close()
        self._pw.stop()

    # ---- public API ----
    def ensure_logged_in(self, timeout_seconds: int = 180) -> None:
        """Open zhipin.com and wait until the user is logged in.

        Detection: a logged-out search page redirects to /login.html.
        A logged-in page has a user avatar in the top right.
        """
        page = self._ctx.new_page()
        page.goto("https://www.zhipin.com/", wait_until="domcontentloaded")
        # Wait until the URL no longer points at the login page and an
        # avatar appears.
        deadline = time.time() + timeout_seconds
        logged = False
        while time.time() < deadline:
            url = page.url
            if "login" not in url and page.query_selector("[class*='user-info'], .btn-secondary"):
                # secondary button on logged-out page says "登录/注册"
                if not page.query_selector("a:has-text('登录/注册')"):
                    logged = True
                    break
            time.sleep(2)
        page.close()
        if not logged:
            raise RuntimeError(
                "Login not detected within the timeout. Run `jh login` again "
                "and complete the QR / phone-number login in the opened window."
            )

    def search(self, query: str, *, limit: int = 30) -> list[m.Job]:
        page = self._ctx.new_page()
        q = urllib.parse.quote(query)
        url = (
            f"https://www.zhipin.com/web/geek/job?"
            f"query={q}&city={self.city_code}"
        )
        page.goto(url, wait_until="domcontentloaded")
        # let lazy-loading settle
        page.wait_for_timeout(3000)

        cards = self._find_cards(page)
        jobs: list[m.Job] = []
        seen: set[str] = set()
        for card in cards:
            if len(jobs) >= limit:
                break
            try:
                title = self._text(card, CARD_TITLE)
                company = self._text(card, CARD_COMPANY)
                salary = self._text(card, CARD_SALARY)
                location = self._text(card, CARD_LOCATION)
                href = self._href(card, CARD_LINK)
            except Exception:
                continue
            if not title or not company:
                continue
            if not href.startswith("http"):
                href = "https://www.zhipin.com" + href
            # dedupe by url
            if href in seen:
                continue
            seen.add(href)

            # BOSS job ids look like /job_detail/abcdef.html
            m_id = re.search(r"/(?:job_detail/)?([\w]+)\.html", href)
            raw_id = m_id.group(1) if m_id else href
            jobs.append(m.Job(
                id=make_id(self.name, raw_id),
                source=self.name,
                company=company.strip(),
                title=title.strip(),
                url=href,
                location=location.strip(),
                salary=salary.strip(),
            ))
        page.close()
        return jobs

    # ---- selector helpers ----
    def _find_cards(self, page):
        for sel in JOB_CARD_SELECTORS:
            cards = page.query_selector_all(sel)
            if cards:
                return cards
        return []

    def _text(self, scope, selectors):
        for sel in selectors:
            el = scope.query_selector(sel)
            if el:
                t = (el.inner_text() or "").strip()
                if t:
                    return t
        return ""

    def _href(self, scope, selectors):
        for sel in selectors:
            el = scope.query_selector(sel)
            if el:
                href = el.get_attribute("href") or ""
                if href:
                    return href
        return ""
