"""Abstraction over Teammate 1's Postgres standards metadata store.

`get_version_status` reads the one-hop version facts Postgres stores
directly (status, the superseded_by FK, amendments) — it is a literal read,
not chain-walking business logic. Postgres is documented as the single
source of truth (07_Data_Flow_And_Databases.md), so this is authoritative.
`GraphRepository.get_supersession` reads the *derived* Neo4j projection of
the same fact and exists specifically so the direction-sensitive traversal
(decision 1) can be tested and cross-checked independently of Postgres.

`get_product_category` is the single accessor for product category
(decision 4): my certification mapper calls this and never needs to know
whether category is a Postgres property or a Neo4j `BELONGS_TO` edge in the
database it's currently pointed at. The concrete implementation tries the
strategy configured in `schema_map.SchemaMap.category_strategy` first, then
falls back to the other source if that comes back empty.
"""

from __future__ import annotations

from typing import Protocol

from contracts.cluster import VersionStatus
from knowledge_reasoning.ports.types import CertificationRuleRow, StandardMetadata


class StandardsRepository(Protocol):
    def get_metadata(self, is_number: str) -> StandardMetadata | None: ...

    def get_version_status(self, is_number: str) -> VersionStatus: ...

    def get_product_category(self, is_number: str) -> str | None: ...

    def get_certification_rules(self, product_category: str) -> list[CertificationRuleRow]: ...
