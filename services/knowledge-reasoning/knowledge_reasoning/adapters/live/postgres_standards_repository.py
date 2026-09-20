"""`StandardsRepository` backed by a real Postgres instance.

Every query it runs comes from `db/queries.py`. A `GraphRepository` is
injected for two things: the category-fallback path (decision 4), and
amendments modelled as `AMENDED_BY`-linked `Standard` rows rather than
`amendments` table rows — confirmed the real, populated representation
during integration (Stage A/B: the `amendments` table exists but is never
written by Teammate 1's actual ingestion path; the one real amendment in
the demo corpus, "IS 4984:2016/Amd 1", is a separate Standard node linked
by `AMENDED_BY`). `get_version_status` reads both sources and unions them,
so a populated `amendments` table (if Teammate 1 ever starts writing to
it) is picked up automatically without a code change.

`verified` is derived from `standards.source_url`/`source_checked_at` —
neither Teammate 1 schema has an actual `verified` column (confirmed
Stage A/B), but `data/schema.sql` has these two, and they're the closest
real signal to "do we know where this came from and when we last looked".

Rule: `source_checked_at` present and within `_RECENT_CHECK_WINDOW_DAYS`
-> verified; `source_checked_at` present but stale -> not verified,
reason "stale_check"; `source_url` present with no check timestamp at all
-> not verified, reason "unchecked_source"; neither -> not verified,
reason "no_provenance". ("stale_check" isn't one of the three cases this
was specified against — it's the natural interpretation of "recent"
implying an expiry, added rather than left undefined.)

CAVEAT, real and not decorative: Teammate 1's real `source_checked_at`
column is `NOT NULL DEFAULT NOW()` (confirmed Stage A/B, `data/schema.sql`)
and their ingestion never writes `source_url` at all — so today this
column means "when this database row was last written", not "when
someone checked the standard is still current against BIS". Every real
row will currently derive as `verified=True` shortly after any ingestion
run, regardless of whether anyone actually re-checked anything. This is
the best signal available today and correctly derived from it, but the
underlying signal doesn't yet mean what this derivation needs it to mean
— flagged in INTEGRATION.md as a real ask, not silently trusted here.

Opens one connection per call rather than pooling — correct and simple;
connection pooling is a performance concern, and at this corpus size
(tens of standards) it isn't one yet.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from contracts.cluster import Amendment, EdgeType, VersionStatus
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db import queries
from knowledge_reasoning.ports.graph_repository import GraphRepository
from knowledge_reasoning.ports.types import CertificationRuleRow, StandardMetadata

_RECENT_CHECK_WINDOW_DAYS = 365


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _derive_verification(
    source_url: str | None, source_checked_at: datetime | None
) -> tuple[bool, str | None]:
    """See module docstring for the rule and its caveat."""
    if source_checked_at is not None:
        checked_at = source_checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - checked_at
        if age <= timedelta(days=_RECENT_CHECK_WINDOW_DAYS):
            return True, None
        return False, "stale_check"
    if source_url:
        return False, "unchecked_source"
    return False, "no_provenance"


class PostgresStandardsRepository:
    def __init__(self, dsn: str, schema: SchemaMap, graph_repository: GraphRepository) -> None:
        self._dsn = dsn
        self._schema = schema
        self._graph_repository = graph_repository
        self._standard_query = queries.build_get_standard_query(schema)
        self._version_row_query = queries.build_get_version_row_query(schema)
        self._amendments_query = queries.build_get_amendments_query(schema)
        self._category_query = queries.build_get_product_category_query(schema)
        self._cert_rules_query = queries.build_get_certification_rules_query(schema)

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def get_metadata(self, is_number: str) -> StandardMetadata | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._standard_query, {"is_number": is_number})
            row = cur.fetchone()
        if row is None:
            return None
        verified, _reason = _derive_verification(row["source_url"], row["source_checked_at"])
        return StandardMetadata(
            is_number=row["is_number"],
            title=row["title"],
            scope_text=row["scope_text"],
            status=row["status"],
            edition=row["edition"],
            category=row["category"],
            last_amended=row["last_amended"],
            verified=verified,
        )

    def _amendments_from_graph(self, is_number: str) -> list[Amendment]:
        """Amendments modelled as AMENDED_BY-linked Standard rows — see
        module docstring. A missing amendment_number/date is not silently
        dropped: real Teammate-1 data always has both (last_amended is
        enforced non-empty at ingestion), so an absence here means the
        graph and metadata disagree and is worth surfacing, not hiding."""
        amendments: list[Amendment] = []
        for path in self._graph_repository.expand([is_number], max_hops=1).paths:
            if path.role != EdgeType.AMENDED_BY:
                continue
            child = self.get_metadata(path.target)
            if child is None:
                continue
            date_issued = _parse_iso_date(child.last_amended)
            if date_issued is None:
                continue
            amendments.append(
                Amendment(
                    # Real amendment-standards don't carry a clean integer
                    # amendment number (e.g. "IS 4984:2016/Amd 1", edition
                    # "Amendment 1, 2022") — the edition string is the
                    # closest honest label available.
                    amendment_number=child.edition or child.is_number,
                    date_issued=date_issued,
                    change_summary=child.scope_text or child.title,
                )
            )
        return amendments

    def get_version_status(self, is_number: str) -> VersionStatus:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._version_row_query, {"is_number": is_number})
            row = cur.fetchone()
            cur.execute(self._amendments_query, {"is_number": is_number})
            amendment_rows = cur.fetchall()

        table_amendments = [
            Amendment(
                amendment_number=a["amendment_number"],
                date_issued=a["date_issued"],
                change_summary=a["change_summary"],
            )
            for a in amendment_rows
        ]
        graph_amendments = self._amendments_from_graph(is_number)

        # Union, deduped on (amendment_number, date_issued) in case the same
        # amendment is ever represented both ways.
        seen: set[tuple[str, date]] = set()
        amendments: list[Amendment] = []
        for a in table_amendments + graph_amendments:
            key = (a.amendment_number, a.date_issued)
            if key in seen:
                continue
            seen.add(key)
            amendments.append(a)
        amendments.sort(key=lambda a: a.date_issued)

        status = row["status"] if row is not None else "active"
        superseded_by = row["superseded_by"] if row is not None else None
        # One-hop only — see FixtureStandardsRepository.get_version_status.
        current_edition = superseded_by or is_number
        data_verified, verification_reason = (
            _derive_verification(row["source_url"], row["source_checked_at"])
            if row is not None
            else (False, "no_provenance")
        )

        return VersionStatus(
            current_edition=current_edition,
            is_current=(status == "active"),
            superseded_by=superseded_by,
            withdrawn=(status == "withdrawn"),
            amendments=amendments,
            last_verified=datetime.now(timezone.utc),
            data_verified=data_verified,
            verification_reason=verification_reason,
        )

    def get_product_category(self, is_number: str) -> str | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._category_query, {"is_number": is_number})
            row = cur.fetchone()
        property_value = row["category"] if row is not None else None
        edge_value = self._graph_repository.get_category_via_edge(is_number)

        if self._schema.category_strategy == "property":
            return property_value if property_value is not None else edge_value
        return edge_value if edge_value is not None else property_value

    def get_certification_rules(self, product_category: str) -> list[CertificationRuleRow]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._cert_rules_query, {"category": product_category})
            rows = cur.fetchall()
        return [
            CertificationRuleRow(
                product_category=r["category"],
                # None of these exist in Teammate 1's real schema — defaulted
                # in code, never fabricated. See INTEGRATION.md,
                # "certification traceability".
                standard_is_number=None,
                scheme=r["scheme"],
                mandatory=bool(r["mandatory"]),
                required_evidence=[],
                notification_reference=None,
                effective_date=None,
                source_url=None,
                verified=False,
            )
            for r in rows
        ]
