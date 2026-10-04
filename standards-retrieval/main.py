import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
import numpy as np
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, timezone
import accounts
import accounts_api
import alerts as alerts_data
import audit as audit_engine
import editions
import expansion
import similar
import certification
import extraction
import translation
import relationships as relationships_data
import explanation as explanation_engine
import amendments as amendments_data
import bis_refresh
from data.models import Standard
from data_loader import load_corpus, get_standard_by_id
from feedback.schema import FeedbackRequest, InteractionLog
from feedback.logger import append_log, read_logs
from feedback.query_log import append_query
from feedback.stats import compute_stats
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
# Models are per-corpus: a ranker's labels reference a specific corpus's ids,
# so serving the mock-corpus model over the canonical corpus would rank
# against standards that are no longer at those ids. ltr/train.py writes to
# the matching directory.
from ltr.train import _models_dir  # noqa: E402

_LTR_MODEL_PATH = _models_dir() / "ltr_model.txt"


# --- Pydantic Schema Contracts ---

class CertificationInfo(BaseModel):
    """Whether a standard's product category legally requires BIS certification.

    Read from BIS's lists of products under compulsory certification and its
    hallmarking order. `status` keeps materially different answers apart, and
    the UI must too: an obligation in force, one named but deferred, a scheme
    that exists but is voluntary, a checked absence, a listed sibling part, not
    on the lists, and 'not_verified' (lists unavailable).
    """
    scheme: Literal["ISI", "CRS", "Scheme X", "Hallmark", "none", "related", "not_listed", "not_verified"] = Field(
        ..., description="Certification scheme, or what kind of non-obligation this is."
    )
    status: Literal["in_force", "deferred", "voluntary", "checked_none", "related_listed", "not_listed", "not_verified"] = Field(
        default="not_verified", description="Whether an obligation is in force, deferred, or absent, and how that is known."
    )
    mandatory: bool = Field(..., description="True only for an obligation in force.")
    explanation: str = Field(..., description="Plain-language guidance for a procurement official.")
    qco: Optional[str] = Field(default=None, description="Governing Quality Control Order.")
    gazette: Optional[str] = Field(default=None, description="Gazette notification number and date.")
    qco_url: Optional[str] = Field(default=None, description="Link to the order.")
    product: Optional[str] = Field(default=None, description="Products as listed by BIS.")
    products: List[str] = Field(default_factory=list, description="Products as listed by BIS.")
    listed_as: Optional[str] = Field(default=None, description="The IS number as BIS lists it.")
    related: List[str] = Field(default_factory=list, description="Listed standards this one relates to, for related_listed.")
    source: Optional[str] = Field(default=None, description="The BIS list the answer was read from.")


class TranslationInfo(BaseModel):
    """What happened to a non-English query before it was searched.

    Surfaced so the user can check the machine translation. A wrong
    translation silently producing wrong standards is the failure to avoid.
    """
    original: str = Field(..., description="Query exactly as the user typed it.")
    translated_text: str = Field(..., description="English text actually searched.")
    detected_language: str = Field(..., description="Language code used.")
    language_name: str = Field(..., description="Human-readable language name.")
    translated: bool = Field(..., description="False when translation was skipped or failed.")
    error: Optional[str] = Field(default=None, description="Why translation did not run, when applicable.")


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

    # Presentation fields. The UI needs these to render a result card, and
    # fetching them per-result would mean N extra round-trips.
    scope: str = Field(default="", description="Formal scope statement of the standard.")
    category: str = Field(default="", description="Sector classification, e.g. 'electrical_cables'.")
    status: str = Field(default="active", description="'active' or 'superseded'.")
    version: str = Field(default="", description="Edition or revision string.")
    last_amended: str = Field(default="", description="Date of latest amendment, YYYY-MM-DD, or empty.")
    superseded_by: Optional[str] = Field(default=None, description="Id of the active replacement, when this entry was penalised as superseded.")
    certification: "CertificationInfo" = Field(..., description="Mandatory BIS certification status for this standard.")
    data_warning: Optional[str] = Field(default=None, description="Known problem with this corpus entry, e.g. an edition that was never published.")
    replaced_by: Optional[str] = Field(
        default=None,
        description="IS number of the edition in force, for a superseded edition, following BIS's replacement chain. May be an edition the corpus does not hold.",
    )
    withdrawn: bool = Field(default=False, description="BIS lists this edition as withdrawn.")
    citation: str = Field(
        default="",
        description=(
            "How to cite this standard in a tender, including its amendments where "
            "they have been researched. Falls back to the bare IS number otherwise."
        ),
    )
    amendment_count: Optional[int] = Field(
        default=None,
        description="Number of published amendments in force, or null when not researched.",
    )
    explanation: Optional[str] = Field(
        default=None,
        description=(
            "One-sentence plain-language reason this standard matched, generated by a "
            "local LLM. Absent when explanations are disabled or unavailable. Never "
            "affects ranking, certification or supersession."
        ),
    )


class RetrieveRequest(BaseModel):
    query: str = Field(..., max_length=4000, description="Natural language procurement specification or tender query.")
    top_k: int = Field(default=10, description="Number of top standards to return (capped at 50).")
    language: Optional[str] = Field(
        default=None,
        description=(
            "Language of the query: 'en', 'hi', 'ta', 'bn', 'mr', 'te', 'gu', 'kn', 'ml', 'pa', "
            "'or', 'ur' or 'as' (GET /languages lists them). Omit or pass 'auto' to detect it "
            "from the script."
        ),
    )
    explain: bool = Field(
        default=False,
        description=(
            "Ask a local LLM for a one-sentence reason per result. Off by default "
            "because it adds seconds to the response; the results themselves are "
            "identical either way."
        ),
    )


class BisProduct(BaseModel):
    """A product on BIS's compulsory certification lists that the query names."""
    product: str = Field(..., description="The product as BIS lists it.")
    is_number: str = Field(..., description="The standard it must be certified to.")
    scheme: str = Field(..., description="ISI, CRS, Scheme X or Hallmark.")
    status: str = Field(..., description="in_force, deferred, or voluntary (a scheme exists but is not compulsory).")
    qco: Optional[str] = Field(default=None, description="The order that makes it compulsory.")
    qco_url: Optional[str] = Field(default=None, description="Link to the order.")
    in_corpus: bool = Field(default=False, description="Whether the catalogue holds the standard's text.")


class RetrieveResponse(BaseModel):
    query: str = Field(..., description="The query string submitted.")
    results: List[StandardResult] = Field(..., description="Ranked list of standard candidates.")
    confidence: Literal["strong", "uncertain", "none"] = Field(
        default="strong",
        description=(
            "Whether the corpus plausibly contains a match for this query. "
            "'none' means the query is very likely outside the covered sectors "
            "and the results should NOT be presented as recommendations."
        ),
    )
    confidence_reason: str = Field(
        default="", description="Plain-language explanation of the confidence verdict, for display."
    )
    corpus_size: int = Field(
        default=0, description="Number of standards searched, so the UI can state coverage honestly."
    )
    translation: Optional["TranslationInfo"] = Field(
        default=None, description="Set when the query was not English, so the UI can show what was searched."
    )
    explanations_available: bool = Field(
        default=False,
        description="Whether a local explanation model is reachable, so the UI can offer the option.",
    )
    expanded_with: List[str] = Field(
        default_factory=list,
        description="The standards' own words added for an everyday product name, e.g. 'information technology equipment' for 'laptop'.",
    )
    bis_products: List["BisProduct"] = Field(
        default_factory=list,
        description="Products on BIS's compulsory certification lists that the query names, with their standard and scheme.",
    )


class CategoryCount(BaseModel):
    category: str = Field(..., description="Sector classification of the top result.")
    queries: int = Field(..., description="Searches whose top result fell in this sector.")


class RecentQuery(BaseModel):
    """One served search, for the dashboard's activity table."""
    query: str = Field(..., description="Query text exactly as submitted.")
    standard: Optional[str] = Field(default=None, description="IS number of the top result, or null when nothing was returned.")
    confidence: str = Field(..., description="'strong', 'uncertain' or 'none' -- the engine's own verdict at the time.")
    score: Optional[float] = Field(default=None, description="final_score of the top result. Comparable only within its own response.")
    timestamp: str = Field(..., description="ISO 8601 time the search was served.")


