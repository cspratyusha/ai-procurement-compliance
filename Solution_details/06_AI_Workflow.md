# AI Workflow

## 1. AI Layer Overview

The system uses **four distinct AI/ML stages**, each with a different job. No single model does everything — this is deliberate, because compliance output requires traceability and each stage is independently verifiable.

```
Stage 1: EMBEDDING & RETRIEVAL        → find plausible candidates
Stage 2: CROSS-ENCODER RE-RANKING     → score precise relevance
Stage 3: LEARNED RE-RANKER (LTR)      → apply real-world usage patterns
Stage 4: LLM REASONING & GENERATION   → explain, summarise, draft
```

---

## 2. Stage 1 — Embedding & Hybrid Retrieval

**Purpose:** Convert meaning into searchable form and produce a candidate pool.

**Offline (indexing):**
- Each standard's title, scope, and abstract is embedded into a dense vector.
- Vectors stored in the vector database with metadata (standard number, category, version, sector).
- A parallel BM25 keyword index is built over the same text.

**Online (query time):**
- User query is embedded with the same multilingual model.
- Dense search returns semantically similar standards.
- BM25 search returns exact-term matches (material grades, partial IS numbers, technical nomenclature).
- Results merged and de-duplicated into a candidate pool of top N.

**Why hybrid:** dense search alone misses exact technical identifiers; sparse search alone misses paraphrasing and vernacular terms. Together they cover both failure modes.

---

## 3. Stage 2 — Cross-Encoder Re-Ranking

**Purpose:** Precision refinement over the candidate pool.

Bi-encoder retrieval (Stage 1) encodes query and document separately, which is fast but approximate. A cross-encoder processes the query and each candidate *together*, producing a far more accurate relevance score — but it is too slow to run over the entire corpus, which is why it runs only over the shortlist.

**Output:** re-ordered candidate list with fine-grained relevance scores.

---

## 4. Stage 3 — Learned Re-Ranker (Supervised ML Layer)

### 4.1 Why a supervised layer is added here and not earlier

A supervised classifier cannot be the *core* engine because:
- No labelled (query → correct standard) dataset exists at project start.
- Collaborative filtering is inapplicable — this is a correctness problem, not a preference problem; "popular" standards are not necessarily correct ones.
- Classifiers are fixed to trained classes; new standards would require full retraining.
- Classification output is not natively explainable, which is disqualifying in an audit context.

But once the system is in use, it *generates* exactly the labelled data a supervised model needs — so the supervised layer is introduced as a **refinement stage on top of retrieval**, not a replacement for it.

### 4.2 Position in the pipeline

```
Retrieval → Cross-encoder → [LEARNED RE-RANKER] → Graph expansion → Validation → LLM
```

### 4.3 Lifecycle

**Phase 0 — Cold start (day 1):**
No feedback data exists. The LTR layer operates as a pass-through; the system runs fully on retrieval + cross-encoder. The product is completely functional without it.

**Phase 1 — Data collection:**
Every interaction is logged with full context:

| Logged | Purpose |
|---|---|
| Original query (normalised) | Input features |
| All candidates shown | Negative examples |
| Scores at each stage | Input features |
| Candidate accepted by user | Positive label |
| Candidates rejected | Negative labels |
| Manual correction (user-substituted standard) | Strong positive label |

**Phase 2 — Training:**
A Learning-to-Rank model (LightGBM Ranker / XGBoost with ranking objective, LambdaMART-style) is trained on grouped query-candidate sets.

**Feature set:**

| Feature | Source |
|---|---|
| Dense semantic similarity score | Vector DB |
| BM25 keyword overlap score | Keyword index |
| Cross-encoder relevance score | Stage 2 |
| Graph centrality / connection count | Neo4j |
| Freshness indicator (latest vs superseded) | PostgreSQL |
| Historical acceptance rate for this standard | Analytics store |
| Category match between query and standard | PostgreSQL + query classifier |
| Certification-relevance match | Certification rules |

