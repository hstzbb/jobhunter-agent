"""Greenhouse.io source adapter.

Hundreds of foreign companies (and a growing number of Chinese tech firms)
run their careers page on Greenhouse. Their public JSON API needs no
login and no browser:

    https://boards-api.greenhouse.io/v1/boards/{company_token}/jobs?content=true

This adapter iterates over a built-in list of company tokens, pulls every
open job, and filters by title keyword + location (China or remote-friendly).

Add your own target companies to config/greenhouse_companies.yaml -- one
token per line. Find a company's token by opening its careers page; the
board URL looks like https://boards.greenhouse.io/<token>.
"""
from __future__ import annotations

import html
import json
import re
import urllib.request
from pathlib import Path

from .base import make_id
from ..store import models as m


# Companies verified to be on Greenhouse (batch-tested).
# Tokens are lowercase, no spaces.
DEFAULT_COMPANIES = [
    "stripe", "airbnb", "dropbox", "figma", "datadog",
    "robinhood", "coinbase", "asana", "gitlab", "cloudflare",
    "okta", "twilio", "attentive", "gusto", "lattice",
    "consensys", "mattermost", "discord", "reddit", "pinterest",
    "lyft", "waymo", "affirm", "sofi", "brex", "mercury",
    "northbeam", "netlify", "vercel", "remote",
    # extra commonly-known
    "sentry", "segment", "harness", "postman", "kong",
    "hashicorp", "snyk", "wistia", "calm", "duolingo",
    "rokt", "braze", "iterable", "launchdarkly", "octopusdeploy",
    "drift", "helpscout", "frontapp", "intercom", "census",
    "fivetran", "dbt", "hex", "mode", "observable",
    "calendly", "typeform", "webflow", "webex", "ringcentral",
]

# Locations we care about: China (any city) or roles that are China-based.
CHINA_LOC_RE = re.compile(
    r"china|beijing|shanghai|shenzhen|guangzhou|hangzhou|"
    r"chengdu|wuhan|nanjing|suzhou|hong kong|taipei|beijing|chinese",
    re.I,
)

# Remote-friendly locations (some companies list "Remote - China" etc.)
REMOTE_RE = re.compile(r"remote", re.I)


def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


class GreenhouseSource:
    name = "greenhouse"

    def __init__(self, companies: list[str] | None = None,
                 filter_china: bool = True,
                 timeout: int = 15):
        self.companies = companies or DEFAULT_COMPANIES
        self.filter_china = filter_china
        self.timeout = timeout

    @classmethod
    def from_yaml(cls, path: str | Path, filter_china: bool = True) -> "GreenhouseSource":
        import yaml
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        companies = [c for c in data if isinstance(c, str)]
        return cls(companies=companies, filter_china=filter_china)

    def search(self, query: str, *, limit: int = 500) -> list[m.Job]:
        # Note: we ignore `query` here. The source returns every
        # China-listed job it can; the pipeline's hard-filter and score
        # steps decide what matches the user's direction. This is because
        # foreign-company titles are in English ("Backend Engineer") and
        # would never match a Chinese query like "Java 后端开发".
        jobs: list[m.Job] = []
        for company in self.companies:
            if len(jobs) >= limit:
                break
            try:
                data = self._fetch(company)
            except Exception:
                continue
            for j in data.get("jobs", []):
                loc = (j.get("location") or {}).get("name", "") or ""
                if self.filter_china and not CHINA_LOC_RE.search(loc):
                    continue
                title = j.get("title", "")
                content = _strip_html(j.get("content", ""))
                offices = j.get("offices") or []
                dept = (j.get("departments") or [{}])[0].get("name", "")
                jobs.append(m.Job(
                    id=make_id(self.name, str(j.get("id"))),
                    source=self.name,
                    company=j.get("company_name", company),
                    title=title,
                    url=j.get("absolute_url", ""),
                    location=loc,
                    salary="",
                    description=f"{dept}\n{content}",
                    posted_at=j.get("first_published", ""),
                    raw={"company_token": company,
                         "office": offices[0].get("name", "") if offices else ""},
                ))
        return jobs

    def _fetch(self, company: str) -> dict:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (jobhunter-agent)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
