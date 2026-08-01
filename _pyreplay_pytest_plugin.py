"""pyreplay's auto-injected pytest plugin (#98).

Reports every test's boundaries to the ACTIVE tracer as chapter
events, so a suite trace stops being one undifferentiated river:
`tracer.py --root . -m pytest tests/` injects this via `-p` and each
test becomes a named, outcome-colored span in the replayer.

Loaded without a tracer (someone runs pytest with -p by hand) it does
nothing. Known limit, stated: a teardown failure after a passing call
phase is not folded back into that test's chapter outcome.

The handoff: tracer.py imports THIS module and sets _ACTIVE_TRACER on
it before launching pytest; pytest's `-p` import then reuses the same
sys.modules entry. (Reading __main__ would not work — runpy swaps
sys.modules["__main__"] to pytest's for the duration of the run.)
"""

_ACTIVE_TRACER = None


def _tracer():
    return _ACTIVE_TRACER


def pytest_runtest_logstart(nodeid, location):
    tr = _tracer()
    if tr is not None:
        # location = (relative fspath, 0-based lineno or None, domain)
        tr.chapter("s", nodeid, f=location[0],
                   l=(location[1] or 0) + 1)


def pytest_runtest_logreport(report):
    tr = _tracer()
    if tr is None:
        return
    # one END per test: the call phase always reports; a setup that
    # failed or skipped IS the test's whole story (no call follows)
    if report.when == "call" or (report.when == "setup"
                                 and report.outcome != "passed"):
        tr.chapter("e", report.nodeid, outcome=report.outcome)