**Phase 3 — Evaluation & promotion:**
Each retrained model is evaluated on a held-out set using ranking metrics (NDCG@k, MRR, Precision@1). A new model is promoted only if it beats the incumbent. Models are versioned so a degrading retrain can be rolled back.

**Phase 4 — Scheduled retraining:**
A background job retrains periodically on accumulated feedback, closing the loop.

### 4.4 Why this is a strong design

- Solves the cold-start problem explicitly rather than pretending it doesn't exist.
- Improves accuracy using users' own corrections at **zero additional labelling cost**.
- Keeps the system functional and correct before any ML training has occurred.
- Demonstrates a complete MLOps lifecycle: log → accumulate → train → evaluate → promote → retrain.

---

## 5. Stage 4 — LLM Reasoning & Generation

**Purpose:** Turn verified structured results into human-usable output.

**Strictly grounded:** The LLM receives only the retrieved, graph-expanded, and validated standards as context. It is not permitted to introduce standard numbers, versions, or certification claims that did not come from the data layer. This is the core hallucination control.

**Tasks performed:**

| Task | Output |
|---|---|
| Relevance explanation | "Why this standard was recommended" in plain language |
| Version diff summarisation | "IS X:2022 supersedes IS X:1983 — key changes: …" |
| Impact estimation | Plain-language consequence of a gap or outdated citation |
| Clause generation | Ready-to-paste specification clause referencing correct standard + version + certification |
| Multilingual response | Output rendered in the user's query language |
| Query understanding (simulator) | Converting use-case parameters into structured retrieval context |

**What the LLM explicitly does NOT do:**
- Decide which standard applies (retrieval + graph does that)
- Determine certification requirements (deterministic rules do that)
- Determine version currency (metadata does that)

---

## 6. Non-LLM Deterministic Logic (Intentionally Not AI)

Certain functions are kept rules-based because probabilistic output is unacceptable:

| Function | Why deterministic |
|---|---|
| Certification requirement mapping | Legal consequence; must be exact |
| Version/supersession resolution | Factual metadata lookup, not inference |
| Orphan-query threshold enforcement | Safety gate; must be predictable |
| Audit trail construction | Must be reproducible and tamper-evident |

---

## 7. AI Workflow Diagram

```
                       ┌──────────────────┐
   User Query  ───────▶│  Preprocessing   │  (OCR, lang detect, speech→text)
                       └────────┬─────────┘
                                │ normalised query
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
   ┌────────────────────┐              ┌────────────────────┐
   │ Embedding Model    │              │  BM25 Keyword      │
   │ → Vector DB search │              │  Index search      │
   └─────────┬──────────┘              └─────────┬──────────┘
             └──────────────┬────────────────────┘
                            ▼
                  ┌───────────────────┐
                  │ Merged Candidates │
                  └─────────┬─────────┘
                            ▼
                  ┌───────────────────┐
                  │  Cross-Encoder     │  precision re-ranking
                  │  Re-Ranker         │
                  └─────────┬─────────┘
                            ▼
                  ┌───────────────────┐        ┌──────────────────┐
                  │  Learned LTR       │◀───────│ Feedback-trained │
                  │  Re-Ranker         │        │ model (versioned)│
                  └─────────┬─────────┘        └──────────────────┘
                            ▼
                  ┌───────────────────┐
                  │  Graph Expansion   │  allied standards cluster
                  └─────────┬─────────┘
                            ▼
                  ┌───────────────────┐
                  │  Deterministic     │  freshness · certification ·
                  │  Validation Layer  │  overlap · trust · orphan gate
                  └─────────┬─────────┘
                            ▼
                  ┌───────────────────┐
                  │  LLM Reasoning &   │  explanations · diffs ·
                  │  Generation        │  impact · clause draft
                  └─────────┬─────────┘
                            ▼
                    Structured Response
                            │
                            ▼
                  ┌───────────────────┐
                  │  User Feedback     │──▶ Analytics Store ──▶ LTR retraining
                  │  (accept/reject/   │
                  │   correct)         │
                  └───────────────────┘
```