class StatsResponse(BaseModel):
    """Usage counted from the append-only logs.

    Every field is a count over `data/query_logs.jsonl` and
    `data/interaction_logs.jsonl`. Nothing is projected or estimated, and the
    synthetic records that bootstrapped the ranker are excluded from every
    live figure and reported separately under `synthetic_interactions`.

    Nullable fields mean "not calculable yet", not zero: `acceptance_rate` is
    null until someone has accepted or rejected something, and a UI must
    render that as an absence rather than as 0%.
    """
    has_live_data: bool = Field(..., description="False when the engine has served no searches; the UI should show an empty state, not zeroed tiles.")
    queries_total: int = Field(..., description="Searches served, all time.")
    queries_last_30d: int = Field(..., description="Searches served in the last 30 days.")
    queries_last_7d: int = Field(..., description="Searches served in the last 7 days.")
    no_match_queries: int = Field(..., description="Searches the engine judged outside corpus coverage ('none'). The standards-gap signal.")
    match_rate: Optional[float] = Field(default=None, description="Percentage of searches that found any match. Null before the first search.")
    median_latency_ms: Optional[int] = Field(default=None, description="Median server-side response time. Median, not mean, so one cold start does not distort it.")
    categories: List[CategoryCount] = Field(default_factory=list, description="Most-searched sectors, by top result.")
    recent_queries: List[RecentQuery] = Field(default_factory=list, description="Most recent searches, newest first.")
    feedback_total: int = Field(..., description="Live feedback records: accepts, rejects and corrections.")
    feedback_accepted: int = Field(..., description="Results accepted by an official.")
    feedback_rejected: int = Field(..., description="Results explicitly dismissed.")
    feedback_corrected: int = Field(..., description="Results manually overridden with a different standard.")
    acceptance_rate: Optional[float] = Field(default=None, description="Accepts as a percentage of all decisions. Null until the first decision.")
    synthetic_interactions: int = Field(..., description="Seed records used to bootstrap the ranker. Reported separately and never counted as usage.")


class AlertFinding(BaseModel):
    """One standards-hygiene fact about the corpus that affects what to cite.

    Derived, not authored: there is no alerts table, and nothing here was
    "sent" to anyone. Carries no timestamp because the corpus does not record
    when a revision was published, and a plausible-looking "2 hours ago" on a
    fact read from a static file would be an invention.
    """
    kind: Literal["supersession", "amendment"] = Field(..., description="What kind of finding this is.")
    severity: Literal["critical", "warning"] = Field(
        ...,
        description=(
            "'critical' is a superseded edition whose active replacement is known, so the "
            "fix can be named. 'warning' is a real problem this corpus cannot fully resolve."
        ),
    )
    standard: str = Field(..., description="IS number the finding is about.")
    title: str = Field(default="", description="Title of that standard.")
    category: str = Field(default="", description="Sector, for filtering.")
    replacement: Optional[str] = Field(default=None, description="Active edition that supersedes it, when the corpus holds one.")
    replacement_title: Optional[str] = Field(default=None, description="Title of the replacement.")
    amendment_count: Optional[int] = Field(default=None, description="Published amendments in force, for amendment findings.")
    detail: str = Field(..., description="Plain-language statement of the problem.")
    action: str = Field(..., description="What to cite instead, or what to confirm.")


class AlertCoverage(BaseModel):
    """The limits of the scan that produced these findings.

    Returned with every response so a short list cannot be read as an
    all-clear: most standards have simply never been checked for amendments.
    """
    corpus_size: int = Field(..., description="Standards scanned.")
    superseded_in_corpus: int = Field(..., description="Records marked superseded.")
    amendments_researched: int = Field(..., description="Standards whose text was read for amendments, or researched by hand.")
    amendments_unchecked: int = Field(..., description="Standards never checked for amendments. Not a statement that they have none.")
    note: str = Field(..., description="Plain-language statement of what this scan does and does not cover.")


class AlertsResponse(BaseModel):
    findings: List[AlertFinding] = Field(default_factory=list, description="Findings, most severe first. Empty when summary=true.")
    critical_count: int = Field(..., description="Findings whose replacement is known and named.")
    total_findings: int = Field(default=0, description="All findings, before any summary trimming.")
    coverage: AlertCoverage = Field(..., description="What this scan covered.")


class SectorCount(BaseModel):
    category: str = Field(..., description="Sector key.")
    standards: int = Field(..., description="Standards held in that sector.")


class CorpusHealthResponse(BaseModel):
    """How complete the corpus's own metadata is.

    Each researched count is paired with the total it is out of: 17
    certification records reads very differently against 45 standards than
    against 4,282, and the ratio is the honest figure.
    """
    corpus_size: int = Field(..., description="Standards in the served corpus.")
    active: int = Field(..., description="Records marked active.")
    superseded: int = Field(..., description="Records marked superseded.")
    certification_mandatory: int = Field(..., description="Standards under a BIS certification obligation in force.")
    certification_deferred: int = Field(default=0, description="Standards named in an order whose enforcement is deferred.")
    certification_related: int = Field(default=0, description="Standards not listed themselves whose parent or general part is.")
    certification_not_listed: int = Field(
        default=0,
        description="Standards with no compulsory certification: not on BIS's lists, checked with none applying, or voluntary only.",
    )
    certification_not_verified: int = Field(..., description="Standards whose status cannot be read (lists unavailable). Not a clearance.")
    certification_retrieved: Optional[str] = Field(default=None, description="Date the BIS lists were read.")
    amendments_researched: int = Field(..., description="Standards with amendments known: researched, or read from their archived text.")
    amendments_checked: int = Field(default=0, description="Standards whose archived text was read for amendment slips, or researched.")
    amendments_total: int = Field(..., description="Published amendments recorded across those standards.")
    sectors: List[SectorCount] = Field(default_factory=list, description="Standards per sector, largest first.")


class AuditFinding(BaseModel):
    """One problem with a citation the tender already makes."""
    severity: Literal["critical", "minor", "info"] = Field(
        ...,
        description=(
            "'critical' is a superseded citation whose replacement is known. 'minor' is a "
            "real defect the corpus cannot fully resolve. 'info' is a coverage gap or an "
            "ambiguity, not a defect in the tender."
        ),
    )
    kind: Literal["superseded", "amendment", "undated", "unknown"] = Field(..., description="What kind of problem this is.")
    cited: str = Field(..., description="The IS number exactly as the document cites it.")
    title: str = Field(default="", description="Title of that standard, when the corpus holds it.")
    occurrences: int = Field(..., description="Times this standard is cited in the document.")
    context: str = Field(..., description="Text around the first citation, so it can be located.")
    replacement: Optional[str] = Field(default=None, description="Edition to cite instead, when one is known.")
    amendment_count: Optional[int] = Field(default=None, description="Amendments in force, for amendment findings.")
    detail: str = Field(..., description="Plain-language statement of the problem.")
    action: str = Field(..., description="What to change in the tender.")


class DependencyGap(BaseModel):
    """A standard that a cited standard depends on, which the document does not cite."""
    standard: str = Field(..., description="The standard to add, as the edition in force when the corpus holds it.")
    title: str = Field(default="", description="Its title, when known.")
    type: str = Field(..., description="normative_reference, material_spec, safety, test_method or installation.")
    required_by: List[str] = Field(..., description="The cited standards that depend on it.")
    evidence: Optional[str] = Field(default=None, description="The sentence the dependency was read from, or the researched note.")
    in_corpus: bool = Field(default=True, description="Whether the catalogue holds it, so it can be opened.")
    parts: List[str] = Field(default_factory=list, description="For a series needed in several parts, which parts.")


