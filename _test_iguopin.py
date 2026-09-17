"""Test the updated iguopin adapter."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))
from jobhunter.sources.iguopin import IguopinSource

with IguopinSource(cookies_path="data/iguopin_cookies.json") as ig:
    jobs = ig.search("Java", limit=20)
    print(f"found {len(jobs)} jobs")
    for j in jobs:
        print(f"  {j.company[:20]:20s} | {j.location:15s} | {j.title} | {j.salary}")
