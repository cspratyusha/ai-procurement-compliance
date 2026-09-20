# Architecture

## 1. High-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          USER / CONSUMER LAYER                            │
│   Govt Departments  │  PSEs  │  Procurement Agencies  │  Private Orgs     │
└────────┬────────────┬────────────┬────────────┬────────────┬─────────────┘
         │            │            │            │            │
    ┌────▼────┐  ┌────▼─────┐ ┌────▼────┐ ┌─────▼─────┐ ┌────▼──────────┐
    │ Web App │  │  Chrome   │ │  Voice  │ │ Public    │ │ GeM / State   │
    │ (React) │  │ Extension │ │  Input  │ │ REST API  │ │ Portal / ERP  │
    └────┬────┘  └────┬─────┘ └────┬────┘ └─────┬─────┘ └────┬──────────┘
         └────────────┴────────────┴────────────┴────────────┘
                                  │
                    ══════════════▼══════════════
                    ║   API GATEWAY / EDGE       ║
                    ║  rate limiting, routing     ║
                    ══════════════╤══════════════
                                  │
                    ┌─────────────▼──────────────┐
                    │  AUTH & ROLE MANAGEMENT     │
                    │  JWT · RBAC · Org profiles  │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │   APPLICATION LAYER         │
                    │   (FastAPI orchestrator)     │
                    └─────────────┬──────────────┘
                                  │
┌─────────────────────────────────┼─────────────────────────────────────┐
│                        AI / PROCESSING LAYER                           │
│                                  │                                     │
│  ┌──────────────┐  ┌─────────────▼────────────┐  ┌─────────────────┐  │
│  │ Preprocessing │  │   Retrieval Engine        │  │ Graph Expansion │  │
│  │ • OCR/parse   │─▶│  • Dense (embeddings)     │─▶│ • Normative refs│  │
│  │ • Lang detect │  │  • Sparse (BM25)          │  │ • Test methods  │  │
│  │ • Translate   │  │  • Cross-encoder rerank   │  │ • Safety/instal.│  │
│  │ • Speech→Text │  │  • Learned LTR reranker   │  │ • Terminology   │  │
│  └──────────────┘  └─────────────┬────────────┘  └────────┬────────┘  │
│                                  │                         │            │
│              ┌───────────────────▼─────────────────────────▼─────────┐ │
│              │        VALIDATION & ENRICHMENT LAYER                   │ │
│              │  Freshness Check │ Certification Mapper │ Overlap      │ │
│              │  Trust Score     │ Orphan Detector      │ Detector     │ │
│              └───────────────────┬────────────────────────────────────┘ │
│                                  │                                       │
│              ┌───────────────────▼────────────────────────┐             │
│              │      LLM REASONING & GENERATION LAYER       │             │
│              │  • "Why recommended" explanation            │             │
│              │  • Plain-language version diff              │             │
│              │  • Impact estimate                          │             │
│              │  • Specification clause draft               │             │
│              │  (grounded strictly on verified data)       │             │
│              └───────────────────┬────────────────────────┘             │
└──────────────────────────────────┼──────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│                           DATA LAYER                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │ PostgreSQL │  │   Neo4j     │  │ Vector DB   │  │ Analytics /      │  │
│  │ metadata,  │  │ standards   │  │ embeddings  │  │ Logging Store    │  │
│  │ versions,  │  │ relationship│  │ of scopes/  │  │ audit trail,     │  │
│  │ cert rules,│  │ graph       │  │ titles      │  │ feedback, LTR    │  │
│  │ users      │  │             │  │             │  │ training data    │  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│                     BACKGROUND / ASYNC LAYER                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│  │ Standards Sync   │  │ LTR Model         │  │ Notification       │    │
│  │ & Revision Check │─▶│ Retraining Job    │  │ Service            │    │
│  │ (scheduled)      │  │ (scheduled)       │  │ (email + in-app)   │    │
│  └──────────────────┘  └──────────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. System Components

### 2.1 Consumer Layer

| Component | Responsibility |
|---|---|
| **Web Application** | Primary UI — query, audit, dashboard, graph visualisation, scenario simulator |
| **Chrome Extension** | Injects inline suggestions into GeM/state portal tender forms |
| **Voice Input Module** | Captures speech, routes to speech-to-text in preprocessing |
| **Public REST API** | Machine-to-machine access for portals and ERPs |