class AuditResponse(BaseModel):
    """Result of checking a tender's citations against the corpus.

    Deliberately carries no score. A compliance percentage would imply the
    audit checked everything a tender needs, when it only verifies the IS
    numbers the document already cites: `citations_found: 0` with no findings
    is not a pass, and the UI must be able to say so.
    """
    filename: str = Field(default="", description="Name of the audited document.")
    citations_found: int = Field(..., description="Distinct IS numbers cited. Zero means nothing could be checked.")
    findings: List[AuditFinding] = Field(default_factory=list, description="Problems found, most severe first.")
    critical_count: int = Field(..., description="Superseded citations whose replacement is known.")
    clean_citations: int = Field(..., description="Cited standards that raised no finding.")
    corpus_size: int = Field(..., description="Standards the citations were checked against.")
    note: str = Field(..., description="What this audit did and did not check.")
    dependency_gaps: List["DependencyGap"] = Field(
        default_factory=list,
        description="Standards the cited ones depend on (read from their own text) that the document does not cite, most-needed first.",
    )
    dependency_gaps_total: int = Field(default=0, description="All such gaps, before the list was capped.")
    text: str = Field(default="", description="Text read from the document, so the user can verify it.")
    char_count: int = Field(default=0, description="Characters extracted.")
    page_count: Optional[int] = Field(default=None, description="Pages read, for PDFs.")
    method: str = Field(default="", description="How the text was extracted, e.g. 'pdf' or 'pdf+ocr'.")
    warnings: List[str] = Field(default_factory=list, description="Problems encountered while reading the document.")


class LineItemResult(BaseModel):
    """One line of a bill of quantities, with the standards it matched."""
    sr: int = Field(..., description="Position in the document, 1-indexed.")
    text: str = Field(..., description="The line item as the document states it.")
    query: str = Field(..., description="Text actually searched, with the item numbering stripped.")
    quantity: Optional[str] = Field(default=None, description="Quantity read from the line, for display only. Never searched.")
    results: List[StandardResult] = Field(default_factory=list, description="Ranked standards for this item alone.")
    confidence: Literal["strong", "uncertain", "none"] = Field(
        default="none",
        description="Per-item verdict. 'none' means the corpus does not cover this item.",
    )
    confidence_reason: str = Field(default="", description="Why that verdict, for display.")


class BOQResponse(BaseModel):
    """A bill of quantities, split into items and searched item by item.

    Each line is searched on its own. Flattening a BOQ into one query lets the
    first item's vocabulary dominate the ranking, so the cement silently loses
    to the cable -- searching per item is the whole point of this endpoint.

    `is_boq: false` means no line-item structure was found. The document may
    still be a perfectly good tender; it is just not a BOQ, and the caller
    should fall back to /extract rather than showing an empty item list.
    """
    filename: str = Field(default="", description="Name of the uploaded document.")
    is_boq: bool = Field(..., description="False when the document has no line-item structure.")
    items: List[LineItemResult] = Field(default_factory=list, description="Line items, in document order.")
    item_count: int = Field(..., description="Line items detected.")
    matched_count: int = Field(..., description="Items where the corpus had a confident match.")
    text: str = Field(default="", description="Text read from the document, so the user can verify it.")
    char_count: int = Field(default=0, description="Characters extracted.")
    page_count: Optional[int] = Field(default=None, description="Pages read, for PDFs.")
    method: str = Field(default="", description="How the text was extracted.")
    warnings: List[str] = Field(default_factory=list, description="Problems encountered while reading the document.")
    corpus_size: int = Field(default=0, description="Standards searched.")


class CertificationRule(BaseModel):
    """One standard on BIS's compulsory lists or hallmarking order (or checked by hand), with its order."""
    is_number: str = Field(..., description="Standard as BIS lists it.")
    scheme: Literal["ISI", "CRS", "Scheme X", "Hallmark", "none"] = Field(..., description="Scheme, or 'none' where checked and none applies.")
    status: Literal["in_force", "deferred", "voluntary", "checked_none"] = Field(
        ..., description="In force, deferred, voluntary (a scheme with no order making it compulsory), or checked with none applying."
    )
    mandatory: bool = Field(..., description="True only for an obligation in force.")
    explanation: str = Field(..., description="What a procurement official should do about it.")
    qco: Optional[str] = Field(default=None, description="Governing Quality Control Order.")
    gazette: Optional[str] = Field(default=None, description="Gazette notification number and date.")
    qco_url: Optional[str] = Field(default=None, description="Link to the order.")
    product: Optional[str] = Field(default=None, description="Products as BIS lists them.")
    products: List[str] = Field(default_factory=list, description="Products as BIS lists them.")
    category: Optional[str] = Field(default=None, description="Heading the product sits under in the BIS list.")
    confidence: str = Field(default="confirmed", description="'confirmed' when read from the BIS list.")
    listed_as: Optional[str] = Field(default=None, description="The IS number as BIS lists it.")
    corpus_number: Optional[str] = Field(default=None, description="The edition the corpus holds, current one preferred; null if not in the corpus.")


class CertificationCoverage(BaseModel):
    """What the certification mapping covers."""
    standards_researched: int = Field(..., description="Standards on the BIS lists, plus those checked by hand.")
    mandatory: int = Field(..., description="Of those, how many carry an obligation in force.")
    deferred: int = Field(default=0, description="Of those, how many are named in an order whose enforcement is deferred.")
    voluntary: int = Field(default=0, description="Of those, how many have a BIS scheme that no order makes compulsory.")
    no_scheme: int = Field(..., description="Of those, how many were checked by hand and carry none.")
    retrieved: Optional[str] = Field(default=None, description="Date the BIS lists were read.")
    sources: Dict[str, str] = Field(default_factory=dict, description="The BIS list pages, by scheme.")
    source: str = Field(..., description="Where the mapping was read from.")
    note: str = Field(..., description="What each status means, and what the lists cannot say.")


class CertificationRulesResponse(BaseModel):
    """Every researched certification rule, plus what was not researched.

    Only researched standards are listed. The corpus holds thousands whose
    status nobody has checked, and rendering those as 'no scheme' would turn
    an absence of research into a positive clearance.
    """
    rules: List[CertificationRule] = Field(default_factory=list, description="Researched rules, mandatory first.")
    coverage: CertificationCoverage = Field(..., description="What this mapping does and does not cover.")


# Confidence thresholds, on the cross-encoder logit of the top result.
#
# Unlike `final_score` -- which apply_supersession_penalty rescales into
# [0, 1] *per response*, so it cannot distinguish a great match from the
# least-bad of a uniformly bad set -- the cross-encoder logit is an absolute
# relevance estimate and is comparable across queries.
#
# Recalibrated on the full 21,848-standard corpus (eval/calibrate_confidence.py):
#   589 held-out in-scope queries        +1.25 .. (median +8.2)
#   realistic short, vague in-scope ones  down to -1.8 ("cotton bedsheet",
#                                          "bricks for wall construction")
#   35 out-of-scope requests             up to -2.7 (services, software,
#                                          travel, insurance, nonsense)
# The first calibration, on 30 standards, put 'none' at -6.0; at full size
# that sent 29% of out-of-scope requests (catering, taxi hire, app
# development) to 'uncertain', showing a result under a caution banner where a
# plain no-match was right. -2.25 sits midway between the highest out-of-scope
# score and the lowest realistic in-scope one, about 0.45 clear of each; vague
# in-scope wording stays 'uncertain' rather than being told it is out of scope.
_CONFIDENCE_STRONG_MIN = 0.0
_CONFIDENCE_NONE_MAX = -2.25

# A buyer describing goods needs the goods' specification first; methods of
# test are allied standards, shown on the standard's page, not the answer. So
# unless the query is itself about testing, a test-method title is ranked as if
# the cross-encoder had scored it 3 lower ("ceramic floor tiles" had put a
# dozen parts of IS 13630, methods of test, above IS 15622, the tiles). The
# score reported, and the confidence verdict, keep the raw value.
_TEST_METHOD_TITLE = re.compile(
    r"\bmethods?\s+(?:of|for)\s+(?:tests?|testing|sampling|analysis|measurement|determination)\b"
    r"|\btest(?:ing)?\s+methods?\b|^\s*determination\s+of\b",
    re.IGNORECASE,
)
_TESTING_QUERY = re.compile(r"\btest|\bsampl|\bmethod|\banalys|\bdetermin|\bmeasur|\bassay|\bexamin", re.IGNORECASE)
_TEST_METHOD_DEMOTION = 3.0

# How many fused candidates reach the cross-encoder. Each one is a forward
# pass, so this is the main latency lever in the whole pipeline. 10 let a
# dozen near-identical parts of one test series (IS 13630, ceramic tiles)
# crowd the product standard out of scoring altogether, and at 31,372 records
# 15 still left IS 13983 (stainless steel sinks) just outside.
_RERANK_DEPTH = 20


