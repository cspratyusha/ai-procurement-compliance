import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.db.vector_store import vector_store_client
from app.db.bm25_index import bm25_index_client
from app.db.neo4j_client import neo4j_client
from app.services.embedding_service import embedding_service
from app.models.postgres_models import (
    StandardModel,
    ProductCategoryModel,
    AmendmentModel,
    CertificationRuleModel,
    CrossReferenceModel,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    @staticmethod
    def vector_search(
        query: str,
        top_k: int = 10,
        category_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Dense semantic search using sentence-transformer embeddings and ChromaDB vector store.
        """
        query_vec = embedding_service.embed_query(query)
        where_filter = {"category_id": category_id} if category_id else None

        results = vector_store_client.query(
            query_embedding=query_vec,
            n_results=top_k,
            where_filter=where_filter,
        )

        candidates = []
        if results and "ids" in results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            metadatas = results["metadatas"][0] if "metadatas" in results and results["metadatas"] else []
            distances = results["distances"][0] if "distances" in results and results["distances"] else []
            documents = results["documents"][0] if "documents" in results and results["documents"] else []

            for idx, std_number in enumerate(ids):
                meta = metadatas[idx] if idx < len(metadatas) else {}
                dist = distances[idx] if idx < len(distances) else 1.0
                doc = documents[idx] if idx < len(documents) else ""

                # Cosine distance to similarity conversion
                similarity = max(0.0, 1.0 - float(dist))

                candidates.append({
                    "standard_number": std_number,
                    "title": meta.get("title", ""),
                    "category_id": meta.get("category_id", ""),
                    "sector": meta.get("sector", ""),
                    "status": meta.get("status", "active"),
                    "year_published": meta.get("year_published", 0),
                    "dense_score": round(similarity, 4),
                    "document_preview": doc[:200] if doc else "",
                })

        # Enrich with PostgreSQL metadata if DB session provided
        if db and candidates:
            RetrievalService._enrich_with_db(candidates, db)

        return candidates

    @staticmethod
    def keyword_search(
        query: str,
        top_k: int = 10,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sparse keyword search using BM25 index over standard numbers, titles, and scopes.
        """
        hits = bm25_index_client.search(query=query, top_k=top_k)
        candidates = []

        max_score = hits[0][1] if hits else 1.0
        for std_number, score, doc in hits:
            norm_score = (score / max_score) if max_score > 0 else 0.0
            candidates.append({
                "standard_number": std_number,
                "title": doc.get("title", ""),
                "scope_text": doc.get("scope_text", ""),
                "bm25_score": round(float(norm_score), 4),
                "raw_bm25_score": round(float(score), 4),
            })

        if db and candidates:
            RetrievalService._enrich_with_db(candidates, db)

        return candidates

    @staticmethod
    def hybrid_search(
        query: str,
        top_k: int = 10,
        category_id: Optional[str] = None,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Stage 1 & 2 AI Pipeline: Hybrid retrieval combining Dense Vector Search + BM25 Sparse Search
        with reciprocal/linear score fusion and PostgreSQL metadata enrichment.
        """
        # Fetch dense candidates
        dense_results = RetrievalService.vector_search(
            query=query, top_k=top_k * 2, category_id=category_id
        )
        dense_map = {c["standard_number"]: c for c in dense_results}

        # Fetch sparse candidates
        sparse_results = RetrievalService.keyword_search(
            query=query, top_k=top_k * 2
        )
        sparse_map = {c["standard_number"]: c for c in sparse_results}

        # Candidate fusion
        all_std_numbers = set(dense_map.keys()) | set(sparse_map.keys())
        merged_candidates = []

        for std_num in all_std_numbers:
            dense_item = dense_map.get(std_num)
            sparse_item = sparse_map.get(std_num)

            d_score = dense_item["dense_score"] if dense_item else 0.0
            s_score = sparse_item["bm25_score"] if sparse_item else 0.0

            hybrid_score = round((dense_weight * d_score) + (sparse_weight * s_score), 4)

            title = (
                (dense_item.get("title") if dense_item else None)
                or (sparse_item.get("title") if sparse_item else "")
            )
            category = (dense_item.get("category_id") if dense_item else "") or ""
            status = (dense_item.get("status") if dense_item else "active") or "active"
            sector = (dense_item.get("sector") if dense_item else "") or ""

            merged_candidates.append({
                "standard_number": std_num,
                "title": title,
                "category_id": category,
                "sector": sector,
                "status": status,
                "dense_score": d_score,
                "bm25_score": s_score,
                "hybrid_score": hybrid_score,
            })

        merged_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        top_candidates = merged_candidates[:top_k]

        if db and top_candidates:
            RetrievalService._enrich_with_db(top_candidates, db)

        return top_candidates

    @staticmethod
    def _enrich_with_db(candidates: List[Dict[str, Any]], db: Session):
        """Enrich candidates with latest versions, amendments count, and mandatory certification flags."""
        std_numbers = [c["standard_number"] for c in candidates]
        stds = (
            db.query(StandardModel)
            .filter(StandardModel.standard_number.in_(std_numbers))
            .all()
        )
        std_by_num = {s.standard_number: s for s in stds}

        # Check certification rules
        categories = {s.category_id for s in stds if s.category_id}
        cert_rules = (
            db.query(CertificationRuleModel)
            .filter(CertificationRuleModel.category_id.in_(categories))
            .all()
        ) if categories else []

        cat_rules_map = {}
        for r in cert_rules:
            cat_rules_map.setdefault(r.category_id, []).append({
                "scheme_type": r.scheme_type,
                "mandatory": r.mandatory_flag,
            })

        for c in candidates:
            std = std_by_num.get(c["standard_number"])
            if std:
                c["standard_id"] = std.standard_id
                c["current_version"] = std.current_version
                c["status"] = std.status
                c["scope_text"] = std.scope_text
                c["abstract"] = std.abstract
                c["year_published"] = std.year_published
                c["category_id"] = std.category_id
                c["amendments_count"] = len(std.amendments) if std.amendments else 0
                c["certification_rules"] = cat_rules_map.get(std.category_id, [])

    @staticmethod
    def get_standard_detail(standard_number: str, db: Session) -> Optional[Dict[str, Any]]:
        """Fetch full standard details, amendments, certification rules, and graph relationships."""
        std = (
            db.query(StandardModel)
            .filter(StandardModel.standard_number == standard_number)
            .first()
        )
        if not std:
            return None

        amendments = [
            {
                "amendment_number": a.amendment_number,
                "date_issued": a.date_issued,
                "change_summary": a.change_summary,
            }
            for a in std.amendments
        ]

        rules = (
            db.query(CertificationRuleModel)
            .filter(
                (CertificationRuleModel.category_id == std.category_id)
                | (CertificationRuleModel.standard_number == std.standard_number)
            )
            .all()
        )
        cert_info = [
            {
                "scheme_type": r.scheme_type,
                "mandatory": r.mandatory_flag,
                "description": r.description,
            }
            for r in rules
        ]

        # Cross references from PostgreSQL
        xrefs = (
            db.query(CrossReferenceModel)
            .filter(
                (CrossReferenceModel.source_standard_number == std.standard_number)
                | (CrossReferenceModel.target_standard_number == std.standard_number)
            )
            .all()
        )
        relationships = [
            {
                "source": x.source_standard_number,
                "target": x.target_standard_number,
                "relationship_type": x.relationship_type,
                "description": x.description,
            }
            for x in xrefs
        ]

        return {
            "standard_id": std.standard_id,
            "standard_number": std.standard_number,
            "title": std.title,
            "scope_text": std.scope_text,
            "abstract": std.abstract,
            "year_published": std.year_published,
            "current_version": std.current_version,
            "status": std.status,
            "category_id": std.category_id,
            "category_name": std.category.name if std.category else None,
            "sector": std.sector,
            "amendments": amendments,
            "certification_rules": cert_info,
            "relationships": relationships,
        }
