# Overall System Workflow & End-to-End Pipeline

## 1. End-to-End Pipeline (Linear View)

```
[1] INPUT
     text query | uploaded spec/tender | voice | API call | extension field
                              │
                              ▼
[2] PREPROCESSING
     file parsing / OCR · speech→text · language detection · translation
     · query normalisation · category hint extraction
                              │
                              ▼
[3] HYBRID RETRIEVAL
     dense semantic search (Vector DB)  +  sparse BM25 keyword search
     → merged candidate pool (top N)
                              │
                              ▼
[4] CROSS-ENCODER RE-RANKING
     query-standard pairs scored for fine-grained relevance
                              │
                              ▼
[5] LEARNED RE-RANKER (Supervised LTR)
     re-orders using features: semantic score, keyword score, cross-encoder
     score, graph centrality, freshness, historical acceptance rate,
     category match
     (pass-through until feedback data accumulates)
                              │
                              ▼
[6] GRAPH EXPANSION
     Neo4j traversal from each top candidate →
     normative refs · test methods · terminology · safety · installation
                              │
                              ▼
[7] VALIDATION & ENRICHMENT
     ├── Freshness check  → latest version? superseded?
     ├── Certification map → BIS / CRS / Hallmarking applicable?
     ├── Overlap detector → competing-scope standards flagged
     ├── Trust score      → dispute-history correlation
     └── Orphan detector  → confidence below threshold? flag, don't force
                              │
                              ▼
[8] LLM REASONING & GENERATION  (grounded on [6]+[7] only)
     "why recommended" · plain-language version diff ·
     impact estimate · draft specification clause
                              │
                              ▼
[9] RESPONSE ASSEMBLY
     structured JSON: ranked standards + confidence + explanations +
     cluster graph + freshness flags + certification flags +
     overlap/trust flags + generated clause
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
[10] DELIVERY                        [11] LOGGING
     web UI / extension /                  full interaction written to
     API response                          Analytics Store (audit trail
                                           + LTR training data)
                                                     │
                                                     ▼
                                          [12] BACKGROUND JOBS
                                           revision sync · alert dispatch ·
                                           periodic LTR retraining
```

---

## 2. Overall System Workflow (Descriptive)

### Stage 1 — Input Capture
The system accepts input from five entry points: the web app (typed or uploaded), the Chrome extension (captured from a live tender form field), voice input, a direct REST API call from an integrated portal, or a batch document upload in audit mode. All entry points converge on the same backend pipeline — no capability exists in one interface that is absent in another.

### Stage 2 — Normalisation
Uploaded documents are parsed (OCR applied for scanned PDFs). Voice is transcribed. Non-English input is detected and translated or handled directly by the multilingual embedding model. The result is a clean, normalised query string plus optional structured hints (product category, sector, use-case parameters from the scenario simulator).

### Stage 3 — Candidate Generation
The normalised query is embedded and searched against the vector store for semantic matches, and simultaneously searched via BM25 for exact technical terms and partial standard numbers. Results are merged and de-duplicated into a candidate pool.

### Stage 4 — Ranking
A cross-encoder scores each query-candidate pair for precise relevance. The learned re-ranker then applies weights derived from real user behaviour, refining the order beyond what similarity alone can capture.

### Stage 5 — Cluster Construction
For each top-ranked candidate, the graph is traversed to assemble the complete standard cluster. This converts a list of standards into a structured, relationship-aware recommendation — which is what procurement specs actually require.

### Stage 6 — Verification
Every standard in the cluster is checked against authoritative metadata: is this the current version, has it been superseded, does it trigger mandatory certification, does it overlap in scope with another candidate, does its history correlate with disputes. Low-confidence result sets are diverted to the orphan-flagging path instead of being returned as recommendations.

### Stage 7 — Explanation & Generation
Only now does the LLM engage, and only over verified data. It produces human-readable reasoning, version-change summaries, risk/impact statements, and draft clause text. It cannot introduce standards that did not come from retrieval.

### Stage 8 — Delivery & Action
The structured result is rendered according to the consumer: rich cards and graph view in the web app, inline suggestions in the extension, redline diff in audit mode, JSON in API responses. The user accepts, rejects, corrects, or edits.

### Stage 9 — Learning
Every action is logged. Accepted/rejected/corrected recommendations become labelled training pairs. The scheduled retraining job consumes these to improve the learned re-ranker — the system's accuracy compounds with usage at zero labelling cost.

### Stage 10 — Continuous Monitoring
Independently of user activity, the background scheduler polls for standards revisions and amendments, updates the data stores, and dispatches alerts to subscribed users and organisations.

---

## 3. Mode-Specific Workflows

### 3.1 Recommendation Mode (new specification)
`Input → Preprocess → Retrieve → Rank → Expand → Verify → Explain → Ranked cluster + clause draft`

### 3.2 Audit Mode (existing tender)
```
Upload draft tender
   → extract all referenced standards (regex + NER on IS numbers)
   → for each: freshness check, certification check
   → graph check for MISSING companion standards
   → compile gap report with severity tags
   → render as track-changes redline over the original document
   → attach impact estimate per gap
```

### 3.3 Scenario Simulator Mode
```
Base query → base cluster returned
   → user adjusts parameter (outdoor use / higher load / marine env.)
   → parameter injected as structured context into the query
   → pipeline re-runs → delta highlighted against base cluster
```

### 3.4 Orphan-Query Path
```
All candidates below confidence threshold
   → suppress recommendation output
   → return "no confident match" with nearest neighbours as reference only
   → log as potential standards-landscape gap
   → queue for BIS / internal standards committee review
```

### 3.5 Alert Path (asynchronous, no user trigger)
```
Scheduler → poll standards source → detect new revision/amendment
   → update PostgreSQL + Neo4j + re-embed into Vector DB
   → identify subscribed users/orgs for that category
   → Notification Service → in-app + email
   → dashboard "outdated citation" counters recalculated
```
