# Standards Retrieval & Ranking Engine (`standards-retrieval`)

> **Microservice for Part 2 (Retrieval & Ranking Engine) and Part 6 (Feedback Loop) of the AI-Powered Indian Standards (BIS) Recommendation System.**

---

## 📌 Overview

This microservice provides intelligent semantic and lexical retrieval of Indian Standards (BIS) from plain-language procurement tender specifications.

While **Part 1 (Real BIS Standards Corpus Extraction)** is being prepared, this codebase is built against a high-fidelity **synthetic mock corpus** (`data/mock_corpus.json`). The system is architected so that transitioning from the mock dataset to the production corpus requires **zero code modifications**—only a data file swap or environment variable configuration.

---

## 🗂️ Project Structure

```text
standards-retrieval/
├── data/
│   ├── mock_corpus.json      # 30 synthetic BIS standards across 3 product categories
│   ├── eval_set.json         # 15 diagnostic NL procurement queries for evaluation
│   ├── models.py             # Pydantic schemas (Standard)
│   └── __init__.py
├── indexing/                 # Sparse (BM25) and Dense (FAISS) vector indexing modules
│   └── __init__.py
├── retrieval/                # Hybrid search fusion & cross-encoder re-ranking
│   └── __init__.py
├── ltr/                      # Learning-to-Rank (LightGBM ranker) feature pipelines
│   └── __init__.py
├── feedback/                 # User click/acceptance feedback ingestion & retraining
│   └── __init__.py
├── eval/                     # Evaluation metrics (MRR@K, NDCG@K, HitRate@K)
│   └── __init__.py
├── data_loader.py            # Cached data loader for corpus & evaluation datasets
├── main.py                   # FastAPI service endpoints
├── requirements.txt          # Production dependencies
└── README.md
```

---

## 📋 Data Schema (`Standard` Model)

Every standard in the corpus conforms to the Pydantic schema defined in [`data/models.py`](data/models.py):

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `id` | `str` | Unique canonical identifier | `"IS-ELEC-001"` |
| `number` | `str` | Realistic IS-style specification numbering | `"IS 1554 (Part 1):2019"` |
| `title` | `str` | Formal title of standard | `"PVC Insulated Cables for Working Voltages..."` |
| `scope` | `str` | Formal regulatory scope (1–3 sentences) | `"This standard covers the requirements of..."` |
| `description` | `str` | Use-case oriented technical summary (2–4 sentences) | `"Designed for domestic conduit and trunking..."` |
| `category` | `str` | Product domain classification | `"Electrical Cables & Wires"` |
| `version` | `str` | Edition / revision string | `"Fourth Revision"` |
| `last_amended`| `str` | Date of latest amendment (`YYYY-MM-DD`) | `"2021-04-15"` |
| `status` | `Literal["active", "superseded"]` | Standard validity status | `"active"` |
| `keywords` | `list[str]` | Lexical terms for BM25 matching | `["PVC insulated", "single-core", ...]` |

---

## 🔄 How to Swap in the Real Part 1 Corpus

Once the real BIS dataset is compiled, swapping the corpus requires **zero code changes**:

### Option 1: Direct File Replacement (Recommended)
Replace the contents of [`data/mock_corpus.json`](data/mock_corpus.json) with your real JSON file matching the schema above.

### Option 2: Pass Custom Path in Code / Environment
```python
from data_loader import load_corpus

# One-line swap pointing to the production dataset:
standards = load_corpus(corpus_path="/path/to/real_bis_corpus.json", force_reload=True)
```

---

## 🎯 Mock Corpus & Diagnostic Eval Set Design

The mock corpus contains **30 entries** evenly distributed across 3 key procurement sectors (10 each):
1. **Electrical Cables & Wires**
2. **Cement & Building Materials**
3. **Steel Pipes & Fittings**

### Deliberate Retrieval Challenges:
- **Near-Duplicate Disambiguation Pairs**: e.g., Single-Core Conduit Wiring (`IS-ELEC-001`) vs Flexible Multi-Strand Panel Wiring (`IS-ELEC-002`), or OPC 43 Grade (`IS-CEM-001`) vs OPC 53 Grade (`IS-CEM-002`).
- **Superseded vs Active Versions**: e.g., IS 1554 (Part 1):1988 (superseded) vs IS 1554 (Part 1):2020 (active).
- **Rich Lexical Signal**: Curated keywords mapped directly to scope and description terms for BM25 sparse retrieval.

