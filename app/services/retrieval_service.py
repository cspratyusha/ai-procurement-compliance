import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import numpy as np

from app.models.postgres_models import (
    StandardModel,
    ProductCategoryModel,
    AmendmentModel,
    CertificationRuleModel,
    CrossReferenceModel,
)

# Import the canonical retrieval pipeline from `standards-retrieval/`.
#
# That directory previously existed as a second copy vendored under
# `app/services/standards_retrieval/`, which drifted from the original.
# The copy has been removed; `standards-retrieval/` is now the single
# source of truth. Because its directory name contains a hyphen it is not
# a valid package name, and its modules import each other by bare name
# (`from data_loader import ...`), so it is added to sys.path rather than
# imported as a package.
from app.services.standards_retrieval_path import ensure_retrieval_on_path

ensure_retrieval_on_path()

from data_loader import load_corpus, get_standard_by_id  # noqa: E402
from indexing.embed_index import dense_search  # noqa: E402
from indexing.bm25_index import bm25_search  # noqa: E402
from retrieval.hybrid import hybrid_search as raw_hybrid_search  # noqa: E402
from retrieval.rerank import rerank  # noqa: E402
from retrieval.postprocess import apply_supersession_penalty  # noqa: E402
from ltr.features import build_features, fallback_score  # noqa: E402
from ltr.train import load_model  # noqa: E402

logger = logging.getLogger(__name__)


