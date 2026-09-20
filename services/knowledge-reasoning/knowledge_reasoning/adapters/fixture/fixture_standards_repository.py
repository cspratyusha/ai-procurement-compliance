"""In-memory `StandardsRepository` backed by fixtures/*.yaml.

Depends on a `FixtureGraphRepository` for the one-hop supersession fact and
the category `belongs_to` edge fallback (decision 4) — in a live deployment
these two facts come from different databases (Neo4j vs Postgres), but here
they're both read from the same parsed fixture, which is fine: the point of
the fixture-backed adapters is interface-shape fidelity, not simulating two
physically separate stores.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from contracts.cluster import Amendment, EdgeType, VersionStatus
from knowledge_reasoning.adapters.fixture.fixture_data import (
    DEFAULT_FIXTURES_ROOT,
    FixtureDomain,
    load_all_fixture_domains,
)
from knowledge_reasoning.adapters.fixture.fixture_graph_repository import (
    FixtureGraphRepository,
)
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.ports.types import CertificationRuleRow, StandardMetadata


class FixtureStandardsRepository:
    def __init__(
        self,
        schema: SchemaMap,
        graph_repository: FixtureGraphRepository,
        domains: list[FixtureDomain] | None = None,
    ) -> None:
        self._schema = schema
        self._graph_repository = graph_repository
        self._domains = domains or load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)
        self._nodes_by_number = {
            node.is_number: node for domain in self._domains for node in domain.nodes
        }
        self._amendments_by_number: dict[str, list] = {}
        for domain in self._domains:
            for amendment in domain.amendments:
                self._amendments_by_number.setdefault(amendment.is_number, []).append(amendment)
        self._cert_rules_by_category: dict[str, list] = {}
        for domain in self._domains:
            for rule in domain.certification_rules:
                self._cert_rules_by_category.setdefault(rule.product_category, []).append(rule)
        # Captured once, not per-call: "when this fixture snapshot was
        # loaded" is a more honest signal than a fresh `now()` on every read.
        self._loaded_at = datetime.now(timezone.utc)

    def get_metadata(self, is_number: str) -> StandardMetadata | None:
        node = self._nodes_by_number.get(is_number)
        if node is None:
            return None
        return StandardMetadata(
            is_number=node.is_number,
            title=node.title,
            scope_text=node.scope_text,
            status=node.status,
            edition=node.edition,
            category=node.category,
            verified=node.verified,
            last_amended=node.last_amended,
        )

    def _amendments_from_graph(self, is_number: str) -> list[Amendment]:
        """Mirrors PostgresStandardsRepository's AMENDED_BY-edge union, for
        fixture/live parity — see that class's docstring."""
        amendments: list[Amendment] = []
        for path in self._graph_repository.expand([is_number], max_hops=1).paths:
            if path.role != EdgeType.AMENDED_BY:
                continue
            child = self.get_metadata(path.target)
            if child is None or not child.last_amended:
                continue
            try:
                date_issued = date.fromisoformat(child.last_amended)
            except ValueError:
                continue
            amendments.append(
                Amendment(
                    amendment_number=child.edition or child.is_number,
                    date_issued=date_issued,
                    change_summary=child.scope_text or child.title,
                )
            )
        return amendments

    def get_version_status(self, is_number: str) -> VersionStatus:
        node = self._nodes_by_number.get(is_number)
        supersession = self._graph_repository.get_supersession(is_number)
        table_amendments = [
            Amendment(
                amendment_number=a.amendment_number,
                date_issued=a.date_issued,
                change_summary=a.change_summary,
            )
            for a in self._amendments_by_number.get(is_number, [])
        ]
        graph_amendments = self._amendments_from_graph(is_number)
        seen: set[tuple[str, date]] = set()
        amendments: list[Amendment] = []
        for a in table_amendments + graph_amendments:
            key = (a.amendment_number, a.date_issued)
            if key in seen:
                continue
            seen.add(key)
            amendments.append(a)
        amendments.sort(key=lambda a: a.date_issued)

        status = node.status if node is not None else "active"
        # One-hop only: the ultimate current edition after a multi-link
        # supersession chain is Phase 3 business logic built on this
        # primitive, not resolved here.
        current_edition = supersession.superseded_by or is_number
        return VersionStatus(
            current_edition=current_edition,
            is_current=(status == "active"),
            superseded_by=supersession.superseded_by,
            withdrawn=(status == "withdrawn"),
            amendments=amendments,
            last_verified=self._loaded_at,
            data_verified=(node.verified if node is not None else False),
            # Fixture data is placeholder by construction (fixtures/README.md)
            # — every record is verified:false, so this is always set. A
            # distinct reason from the Postgres derivation's own strings
            # (no_provenance/unchecked_source/stale_check): those describe
            # "we don't know" about real data, this describes "this isn't
            # real data at all".
            verification_reason=(
                None if (node is not None and node.verified) else "unverified_fixture_data"
            ),
        )

    def get_product_category(self, is_number: str) -> str | None:
        node = self._nodes_by_number.get(is_number)
        property_value = node.category if node is not None else None
        edge_value = self._graph_repository.get_category_via_edge(is_number)

        if self._schema.category_strategy == "property":
            return property_value if property_value is not None else edge_value
        return edge_value if edge_value is not None else property_value

    def get_certification_rules(self, product_category: str) -> list[CertificationRuleRow]:
        return [
            CertificationRuleRow(
                product_category=r.product_category,
                standard_is_number=r.standard_is_number,
                scheme=r.scheme,
                mandatory=r.mandatory,
                required_evidence=r.required_evidence,
                notification_reference=r.notification_reference,
                effective_date=r.effective_date,
                source_url=r.source_url,
                verified=r.verified,
            )
            for r in self._cert_rules_by_category.get(product_category, [])
        ]
