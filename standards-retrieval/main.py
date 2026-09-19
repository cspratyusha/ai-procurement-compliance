import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
import numpy as np
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request

from datetime import datetime, timezone
from data.models import Standard
from data_loader import load_corpus, get_standard_by_id
from feedback.schema import FeedbackRequest, InteractionLog
from feedback.logger import append_log, read_logs
from indexing.embed_index import (
    load_index as load_faiss_index,
    get_embedding_model,
    dense_search,
    build_index as build_faiss_index
)
from indexing.bm25_index import (
    load_index as load_bm25_index,
    bm25_search,
    build_index as build_bm25_index
)
from retrieval.hybrid import hybrid_search
from retrieval.rerank import rerank, get_cross_encoder_model
from retrieval.postprocess import apply_supersession_penalty
from ltr.features import build_features, fallback_score
from ltr.train import load_model

# Configure logger
logger = logging.getLogger("standards-retrieval")
logging.basicConfig(level=logging.INFO)

_PROJECT_ROOT = Path(__file__).resolve().parent
_LTR_MODEL_PATH = _PROJECT_ROOT / "models" / "ltr_model.txt"


# --- Pydantic Schema Contracts ---

class StageScores(BaseModel):
    dense: float = Field(..., description="Dense vector similarity score (e5-base-v2).")
    bm25: float = Field(..., description="Raw sparse lexical score (BM25Okapi).")
    cross_encoder: float = Field(..., description="Joint cross-attention logit score (ms-marco-MiniLM-L-6-v2).")
    ltr_or_fallback: float = Field(..., description="Raw model prediction or heuristic fallback blend.")


class StandardResult(BaseModel):
    id: str = Field(..., description="Standard unique identifier (e.g. 'IS-ELEC-001').")
    number: str = Field(..., description="Official BIS designation (e.g. 'IS 694:2010').")
    title: str = Field(..., description="Full canonical standard title.")
    final_score: float = Field(..., description="Relative ranking signal bounded in [0.0, 1.0]. Only comparable within a single response.")
    stage_scores: StageScores = Field(..., description="Scores emitted by individual retrieval and ranking stages.")
    ranker_used: Literal["ltr", "fallback"] = Field(..., description="Ranker algorithm used ('ltr' or 'fallback').")


class RetrieveRequest(BaseModel):
    query: str = Field(..., description="Natural language procurement specification or tender query.")
    top_k: int = Field(default=10, description="Number of top standards to return (capped at 50).")


class RetrieveResponse(BaseModel):
    query: str = Field(..., description="The query string submitted.")
    results: List[StandardResult] = Field(..., description="Ranked list of standard candidates.")


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service operational status.")
    corpus_size: int = Field(..., description="Number of BIS standards loaded in memory.")
    ltr_model_loaded: bool = Field(..., description="Whether a trained LTR LightGBM model is active.")


# --- Lifespan Startup & Resource Management ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preloads all models, vector indices, and sparse dictionaries into memory once on startup."""
    logger.info("[Lifespan] Initializing standards-retrieval service...")

    # 1. Preload corpus
    standards = load_corpus()
    corpus_dict = {s.id: s for s in standards}
    app.state.corpus = corpus_dict
    logger.info(f"[Lifespan] Loaded {len(corpus_dict)} standards into memory.")

    # 2. Preload Dense embedding model & FAISS index
    app.state.embedding_model = get_embedding_model()
    try:
        faiss_index, faiss_ids = load_faiss_index()
    except FileNotFoundError:
        logger.warning("[Lifespan] FAISS index missing. Building from corpus...")
        build_faiss_index(standards)
        faiss_index, faiss_ids = load_faiss_index()
    app.state.faiss_index = faiss_index
    app.state.faiss_ids = faiss_ids
    logger.info(f"[Lifespan] FAISS index loaded ({faiss_index.ntotal} vectors).")

    # 3. Preload BM25 sparse index
    try:
        bm25_index, bm25_ids = load_bm25_index()
    except FileNotFoundError:
        logger.warning("[Lifespan] BM25 index missing. Building from corpus...")
        build_bm25_index(standards)
        bm25_index, bm25_ids = load_bm25_index()
    app.state.bm25_index = bm25_index
    app.state.bm25_ids = bm25_ids
    logger.info("[Lifespan] BM25 index loaded.")

    # 4. Preload Cross-Encoder model
    app.state.cross_encoder = get_cross_encoder_model()
    logger.info("[Lifespan] Cross-Encoder model loaded.")

    # 5. Preload LTR model if present on disk
    if _LTR_MODEL_PATH.exists():
        ltr_booster = load_model(path=_LTR_MODEL_PATH, force_reload=True)
        if ltr_booster is not None:
            app.state.ltr_model = ltr_booster
            logger.info(f"[Lifespan] Live LTR model successfully loaded from '{_LTR_MODEL_PATH}'.")
        else:
            logger.warning(f"[Lifespan] Failed to parse LTR model at '{_LTR_MODEL_PATH}'. Relying on fallback_score().")
            app.state.ltr_model = None
    else:
        logger.warning(f"[Lifespan] LTR model not found at '{_LTR_MODEL_PATH}'. Relying on fallback_score().")
        app.state.ltr_model = None

    yield

    logger.info("[Lifespan] Shutting down standards-retrieval service.")


