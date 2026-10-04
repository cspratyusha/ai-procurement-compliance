"""USAGE_LOG_DIR keeps a test engine's clicks out of the real usage logs."""

from feedback import logger as interaction_log
from feedback import query_log


def test_both_usage_logs_follow_the_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("USAGE_LOG_DIR", str(tmp_path))
    assert interaction_log.usage_logs_redirected()
    assert interaction_log.resolve_usage_path("data/interaction_logs.jsonl") == tmp_path / "interaction_logs.jsonl"
    # The literal default: conftest repoints DEFAULT_QUERY_LOG at a temp file for the session.
    assert query_log._resolve("data/query_logs.jsonl") == tmp_path / "query_logs.jsonl"


def test_other_files_and_absolute_paths_are_not_moved(tmp_path, monkeypatch):
    monkeypatch.setenv("USAGE_LOG_DIR", str(tmp_path))
    other = interaction_log.resolve_usage_path("data/standards_corpus_full.json")
    assert other.parent.name == "data" and other.parent != tmp_path
    absolute = tmp_path / "elsewhere" / "interaction_logs.jsonl"
    assert interaction_log.resolve_usage_path(absolute) == absolute


def test_without_it_the_logs_stay_where_they_were(monkeypatch):
    monkeypatch.delenv("USAGE_LOG_DIR", raising=False)
    assert not interaction_log.usage_logs_redirected()
    assert interaction_log.resolve_usage_path("data/interaction_logs.jsonl") == \
        interaction_log._BASE_DIR / "data" / "interaction_logs.jsonl"
