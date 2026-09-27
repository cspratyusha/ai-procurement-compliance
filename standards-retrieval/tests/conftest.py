"""Shared test fixtures.

Two problems this solves.

**The suite silently changed meaning with the environment.** Nothing pinned
which corpus the tests ran against, so `STANDARDS_CORPUS` leaking in from a
shell, the same variable used to serve the full 6,360-standard corpus, quietly repointed every test at different data. Sixteen tests then failed,
not because the code was wrong but because they assert on pilot-corpus ids
(`IS-ELEC-005`) that do not exist in the full corpus. A test that passes or
fails on an ambient variable is not testing anything reliably, so the corpus
is now pinned for the whole session.

**Unit tests borrowed production data as a fixture.** Ranking rules like the
supersession penalty are corpus-independent: they take a corpus argument.
Tests for them should construct the two or three records the rule needs
rather than reaching into whatever `load_corpus()` happens to return, which
is what tied them to the pilot corpus in the first place. `fixture_corpus`
below provides that, so those tests state their own preconditions and keep
working whatever the shipped corpus becomes.

**Test runs wrote themselves into the usage log.** `/retrieve` records every
search it serves so the dashboard can report real use, and the suite calls
`/retrieve` several hundred times. Left alone that puts a four-figure query
count on a dashboard nobody has used -- the exact dishonesty the logging was
added to remove. `_isolate_query_log` below redirects the log to a temporary
file for the whole session.
"""

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Pin the corpus at conftest import time, which happens before any test
# module is imported. A fixture is too late: test_api.py does
# `from main import app` at module level, and main resolves its corpus on
# import, so by the time a fixture ran the wrong corpus was already loaded.
# The default corpus is what the committed indexes and the LightGBM model
# were built against, so it is the only one this suite's assertions are
# meaningful against. Tests that want the full corpus set it themselves.
_INHERITED_CORPUS = os.environ.pop("STANDARDS_CORPUS", None)

# The API loads the local explanation model at startup when Ollama is
# running. Tests that start the lifespan must not pull a 4 GB model onto the
# GPU as a side effect, so warm-up is off for the whole suite.
os.environ["EXPLANATION_WARMUP"] = "0"

# The engine tests exercise ranking, not sign-in, so they call the API
# anonymously. test_accounts.py switches this back on for itself. Accounts go
# to a throwaway database, never the deployment's.
os.environ["AUTH_REQUIRED"] = "0"
import tempfile  # noqa: E402

os.environ["ACCOUNTS_DB"] = str(Path(tempfile.mkdtemp(prefix="accounts-test-")) / "accounts.db")


@pytest.fixture(scope="session", autouse=True)
def _restore_inherited_corpus():
    """Put the caller's STANDARDS_CORPUS back when the session ends."""
    try:
        yield
    finally:
        if _INHERITED_CORPUS is not None:
            os.environ["STANDARDS_CORPUS"] = _INHERITED_CORPUS


def _standard(**kwargs):
    """Build a Standard without depending on the loaded corpus."""
    from data_loader import Standard

    base = {
        "id": "",
        "number": "",
        "title": "",
        "scope": "",
        "description": "",
        "category": "electrical_cables",
        "keywords": [],
        "version": "",
        "status": "active",
        "last_amended": "",
    }
    base.update(kwargs)
    # Standard is a pydantic model; tolerate it gaining or losing fields.
    allowed = set(Standard.model_fields)
    return Standard(**{k: v for k, v in base.items() if k in allowed})


@pytest.fixture
def fixture_corpus():
    """A minimal corpus exercising the supersession rule.

    One superseded standard and its active successor in the same family,
    plus two unrelated active standards to check that the rule leaves the
    rest of the ranking alone.
    """
    records = [
        _standard(
            id="FIX-CABLE-OLD",
            number="IS 1554 (Part 1):1988",
            title="PVC Insulated Heavy Duty Electric Cables, superseded edition",
            scope="Heavy duty PVC insulated power cables up to 1100 V.",
            status="superseded",
        ),
        _standard(
            id="FIX-CABLE-NEW",
            number="IS 1554 (Part 1):2020",
            title="PVC Insulated Heavy Duty Electric Cables, current edition",
            scope="Heavy duty PVC insulated power cables up to 1100 V.",
            status="active",
        ),
        _standard(
            id="FIX-CABLE-A",
            number="IS 694:2010",
            title="PVC Insulated Cables for Working Voltages up to 1100 V",
            scope="Single-core non-sheathed PVC insulated copper cables.",
            status="active",
        ),
        _standard(
            id="FIX-CABLE-B",
            number="IS 7098 (Part 2):2011",
            title="XLPE Insulated Power Cables for 3.3 kV to 33 kV",
            scope="Cross-linked polyethylene insulated armoured power cables.",
            status="active",
        ),
    ]
    return {s.id: s for s in records}


@pytest.fixture(scope="session", autouse=True)
def _isolate_query_log(tmp_path_factory):
    """Keep the suite's own searches out of the real usage log.

    Every `/retrieve` call appends a record, and the suite makes hundreds of
    them. Those are tests, not use, and counting them would make the
    dashboard's headline figure a fiction. `main` imported `append_query` by
    name, so both that binding and the module default are redirected.
    """
    import feedback.query_log as query_log

    log_path = tmp_path_factory.mktemp("query-log") / "query_logs.jsonl"
    real_append = query_log.append_query

    def _append_to_temp(**kwargs):
        kwargs["path"] = log_path
        real_append(**kwargs)

    previous_default = query_log.DEFAULT_QUERY_LOG
    query_log.DEFAULT_QUERY_LOG = log_path
    query_log.append_query = _append_to_temp

    import main
    main_previous = getattr(main, "append_query", None)
    if main_previous is not None:
        main.append_query = _append_to_temp

    try:
        yield log_path
    finally:
        query_log.append_query = real_append
        query_log.DEFAULT_QUERY_LOG = previous_default
        if main_previous is not None:
            main.append_query = main_previous
