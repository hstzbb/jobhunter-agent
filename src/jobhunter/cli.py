"""`jh` command-line entry point.

    jh submit --yes     run the full 8-step pipeline end-to-end
    jh status           print the daily panel
    jh ask              list / answer the human-in-the-loop questions
    jh ask <id> --answer "..."
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .browser.base import DryRunBrowser
from .config import load_config
from .dashboard.panel import render
from .loop.queue import HumanQueue
from .pipeline import Pipeline
from .sources.dummy import DummySource
from .store.db import Store


def _project_root() -> Path:
    # config lives in ./config relative to CWD by default.
    return Path.cwd()


def cmd_submit(args) -> int:
    root = _project_root()
    cfg = load_config(root)
    store = Store(root / "data" / "applied.db")
    sources = [DummySource()]  # replace with real sources here
    browser = DryRunBrowser() if args.dry_run else _maybe_playwright()

    pipe = Pipeline(
        store=store,
        master=cfg.master,
        sources=sources,
        rules=cfg.rules,
        browser=browser,
        config={
            "min_score": cfg.min_score,
            "daily_cap": cfg.daily_cap,
            "must_have_any": cfg.must_have_any,
            "screenshot_dir": str(root / "data" / "shots"),
        },
    )
    result = pipe.run(cfg.query, limit_per_source=args.limit, dry_run=args.dry_run)
    print(f"scraped={result.scraped} "
          f"hard_rejected={result.hard_rejected} "
          f"scored={result.scored} "
          f"tailored={result.tailored} "
          f"facts_rejected={result.facts_rejected} "
          f"submitted={result.submitted} "
          f"awaiting_human={result.held_for_human}")
    for line in result.details:
        print("  -", line)
    print()
    print(render(store))
    store.close()
    return 0


def cmd_status(args) -> int:
    root = _project_root()
    store = Store(root / "data" / "applied.db")
    print(render(store))
    store.close()
    return 0


def cmd_ask(args) -> int:
    root = _project_root()
    store = Store(root / "data" / "applied.db")
    q = HumanQueue(store)
    if args.id and args.answer:
        q.answer(args.id, args.answer)
        print(f"answered {args.id}: {args.answer}")
        store.close()
        return 0
    open_qs = q.open()
    if not open_qs:
        print("nothing waiting on you right now.")
        store.close()
        return 0
    for question in open_qs:
        print(f"[{question.id}] job={question.job_id}")
        print(f"  Q: {question.question}")
        if question.context:
            print(f"  context: {question.context}")
        if question.options:
            print(f"  options: {question.options}")
        print(f"  -> jh ask {question.id} --answer \"...\"")
    store.close()
    return 0


def _maybe_playwright():
    try:
        from .browser.base import PlaywrightBrowser
        return PlaywrightBrowser(headless=False)
    except Exception as e:  # pragma: no cover
        print(f"[warn] playwright unavailable ({e}); falling back to dry-run",
              file=sys.stderr)
        return DryRunBrowser()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jh", description="autonomous job application pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("submit", help="run the full pipeline")
    sp.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    sp.add_argument("--dry-run", action="store_true", default=True,
                    help="do not really submit (default: on)")
    sp.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                    help="actually drive the browser and submit")
    sp.add_argument("--limit", type=int, default=20,
                    help="max jobs per source")
    sp.set_defaults(func=cmd_submit)

    st = sub.add_parser("status", help="print the daily panel")
    st.set_defaults(func=cmd_status)

    aq = sub.add_parser("ask", help="list / answer human questions")
    aq.add_argument("id", nargs="?")
    aq.add_argument("--answer", default=None)
    aq.set_defaults(func=cmd_ask)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
