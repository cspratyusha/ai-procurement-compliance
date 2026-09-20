import pytest

from knowledge_reasoning import factory
from knowledge_reasoning.adapters.fixture import (
    FixtureGraphRepository,
    FixtureRetrievalPort,
    FixtureStandardsRepository,
)
from knowledge_reasoning.config.settings import load_settings


def test_default_settings_wire_up_postgres_graph_and_standards_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # As of integration Stage E: postgres is the default graph/standards
    # backend, not fixture — a default pointing at an empty Neo4j that
    # silently returns nothing is a trap. See settings.py.
    monkeypatch.delenv("KR_GRAPH_BACKEND", raising=False)
    monkeypatch.delenv("KR_STANDARDS_BACKEND", raising=False)
    settings = load_settings()
    assert settings.graph_backend == "postgres"
    assert settings.standards_backend == "postgres"


def test_fixture_mode_still_works_end_to_end_when_explicitly_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Offline, no database required — the suite this test lives in relies
    # on this staying true for the rest of the project.
    monkeypatch.setenv("KR_GRAPH_BACKEND", "fixture")
    monkeypatch.setenv("KR_STANDARDS_BACKEND", "fixture")
    monkeypatch.setenv("KR_RETRIEVAL_BACKEND", "fixture")
    settings = load_settings()
    services = factory.build_services(settings)

    assert isinstance(services.graph_repository, FixtureGraphRepository)
    assert isinstance(services.standards_repository, FixtureStandardsRepository)
    assert isinstance(services.retrieval_port, FixtureRetrievalPort)

    result = services.retrieval_port.retrieve("LED street light", top_k=1)
    assert result.candidates[0].is_number == "IS 10322-5-1:2015"
    paths = services.graph_repository.expand(["IS 10322-5-1:2015"], max_hops=1).paths
    assert len(paths) > 0


def test_postgres_graph_backend_without_dsn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KR_GRAPH_BACKEND", "postgres")
    monkeypatch.delenv("KR_POSTGRES_DSN", raising=False)
    settings = load_settings()
    from knowledge_reasoning.config.schema_map import SchemaMap

    with pytest.raises(ValueError, match="KR_POSTGRES_DSN"):
        factory.build_graph_repository(settings, SchemaMap())


def test_neo4j_graph_backend_without_uri_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KR_GRAPH_BACKEND", "neo4j")
    monkeypatch.delenv("KR_NEO4J_URI", raising=False)
    settings = load_settings()
    from knowledge_reasoning.config.schema_map import SchemaMap

    with pytest.raises(ValueError, match="KR_NEO4J_URI"):
        factory.build_graph_repository(settings, SchemaMap())


def test_unknown_graph_backend_value_rejected_at_settings_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KR_GRAPH_BACKEND", "sqlite")
    with pytest.raises(ValueError, match="KR_GRAPH_BACKEND"):
        load_settings()
