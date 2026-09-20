"""Environment-driven wiring: which port implementation backs each Protocol.

This is the *only* place that decides fixture vs. live. Business logic
(Phase 2/3/4) takes `GraphRepository` / `StandardsRepository` / `RetrievalPort`
as constructor arguments and never imports an adapter directly — so
pointing at Teammate 1's real database, once it exists, is a change to
this module (or just the `KR_*` environment variables it reads), never a
change to the algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass

from knowledge_reasoning.config.schema_map import SchemaMap, load_schema_map
from knowledge_reasoning.config.settings import Settings, load_settings
from knowledge_reasoning.ports.graph_repository import GraphRepository
from knowledge_reasoning.ports.retrieval_port import RetrievalPort
from knowledge_reasoning.ports.standards_repository import StandardsRepository


@dataclass(frozen=True)
class Services:
    schema: SchemaMap
    graph_repository: GraphRepository
    standards_repository: StandardsRepository
    retrieval_port: RetrievalPort


def build_graph_repository(settings: Settings, schema: SchemaMap) -> GraphRepository:
    if settings.graph_backend == "fixture":
        from knowledge_reasoning.adapters.fixture import FixtureGraphRepository

        return FixtureGraphRepository(schema)

    if settings.graph_backend == "postgres":
        from knowledge_reasoning.adapters.live import PostgresGraphRepository

        if not settings.postgres_dsn:
            raise ValueError("KR_GRAPH_BACKEND=postgres requires KR_POSTGRES_DSN")
        return PostgresGraphRepository(settings.postgres_dsn, schema)

    if settings.graph_backend == "neo4j":
        from neo4j import GraphDatabase

        from knowledge_reasoning.adapters.live import Neo4jGraphRepository

        if not settings.neo4j_uri:
            raise ValueError("KR_GRAPH_BACKEND=neo4j requires KR_NEO4J_URI")
        auth = (
            (settings.neo4j_user, settings.neo4j_password)
            if settings.neo4j_user
            else None
        )
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=auth)
        return Neo4jGraphRepository(driver, schema)

    raise ValueError(f"unknown graph backend: {settings.graph_backend!r}")


def build_standards_repository(
    settings: Settings, schema: SchemaMap, graph_repository: GraphRepository
) -> StandardsRepository:
    if settings.standards_backend == "fixture":
        from knowledge_reasoning.adapters.fixture import FixtureGraphRepository
        from knowledge_reasoning.adapters.fixture import FixtureStandardsRepository

        if not isinstance(graph_repository, FixtureGraphRepository):
            raise ValueError(
                "KR_STANDARDS_BACKEND=fixture requires KR_GRAPH_BACKEND=fixture "
                "too, since FixtureStandardsRepository shares the same "
                "in-memory graph for its category-edge fallback"
            )
        return FixtureStandardsRepository(schema, graph_repository)

    if settings.standards_backend == "postgres":
        from knowledge_reasoning.adapters.live import PostgresStandardsRepository

        if not settings.postgres_dsn:
            raise ValueError("KR_STANDARDS_BACKEND=postgres requires KR_POSTGRES_DSN")
        return PostgresStandardsRepository(settings.postgres_dsn, schema, graph_repository)

    raise ValueError(f"unknown standards backend: {settings.standards_backend!r}")


def build_retrieval_port(settings: Settings) -> RetrievalPort:
    if settings.retrieval_backend == "fixture":
        from knowledge_reasoning.adapters.fixture import FixtureRetrievalPort

        return FixtureRetrievalPort()

    if settings.retrieval_backend == "live":
        from knowledge_reasoning.adapters.live import HttpRetrievalPort

        if not settings.retrieval_base_url:
            raise ValueError("KR_RETRIEVAL_BACKEND=live requires KR_RETRIEVAL_BASE_URL")
        return HttpRetrievalPort(settings.retrieval_base_url)

    raise ValueError(f"unknown retrieval backend: {settings.retrieval_backend!r}")


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or load_settings()
    schema = load_schema_map(settings.schema_map_path)
    graph_repository = build_graph_repository(settings, schema)
    standards_repository = build_standards_repository(settings, schema, graph_repository)
    retrieval_port = build_retrieval_port(settings)
    return Services(
        schema=schema,
        graph_repository=graph_repository,
        standards_repository=standards_repository,
        retrieval_port=retrieval_port,
    )
