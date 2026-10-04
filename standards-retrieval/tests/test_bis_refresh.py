"""The engine's own refresh from BIS: when it runs, and that a failure or an
interruption never leaves a corpus and an index that disagree."""

import json
from datetime import datetime, timedelta, timezone

import pytest

import bis_refresh


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """The refresh pointed at throwaway files, its steps replaced by stand-ins."""
    data = tmp_path / "data"
    index = tmp_path / "index"
    data.mkdir()
    index.mkdir()
    guarded = [data / "standards_corpus_full.json", data / "eval_set_full.json", data / "train_queries_full.json"]
    for path in guarded:
        path.write_text("old", encoding="utf-8")
    (index / "faiss.index").write_text("old", encoding="utf-8")
    monkeypatch.setattr(bis_refresh, "_STATE", tmp_path / "state.json")
    monkeypatch.setattr(bis_refresh, "_LOG", tmp_path / "refresh.log")
    monkeypatch.setattr(bis_refresh, "_LOCK", tmp_path / "refresh.lock")
    monkeypatch.setattr(bis_refresh, "_BACKUP", tmp_path / "backup")
    monkeypatch.setattr(bis_refresh, "_INDEX_DIR", index)
    monkeypatch.setattr(bis_refresh, "_GUARDED", guarded)
    monkeypatch.setenv("STANDARDS_CORPUS", "full")
    monkeypatch.setenv("BIS_AUTO_REFRESH", "1")
    steps = []

    def run(label, args, env_extra=None):
        steps.append(label)
        if label in ("merge", "index"):           # the steps that rewrite served files
            for path in guarded:
                path.write_text("new", encoding="utf-8")
            (index / "faiss.index").write_text("new", encoding="utf-8")
        if label == sandbox_fail.get("at"):
            raise RuntimeError(f"{label} failed")

    sandbox_fail = {}
    monkeypatch.setattr(bis_refresh, "_run", run)
    return {"guarded": guarded, "index": index, "steps": steps, "fail": sandbox_fail, "tmp": tmp_path}


def served(box):
    return {p.read_text(encoding="utf-8") for p in box["guarded"] + [box["index"] / "faiss.index"]}


def test_a_refresh_is_due_when_none_has_completed_or_the_last_is_a_week_old(sandbox):
    assert bis_refresh.due()
    bis_refresh._save_state(last_completed=datetime.now(timezone.utc).isoformat())
    assert not bis_refresh.due()
    old = datetime.now(timezone.utc) - timedelta(days=8)
    bis_refresh._save_state(last_completed=old.isoformat())
    assert bis_refresh.due()


def test_it_is_off_for_other_corpora_and_when_switched_off(sandbox, monkeypatch):
    assert bis_refresh.enabled()
    monkeypatch.setenv("STANDARDS_CORPUS", "mock")
    assert not bis_refresh.enabled()
    monkeypatch.setenv("STANDARDS_CORPUS", "full")
    monkeypatch.setenv("BIS_AUTO_REFRESH", "0")
    assert not bis_refresh.enabled()
    assert bis_refresh.start_if_due() is False


def test_a_complete_refresh_is_served_and_recorded(sandbox):
    swapped = []
    assert bis_refresh.refresh(on_success=lambda: swapped.append(True))
    assert served(sandbox) == {"new"} and swapped == [True]
    assert sandbox["steps"][-1] == "index"
    assert bis_refresh.last_completed() and not bis_refresh._state().get("applying_since")
    assert bis_refresh.status()["state"] == "idle"
    assert not bis_refresh._LOCK.exists()


def test_a_failed_step_puts_the_served_corpus_and_index_back(sandbox):
    sandbox["fail"]["at"] = "index"
    swapped = []
    assert not bis_refresh.refresh(on_success=lambda: swapped.append(True))
    assert served(sandbox) == {"old"}, "corpus and index must agree after a failure"
    assert swapped == [] and bis_refresh.last_completed() is None
    assert bis_refresh.status()["state"] == "failed" and "index" in bis_refresh.status()["error"]


def test_a_portal_failure_changes_nothing_served(sandbox):
    sandbox["fail"]["at"] = "portal: records"
    assert not bis_refresh.refresh()
    assert served(sandbox) == {"old"} and "merge" not in sandbox["steps"]


def test_one_refresh_at_a_time(sandbox):
    bis_refresh._LOCK.write_text("1234 earlier", encoding="utf-8")
    assert not bis_refresh.refresh()
    assert sandbox["steps"] == []


def test_an_interrupted_refresh_is_rolled_back_at_the_next_start(sandbox):
    # The engine closed after the merge rewrote the corpus, before the index.
    bis_refresh._back_up()
    bis_refresh._save_state(applying_since=datetime.now(timezone.utc).isoformat())
    for path in sandbox["guarded"]:
        path.write_text("new", encoding="utf-8")
    assert bis_refresh.recover()
    assert served(sandbox) == {"old"}
    assert not bis_refresh._state().get("applying_since")
    assert not bis_refresh.recover(), "nothing to roll back twice"
