# jobhunter-agent

> 一条命令
> `jh submit --yes`
> ，自己抓岗、自己打分、自己定制简历、自己开浏览器填表、过七道闸、提交、比对接口。
> 人只做三件事：
> **拍板、注册账号、交验证码**
> 。

A reference implementation of the autonomous job-application agent shown in the demo video. It is a **skeleton with the hard safety rules built in**, not a turnkey scraper. Real job-site adapters are pluggable; you write them one site at a time, and every pit you hit becomes a rule under `config/rules/`.



***

## What it does

The pipeline has eight stages, exactly as in the video:



```
scrape → hard-filter → score → tailor → fill → seven gates → submit → verify
```



| Step               | What happens                                                                                                                                                                     |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. scrape**      | Every configured source adapter pulls postings into a SQLite pool.                                                                                                               |
| **2. hard-filter** | Drops anything blocked by `config/rules/*.yaml` or missing must-have keywords.                                                                                                   |
| **3. score**       | Survivors are scored 0–100 by how well the JD matches your skills. Only `score ≥ min_score` (default 80) moves on.                                                               |
| **4. tailor**      | Renders a one-page markdown resume per job. **Every number in it must trace back to a fact in&#x20;**`data/resume_master.yaml` — otherwise the resume is *rejected*, not warned. |
| **5. fill**        | Opens a browser adapter and fills the application form.                                                                                                                          |
| **6. seven gates** | Runs all seven pre-submission gates. Any fail / needs-human blocks submission.                                                                                                   |
| **7. submit**      | Only when **all seven gates pass**. Never resubmits the same URL.                                                                                                                |
| **8. verify**      | Compares the POST response. Unclear results are *held*, never guessed.                                                                                                           |

### The seven gates



1. **facts\_traceable** — every number in the tailored resume appears verbatim in the master resume.

2. **no\_open\_questions** — nothing left for the human to decide.

3. **not\_already\_applied** — no double-submission.

4. **score\_above\_threshold** — JD score ≥ `min_score`.

5. **daily\_quota** — respects `daily_cap` so you don't get banned.

6. **resume\_renders** — the tailored resume is non-empty and well-formed.

7. **hard\_requirements\_still\_match** — re-checks the JD right before submitting (in case it changed).

### What the human does (only 3 things)



1. **拍板 (decide)** — when the master resume has no answer, the agent pastes the original question and waits. It never guesses.

2. **注册账号 (register accounts)** — new company ATS accounts are yours to create.

3. **交验证码 (SMS/email codes)** — hand the verification code over when asked.

Everything else runs on its own. The process is independent of the chat: close the terminal, it keeps going (state is in SQLite).



***

## Quickstart (offline, safe)



```
git clone https://github.com/hstzbb/jobhunter-agent.git

cd jobhunter-agent

python -m venv .venv && . .venv/Scripts/activate    # Windows: .venv\Scripts\Activate.ps1

pip install -e .

cp config/config.example.yaml config/config.yaml

\\# run the whole pipeline against the built-in DummySource, dry-run browser:

jh submit --yes

\\# inspect the daily panel:

jh status

\\# answer questions the agent couldn't:

jh ask

jh ask q\\\_xxxxxxxxxx --answer "No, I do not need visa sponsorship."
```

The DummySource emits a handful of sample jobs so you can watch the full pipeline run without touching a real job site.



***

## Project layout



