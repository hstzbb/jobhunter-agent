"""Browser adapter: open a real browser, fill the form, submit, verify.

The video: "他自己开浏览器，把申请表一栏填掉，选项题也自己答，
填完自己点提交，再比对接口返回。"

This module defines the interface. A concrete Playwright adapter is
optional (import only when you actually want to drive a browser). The
default `DryRunBrowser` records what WOULD have been submitted, so the
pipeline is testable and safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FilledForm:
    """What the agent decided to put into the application form."""
    fields: dict[str, str] = field(default_factory=dict)
    questions_answered: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SubmissionResult:
    ok: bool
    detail: str = ""
    response: dict[str, Any] = field(default_factory=dict)
    screenshot_path: str = ""


class DryRunBrowser:
    """No real browser -- just record the fill and pretend success."""
    name = "dry-run"

    def open(self, url: str) -> None:
        self.url = url

    def fill(self, form: FilledForm) -> None:
        self.last_form = form

    def submit(self) -> SubmissionResult:
        return SubmissionResult(
            ok=True,
            detail="dry-run: nothing was actually submitted",
            response={"dry_run": True, "url": getattr(self, "url", "")},
        )

    def screenshot(self, path: str | Path) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            f"# dry-run screenshot stub\nurl={getattr(self,'url','')}\n",
            encoding="utf-8",
        )
        return str(path)


class PlaywrightBrowser:
    """Real browser automation via Playwright.

    Install:  pip install playwright && playwright install chromium
    This is intentionally NOT imported at module import time, so the
    project works without Playwright installed.
    """
    name = "playwright"

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        return self

    def open(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded")

    def fill(self, form: FilledForm) -> None:
        # This is a skeleton. Real-world form filling is site-specific --
        # each company ATS has its own DOM. That is exactly what the
        # "every pit becomes a rule" comment in the video means: you
        # write a per-site adapter that knows the selectors, and it
        # accumulates here.
        raise NotImplementedError(
            "Write a per-company adapter that knows the form's selectors. "
            "Start from DryRunBrowser, then add real selectors one site at "
            "a time. Every unexpected selector becomes a rule under "
            "config/rules/."
        )

    def submit(self, submit_button: str = "Submit") -> SubmissionResult:
        with self._page.expect_response(lambda r: r.status < 400) as resp_info:
            self._page.get_by_role("button", name=submit_button).click()
        resp = resp_info.value
        return SubmissionResult(
            ok=True,
            detail=f"HTTP {resp.status}",
            response={"status": resp.status, "url": resp.url},
        )

    def screenshot(self, path: str | Path) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(path), full_page=True)
        return str(path)

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()
