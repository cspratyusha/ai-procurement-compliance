# Technology Stack

## 1. Stack by Layer

| Layer | Technology | Why this choice |
|---|---|---|
| **Frontend** | React | Component model suits the card/graph/dashboard-heavy UI; large ecosystem for visualisation |
| **Graph visualisation** | react-force-graph or vis.js | Interactive, incrementally loadable node-link rendering for standard clusters |
| **Charting** | Recharts or Chart.js | Lightweight dashboard charts; integrates cleanly with React |
| **Browser extension** | Chrome Extension APIs (content script injection) | Only viable way to overlay suggestions inside existing portal forms |
| **Backend / API** | FastAPI (Python) | Native to the ML/retrieval stack, avoiding cross-language service hops; async support; auto-generated API docs for portal integrators |
| **Authentication** | JWT + role-based access control | Stateless, integrates with existing departmental SSO if available |
| **Document parsing** | PyMuPDF / pdfplumber (text PDFs), Tesseract (scanned) | Handles both digital and scanned tender documents |
| **Embedding model** | Multilingual sentence-transformer | Single model serves English, Hindi, and regional queries without a separate translation step |
| **Vector database** | FAISS or Chroma (self-hosted) | Fast, no external dependency, sufficient for the target corpus size; swappable for Weaviate/Pinecone at scale |
| **Sparse search** | BM25 (rank-bm25 or Elasticsearch) | Exact technical term and partial standard-number matching |
| **Cross-encoder re-ranker** | Sentence-transformers cross-encoder | Precision refinement over the retrieved shortlist |
| **Supervised re-ranker** | LightGBM Ranker / XGBoost (ranking objective) | Purpose-built for learning-to-rank; trains well on small feedback datasets; fast inference |
| **Graph database** | Neo4j (Cypher) | Native multi-hop traversal for allied-standard discovery; NetworkX is a viable lighter fallback |
| **Relational database** | PostgreSQL | Source of truth for metadata, versions, certification rules, users |
| **Analytics store** | PostgreSQL (separate schema/instance) | Append-heavy logging isolated from transactional reads |
| **LLM reasoning** | Claude / GPT API, context-grounded | Explanation, diff summarisation, impact estimation, clause drafting — with strict grounding |
| **Speech-to-text** | Multilingual STT API | Voice query support for regional and field offices |
| **Background jobs** | Celery + Redis | Scheduled revision checks, retraining, aggregation, notification dispatch |
| **Notifications** | SMTP / SendGrid + in-app queue | Alert delivery for subscribed categories |
| **Containerisation** | Docker + Docker Compose | Reproducible multi-service environment (API, Neo4j, Postgres, Redis, vector DB) |

---

## 2. Why These Combinations Work Together

**Python-native end to end (FastAPI + ML stack).**
The retrieval, re-ranking, and preprocessing components are all Python libraries. Choosing a Python backend eliminates inter-service serialisation overhead and a second runtime to maintain.

**PostgreSQL as source of truth, everything else derived.**
Neo4j, the vector DB, and the keyword index are all rebuildable projections. This avoids the common multi-database drift problem and makes the ingestion pipeline the single write path.

**FAISS/Chroma over managed vector DBs initially.**
Self-hosted keeps the whole system runnable offline and deployable inside government infrastructure — a genuine requirement for public-sector adoption where external data egress may be restricted. The interface is abstracted so a managed store can replace it at scale.

**Cross-encoder + LTR as separate stages.**
The cross-encoder provides quality from day one with no training data. The LTR model adds usage-derived refinement later. Keeping them separate means the system is never dependent on data it doesn't yet have.

**Deterministic rules engine alongside ML.**
Certification and version logic run in PostgreSQL as plain queries, not inference. This is a deliberate architectural boundary: probabilistic components handle discovery, deterministic components handle legal correctness.

**LLM as the last stage only.**
Placing generation after validation means the LLM can only ever describe verified data. Reversing this order — LLM first, verification after — is the standard failure pattern in compliance AI tools, and this architecture structurally prevents it.

---

## 3. Deployment Considerations

| Concern | Approach |
|---|---|
| **Government infrastructure constraints** | Self-hostable stack; no mandatory external services except the LLM API (which can be swapped for a self-hosted open model if data residency requires it) |
| **Low-bandwidth offices** | Progressive web app with cached standard summaries for offline lookup |
| **Portal integration** | Versioned REST API with API key auth; no requirement for the portal to adopt the UI |
| **Data residency** | All standards data and interaction logs remain in the deployed environment |
| **Scale path** | Vector store swappable to a managed service; retrieval and reasoning services horizontally scalable behind the gateway; Postgres read replicas for dashboard load |
