# Database Design, Data Flow & AI Pipeline Integration

## 1. Storage Layers and Their Roles

| Store | Type | Holds | Why this store |
|---|---|---|---|
| **PostgreSQL** | Relational | Standard metadata, version history, certification rules, users, orgs, subscriptions, pre-aggregated dashboard metrics | Exact, transactional, queryable facts that must never be approximate |
| **Neo4j** | Graph | Standard-to-standard relationships | Allied/normative discovery is inherently a traversal problem; SQL joins scale badly for multi-hop relationship queries |
| **Vector Database** | Vector | Embeddings of standard titles, scopes, abstracts | Enables semantic similarity search |
| **Keyword Index** | Inverted index | Tokenised standard text | Exact technical term and partial-number matching |
| **Analytics / Logging Store** | Relational or columnar | Query logs, candidate sets, scores, user actions, audit trail, LTR training data | Append-heavy, analytical workload — separated so it never contends with transactional reads |

---

## 2. Core Data Model

### 2.1 PostgreSQL — key entities

```
standards
  ├── standard_id (PK)
  ├── standard_number          (e.g. IS 456)
  ├── title
  ├── scope_text
  ├── year_published
  ├── current_version
  ├── reaffirmation_date
  ├── status                   (active / superseded / withdrawn)
  ├── superseded_by_id         (FK → standards)
  ├── product_category_id      (FK)
  └── sector

amendments
  ├── amendment_id (PK)
  ├── standard_id (FK)
  ├── amendment_number
  ├── date_issued
  └── change_summary

certification_rules
  ├── rule_id (PK)
  ├── product_category_id (FK)
  ├── standard_id (FK, nullable)
  ├── scheme_type              (BIS Product Cert / CRS / Hallmarking)
  └── mandatory_flag

product_categories
  ├── category_id (PK)
  ├── name
  └── parent_category_id

users / organisations / subscriptions
  └── (auth, role, org association, alert category subscriptions)

dashboard_aggregates
  └── (pre-computed metrics refreshed on schedule)
```

### 2.2 Neo4j — graph model

**Nodes**
- `Standard` (standard_id, number, title, status)
- `ProductCategory`
- `CertificationScheme`

**Relationships**
```
(Standard)-[:NORMATIVE_REFERENCE]->(Standard)
(Standard)-[:TEST_METHOD_FOR]->(Standard)
(Standard)-[:TERMINOLOGY_FOR]->(Standard)
(Standard)-[:SAFETY_REQUIREMENT_FOR]->(Standard)
(Standard)-[:INSTALLATION_GUIDE_FOR]->(Standard)
(Standard)-[:SUPERSEDED_BY]->(Standard)
(Standard)-[:OVERLAPS_SCOPE_WITH]->(Standard)
(Standard)-[:BELONGS_TO]->(ProductCategory)
(Standard)-[:REQUIRES_CERTIFICATION]->(CertificationScheme)
```

The graph holds **relationships and identifiers only**; full descriptive metadata stays in PostgreSQL. This avoids duplicating the source of truth.

### 2.3 Vector Database — record shape

```
{
  vector:     [embedding of title + scope + abstract],
  metadata: {
    standard_id, standard_number, category_id,
    sector, status, version
  }
}
```

Metadata is duplicated intentionally so filters can be applied *during* vector search rather than after, improving both speed and precision.

### 2.4 Analytics Store — interaction record

```
interaction
  ├── interaction_id
  ├── user_id, org_id, timestamp
  ├── normalised_query
  ├── input_mode              (text / file / voice / api / extension)
  ├── candidates_shown        [{standard_id, dense_score, bm25_score,
  │                             cross_encoder_score, ltr_score, rank}]
  ├── cluster_returned        [standard_ids]
  ├── flags_raised            (outdated / certification / overlap / orphan)
  ├── user_action             (accepted / rejected / corrected / ignored)
  ├── corrected_to_standard_id
  └── response_version_stamp
```

This single record simultaneously serves **three purposes**: audit trail, dashboard source data, and LTR training data. Designing it once for all three avoids three parallel logging systems.

---

## 3. Data Flow: Ingestion Pipeline (Offline / Scheduled)

```
[Source: BIS public standards catalogue / official metadata]
            │
            ▼
   ┌──────────────────┐
   │  Scraper/Parser  │  extract number, title, scope, version,
   │                  │  amendment list, cross-reference list
   └────────┬─────────┘
            ▼
   ┌──────────────────┐
   │  Normalisation   │  standardise numbering formats, dates,
   │  & Validation    │  category tagging, dedupe
   └────────┬─────────┘
            ▼
   ┌────────────────────────────────────────────┐
   │              FAN-OUT WRITE                  │
   ├──────────────┬──────────────┬──────────────┤
   ▼              ▼              ▼              ▼
PostgreSQL     Neo4j        Embedding      Keyword
(metadata,   (relationship   Generator →    Indexer →
 versions,    edges from     Vector DB      BM25 Index
 cert rules)  cross-ref list)
```

