"""The FactChecker is the heart of the system. Test it hard."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from jobhunter.resume.fact_checker import FactChecker


MASTER = """
Zhang San
Backend Engineer
6 years of backend engineering in Python and Go.
Led a team of 4 engineers.
Reduced p99 latency from 800ms to 120ms.
Processed 10 TB of data per day.
"""


def test_fact_traceable():
    fc = FactChecker(MASTER)
    good = """Zhang San - Backend Engineer
Summary: 6 years in Python and Go. Led a team of 4 engineers.
Reduced p99 from 800ms to 120ms.
"""
    r = fc.check(good)
    assert r.verified, r.untraceable


def test_invented_number_rejected():
    fc = FactChecker(MASTER)
    bad = """Zhang San
Shipped a product used by 50,000,000 users.  # invented number
"""
    r = fc.check(bad)
    assert not r.verified
    assert any("50" in u for u in r.untraceable), r.untraceable


def test_year_must_appear_in_master():
    fc = FactChecker(MASTER)
    bad = "Worked at Acme from 2015 to 2017."
    r = fc.check(bad)
    assert not r.verified
