"""`jh` command-line entry point.

    jh submit --yes     run the full 8-step pipeline end-to-end
    jh status           print the daily panel
    jh ask              list / answer human-in-the-loop questions
    jh login <site>     open browser and log into zhipin | iguopin
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
from .sources.greenhouse import GreenhouseSource
from .store.db import Store


def _project_root() -> Path:
    return Path.cwd()


def _build_sources(root: Path, cfg, args) -> list:
    """Build the list of job sources based on config + flags."""
    sources = []

    # 1) Greenhouse (foreign companies, no login needed, always on)
    gh_yaml = root / "config" / "greenhouse_companies.yaml"
    if gh_yaml.exists() and not args.demo:
        gh = GreenhouseSource.from_yaml(gh_yaml, filter_china=True)
        sources.append(gh)
        print(f"[greenhouse] {len(gh.companies)} companies configured")

    # 2) Iguopin (state-owned / central enterprises, needs login)
    if cfg.raw.get("use_iguopin", False) and not args.demo:
        from .sources.iguopin import IguopinSource
        profile = root / "data" / "browser_profile_iguopin"
        try:
            ig = IguopinSource(profile_dir=profile)
            ig.__enter__()
            sources.append(ig)
            print(f"[iguopin] profile={profile}")
        except Exception as e:
            print(f"[warn] iguopin unavailable ({e})", file=sys.stderr)

    # 3) Zhipin (optional, off by default)
    if cfg.raw.get("use_zhipin", False) and not args.demo:
        from .sources.zhipin import ZhipinSource
        profile = root / "data" / "browser_profile"
        city = cfg.raw.get("zhipin_city", "101220800")
        try:
            z = ZhipinSource(profile_dir=profile, city_code=city)
            z.__enter__()
            sources.append(z)
            print(f"[zhipin] city={city}")
        except Exception as e:
            print(f"[warn] zhipin unavailable ({e})", file=sys.stderr)

    if not sources:
        print("[demo] using offline DummySource")
        sources.append(DummySource())
    return sources


def cmd_submit(args) -> int:
    root = _project_root()
    cfg = load_config(root)
    store = Store(root / "data" / "applied.db")
    sources = _build_sources(root, cfg, args)
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
    for s in sources:
        if hasattr(s, "__exit__") and type(s).__name__ in ("ZhipinSource", "IguopinSource"):
            try:
                s.__exit__()
            except Exception:
                pass
    return 0


def cmd_login(args) -> int:
    """Open a browser and log into the requested site."""
    root = _project_root()
    site = args.site or "zhipin"

    if site == "zhipin":
        from .sources.zhipin import ZhipinSource
        profile = root / "data" / "browser_profile"
        with ZhipinSource(profile_dir=profile, city_code=args.city or "101220800") as z:
            z.ensure_logged_in(timeout_seconds=args.timeout)
        print("Saved to:", profile)

    elif site == "iguopin":
        from .sources.iguopin import IguopinSource
        profile = root / "data" / "browser_profile_iguopin"
        with IguopinSource(profile_dir=profile) as ig:
            ig.ensure_logged_in()
        print("Saved to:", profile)
        print("Now set use_iguopin: true in config/config.yaml")

    else:
        print(f"unknown site: {site}. Use 'zhipin' or 'iguopin'.")
        return 1
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
    except Exception as e:
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
    sp.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--demo", action="store_true", help="offline DummySource only")
    sp.set_defaults(func=cmd_submit)

    lg = sub.add_parser("login", help="open browser and log into a site")
    lg.add_argument("site", nargs="?", default="zhipin",
                    choices=["zhipin", "iguopin"])
    lg.add_argument("--city", default=None)
    lg.add_argument("--timeout", type=int, default=180)
    lg.set_defaults(func=cmd_login)

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