def assess_confidence(results: List["StandardResult"]) -> Dict[str, str]:
    """Judge whether the corpus plausibly covers this query at all.

    The corpus covers only a few sectors. Without this check a query for
    something it does not contain still returns its best guess, which reads
    to a user as a confident recommendation.
    """
    if not results:
        return {
            "level": "none",
            "reason": "No standards matched this query.",
        }

    top_ce = results[0].stage_scores.cross_encoder

    if top_ce >= _CONFIDENCE_STRONG_MIN and not (results[0].scope or "").strip():
        # Matched on a title alone: the catalogue holds only the number and
        # title, so there is no scope text to confirm what the standard covers.
        return {
            "level": "uncertain",
            "reason": (
                "The top result matches on its title, but the catalogue holds only its number and "
                "title, not its scope, so the match cannot be confirmed. Check the standard itself "
                "before citing it."
            ),
        }

    if top_ce >= _CONFIDENCE_STRONG_MIN:
        return {
            "level": "strong",
            "reason": "The top result closely matches the wording of this query.",
        }

    if top_ce <= _CONFIDENCE_NONE_MAX:
        return {
            "level": "none",
            # Not "outside the covered sectors": with the full archive loaded a
            # miss is as often a product described in words no standard uses
            # ("laptop" for IT equipment) as one BIS does not cover at all.
            "reason": (
                "No standard matched this description closely. It may be outside the "
                "Indian Standards catalogue, or described in words the standards do not "
                "use; try naming the material, rating or function. The entries below are "
                "the nearest text matches, not recommendations."
            ),
        }

    return {
        "level": "uncertain",
        "reason": (
            "The closest matches are only loosely related to this query. Review them "
            "carefully, and consider rephrasing with the material, rating or "
            "application you are procuring."
        ),
    }


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service operational status.")
    corpus_size: int = Field(..., description="Number of BIS standards loaded in memory.")
    ltr_model_loaded: bool = Field(..., description="Whether a trained LTR LightGBM model is active.")
    explanations_available: bool = Field(
        default=False,
        description=(
            "Whether the local explanation model is reachable, so the UI can offer "
            "explanations before the first search rather than discovering it after."
        ),
    )
    bis_refresh: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "The background refresh from BIS's standards portal: state (idle, running, failed), "
            "the step it is on, when the last one completed, and whether it is enabled."
        ),
    )


class ExplainRequest(BaseModel):
    query: str = Field(..., description="The query the results were retrieved for (as searched, i.e. after translation).")
    numbers: List[str] = Field(
        ...,
        description="IS numbers of the results to explain, in rank order. Only the first five are used.",
    )


class ExplainResponse(BaseModel):
    available: bool = Field(..., description="Whether the explanation model was reachable.")
    explanations: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "IS number -> one-sentence reason. Only numbers that were asked about ever "
            "appear; anything the model invents is discarded before this is returned."
        ),
    )


# --- Lifespan Startup & Resource Management ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preloads all models, vector indices, and sparse dictionaries into memory once on startup."""
    logger.info("[Lifespan] Initializing standards-retrieval service...")

    # 0. If the engine was closed in the middle of a BIS refresh, the corpus and
    #    index on disk may disagree; put back the pair from before it.
    if bis_refresh.enabled():
        bis_refresh.recover()

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

    # 6. Load the optional explanation model in the background, so the first
    #    person to ask for an explanation does not wait for it to load. Never
    #    blocks startup; does nothing if Ollama is absent. EXPLANATION_WARMUP=0
    #    turns it off (the test suite does, to keep runs off the GPU).
    if os.environ.get("EXPLANATION_WARMUP", "1") != "0":
        explanation_engine.warm_up()

    # 7. Load the allied-standards graph (~88,000 links) now rather than on the
    #    first request, which otherwise pays about a second for it.
    graph = relationships_data.coverage()
    logger.info(
        "[Lifespan] Allied-standards graph loaded: %d links (%d curated, %d read from text).",
        graph["total_relationships"], graph["curated_relationships"], graph["extracted_relationships"],
    )

    # 8. Bring the corpus up to date with BIS when the last refresh is more than
    #    a week old. It runs in the background while this corpus is served, and
    #    swaps the new one in when it is complete.
    bis_refresh.start_if_due(on_success=lambda: _serve_refreshed_corpus(app))

    yield

    logger.info("[Lifespan] Shutting down standards-retrieval service.")


def _serve_refreshed_corpus(app: FastAPI) -> None:
    """Swap in the corpus and indexes a BIS refresh has just written.

    Everything is read before anything is replaced, and the corpus goes in
    first: an index id the old corpus lacks would be skipped, but every id the
    old index holds is still in the new corpus, since records are never dropped.
    Caches derived from the corpus (editions, hygiene findings) are keyed on it
    and rebuild on their own; the IS-number map and the amendment record are
    cleared here.
    """
    standards = load_corpus(force_reload=True)
    faiss_index, faiss_ids = load_faiss_index(force_reload=True)
    bm25_index, bm25_ids = load_bm25_index(force_reload=True)
    app.state.corpus = {s.id: s for s in standards}
    app.state.by_number = None
    app.state.faiss_index, app.state.faiss_ids = faiss_index, faiss_ids
    app.state.bm25_index, app.state.bm25_ids = bm25_index, bm25_ids
    amendments_data.reset_cache()
    logger.info("[BIS refresh] Now serving %d standards.", len(standards))


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

# The React frontend runs on a different origin during development
# (Vite on :5173, this service on :8000), so the browser preflights every
# POST. Without this the UI cannot call the API at all.
#
# Origins are explicit rather than "*" because the service reads and writes
# feedback logs; if this is ever deployed, add the deployed origin here
# instead of loosening the list.
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",  # `vite preview`
    "http://127.0.0.1:4173",
]

# Every route except the docs, /health and the sign-in routes needs a session
# token or an API key (see accounts_api.PUBLIC_PATHS). Added before CORS so
# CORS wraps it: a 401 still carries CORS headers and the browser can read it.
app.add_middleware(accounts_api.AuthMiddleware)

# Extra origins for a deployment, comma separated, e.g.
# ALLOWED_ORIGINS=https://standeng.example.gov.in
_ALLOWED_ORIGINS += [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

app.include_router(accounts_api.router)


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
        ltr_model_loaded=ltr_loaded,
        explanations_available=explanation_engine.is_available(),
        bis_refresh=bis_refresh.status(),
    )