The evaluation set [`data/eval_set.json`](data/eval_set.json) contains **15 real-world procurement tender queries** designed to benchmark hybrid search precision and cross-encoder disambiguation capability.

---

## 🚀 Quick Start

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Verify Data Loader
```python
from data_loader import load_corpus, load_eval_set

standards = load_corpus()
eval_queries = load_eval_set()

print(f"Loaded {len(standards)} standards across {len(set(s.category for s in standards))} categories.")
print(f"Loaded {len(eval_queries)} diagnostic evaluation queries.")
```

### 3. Launch FastAPI Development Server
```bash
uvicorn main:app --reload --port 8000
```
Visit `http://localhost:8000/docs` for interactive Swagger UI documentation.

---

## 📡 API Contract & Service Specification

This service is the official contract built against by **Part 4 (Orchestration & Disambiguation)** and **Part 6 (Feedback Loop)**.

### 1. Primary Retrieval Endpoint: `POST /retrieve`
Retrieves and ranks BIS standards for natural language procurement specification queries using the full Part 2 cascade: Hybrid Search (Dense + BM25 RRF) $\to$ Cross-Encoder Re-Ranking $\to$ LightGBM LambdaMART LTR (or fallback) $\to$ Deterministic Business Rules.

**Request Body:**
```json
{
  "query": "Concealed 1.5 sq mm single core copper building wire up to 1100V",
  "top_k": 10
}
```

**Response Schema (Frozen Contract):**
```json
{
  "query": "Concealed 1.5 sq mm single core copper building wire up to 1100V",
  "results": [
    {
      "id": "IS-ELEC-001",
      "number": "IS 694:2010",
      "title": "PVC Insulated Cables for Working Voltages up to and Including 1100V",
      "final_score": 0.9452,
      "stage_scores": {
        "dense": 0.8812,
        "bm25": 14.521,
        "cross_encoder": 5.412,
        "ltr_or_fallback": 0.9452
      },
      "ranker_used": "ltr"
    }
  ]
}
```

**Key Guarantees:**
- `final_score`: Relative ranking signal strictly bounded in $[0.0, 1.0]$. Only comparable within a single response, not across separate `/retrieve` calls.
- `ranker_used`: Explicitly emitted as `"ltr"` or `"fallback"` for operational traceability.
- `stage_scores`: Preserves raw component signals (`dense`, `bm25`, `cross_encoder`, `ltr_or_fallback`) for disambiguation analysis.
- **Graceful Degradation**: If the LTR model throws during scoring, the service automatically falls back to `fallback_score()` and emits `"ranker_used": "fallback"` without 500-ing.

### 2. Service Health: `GET /health`
Returns service status, in-memory corpus size, and whether the trained LTR model is active:
```json
{
  "status": "ok",
  "corpus_size": 30,
  "ltr_model_loaded": true
}
```

### 3. Backward Compatibility: `GET /retrieve` & `GET /search`
Supports browser and query-string debugging via `GET /retrieve?query=...&top_k=10`.


---

## 📊 Model Details & Evaluation Metrics

For complete architectural breakdowns, model cards, feature importance weights, 5-fold cross-validation statistics, conservative promotion gates, and benchmark results, see:

👉 **[MODEL_AND_EVALUATION.md](MODEL_AND_EVALUATION.md)**

### Executive Benchmark Highlights (Held-Out Eval Set):
| Pipeline Stage | Precision@1 | Recall@5 | NDCG@5 |
|---|---|---|---|
| **Hybrid Search (Dense + BM25 RRF)** | 87.5% | 100.0% | 0.9430 |
| **Full Retrieve (+ Cross-Encoder Re-Ranking)** | 91.7% | 100.0% | 0.9609 |
| **LTR Final Pipeline (+ Post-Processing)** | **95.8%** | **100.0%** | **0.9846** |


