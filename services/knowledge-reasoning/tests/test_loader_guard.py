import pytest

from knowledge_reasoning.adapters.fixture.fixture_data import DEFAULT_FIXTURES_ROOT, load_all_fixture_domains
from knowledge_reasoning.loader.fixture_loader import ProductionUnverifiedDataError, _guard_unverified


@pytest.fixture(scope="module")
def domains():
    return load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)


def test_all_fixture_data_is_unverified_by_convention(domains) -> None:
    # If this ever fails, someone marked fixture data verified: true, which
    # defeats the point of "placeholder data must be visibly unverified".
    for domain in domains:
        assert all(not n.verified for n in domain.nodes)
        assert all(not e.verified for e in domain.edges)


def test_guard_blocks_unverified_data_in_production(domains) -> None:
    with pytest.raises(ProductionUnverifiedDataError):
        _guard_unverified(domains, env="production", allow_unverified_in_production=False)


def test_guard_allows_override_in_production(domains) -> None:
    _guard_unverified(domains, env="production", allow_unverified_in_production=True)  # no raise


def test_guard_allows_unverified_data_outside_production(domains) -> None:
    _guard_unverified(domains, env="dev", allow_unverified_in_production=False)  # no raise
    _guard_unverified(domains, env="staging", allow_unverified_in_production=False)  # no raise