@app.post("/explain", response_model=ExplainResponse, summary="Explain results already retrieved")
def explain_results(body: ExplainRequest):
    """One plain-language sentence per result, for results already on screen.

    Split from `/retrieve` so a search never waits on the language model: the
    results render at retrieval speed and the explanations fill in after.

    The boundary is the same as before. The model sees only standards the
    caller names, and only those present in the corpus, so it can describe a
    retrieved candidate but never introduce one; any number it returns that was
    not asked about is discarded in `explanation.explain`. The caller is
    responsible for not asking on a `none` verdict: those results are nearest
    text matches, and a fluent reason beside each would read as endorsement.
    """
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    available = explanation_engine.is_available()
    if not available or not body.numbers:
        return ExplainResponse(available=available)

    by_number = _standards_by_number()

    candidates = []
    for number in body.numbers[:5]:
        std = by_number.get(number)
        if std is not None:
            candidates.append({"number": std.number, "title": std.title, "scope": std.scope})

    return ExplainResponse(
        available=True,
        explanations=explanation_engine.explain(query, candidates) if candidates else {},
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
    response = _retrieve(body)
    top = response.results[0] if response.results else None
    accounts.record_current(
        "search.query",
        f'"{body.query.strip()[:160]}"',
        {
            "query": body.query.strip()[:500],
            "top": top.number if top else None,
            "confidence": response.confidence,
            "results": [r.number for r in response.results[:5]],
        },
    )
    return response


# The browser refuses files over 10 MB, but the server must not trust that: a
# client can send anything, and the whole file is read into memory.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB. Upload a smaller file.")
    return data


_HELD_FAMILIES: Dict[int, set] = {}


def _bis_products(query: str, expanded_with: Optional[List[str]] = None) -> List[dict]:
    """BIS-listed products the query names, flagged by whether the catalogue holds the standard.

    Also tried with each added phrase, so "OPC 43 grade cement" finds BIS's
    "Ordinary Portland Cement" listing through "ordinary portland cement".
    """
    corpus = load_corpus()
    held = _HELD_FAMILIES.get(id(corpus))
    if held is None:
        _HELD_FAMILIES.clear()
        held = _HELD_FAMILIES[id(corpus)] = {certification.family(s.number) for s in corpus}
    found, seen = [], set()
    for text in [query, *(expanded_with or [])]:
        for p in certification.products_for_query(text):
            if p["is_number"] not in seen:
                seen.add(p["is_number"])
                found.append({**p, "in_corpus": certification.family(p["is_number"]) in held})
    return found[:5]


def _retrieve(body: RetrieveRequest) -> "RetrieveResponse":
    """The ranking pipeline itself, shared by /retrieve, /boq and /simulate.

    Kept apart from the endpoint so that a BOQ of forty line items, or a
    scenario's two runs, record one entry in the user's trail rather than one
    per internal search.
    """
    # Timed from here so the logged figure is server-side work only, excluding
    # network time the engine cannot influence.
    _started = time.perf_counter()

    # 1. Input validation
    query = body.query
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query string must not be empty.")

    if body.top_k < 1:
        raise HTTPException(status_code=400, detail="top_k must be at least 1.")

    # Sane upper-bound cap
    top_k = min(body.top_k, 50)

    # 1b. Translate non-English queries before anything touches the index.
    #
    # The retrieval stack is English-only. Measured on this corpus, an
    # untranslated Hindi query scores -8 to -9 on the cross-encoder, which the
    # confidence gate correctly reports as no match; translating first brings
    # the same queries to +2.8 to +8.5 and returns the same standards the
    # English phrasing returns.
    translation_info = None
    result = translation.translate_to_english(query, body.language)
    if result["detected"] != "en" or result["translated"]:
        language_entry = translation.SUPPORTED_LANGUAGES.get(result["detected"], {})
        translation_info = TranslationInfo(
            original=result["original"],
            translated_text=result["text"],
            detected_language=result["detected"],
            language_name=language_entry.get(
                "name", "Unsupported language" if result["detected"] == translation.UNSUPPORTED else result["detected"]),
            translated=result["translated"],
            error=result["error"],
        )
    query = result["text"]

    # 1c. Add the standards' own words for an everyday product name ("laptop"
    # -> "information technology equipment"). Retrieval and ranking use the
    # expanded text; the response keeps the user's words and lists what was
    # added, so the screen can say so.
    search_query, expanded_with = expansion.expand(query)

    # 2. Access preloaded corpus and models
    corpus = getattr(app.state, "corpus", None)
    if corpus is None:
        corpus = {s.id: s for s in load_corpus()}
        app.state.corpus = corpus

    # 3. Step 1: Hybrid Search (Dense + BM25 RRF) -> Top-20 candidates
    hybrid_candidates = hybrid_search(search_query, top_k=20)
    candidate_ids = [cid for cid, _ in hybrid_candidates]
    if not candidate_ids:
        return RetrieveResponse(query=query, results=[], translation=translation_info)

    # 4. Step 2: Cross-Encoder Re-Ranking over candidate IDs
    #
    # The cross-encoder runs one forward pass per candidate, so its cost is
    # linear in how many it is given and it dominates the response: at 6,360
    # standards, re-ranking 20 candidates was ~1.0 s of a ~1.9 s request.
    #
    # Recall@5 is 0.9958, so the correct standard is almost always near the
    # top of the fused list already. Re-ranking the top 10 rather than all 20
    # halves that cost for a candidate that was very unlikely to be promoted
    # from rank 11-20 anyway.
    rerank_depth = min(len(candidate_ids), _RERANK_DEPTH)
    window = candidate_ids[:rerank_depth]
    # A superseded edition being scored brings its current edition with it, so
    # the supersession rule below has both to choose between. Without this the
    # 2006 edition of IS 15622 was scored and the 2017 one, just outside the
    # window, was not.
    edition_index = editions.for_corpus(load_corpus())
    for cid in list(window):
        std = corpus.get(cid)
        if std is None or getattr(std, "status", "active") != "superseded":
            continue
        # Its newer edition, and the replacement BIS names, which can carry a
        # different number (IS 325 was replaced by IS 12615).
        found = edition_index.replacement(std)
        named = found["record"] if found["held"] else None
        for current in (edition_index.active_in_family(std.number), named):
            if (current is not None and getattr(current, "status", "active") == "active"
                    and current.id in corpus and current.id not in window):
                window.append(current.id)
                if current.id not in candidate_ids:
                    candidate_ids.append(current.id)
    ce_ranked = rerank(search_query, window, corpus=corpus, top_k=len(window))
    ce_dict = dict(ce_ranked)

    # Fetch individual dense and bm25 scores for candidate feature extraction
    dense_dict = dict(dense_search(search_query, top_k=len(candidate_ids) + 10))
    bm25_dict = dict(bm25_search(search_query, top_k=len(candidate_ids) + 10))

    # Per-query min-max normalization for BM25 feature
    raw_bm25_vals = [bm25_dict.get(cid, 0.0) for cid in candidate_ids]
    min_b = min(raw_bm25_vals) if raw_bm25_vals else 0.0
    max_b = max(raw_bm25_vals) if raw_bm25_vals else 0.0
    range_b = max_b - min_b

    valid_cids = []
    features_list = []
    stage_scores_list = []
    testing_query = bool(_TESTING_QUERY.search(query))

    for cid in candidate_ids:
        std = corpus.get(cid)
        if not std:
            continue
        valid_cids.append(cid)

        d_s = float(dense_dict.get(cid, 0.0))
        raw_b = float(bm25_dict.get(cid, 0.0))
        b_norm = (raw_b - min_b) / (range_b + 1e-6) if range_b > 1e-6 else 0.5
        ce_s = float(ce_dict.get(cid, -10.0))
        ce_for_rank = ce_s
        if cid in ce_dict and not testing_query and _TEST_METHOD_TITLE.search(std.title or ""):
            ce_for_rank -= _TEST_METHOD_DEMOTION

        fv = build_features(
            query=search_query,
            candidate_id=cid,
            standard=std,
            dense_score=d_s,
            bm25_score_normalized=b_norm,
            cross_encoder_score=ce_for_rank,
            historical_acceptance_rate=0.0
        )
        features_list.append(fv)
        stage_scores_list.append({
            "dense": round(d_s, 4),
            "bm25": round(raw_b, 4),
            "cross_encoder": round(ce_s, 4)
        })

    if not features_list:
        return RetrieveResponse(query=query, results=[], translation=translation_info)

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
    results = []
    for item in penalized_results[:top_k]:
        std = corpus.get(item["id"])
        amendment_info = amendments_data.for_standard(item["number"])
        results.append(
            StandardResult(
                id=item["id"],
                number=item["number"],
                title=item["title"],
                final_score=float(item["final_score"]),
                stage_scores=StageScores(**item["stage_scores"]),
                ranker_used=ranker_used,
                scope=getattr(std, "scope", "") if std else "",
                category=getattr(std, "category", "") if std else "",
                status=getattr(std, "status", "active") if std else "active",
                version=getattr(std, "version", "") if std else "",
                last_amended=getattr(std, "last_amended", "") if std else "",
                superseded_by=item.get("superseded_by"),
                replaced_by=(editions.for_corpus(load_corpus()).replacement(std)["number"]
                             if std is not None and getattr(std, "status", "active") == "superseded" else None),
                withdrawn=bool(getattr(std, "withdrawn", False)) if std else False,
                certification=CertificationInfo(**certification.lookup(item["number"])),
                citation=amendment_info["citation"],
                amendment_count=amendment_info["count"],
                data_warning=(certification.withdrawn_note(item["number"]) or {}).get("issue"),
            )
        )

    confidence = assess_confidence(results)

    # An everyday word matched through the standards' own term ("laptop" ->
    # "information technology equipment") can still score low on the
    # cross-encoder, which compares the user's word with technical prose. When
    # the added term is in the top result's own title, the match is real but
    # indirect: raised to 'uncertain', never 'strong', and said so.
    if confidence["level"] == "none" and expanded_with and results:
        top_title = results[0].title.lower()
        term = next((t for t in expanded_with
                     if all(w in top_title for w in re.findall(r"[a-z]{4,}", t.lower()))), None)
        if term:
            confidence = {
                "level": "uncertain",
                "reason": (
                    f"Matched through the standards' own term \"{term}\", which appears in the title of "
                    f"{results[0].number}. Check that it covers what you are buying."
                ),
            }

    # Explanations are strictly additive: generated after ranking is final,
    # validated against the candidate list, and dropped entirely on any
    # failure. The result set is identical whether or not this runs.
    explanations_available = explanation_engine.is_available()
    # `confidence` is the dict returned by assess_confidence, so the level has
    # to be read out of it. Skipping generation on a 'none' verdict matters:
    # the UI presents those results as "nearest text matches, not
    # recommendations", and an explanation beside each one would undercut that.
    if body.explain and explanations_available and confidence["level"] != "none":
        reasons = explanation_engine.explain(
            query, [r.model_dump() for r in results]
        )
        for item in results:
            if item.number in reasons:
                item.explanation = reasons[item.number]

    response = RetrieveResponse(
        query=query,
        results=results,
        confidence=confidence["level"],
        confidence_reason=confidence["reason"],
        corpus_size=len(corpus),
        translation=translation_info,
        explanations_available=explanations_available,
        expanded_with=expanded_with,
        bis_products=_bis_products(query, expanded_with),
    )

    # Record that this search happened, so the dashboard reports use rather
    # than a fixture. Written after the response is fully built and wrapped so
    # that no bookkeeping failure can turn a successful search into a 500 --
    # append_query swallows its own errors, and this guards the rest.
    try:
        top = results[0] if results else None
        append_query(
            query=query,
            top_result_id=top.id if top else None,
            top_result_number=top.number if top else None,
            top_score=round(float(top.final_score), 4) if top else None,
            confidence=confidence["level"],
            category=(top.category or None) if top else None,
            result_count=len(results),
            corpus_size=len(corpus),
            elapsed_ms=int((time.perf_counter() - _started) * 1000),
            language=translation_info.detected_language if translation_info else None,
            source="live",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:  # noqa: BLE001 -- a served search must not fail on its own logging
        logger.warning("Query logging failed: %s", e)

    return response


# --- Convenience Endpoints for Compatibility ---

@app.get("/retrieve", response_model=RetrieveResponse, summary="Retrieve & Rank Standards (GET Alias)")
def retrieve_standards_get(query: str, top_k: int = 10):
    """GET alias for /retrieve enabling query parameter testing in browser and backward compatibility."""
    return retrieve_standards_post(RetrieveRequest(query=query, top_k=top_k))


class SimulateRequest(BaseModel):
    query: str = Field(..., max_length=2000, description="The base description, as it would be typed into search.")
    conditions: List[str] = Field(
        default_factory=list,
        description="Extra requirements for the scenario, e.g. 'installed outdoors, exposed to sunlight'.",
    )
    top_k: int = Field(10, ge=3, le=20)


class ScenarioStandard(BaseModel):
    number: str
    title: str
    id: str
    status: str = "active"
    base_rank: Optional[int] = None
    scenario_rank: Optional[int] = None


class SimulateResponse(BaseModel):
    query: str
    scenario_query: str
    conditions: List[str]
    base_confidence: str
    scenario_confidence: str
    base: List[ScenarioStandard]
    scenario: List[ScenarioStandard]
    added: List[ScenarioStandard]
    removed: List[ScenarioStandard]
    moved: List[ScenarioStandard]
    unchanged: int


@app.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="What changes if the requirement changes",
    description=(
        "Runs the full search twice, once on the base description and once with the scenario's "
        "conditions added, and reports which standards enter the top results, which drop out and "
        "which move. Every standard in the answer came from a real search over the corpus."
    ),
)
def simulate(body: SimulateRequest):
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Describe the base item first.")
    conditions = [c.strip() for c in body.conditions if c and c.strip()][:8]
    if not conditions:
        raise HTTPException(status_code=400, detail="Add at least one condition to compare against.")

    scenario_query = query.rstrip(" .,;") + ", " + ", ".join(conditions)
    base = _retrieve(RetrieveRequest(query=query, top_k=body.top_k))
    scenario = _retrieve(RetrieveRequest(query=scenario_query, top_k=body.top_k))

    base_rank = {r.number: i + 1 for i, r in enumerate(base.results)}
    scenario_rank = {r.number: i + 1 for i, r in enumerate(scenario.results)}

    def row(r) -> ScenarioStandard:
        return ScenarioStandard(
            number=r.number, title=r.title, id=r.id, status=r.status or "active",
            base_rank=base_rank.get(r.number), scenario_rank=scenario_rank.get(r.number),
        )

    base_rows = [row(r) for r in base.results]
    scenario_rows = [row(r) for r in scenario.results]
    added = [r for r in scenario_rows if r.base_rank is None]
    removed = [r for r in base_rows if r.scenario_rank is None]
    moved = [r for r in scenario_rows if r.base_rank is not None and r.base_rank != r.scenario_rank]

    accounts.record_current(
        "search.scenario",
        f'"{query[:120]}" with {", ".join(conditions)[:120]}',
        {"query": query, "conditions": conditions, "added": [r.number for r in added],
         "removed": [r.number for r in removed]},
    )

    return SimulateResponse(
        query=query,
        scenario_query=scenario_query,
        conditions=conditions,
        base_confidence=base.confidence,
        scenario_confidence=scenario.confidence,
        base=base_rows,
        scenario=scenario_rows,
        added=added,
        removed=removed,
        moved=moved,
        unchanged=sum(1 for r in scenario_rows if r.base_rank == r.scenario_rank),
    )


@app.get("/search", response_model=RetrieveResponse, summary="Search Standards (GET Alias)")
def search_standards_get(query: str, top_k: int = 10):
    """Alias for /retrieve providing backwards compatibility."""
    return retrieve_standards_post(RetrieveRequest(query=query, top_k=top_k))


def _normalize_is_number(value: str) -> str:
    """Canonical form of an IS number for comparison.

    Collapses whitespace, normalises `(Part n)` casing and strips spaces
    around the edition colon, so user- and URL-supplied spellings match the
    corpus. Mirrors the normalisation in data/consolidate.py.
    """
    text = " ".join(value.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


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


class StandardSummary(BaseModel):
    id: str
    number: str
    title: str
    category: str
    status: str
    version: str = ""
    scope: str = Field(default="", description="Opening of the scope clause, for a list row; the full text is on the detail endpoint.")


class CatalogueSectorCount(BaseModel):
    category: str
    count: int


class StandardSearchResponse(BaseModel):
    total: int = Field(..., description="Standards matching the filters, before paging.")
    corpus_size: int
    superseded_total: int = Field(..., description="Superseded editions in the whole corpus.")
    sectors: List[CatalogueSectorCount] = Field(..., description="Every sector in the corpus with its size, for a filter.")
    results: List[StandardSummary]


_SCOPE_EXCERPT = 200


def _search_index():
    """(standard, lowercase haystack) pairs, built once per process."""
    index = getattr(app.state, "search_index", None)
    if index is None:
        corpus = getattr(app.state, "corpus", None)
        standards = list(corpus.values()) if corpus else load_corpus()
        index = [
            (s, " ".join([s.number, s.title, s.scope or "", " ".join(s.keywords or [])]).lower())
            for s in sorted(standards, key=lambda s: (s.category, s.number))
        ]
        app.state.search_index = index
    return index


@app.get("/standards/search", response_model=StandardSearchResponse, summary="Search the catalogue")
def search_standards(
    q: str = "",
    category: Optional[str] = None,
    include_superseded: bool = True,
    limit: int = 50,
    offset: int = 0,
):
    """One page of the catalogue, filtered on the server.

    `/standards` returns the whole corpus, which at 21,848 records is about
    10 MB and took seconds to download before the catalogue could draw a row.
    This matches the same fields the catalogue always searched (IS number,
    title, scope and keywords) and returns only the page shown, with scope
    trimmed to an excerpt. With a search term, number matches rank first,
    then title matches, then scope or keyword matches.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    term = q.strip().lower()
    index = _search_index()

    matches = [
        s for s, haystack in index
        if (not category or s.category == category)
        and (include_superseded or s.status != "superseded")
        and (not term or term in haystack)
    ]
    if term:
        # "IS 694" must put IS 694 before IS 6943: a whole-number match (the
        # term not followed by another digit) outranks a mere prefix.
        whole_number = re.compile(re.escape(term) + r"(?!\d)")

        def rank(s):
            number = s.number.lower()
            if whole_number.match(number):
                return 0
            if term in number:
                return 1
            return 2 if term in s.title.lower() else 3

        matches.sort(key=lambda s: (rank(s), s.number))

    counts: Dict[str, int] = {}
    for s, _ in index:
        counts[s.category] = counts.get(s.category, 0) + 1

    return StandardSearchResponse(
        total=len(matches),
        corpus_size=len(index),
        superseded_total=sum(1 for s, _ in index if s.status == "superseded"),
        sectors=[CatalogueSectorCount(category=c, count=n) for c, n in sorted(counts.items())],
        results=[
            StandardSummary(
                id=s.id, number=s.number, title=s.title, category=s.category,
                status=s.status, version=s.version or "",
                scope=(s.scope or "")[:_SCOPE_EXCERPT],
            )
            for s in matches[offset: offset + limit]
        ],
    )


@app.get("/standards/{standard_id}", response_model=Standard, summary="Get Standard by ID or IS Number")
def get_standard(standard_id: str):
    """Retrieve a single standard by internal id or by IS number.

    Accepts either form because the internal id (`IS-ELEC-009`) is an
    implementation detail that changes when the corpus is rebuilt, whereas the
    IS number (`IS 694:2010`) is what a procurement officer actually has and
    what the UI puts in its URLs.
    """
    standard = get_standard_by_id(standard_id)
    if standard:
        return standard

    # Fall back to IS-number lookup, normalising case and spacing so that
    # "is 694:2010" and "IS 694 : 2010" resolve to the same standard.
    wanted = _normalize_is_number(standard_id)
    corpus = getattr(app.state, "corpus", None)
    standards = list(corpus.values()) if corpus else load_corpus()
    for candidate in standards:
        if _normalize_is_number(candidate.number) == wanted:
            return candidate

    raise HTTPException(
        status_code=404,
        detail=f"No standard found with id or IS number '{standard_id}'.",
    )


@app.get("/languages", summary="Supported Query Languages")
def list_languages():
    """Languages the UI can offer for queries.

    Served from the backend rather than hardcoded in the frontend, so the two
    cannot drift apart when a language is added or removed.
    """
    return {
        "languages": [
            {"code": code, "name": entry["name"], "native": entry["native"]}
            for code, entry in translation.SUPPORTED_LANGUAGES.items()
        ]
    }


class ExtractionResponse(BaseModel):
    """Text pulled out of an uploaded tender, plus the search built from it."""
    filename: str
    query: str = Field(..., description="The portion describing the goods, used as the search query.")
    text: str = Field(..., description="Full extracted text, so the user can check what was read.")
    char_count: int
    page_count: int = 0
    method: str = Field(..., description="How the text was obtained, e.g. 'pdf-text-layer'.")
    matched_section: Optional[str] = Field(
        default=None, description="Heading the query came from, when one was recognised."
    )
    warnings: List[str] = Field(default_factory=list)
    retrieval: RetrieveResponse = Field(..., description="Search results for the extracted query.")


@app.post(
    "/extract",
    response_model=ExtractionResponse,
    summary="Extract a Tender Document and Search",
)
async def extract_and_search(file: UploadFile = File(...), top_k: int = 10):
    """Accept a tender (PDF/DOCX/TXT), extract the specification, and search it.

    Runs the same pipeline as a typed query: the document only supplies the
    text. The full extracted text comes back too, so the user can verify what
    was read rather than trusting an invisible step.
    """
    data = await _read_upload(file)

    try:
        extracted = extraction.extract(file.filename or "upload", data)
    except extraction.ExtractionError as exc:
        # 422: the request was well-formed, the file was not usable. The
        # message is written for the user, so pass it through verbatim.
        raise HTTPException(status_code=422, detail=str(exc))

    retrieval = retrieve_standards_post(
        RetrieveRequest(query=extracted.query, top_k=top_k)
    )

    return ExtractionResponse(
        filename=file.filename or "upload",
        query=extracted.query,
        text=extracted.text,
        char_count=extracted.char_count,
        page_count=extracted.page_count,
        method=extracted.method,
        matched_section=extracted.matched_section,
        warnings=extracted.warnings,
        retrieval=retrieval,
    )


@app.get(
    "/standards/{standard_id}/amendments",
    summary="Published Amendments",
)
def get_amendments(standard_id: str):
    """Amendments for one standard.

    `status` is researched, found_in_text (read from the slips in the archived
    copy, current to `copy_as_of`: at least these, later ones may exist),
    none_in_copy (no slips in that copy, not a statement that none exist) or
    unchecked.
    """
    standard = get_standard(standard_id)  # reuses id/IS-number resolution and 404
    return {
        "number": standard.number,
        "title": standard.title,
        **amendments_data.for_standard(standard.number),
    }


@app.get(
    "/standards/{standard_id}/related",
    summary="Allied Standards Cluster",
)
def get_related(standard_id: str):
    """Standards this one cites, and standards in the corpus that cite it.

    `researched: false` means no relationships have been recorded for this
    standard, which is not a statement that it has none. Entries marked
    `outside_corpus` are real citations to standards the pilot corpus does not
    contain; they are listed so the cluster is not silently truncated.
    """
    standard = get_standard(standard_id)  # reuses id/IS-number resolution and 404
    result = relationships_data.related_to(standard.number)

    # Extracted links are stored without titles (there are ~88,000 of them),
    # so fill titles, and whether each target is current, from the corpus.
    by_number = _standards_by_number()
    for edge in [e for g in result["depends_on"] for e in g["standards"]] + result["referenced_by"]:
        held = by_number.get(edge["number"])
        if held is not None:
            edge["title"] = edge["title"] or held.title
            edge["status"] = held.status
            # The link was read when the catalogue lacked the standard; it
            # holds it now (a record added from BIS's list), so it can be opened.
            edge["outside_corpus"] = False

    # Related products: the standards closest in scope, which this one does
    # not cite. Scopes overlap, and choosing between neighbours is the choice
    # a tender has to get right.
    corpus = load_corpus()
    by_id = getattr(app.state, "corpus", None) or {s.id: s for s in corpus}
    cited = [e["number"] for g in result["depends_on"] for e in g["standards"]]
    neighbours = similar.similar_scope(standard, by_id, editions.for_corpus(corpus), exclude=cited)
    if neighbours:
        edges = [{
            "number": s.number, "title": s.title, "type": "related_product", "note": None,
            "outside_corpus": False, "method": "similar_scope", "status": s.status,
            "similarity": round(score, 3),
        } for s, score in neighbours]
        group = next((g for g in result["depends_on"] if g["type"] == "related_product"), None)
        if group is not None:
            group["standards"].extend(edges)
        else:
            result["depends_on"].append({
                "type": "related_product",
                "heading": "Related product standards",
                "explanation": (
                    "Standards whose scope is closest to this one's, found by comparing their text; "
                    "this standard does not cite them. Check which one fits the product being bought."
                ),
                "standards": edges,
            })

    return {
        "number": standard.number,
        "title": standard.title,
        **result,
    }


def _standards_by_number():
    """IS number -> Standard for the served corpus, built once and cached."""
    by_number = getattr(app.state, "by_number", None)
    if by_number is None:
        corpus = getattr(app.state, "corpus", None) or {s.id: s for s in load_corpus()}
        by_number = {s.number: s for s in corpus.values()}
        app.state.by_number = by_number
    return by_number


@app.get(
    "/standards/{standard_id}/certification",
    response_model=CertificationInfo,
    summary="Mandatory Certification Status",
)
def get_certification(standard_id: str):
    """Certification requirement for one standard, by id or IS number.

    Read from BIS's compulsory lists; `status` says whether an obligation is in
    force, deferred, related through another part, or absent. 'not_verified'
    appears only when the lists cannot be read, and is not a clearance.
    """
    standard = get_standard(standard_id)  # reuses id/IS-number resolution and 404
    return CertificationInfo(**certification.lookup(standard.number))


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
    verb = {"accept": "Accepted", "reject": "Dismissed", "correct": "Corrected"}.get(body.action, body.action)
    accounts.record_current(
        f"result.{body.action}",
        f'{verb} {body.chosen_id or body.corrected_id or "a result"} for "{body.query[:120]}"',
        {"query": body.query, "chosen_id": body.chosen_id, "corrected_id": body.corrected_id},
    )
    return {"status": "logged"}


@app.get(
    "/logs",
    response_model=List[Dict[str, Any]],
    summary="Get Recent Interaction Logs (Dev/Demo Endpoint)"
)
def get_recent_logs(request: Request, limit: int = 50):
    """Returns the last N lines from the JSONL file, most recent first.

    The raw feedback stream spans every user, so it is for administrators
    only. Each user's own actions are at /activity.
    """
    principal = request.scope.get("state", {}).get("principal")
    if accounts_api.auth_required() and (principal is None or principal.get("role") != "admin"):
        raise HTTPException(status_code=403, detail="Only a department administrator can read the raw logs.")
    safe_limit = max(1, min(limit, 500))
    return read_logs(limit=safe_limit)


@app.get(
    "/stats",
    response_model=StatsResponse,
    summary="Usage Statistics",
    description=(
        "Counts served searches and recorded feedback from the append-only logs. "
        "Every figure is counted, never estimated; synthetic bootstrap records are "
        "excluded from live counts and reported separately."
    ),
)
def get_stats(request: Request):
    """Dashboard figures, aggregated from the query and interaction logs.

    The counts cover the whole installation, which says nothing about anyone's
    work. The recent searches are text, and with registration open another
    organisation's queries must never show: for a signed-in caller they come
    from that caller's own activity trail.
    """
    stats = compute_stats()
    principal = request.scope.get("state", {}).get("principal")
    if principal is not None:
        mine = accounts.list_activity(principal, action="search.query", limit=10)["items"]
        stats["recent_queries"] = [
            {
                "query": item["meta"].get("query") or item["detail"].strip('"'),
                "standard": item["meta"].get("top"),
                "confidence": item["meta"].get("confidence") or "unknown",
                "score": None,
                "timestamp": item["at"],
            }
            for item in mine
        ]
    return StatsResponse(**stats)


@app.post(
    "/boq",
    response_model=BOQResponse,
    summary="Split a Bill of Quantities and Search Each Item",
    description=(
        "Reads a BOQ (PDF/DOCX/TXT), splits it into line items, and runs a separate "
        "search for each one. Returns is_boq=false when the document has no line-item "
        "structure, in which case /extract is the right endpoint."
    ),
)
async def analyse_boq(file: UploadFile = File(...), top_k: int = 5):
    """Per-line-item recommendations for a bill of quantities."""
    data = await _read_upload(file)

    try:
        extracted = extraction.extract(file.filename or "upload", data)
    except extraction.ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    line_items = extraction.split_line_items(extracted.text)

    items: List[LineItemResult] = []
    matched = 0
    for item in line_items:
        # Each item is a full retrieval: same ranking, same confidence gate,
        # same supersession rules as a typed query.
        retrieval = _retrieve(RetrieveRequest(query=item["query"], top_k=top_k))
        if retrieval.confidence != "none":
            matched += 1

        items.append(
            LineItemResult(
                sr=item["sr"],
                text=item["text"],
                query=item["query"],
                quantity=item.get("quantity"),
                results=retrieval.results,
                confidence=retrieval.confidence,
                confidence_reason=retrieval.confidence_reason,
            )
        )

    accounts.record_current(
        "document.boq",
        f"{file.filename or 'upload'}: {matched} of {len(items)} line items matched",
        {"filename": file.filename, "items": len(items), "matched": matched},
    )

    return BOQResponse(
        filename=file.filename or "upload",
        is_boq=bool(line_items),
        items=items,
        item_count=len(items),
        matched_count=matched,
        text=extracted.text,
        char_count=extracted.char_count,
        page_count=extracted.page_count,
        method=extracted.method,
        warnings=extracted.warnings,
        corpus_size=len(load_corpus()),
    )


@app.post(
    "/audit",
    response_model=AuditResponse,
    summary="Audit a Tender Document's Citations",
    description=(
        "Reads a tender (PDF/DOCX/TXT), finds the IS numbers it cites, and checks each "
        "against the corpus for supersession, amendments in force, undated citations and "
        "standards outside coverage. "
        "Checks only the citations the document already makes. Whether it cites the right "
        "standards for its goods is not assessed, so no findings is not a pass."
    ),
)
async def audit_tender(file: UploadFile = File(...)):
    """Audit the citations in an uploaded tender document."""
    data = await _read_upload(file)

    try:
        extracted = extraction.extract(file.filename or "upload", data)
    except extraction.ExtractionError as exc:
        # 422: well-formed request, unusable file. The message is written for
        # the user, so it passes through verbatim.
        raise HTTPException(status_code=422, detail=str(exc))

    result = audit_engine.audit_text(extracted.text)

    accounts.record_current(
        "document.audit",
        f"{file.filename or 'upload'}: {len(result.get('findings', []))} findings",
        {"filename": file.filename, "findings": len(result.get("findings", []))},
    )

    return AuditResponse(
        filename=file.filename or "upload",
        text=extracted.text,
        char_count=extracted.char_count,
        page_count=extracted.page_count,
        method=extracted.method,
        warnings=extracted.warnings,
        **result,
    )


@app.get(
    "/certification-rules",
    response_model=CertificationRulesResponse,
    summary="Standards under compulsory BIS certification",
    description=(
        "Every standard on BIS's lists of products under compulsory certification (ISI, "
        "CRS, Scheme X) and under BIS hallmarking, with the order, gazette notification and "
        "a link to the order, plus the codes of practice checked by hand. Deferred entries "
        "are named in an order whose enforcement is deferred and are not mandatory; voluntary "
        "ones have a BIS scheme that no order makes compulsory (silver hallmarking)."
    ),
)
def get_certification_rules():
    """The certification mapping, with its own coverage stated."""
    # BIS often lists a number without its edition ("IS 269"). Point each rule
    # at the edition the corpus holds, preferring the current one, so the
    # screen can open the standard.
    editions: Dict[tuple, List[Standard]] = {}
    for std in load_corpus():
        editions.setdefault(certification.family(std.number), []).append(std)

    def current(number: str) -> Optional[str]:
        found = editions.get(certification.family(number))
        if not found:
            return None
        found.sort(key=lambda s: (s.status != "superseded", s.number))
        return found[-1].number

    return CertificationRulesResponse(
        rules=[CertificationRule(**r, corpus_number=current(r["is_number"])) for r in certification.all_rules()],
        coverage=CertificationCoverage(**certification.coverage()),
    )


@app.get(
    "/alerts",
    response_model=AlertsResponse,
    summary="Standards-Hygiene Findings",
    description=(
        "Superseded editions and standards with published amendments in force, derived "
        "from the corpus and the amendment data. These are computed facts about the "
        "corpus, not a notification feed: nothing monitors BIS for new revisions, and "
        "no finding carries a timestamp."
    ),
)
def get_alerts(category: Optional[str] = None, summary: bool = False):
    """Findings that would change what a tender should cite.

    With the full archive this is ~2,240 findings (about 1.2 MB). Screens that
    only show counts pass summary=true and get the counts without the list.
    """
    data = alerts_data.findings(category=category)
    data["total_findings"] = len(data["findings"])
    if summary:
        data = {**data, "findings": []}
    return AlertsResponse(**data)


class AlertsCheckRequest(BaseModel):
    numbers: List[str] = Field(..., description="IS numbers to check, e.g. the standards in a spec basket.")


@app.post("/alerts/check", response_model=AlertsResponse, summary="Findings for specific standards")
def check_alerts(body: AlertsCheckRequest):
    """Only the findings for the standards named.

    The sidebar badge counts replaced editions in the officer's spec basket.
    It used to download every finding in the corpus on each page change to
    work that out; this answers for the handful of standards actually held.
    """
    wanted = set(body.numbers[:500])
    data = alerts_data.findings()
    picked = [f for f in data["findings"] if f["standard"] in wanted]
    return AlertsResponse(
        findings=picked,
        critical_count=sum(1 for f in picked if f["severity"] == "critical"),
        total_findings=len(picked),
        coverage=data["coverage"],
    )


@app.get(
    "/corpus-health",
    response_model=CorpusHealthResponse,
    summary="Corpus Metadata Completeness",
    description=(
        "Counts describing how complete the served corpus's own metadata is, "
        "supersession, certification and amendment coverage, and the sector spread."
    ),
)
def get_corpus_health():
    """How much of the corpus has been researched, counted per field."""
    return CorpusHealthResponse(**alerts_data.corpus_health())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