### 2.2 Gateway & Access Control

| Component | Responsibility |
|---|---|
| **API Gateway** | Routing, rate limiting, request logging, API key validation for external portals |
| **Auth & Role Management** | Credential validation, JWT issuance, RBAC enforcement (Officer / PSE Admin / Agency Integrator / Private User), org profile resolution |

### 2.3 Application Layer

| Component | Responsibility |
|---|---|
| **Orchestrator (FastAPI)** | Sequences the pipeline, aggregates sub-service responses, assembles final structured payload, writes logs |

### 2.4 AI / Processing Layer

| Component | Responsibility |
|---|---|
| **Preprocessing Service** | File parsing/OCR, language detection, translation, speech-to-text, query normalisation |
| **Retrieval Engine** | Dense + sparse candidate retrieval, cross-encoder re-ranking, learned LTR re-ranking |
| **Graph Expansion Service** | Traverses standards graph to surface allied/normative/test/safety/installation standards |
| **Validation & Enrichment Layer** | Freshness/supersession check, certification mapping, overlap detection, trust scoring, orphan-query detection |
| **LLM Reasoning Layer** | Generates explanations, version diffs, impact estimates, and draft clause text — grounded only on verified retrieved data |

### 2.5 Data Layer

| Store | Holds |
|---|---|
| **PostgreSQL** | Standard metadata (number, title, scope, dates, version), certification rules, user/org records, subscriptions |
| **Neo4j** | Standard-to-standard relationship graph (normative refs, supersession, test methods, category links) |
| **Vector Database** | Embeddings of standard titles/scopes/abstracts for semantic retrieval |
| **Analytics / Logging Store** | Query logs, candidate sets, scores, user actions, audit trail, LTR training data |

### 2.6 Background Layer

| Component | Responsibility |
|---|---|
| **Standards Sync & Revision Checker** | Scheduled check for new revisions/amendments; updates stores; triggers alerts |
| **LTR Retraining Job** | Periodically retrains the learned re-ranker on accumulated feedback; versions and evaluates before promotion |
| **Notification Service** | Delivers in-app and email alerts to subscribed users/orgs |

---

## 3. How Components Interact

1. **Request entry** — any consumer (web app, extension, voice, API, portal) hits the API Gateway.
2. **Gateway → Auth** — token/API key validated; role and org context attached to the request.
3. **Auth → Orchestrator** — authorised request passed to the application layer with user context.
4. **Orchestrator → Preprocessing** — raw input normalised into a clean, language-normalised query string.
5. **Orchestrator → Retrieval Engine** — normalised query embedded and searched against Vector DB (dense) and keyword index (sparse); candidates merged, re-ranked by cross-encoder, then re-ordered by the LTR model.
6. **Orchestrator → Graph Expansion** — top candidates sent to Neo4j; allied standard clusters returned.
7. **Orchestrator → Validation & Enrichment** — PostgreSQL consulted for version/supersession status and certification rules; overlap detector and trust scorer applied; orphan check applied against confidence threshold.
8. **Orchestrator → LLM Reasoning** — verified, enriched result set passed as grounding context; explanations, diffs, impact estimates, and clause drafts generated.
9. **Orchestrator → Response Assembly** — single structured JSON returned to the originating consumer.
10. **Orchestrator → Logging Store** — full interaction written asynchronously (query, candidates, scores, final output).
11. **User action → Logging Store** — accept/reject/correct events appended, becoming LTR training labels.
12. **Background jobs** — read from the Logging Store (retraining) and the Standards stores (revision checks), and push to the Notification Service.

---

## 4. Architectural Guarantees

| Guarantee | Enforced By |
|---|---|
| No hallucinated standard numbers | LLM receives only retrieved, verified standards as context; it cannot introduce new ones |
| No confident wrong answers | Orphan detector blocks low-confidence forced recommendations |
| Legal correctness of certification info | Deterministic rules engine, not ML inference |
| Defensibility under audit | Full immutable interaction log with version stamps |
| New standards without retraining | Retrieval-based core — add embedding + graph node, no model retrain required |
| Graceful cold start | LTR layer is pass-through until feedback data exists |