class RetrievalService:
    @staticmethod
    def vector_search(
        query: str,
        top_k: int = 10,
        category_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Dense semantic search using intfloat/e5-base-v2 and FAISS vector index."""
        corpus = {s.id: s for s in load_corpus()}
        hits = dense_search(query=query, top_k=top_k * 2)

        candidates = []
        for std_id, score in hits:
            std = corpus.get(std_id)
            if not std:
                continue
            if category_id and std.category != category_id:
                continue

            candidates.append({
                "standard_id": std.id,
                "standard_number": std.number,
                "title": std.title,
                "category_id": std.category,
                "status": std.status,
                "dense_score": round(float(score), 4),
                "document_preview": f"{std.title}. {std.scope[:150]}...",
            })
            if len(candidates) >= top_k:
                break

        if db and candidates:
            RetrievalService._enrich_with_db(candidates, db)

        return candidates

    @staticmethod
    def keyword_search(
        query: str,
        top_k: int = 10,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Sparse keyword search using BM25Okapi over standard numbers, titles, scopes, and keywords."""
        corpus = {s.id: s for s in load_corpus()}
        hits = bm25_search(query=query, top_k=top_k * 2)

        candidates = []
        max_score = hits[0][1] if hits else 1.0
        for std_id, score in hits:
            std = corpus.get(std_id)
            if not std:
                continue

            norm_score = (score / max_score) if max_score > 0 else 0.0
            candidates.append({
                "standard_id": std.id,
                "standard_number": std.number,
                "title": std.title,
                "scope_text": std.scope,
                "bm25_score": round(float(norm_score), 4),
                "raw_bm25_score": round(float(score), 4),
            })
            if len(candidates) >= top_k:
                break

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
        """Stage 1 & 2 Full AI Retrieval Pipeline:
        1. Hybrid Dense (e5-base-v2 FAISS) + Sparse (BM25Okapi) RRF retrieval
        2. Cross-Encoder joint semantic re-ranking (ms-marco-MiniLM-L-6-v2)
        3. Learning-to-Rank (LambdaMART LightGBM / fallback scoring)
        4. Deterministic supersession penalty & tie-breaking post-processing
        5. PostgreSQL metadata enrichment (annotations applied post-ranking; preserves ordering)
        """
        if not query or not query.strip():
            return []

        corpus = {s.id: s for s in load_corpus()}

        # 1. First-Stage: Hybrid Search (Dense + BM25 RRF)
        candidate_pool_k = max(20, top_k * 2)
        hybrid_candidates = raw_hybrid_search(query, top_k=candidate_pool_k)
        candidate_ids = [cid for cid, _ in hybrid_candidates]
        if not candidate_ids:
            return []

        # 2. Second-Stage: Cross-Encoder Re-Ranking
        ce_ranked = rerank(query=query, candidate_ids=candidate_ids, corpus=corpus, top_k=len(candidate_ids))
        ce_dict = dict(ce_ranked)

        dense_dict = dict(dense_search(query, top_k=len(candidate_ids) + 10))
        bm25_dict = dict(bm25_search(query, top_k=len(candidate_ids) + 10))

        raw_bm25_vals = [bm25_dict.get(cid, 0.0) for cid in candidate_ids]
        min_b = min(raw_bm25_vals) if raw_bm25_vals else 0.0
        max_b = max(raw_bm25_vals) if raw_bm25_vals else 0.0
        range_b = max_b - min_b

        valid_cids = []
        features_list = []
        raw_candidates_meta = []

        for cid in candidate_ids:
            std = corpus.get(cid)
            if not std:
                continue
            if category_id and std.category != category_id:
                continue

            valid_cids.append(cid)
            d_s = float(dense_dict.get(cid, 0.0))
            raw_b = float(bm25_dict.get(cid, 0.0))
            b_norm = (raw_b - min_b) / (range_b + 1e-6) if range_b > 1e-6 else 0.5
            ce_s = float(ce_dict.get(cid, -10.0))

            fv = build_features(
                query=query,
                candidate_id=cid,
                standard=std,
                dense_score=d_s,
                bm25_score_normalized=b_norm,
                cross_encoder_score=ce_s,
                historical_acceptance_rate=0.0,
            )
            features_list.append(fv)
            raw_candidates_meta.append({
                "dense": d_s,
                "bm25": raw_b,
                "cross_encoder": ce_s,
                "standard": std,
            })

        if not valid_cids:
            return []

        # 3. Third-Stage: LTR Prediction or Fallback
        booster = load_model()
        if booster is not None:
            X = np.array(features_list, dtype=np.float32)
            ltr_scores = booster.predict(X)
            ranker_used = "ltr"
        else:
            ltr_scores = [fallback_score(fv) for fv in features_list]
            ranker_used = "fallback"

        unadjusted = []
        for cid, meta, score in zip(valid_cids, raw_candidates_meta, ltr_scores):
            std = meta["standard"]
            unadjusted.append({
                "id": cid,
                "standard_id": cid,
                "standard_number": std.number,
                "title": std.title,
                "category_id": std.category,
                "status": std.status,
                "dense_score": round(meta["dense"], 4),
                "bm25_score": round(meta["bm25"], 4),
                "cross_encoder_score": round(meta["cross_encoder"], 4),
                "ltr_score": round(float(score), 4),
                "final_score": float(score),
                "ranker_used": ranker_used,
            })

        # 4. Fourth-Stage: Deterministic Supersession Penalty Post-Processing
        penalized_results = apply_supersession_penalty(
            unadjusted, corpus=corpus, penalty=2.0, top_k=top_k, return_metadata=False
        )

        top_candidates = penalized_results[:top_k]

        # 5. Enrichment: runs AFTER ranking, adding PG metadata without re-ordering
        if db and top_candidates:
            RetrievalService._enrich_with_db(top_candidates, db)

        return top_candidates

    @staticmethod
    def _enrich_with_db(candidates: List[Dict[str, Any]], db: Session):
        """Enrich candidates in-place with latest versions, amendments count, and mandatory certification flags.
        Preserves ranking order strictly (annotates in-place).
        """
        std_numbers = [c.get("standard_number") or c.get("number") for c in candidates if c.get("standard_number") or c.get("number")]
        if not std_numbers:
            return

        try:
            stds = (
                db.query(StandardModel)
                .filter(StandardModel.standard_number.in_(std_numbers))
                .all()
            )
            std_by_num = {s.standard_number: s for s in stds}

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
                num = c.get("standard_number") or c.get("number")
                std = std_by_num.get(num)
                if std:
                    c["current_version"] = getattr(std, "current_version", c.get("version"))
                    c["status"] = getattr(std, "status", c.get("status"))
                    c["scope_text"] = getattr(std, "scope_text", c.get("scope"))
                    c["abstract"] = getattr(std, "abstract", "")
                    c["year_published"] = getattr(std, "year_published", 0)
                    c["category_id"] = getattr(std, "category_id", c.get("category_id"))
                    c["amendments_count"] = len(std.amendments) if hasattr(std, "amendments") and std.amendments else 0
                    c["certification_rules"] = cat_rules_map.get(getattr(std, "category_id", ""), [])
        except Exception as exc:
            logger.warning(f"DB enrichment skipped due to exception: {exc}")

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
            for a in getattr(std, "amendments", [])
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
