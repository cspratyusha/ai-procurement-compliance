"""Environment-driven runtime configuration.

Everything here is what `factory.py` reads to decide which port
implementation to wire up. Business-logic tuning knobs that belong to a
specific Phase 2/3 algorithm (hub-degree threshold, orphan confidence
threshold, etc.) live next to that algorithm's module, not here — this file
is scoped to "which backend, which database, which environment", nothing
about how the algorithms themselves behave.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

# Graph and standards backends default to "postgres", not "fixture", as of
# integration Stage E: there is no real Neo4j data anywhere (confirmed
# Stage A/B — nothing has ever written to it), and the real relationship
# data lives in Postgres's `standard_relationships` table. A default that
# quietly points at an empty database and returns nothing is worse than one
# that fails loudly when Postgres isn't configured — "postgres" as the
# default makes that the thing you have to notice, not "live" pointing at
# an empty Neo4j that silently returns []. `neo4j` stays selectable
# (`Neo4jGraphRepository` is kept intact) for whenever Teammate 1 populates
# it for real — see INTEGRATION.md.
GraphBackend = Literal["fixture", "postgres", "neo4j"]
StandardsBackend = Literal["fixture", "postgres"]
RetrievalBackend = Literal["fixture", "live"]
Environment = Literal["dev", "staging", "production"]


@dataclass(frozen=True)
class Settings:
    env: Environment
    graph_backend: GraphBackend
    standards_backend: StandardsBackend
    retrieval_backend: RetrievalBackend

    neo4j_uri: str | None
    neo4j_user: str | None
    neo4j_password: str | None

    postgres_dsn: str | None

    retrieval_base_url: str | None

    schema_map_path: str | None

    # Loader safety gate (decision 5): the loader refuses to write
    # verified=false records into anything flagged as `production` unless
    # this is explicitly set.
    allow_unverified_in_production: bool


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    env = os.environ.get("KR_ENV", "dev")
    if env not in ("dev", "staging", "production"):
        raise ValueError(f"KR_ENV must be one of dev/staging/production, got {env!r}")

    graph_backend = os.environ.get("KR_GRAPH_BACKEND", "postgres")
    if graph_backend not in ("fixture", "postgres", "neo4j"):
        raise ValueError(
            f"KR_GRAPH_BACKEND must be one of fixture/postgres/neo4j, got {graph_backend!r}"
        )

    standards_backend = os.environ.get("KR_STANDARDS_BACKEND", "postgres")
    if standards_backend not in ("fixture", "postgres"):
        raise ValueError(
            f"KR_STANDARDS_BACKEND must be one of fixture/postgres, got {standards_backend!r}"
        )

    retrieval_backend = os.environ.get("KR_RETRIEVAL_BACKEND", "fixture")
    if retrieval_backend not in ("fixture", "live"):
        raise ValueError(
            f"KR_RETRIEVAL_BACKEND must be one of fixture/live, got {retrieval_backend!r}"
        )

    return Settings(
        env=env,  # type: ignore[arg-type]
        graph_backend=graph_backend,  # type: ignore[arg-type]
        standards_backend=standards_backend,  # type: ignore[arg-type]
        retrieval_backend=retrieval_backend,  # type: ignore[arg-type]
        neo4j_uri=os.environ.get("KR_NEO4J_URI"),
        neo4j_user=os.environ.get("KR_NEO4J_USER"),
        neo4j_password=os.environ.get("KR_NEO4J_PASSWORD"),
        postgres_dsn=os.environ.get("KR_POSTGRES_DSN"),
        retrieval_base_url=os.environ.get("KR_RETRIEVAL_BASE_URL"),
        schema_map_path=os.environ.get("KR_SCHEMA_MAP_PATH"),
        allow_unverified_in_production=_bool_env(
            "KR_ALLOW_UNVERIFIED_IN_PRODUCTION", default=False
        ),
    )