# --- FastAPI Application ---

app = FastAPI(
    title="BIS Standards Retrieval & Ranking Engine",
    description=(
        "Microservice for retrieving and ranking Indian Standards (BIS) from natural language procurement queries.\n\n"
        "**Scoring Contract:** `final_score` is a relative ranking signal bounded in range [0.0, 1.0]. "
        "It is **only comparable within a single response**, not across separate `/retrieve` calls."
    ),
    version="0.2.0",
    lifespan=lifespan
)


# --- API Endpoints ---

from fastapi.responses import RedirectResponse, Response

@app.get("/", include_in_schema=False)
def root():
    """Redirect root path to interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Empty favicon handler to prevent 404 logs in browser."""
    return Response(content=b"", media_type="image/x-icon")


@app.get("/health", response_model=HealthResponse, summary="Health Check")
def health_check():
    """Returns service health status, corpus size, and LTR ranker status."""
    corpus = getattr(app.state, "corpus", None)
    if corpus is None:
        corpus = {s.id: s for s in load_corpus()}
        app.state.corpus = corpus

    ltr_loaded = getattr(app.state, "ltr_model", None) is not None
    return HealthResponse(
        status="ok",
        corpus_size=len(corpus),
        ltr_model_loaded=ltr_loaded
    )


@app.post(
    "/retrieve",
    response_model=RetrieveResponse,
    summary="Retrieve & Rank Standards (POST Contract)",
    description=(
        "Retrieves top candidate BIS standards using Hybrid Search (Dense + BM25 RRF), "
        "re-scores them via Cross-Encoder and Learning-to-Rank (or fallback), and applies deterministic "
        "business-rule post-processing.\n\n"
        "Returns candidates with `final_score` bounded in [0.0, 1.0] and detailed `stage_scores`."
    )
)
def retrieve_standards_post(body: RetrieveRequest):
    """Primary POST retrieval endpoint integrating Part 2's full ranking pipeline."""
    # 1. Input validation
    query = body.query
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query string must not be empty.")

    if body.top_k < 1:
        raise HTTPException(status_code=400, detail="top_k must be at least 1.")

    # Sane upper-bound cap
    top_k = min(body.top_k, 50)

    # 2. Access preloaded corpus and models
    corpus = getattr(app.state, "corpus", None)
    if corpus is None:
        corpus = {s.id: s for s in load_corpus()}
        app.state.corpus = corpus

    # 3. Step 1: Hybrid Search (Dense + BM25 RRF) -> Top-20 candidates
    hybrid_candidates = hybrid_search(query, top_k=20)
    candidate_ids = [cid for cid, _ in hybrid_candidates]
    if not candidate_ids:
        return RetrieveResponse(query=query, results=[])

    # 4. Step 2: Cross-Encoder Re-Ranking over candidate IDs
    ce_ranked = rerank(query, candidate_ids, corpus=corpus, top_k=len(candidate_ids))
    ce_dict = dict(ce_ranked)

    # Fetch individual dense and bm25 scores for candidate feature extraction
    dense_dict = dict(dense_search(query, top_k=len(candidate_ids) + 10))
    bm25_dict = dict(bm25_search(query, top_k=len(candidate_ids) + 10))

    # Per-query min-max normalization for BM25 feature
    raw_bm25_vals = [bm25_dict.get(cid, 0.0) for cid in candidate_ids]
    min_b = min(raw_bm25_vals) if raw_bm25_vals else 0.0
    max_b = max(raw_bm25_vals) if raw_bm25_vals else 0.0
    range_b = max_b - min_b

    valid_cids = []
    features_list = []
    stage_scores_list = []

    for cid in candidate_ids:
        std = corpus.get(cid)
        if not std:
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
            historical_acceptance_rate=0.0
        )
        features_list.append(fv)
        stage_scores_list.append({
            "dense": round(d_s, 4),
            "bm25": round(raw_b, 4),
            "cross_encoder": round(ce_s, 4)
        })

    if not features_list:
        return RetrieveResponse(query=query, results=[])

    # 5. Step 3: Score via LTR model with graceful degradation to fallback_score()
    ltr_model = getattr(app.state, "ltr_model", None)
    scores = []
    ranker_used: Literal["ltr", "fallback"] = "ltr"

    if ltr_model is not None:
        try:
            X = np.array(features_list, dtype=np.float32)
            raw_preds = ltr_model.predict(X)
            scores = [float(s) for s in raw_preds]
            ranker_used = "ltr"
        except Exception as e:
            logger.error(
                f"[LTR Scoring Error] Model inference failed: {e}. Degrading gracefully to fallback_score().",
                exc_info=True
            )
            scores = [fallback_score(fv) for fv in features_list]
            ranker_used = "fallback"
    else:
        scores = [fallback_score(fv) for fv in features_list]
        ranker_used = "fallback"

    # Attach stage score for LTR or fallback
    for stage_d, score_val in zip(stage_scores_list, scores):
        stage_d["ltr_or_fallback"] = round(float(score_val), 4)

    # 6. Step 4: Deterministic business-rule enforcement & supersession penalty
    candidate_dicts = []
    for cid, score, stage_d in zip(valid_cids, scores, stage_scores_list):
        std = corpus[cid]
        candidate_dicts.append({
            "id": cid,
            "number": std.number,
            "title": std.title,
            "score": score,
            "stage_scores": stage_d,
            "ranker_used": ranker_used
        })

    # apply_supersession_penalty sorts descending, enforces active > superseded,
    # shifts & rescales to strictly [0.0, 1.0], and resolves floor ties
    penalized_results = apply_supersession_penalty(
        candidate_dicts,
        corpus=corpus,
        penalty=2.0,
        top_k=top_k,
        return_metadata=False
    )

    # 7. Step 5: Format response matching contract
    results = [
        StandardResult(
            id=item["id"],
            number=item["number"],
            title=item["title"],
            final_score=float(item["final_score"]),
            stage_scores=StageScores(**item["stage_scores"]),
            ranker_used=ranker_used
        )
        for item in penalized_results[:top_k]
    ]

    return RetrieveResponse(query=query, results=results)