```
jobhunter-agent/

├── config/

│   ├── config.example.yaml      # copy to config.yaml

│   └── rules/                   # every pit becomes one YAML here

│       ├── 00-blocklist.yaml

│       └── 10-default-answers.yaml

├── data/

│   └── resume\\\_master.yaml        # the ONLY source of truth for facts

├── src/jobhunter/

│   ├── cli.py                   # \\\`jh\\\` entry point

│   ├── pipeline.py              # the 8-step pipeline

│   ├── config.py                # loads config + rules + master

│   ├── resume/

│   │   ├── master.py            # master resume model

│   │   ├── fact\\\_checker.py     # hard-reject on untraceable facts

│   │   └── tailor.py           # per-JD resume rendering

│   ├── gates/gates.py           # the seven gates

│   ├── sources/

│   │   ├── base.py              # Source protocol

│   │   └── dummy.py            # offline sample source

│   ├── browser/base.py         # DryRun + Playwright skeleton

│   ├── loop/queue.py            # human-in-the-loop question queue

│   ├── rules/engine.py          # YAML rule engine

│   ├── store/                  # SQLite persistence

│   └── dashboard/panel.py       # \\\`jh status\\\` panel

├── tests/

├── pyproject.toml

└── README.md
```



***

## Job sources

Three sources are built in. They all feed the same pipeline (hard-filter -> score -> tailor -> seven gates -> dry-run submit). None auto-submits.

### 1. Greenhouse (foreign companies, default ON, no login)

Hundreds of foreign companies run their careers page on Greenhouse. The public JSON API needs no browser and no login:

``bash
jh submit --yes --limit 50
``

Companies are listed in `config/greenhouse_companies.yaml` - one token per line. Find a company's token on its careers page (URL looks like `boards.greenhouse.io/<token>`). Add as many as you want; 404s are skipped. Jobs are filtered to China-based locations (Beijing / Shanghai / Shenzhen / Hong Kong / Taipei).

### 2. iguopin.com (state-owned / central enterprises)

SASAC-backed central SOE job board. Requires a one-time login:

``bash
jh login iguopin     # opens Edge, log in with phone, press Enter
# then in config/config.yaml: use_iguopin: true
jh submit --yes
``

### 3. BOSS直聘 (optional, off by default)

Anti-bot is aggressive. Only enable after going through the captcha dance once:

``bash
jh login zhipin
# then in config/config.yaml: use_zhipin: true
``

All three adapters only scrape the list. Submissions stay in dry-run until you wire up a per-company form adapter you trust.



***

## Adding another real job source

Implement the `Source` protocol in `src/jobhunter/sources/your_site.py`:



```
class YourSiteSource:

\&#x20;   name = "yoursite"

\&#x20;   def search(self, query: str, limit: int = 50) -> list\\\[m.Job]:

\&#x20;       ...  # scrape / query the site, return Job objects
```

Then register it in `cli.py`:



```
sources = \\\[DummySource(), YourSiteSource()]
```

## Adding a real browser flow

`browser/base.py` ships `DryRunBrowser` (default, safe) and a `PlaywrightBrowser` skeleton. For each company ATS you hit, write a small adapter that knows that form's selectors. The video's line *"每个坑都沉淀成一条规则"* means: every time a selector or a weird question surprises you, write a `config/rules/*.yaml` entry or a per-site adapter — don't one-off it.



***

## Design rules (do not relax these)



* **Fact-check is a hard reject, not a warning.** If the tailored resume contains a number not present in `resume_master.yaml`, the whole resume is rejected. This is the line between an honest agent and a lying one.

* **Seven gates must ALL pass.** One fail = no submission. One `needs_human` = pause, ask, wait.

* **Never resubmit the same URL.** `not_already_applied` is permanent.

* **Daily cap.** Even if there are 5,000 good jobs, stop at `daily_cap`. Anti-ban and politeness.

* **State is on disk.** SQLite + screenshots under `data/shots/`. Close the chat, re-run, it resumes.



***

## Tests



```
pip install -e .\\\[dev]

pytest -q
```



***

## Legal / ethical note

This is a **reference skeleton**. Scraping real job sites may violate their Terms of Service. Use it on sites you have permission to automate, respect `robots.txt` and rate limits, and do not use it to mass-spam employers. The human-in-the-loop gates exist precisely to keep submissions honest and targeted. You are responsible for how you use it.

## License

MIT.