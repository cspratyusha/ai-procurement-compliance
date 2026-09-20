from datetime import datetime, timedelta, timezone

from knowledge_reasoning.adapters.live.postgres_standards_repository import (
    _RECENT_CHECK_WINDOW_DAYS,
    _derive_verification,
)


def test_recent_check_is_verified() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(days=1)
    verified, reason = _derive_verification(None, checked_at)
    assert verified is True
    assert reason is None


def test_stale_check_is_not_verified() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(days=_RECENT_CHECK_WINDOW_DAYS + 1)
    verified, reason = _derive_verification(None, checked_at)
    assert verified is False
    assert reason == "stale_check"


def test_source_url_without_checked_at_is_unchecked_source() -> None:
    verified, reason = _derive_verification("https://bis.gov.in/standard/123", None)
    assert verified is False
    assert reason == "unchecked_source"


def test_neither_field_is_no_provenance() -> None:
    verified, reason = _derive_verification(None, None)
    assert verified is False
    assert reason == "no_provenance"


def test_naive_datetime_is_treated_as_utc_not_a_crash() -> None:
    # Postgres can hand back naive datetimes depending on column type;
    # this must not raise a tz-aware/naive comparison TypeError.
    naive_recent = datetime.now() - timedelta(days=1)
    verified, reason = _derive_verification(None, naive_recent)
    assert verified is True
    assert reason is None
