# Feature Catalogue

## A. Core Features (Directly Addressing PS Requirements)

### A1. Hybrid Semantic Retrieval
Combines three signals instead of relying on one:
- **Dense semantic search** (embeddings) — understands intent, handles paraphrasing and vernacular product terms.
- **Sparse keyword search (BM25)** — catches exact technical terms, material grades, partial IS numbers.
- **Metadata filtering** — narrows by product category, sector, applicable scheme.

**Why it matters:** Pure embedding search hallucinates confidently wrong standards; pure keyword search misses semantic matches. The hybrid materially reduces false recommendations.

### A2. Knowledge-Graph-Driven Allied Standard Discovery
Standards are modelled as nodes in a graph, not rows in a table:

```
Product Category → Primary Standard → Normative References
                                    → Test Method Standards
                                    → Terminology Standards
                                    → Safety Standards
                                    → Installation Standards
                                    → Certification Scheme
```

Once a primary standard is identified, graph traversal (1–2 hops) surfaces the full cluster. **This directly answers the hardest requirement in the problem statement** and is the single biggest differentiator.

### A3. Confidence-Scored, Explainable Recommendations
Every recommendation carries:
- A confidence score
- The matched concepts/clauses that triggered it
- A natural-language "why this was recommended" explanation

**Why it matters:** Officials must defend tender specs under audit. An unexplained AI output cannot be defended.

### A4. Version & Amendment Freshness Engine
Each standard node stores version metadata and `superseded_by` relationships. The system:
- Always surfaces the latest published version
- Flags superseded references in existing documents
- Produces a plain-language diff ("IS X:2022 supersedes IS X:1983 — key changes: …")

### A5. Certification Requirement Mapper
Deterministic rules-based mapping from standard/product category → applicable mandatory certification scheme (BIS Product Certification, CRS, Hallmarking). Kept rules-based rather than ML-based because certification correctness carries legal consequence.

### A6. Tender Auto-Audit Mode
Upload an existing draft tender → system extracts all referenced standards → checks each for outdated versions, missing allied standards, and missing certification requirements → produces a structured gap report with severity tags.

### A7. Specification Clause Generator
Auto-generates ready-to-paste specification clause text referencing the correct standard(s), version, and certification requirement — reducing drafting effort, not just lookup effort.

### A8. Multilingual & Voice Query Support
Accepts natural-language queries in English, Hindi, and regional languages — as text or speech. Handles vernacular technical synonyms used in field offices.

### A9. Compliance Dashboard & Alerts
- Org-wide view: % of tenders citing outdated standards, most-queried categories, gap trends, certification compliance rates.
- Subscription-based alerts when a standard in a subscribed category is revised or amended.

### A10. Audit Trail & Version-Controlled History
Every recommendation is logged with query, candidates shown, scores, standard versions, timestamp, and the user's final action — producing a defensible record.

### A11. Portal-Agnostic REST API
Every core capability (recommend, audit, certification-check) exposed as a versioned REST endpoint for GeM, state e-procurement portals, and private ERPs.

---

## B. Differentiating Features

### B1. Standard "Trust Score" via Dispute Correlation
Correlates historical procurement disputes, tender cancellations, and quality-rejection cases with the standards cited in those tenders. Flags standard combinations that historically correlate with disputes.

**Impact:** Moves the system from "technically correct" to "practically risk-aware" — grounded in real procurement outcomes rather than theory alone.

### B2. Scenario Simulator ("What-If" Mode)
The official adjusts a use-case parameter — e.g. *"same product, but for outdoor use"*, *"higher load rating"*, *"marine environment"* — and the recommended standard cluster updates live.

**Impact:** Teaches officials *why* specs differ across use-cases, rather than handing them an opaque answer. Turns the tool into a training aid as well as a lookup engine.

### B3. Standard Similarity / Overlap Detector
When two or more standards have overlapping scope (common due to legacy revisions and parallel standards), the system explicitly flags the overlap and explains which is currently authoritative for the given use-case.

**Impact:** Resolves a genuine, frequent source of procurement confusion that keyword search actively worsens.

### B4. Voice-Based Multilingual Query
Officials can speak a requirement in Hindi or a regional language and receive the standard cluster back.

**Impact:** Accessibility for regional and field offices where typing technical English specs is a barrier. Also a strong live-demo moment.

### B5. Chrome Extension / GeM Portal Overlay
A lightweight browser extension that activates while the official is typing directly into a GeM or state portal tender-creation form, showing inline standard suggestions without tab-switching.

**Impact:** Integration friction is the primary reason government tools go unused. Meeting officials inside their existing workflow dramatically raises real adoption probability.

### B6. Auto-Flagging of "Orphan" Queries
When no candidate standard clears a confidence threshold, the system **refuses to force a weak recommendation**. Instead it flags the query as a potential gap in the standards landscape itself and routes it toward BIS / an internal standards committee for review.

**Impact:** Transforms the tool from a consumer of the standards ecosystem into a contributor that helps improve it. Also prevents the most dangerous failure mode — a confident wrong answer.

### B7. Explainable Diff View (Audit Mode)
Instead of a flat gap report, the audit output is presented as a track-changes-style redline over the user's draft tender — showing exactly what to add, remove, or update, inline.

**Impact:** Reduces "understand the report → manually fix the document" friction to near zero.

### B8. Impact Estimator
For every flagged gap or outdated citation, generates a plain-language risk explanation, e.g.:

> *"Using superseded IS 456:2000 instead of IS 456:2019 may lead to non-compliant load specifications and structural acceptance disputes at inspection stage."*

**Impact:** Makes risk legible to non-technical decision-makers (PSE admins, finance approvers), not just engineers — driving action, not just awareness.

---

## C. Feature-to-Objective Traceability

| Objective | Features Serving It |
|---|---|
| Accurate identification | A1, A3, B3 |
| Complete coverage | A2, A6, B2 |
| Currency assurance | A4, A9 |
| Certification awareness | A5 |
| Universal accessibility | A8, B4, B5 |
| Auditability | A3, A10, B7, B8 |
| Systemic reach | A11, B5 |
| Continuous improvement | A10 (feedback logs) → ML layer |
| Ecosystem feedback | B6 |
| Risk awareness | B1, B8 |
