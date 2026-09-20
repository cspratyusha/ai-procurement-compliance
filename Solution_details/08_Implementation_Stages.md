# Implementation Stages

Implementation is divided into ten stages. Stages 1–2 are foundational and block everything else. Stages 3–6 form the core engine. Stages 7–10 are the product and intelligence layers.

```
STAGE 1  Data Acquisition & Corpus Construction
STAGE 2  Data Modelling & Storage Setup
   ↓
STAGE 3  Semantic Retrieval Engine
STAGE 4  Knowledge Graph & Allied Standard Expansion
STAGE 5  Validation & Enrichment Layer
STAGE 6  LLM Reasoning & Generation Layer
   ↓
STAGE 7  Application & API Layer
STAGE 8  Frontend, Extension & Voice Interface
STAGE 9  Feedback Loop & Supervised LTR Layer
STAGE 10 Background Jobs, Alerts & Dashboard
```

---

## Stage 1 — Data Acquisition & Corpus Construction

**Objective:** Build the foundational standards dataset.

**Key tasks**
- Identify and scope the source: publicly available BIS standards catalogue metadata (standard number, title, scope/abstract, publication year, amendment list, cross-reference list). Full standard text is copyrighted — work with metadata, scopes and abstracts only.
- Build a scraper/parser for catalogue pages and published metadata listings.
- Select a focused demo domain: **2–4 product categories** covered deeply (e.g. steel and structural materials, PVC/pipes, electrical fittings, PPE/safety equipment) rather than shallow coverage of the entire corpus.
- Manually curate and verify the cross-reference relationships for the chosen categories — this is the highest-value manual effort in the entire project.
- Curate the certification mapping dataset (which product categories fall under BIS Product Certification, CRS, Hallmarking).
- Normalise all extracted data: consistent numbering format, date formats, status labels, category tagging.

**Expected output**
- A cleaned, normalised standards dataset for the chosen categories.
- A verified cross-reference/relationship table (standard → related standard, with relationship type).
- A certification rules mapping table.
- A documented ingestion script that can be re-run to refresh the corpus.

---

## Stage 2 — Data Modelling & Storage Setup

**Objective:** Stand up the four storage layers and the fan-out ingestion pipeline.

**Key tasks**
- Design and create the PostgreSQL schema (standards, amendments, certification rules, categories, users, orgs, subscriptions, aggregates).
- Design and create the Neo4j graph model (nodes and typed relationships).
- Set up the vector database and define the embedding record shape with metadata for filtered search.
- Build the BM25 keyword index.
- Build the fan-out ingestion pipeline: PostgreSQL as source of truth, with derived writes to Neo4j, vector DB, and keyword index.
- Implement a rebuild routine so derived stores can be regenerated from PostgreSQL if they drift.
- Set up the analytics/logging store schema for interaction records.

**Expected output**
- All four stores provisioned and populated with the Stage 1 corpus.
- A working, repeatable ingestion pipeline.
- Verified consistency between PostgreSQL and all derived stores.

---

## Stage 3 — Semantic Retrieval Engine

**Objective:** Given a text query, return a well-ranked candidate list of standards.

**Key tasks**
- Select and integrate a multilingual sentence-embedding model.
- Generate embeddings for all standards (title + scope + abstract) and load into the vector DB.
- Implement dense semantic search with metadata filtering.
- Implement BM25 sparse search.
- Implement the merge/de-duplication logic producing a unified candidate pool.
- Integrate a cross-encoder model for precision re-ranking of the shortlist.
- Build an internal evaluation set (a set of hand-labelled query → expected standard pairs for the chosen categories) to measure retrieval quality.
- Tune the dense/sparse weighting and candidate pool size against that evaluation set.

**Expected output**
- A retrieval service that accepts a query and returns ranked, scored candidate standards.
- Measured baseline accuracy (Precision@1, Recall@5) on the internal evaluation set.

---

## Stage 4 — Knowledge Graph & Allied Standard Expansion

**Objective:** Convert single-standard hits into complete standard clusters.

**Key tasks**
- Load the verified cross-reference relationships from Stage 1 into Neo4j as typed edges.
- Implement traversal queries: for a given standard, retrieve 1–2 hop neighbours filtered by relationship type.
- Implement graph centrality computation (used later as an LTR feature and for ambiguity resolution).
- Implement scope-overlap detection between candidate standards.
- Build the cluster-assembly service that groups expanded results by relationship type (normative / test method / terminology / safety / installation).
- Implement the supersession chain traversal.

**Expected output**
- A graph expansion service returning a structured, categorised standard cluster for any given standard.
- Overlap detection flagging competing-scope standards.
- Graph centrality scores available per standard.

---

## Stage 5 — Validation & Enrichment Layer

**Objective:** Apply deterministic correctness checks before anything reaches the user.

**Key tasks**
- Implement the freshness checker: resolve supersession chains, always return the current version, flag outdated references.
- Implement the certification mapper as a deterministic rules engine over the Stage 1 certification table.
- Implement the orphan detector: a configurable confidence threshold below which no recommendation is issued and the query is flagged as a potential standards-landscape gap.
- Implement the trust-score module: correlate standards with any available dispute/rejection history data; degrade gracefully (omit score) where no data exists.
- Implement the overlap flagging output format.

**Expected output**
- A validation service that annotates every candidate with version status, certification requirement, overlap flags, and trust score.
- A functioning orphan-query path that refuses to return low-confidence recommendations.

---

## Stage 6 — LLM Reasoning & Generation Layer