# --- Convenience Endpoints for Compatibility ---

@app.get("/retrieve", response_model=RetrieveResponse, summary="Retrieve & Rank Standards (GET Alias)")
def retrieve_standards_get(query: str, top_k: int = 10):
    """GET alias for /retrieve enabling query parameter testing in browser and backward compatibility."""
    return retrieve_standards_post(RetrieveRequest(query=query, top_k=top_k))


@app.get("/search", response_model=RetrieveResponse, summary="Search Standards (GET Alias)")
def search_standards_get(query: str, top_k: int = 10):
    """Alias for /retrieve providing backwards compatibility."""
    return retrieve_standards_post(RetrieveRequest(query=query, top_k=top_k))


@app.get("/standards", response_model=List[Standard], summary="List Standards")
def list_standards(category: Optional[str] = None):
    """List all available standards in the corpus, optionally filtered by category."""
    corpus = getattr(app.state, "corpus", None)
    if corpus is None:
        standards = load_corpus()
    else:
        standards = list(corpus.values())

    if category:
        return [s for s in standards if s.category.lower() == category.lower()]
    return standards


@app.get("/standards/{standard_id}", response_model=Standard, summary="Get Standard by ID")
def get_standard(standard_id: str):
    """Retrieve a single standard by its identifier."""
    standard = get_standard_by_id(standard_id)
    if not standard:
        raise HTTPException(status_code=404, detail=f"Standard with ID '{standard_id}' not found.")
    return standard


# --- Feedback & Interaction Logging Endpoints (Part 6) ---

@app.post(
    "/feedback",
    summary="Record User Feedback / Interaction Log",
    description="Captures user selection, rejection, or manual correction feedback for /retrieve recommendations."
)
def record_feedback(body: FeedbackRequest):
    """Logs an official's interaction with retrieval results to append-only JSONL storage.
    
    Server sets the current ISO timestamp and tags source='live'.
    """
    interaction = InteractionLog(
        query=body.query,
        candidates_shown=body.candidates_shown,
        chosen_id=body.chosen_id,
        action=body.action,
        corrected_id=body.corrected_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="live"
    )
    append_log(interaction)
    return {"status": "logged"}


@app.get(
    "/logs",
    response_model=List[Dict[str, Any]],
    summary="Get Recent Interaction Logs (Dev/Demo Endpoint)"
)
def get_recent_logs(limit: int = 50):
    """Returns the last N lines from the JSONL file, most recent first.
    
    NOTE: This is a dev/demo convenience endpoint, not meant for production use.
    It allows developers and demo UI tools to inspect captured feedback stream in real time.
    """
    safe_limit = max(1, min(limit, 500))
    return read_logs(limit=safe_limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