**Consistency rule:** PostgreSQL is the **single source of truth**. Neo4j, the vector DB, and the keyword index are all derived projections. If they diverge, they are rebuilt from PostgreSQL — never the reverse. This prevents the classic multi-store drift problem.

---

## 4. Data Flow: Query-Time (Online)

```
USER QUERY
    │
    ▼
Preprocessing ──────────────────────────────────┐
    │ normalised query                          │
    ├──────────────┬──────────────┐             │
    ▼              ▼              │             │
Embedding      BM25 lookup        │             │
    │              │              │             │
    ▼              ▼              │             │
VECTOR DB      KEYWORD INDEX      │             │
    │ candidates   │ candidates   │             │
    └──────┬───────┘              │             │
           ▼                      │             │
     Merged pool                  │             │
           │                      │             │
           ▼                      │             │
   Cross-encoder rerank           │             │
           │                      │             │
           ▼                      │             │
   LTR rerank ◀───────────────────┘             │
   (reads historical acceptance rates           │
    from ANALYTICS STORE)                       │
           │                                    │
           ▼                                    │
   NEO4J traversal ──▶ allied standard cluster  │
           │                                    │
           ▼                                    │
   POSTGRESQL lookup ──▶ version status,        │
           │             amendments,            │
           │             certification rules,   │
           │             overlap flags          │
           ▼                                    │
   Trust score ◀── ANALYTICS STORE (dispute correlation)
           │
           ▼
   LLM grounding context assembled
           │
           ▼
   Response returned
           │
           ▼
   WRITE interaction record ──▶ ANALYTICS STORE
```

---

## 5. Data Flow: Feedback → Model Improvement

```
User accepts / rejects / corrects a recommendation
            │
            ▼
   Interaction record updated in ANALYTICS STORE
            │
            ▼ (scheduled batch job)
   ┌──────────────────────────┐
   │ Training-set builder      │  group by query, label candidates,
   │                           │  assemble feature vectors
   └────────────┬─────────────┘
                ▼
   ┌──────────────────────────┐
   │ LTR model training        │  LightGBM/XGBoost ranker
   └────────────┬─────────────┘
                ▼
   ┌──────────────────────────┐
   │ Evaluation (NDCG, MRR,    │  held-out set
   │ Precision@1)              │
   └────────────┬─────────────┘
                ▼
        Beats incumbent?
         ┌──────┴──────┐
        Yes            No
         │              │
         ▼              ▼
   Promote to      Retain current
   serving         model, log result
   (versioned)
```

Historical acceptance rates computed from the same store are also fed back as a **live feature** during inference — so the system benefits from feedback even between retraining cycles.

---

## 6. Data Flow: Revision Monitoring & Alerts

```
Scheduler (periodic)
    │
    ▼
Poll standards source for new revisions/amendments
    │
    ▼
Diff against PostgreSQL current state
    │
    ├── new/changed standard detected
    │        │
    │        ▼
    │   Update PostgreSQL → propagate to Neo4j,
    │   re-embed into Vector DB, re-index BM25
    │        │
    │        ▼
    │   Match affected category against SUBSCRIPTIONS
    │        │
    │        ▼
    │   Notification Service → in-app + email
    │        │
    │        ▼
    │   Recompute "outdated citation" dashboard aggregates
    │
    └── no change → exit
```

---

## 7. Data Flow: Audit Mode

```
Uploaded tender document
    │
    ▼
Parser/OCR → raw text
    │
    ▼
Standard-reference extraction (pattern matching + NER on IS numbers)
    │
    ▼
For each extracted standard:
    ├── POSTGRESQL → is this the current version? superseded?
    ├── POSTGRESQL → certification rules triggered?
    └── NEO4J      → which companion standards are MISSING from this doc?
    │
    ▼
Gap set compiled with severity tags
    │
    ▼
LLM → impact estimate per gap + corrected clause text
    │
    ▼
Redline diff rendered over original document
    │
    ▼
Interaction record written to ANALYTICS STORE
```

---

## 8. Database & AI Pipeline Summary Table

| Pipeline Step | Reads From | Writes To | AI Involved |
|---|---|---|---|
| Ingestion | External source | PostgreSQL, Neo4j, Vector DB, Keyword Index | Embedding model |
| Query preprocessing | — | — | Speech-to-text, language detection |
| Candidate retrieval | Vector DB, Keyword Index | — | Embedding model |
| Cross-encoder rerank | — | — | Cross-encoder model |
| LTR rerank | Analytics Store (acceptance rates) | — | LightGBM/XGBoost ranker |
| Graph expansion | Neo4j | — | No |
| Validation/enrichment | PostgreSQL, Analytics Store | — | No (deterministic) |
| Reasoning & generation | — (grounded context only) | — | LLM |
| Response logging | — | Analytics Store | No |
| Feedback capture | — | Analytics Store | No |
| Model retraining | Analytics Store | Model registry | LTR training |
| Revision monitoring | External source, PostgreSQL | All stores, Notification queue | Embedding model (re-embed) |