**Objective:** Produce human-readable, defensible output from verified data.

**Key tasks**
- Design the grounding contract: the LLM receives only retrieved and validated standards as context, with explicit instructions that it must not introduce standards, versions, or certification claims outside that context.
- Implement the explanation generator ("why this standard was recommended").
- Implement the plain-language version-diff summariser.
- Implement the impact estimator for gaps and outdated citations.
- Implement the specification clause generator (standard + version + certification requirement, formatted as tender-ready text).
- Implement multilingual response rendering.
- Build a hallucination guard: post-process LLM output to verify every standard number mentioned exists in the provided context; reject and regenerate if not.

**Expected output**
- A reasoning service producing explanations, diffs, impact estimates, and clause drafts.
- A verified hallucination guard with test cases demonstrating it catches out-of-context standard references.

---

## Stage 7 — Application & API Layer

**Objective:** Orchestrate the pipeline and expose it for both UI and machine consumption.

**Key tasks**
- Build the orchestrator service sequencing preprocessing → retrieval → ranking → expansion → validation → reasoning → assembly.
- Implement the preprocessing service (document parsing, OCR, language detection, translation, speech-to-text routing).
- Build the authentication and RBAC service (JWT, four roles, org association).
- Define and implement the public REST API surface: recommend, audit, certification-check, standard-detail, graph-expand, feedback.
- Implement API key management for portal/ERP integrators.
- Implement structured response assembly and asynchronous interaction logging.
- Add rate limiting and request validation at the gateway.

**Expected output**
- A working end-to-end API: query in → full structured recommendation out.
- Documented, versioned public API endpoints.
- Functioning role-based access control.

---

## Stage 8 — Frontend, Extension & Voice Interface

**Objective:** Deliver the user-facing surfaces.

**Key tasks**
- Build the web application: login, dashboard home, new specification query, result view with recommendation cards, standards explorer with graph visualisation, scenario simulator, settings.
- Implement the interactive graph visualisation for standard clusters with incremental node expansion.
- Build audit mode: document upload, gap report view, track-changes redline rendering, one-click fix application, corrected-document export.
- Build the scenario simulator UI: parameter controls and delta view against the base cluster.
- Implement voice input capture and routing.
- Build the Chrome extension: field detection on portal tender forms, authenticated API calls, inline suggestion panel, clause insertion into the form field.
- Implement multilingual UI rendering.

**Expected output**
- A complete, usable web application covering every feature.
- A working Chrome extension demonstrating inline suggestion and clause insertion on a portal form.
- Voice query working end-to-end in at least two languages.

---

## Stage 9 — Feedback Loop & Supervised LTR Layer

**Objective:** Make the system improve with usage.

**Key tasks**
- Implement feedback capture in the UI and API (accept / reject / correct / edit).
- Ensure interaction records capture the full candidate set with per-stage scores — the LTR layer is impossible without this.
- Build the training-set builder: group interactions by query, assign labels from user actions, assemble feature vectors.
- Implement the LTR model training pipeline (LightGBM/XGBoost ranker).
- Implement evaluation against held-out data using NDCG@k, MRR, Precision@1.
- Implement model versioning and a promotion gate (new model serves only if it beats the incumbent).
- Wire the LTR model into the pipeline as a pass-through-capable stage (functions correctly with no model present).
- Add historical acceptance rate as a live inference feature computed from the analytics store.

**Expected output**
- A closed feedback loop from user action to training data.
- A trainable, evaluable, versioned LTR model integrated into the ranking pipeline.
- Demonstrated ranking improvement on a simulated or collected feedback set.

---

## Stage 10 — Background Jobs, Alerts & Dashboard

**Objective:** Deliver continuous monitoring and organisational oversight.

**Key tasks**
- Implement the scheduled standards revision checker with diffing against current state.
- Implement propagation of detected changes across all four stores.
- Implement the subscription matching engine and notification dispatch (in-app + email).
- Implement the scheduled LTR retraining job.
- Build the dashboard aggregation job producing pre-computed metrics.
- Build the compliance dashboard UI: outdated-citation rate, gap trends, category distribution, certification compliance rate, orphan-query volume, with drill-down.
- Implement the audit trail view with version-stamped recommendation history.
- Implement anonymised peer-comparison metrics where enabled.

**Expected output**
- Automated revision detection with working alerts.
- A populated compliance dashboard with drill-down to underlying tenders.
- An accessible, exportable audit trail.
- Scheduled retraining running on a defined cadence.

---

## Dependency Map

```
Stage 1 ──▶ Stage 2 ──┬──▶ Stage 3 ──┐
                      ├──▶ Stage 4 ──┼──▶ Stage 6 ──▶ Stage 7 ──▶ Stage 8
                      └──▶ Stage 5 ──┘                    │
                                                          ├──▶ Stage 9
                                                          └──▶ Stage 10
```

- Stages 3, 4, and 5 can be developed in parallel once Stage 2 is complete.
- Stage 9 requires Stage 7 and 8 to exist (feedback needs an interface to be captured from).
- Stage 10 requires Stage 2 (stores) and Stage 7 (API), but is independent of Stage 9.

---

## Scope Recommendation

Build the **full vertical pipeline for a narrow domain** rather than partial coverage of everything. Two to four product categories with complete graph relationships, certification mapping, validation, explanation, audit mode, and dashboard will demonstrate far more capability than thousands of standards with only keyword search. Scalability is then an argued property of the architecture — which the retrieval-based, no-retraining-required design supports directly.
