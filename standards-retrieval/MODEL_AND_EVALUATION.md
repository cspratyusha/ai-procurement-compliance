# 🧠 Model Details & Evaluation Metrics (BIS Standards Retrieval)

This document provides a comprehensive technical reference for the multi-stage retrieval, ranking, and evaluation pipeline implemented in `standards-retrieval` (Part 2, Stages A–C). It details model architectures, feature engineering, hyperparameters, training methodology, cross-validation, conservative promotion gates, benchmark evaluation metrics, and scoring contracts.

> ### ⚠️ Read this before quoting any number in this document
>
> **Every metric below is measured on a 30-standard development corpus
> ([`data/mock_corpus.json`](data/mock_corpus.json)) against 24 evaluation queries.**
>
> - The corpus is **not** curated BIS data. The IS numbers and titles are
>   realistic but have **not been verified against the BIS catalogue**.
> - 30 documents is small enough that retrieval is an *easy* problem: with
>   only ~10 standards per sector, a query rarely has close competitors.
>   Scores this high are expected at this scale and **will drop** as the
>   corpus grows toward realistic size (BIS publishes ~22,000 standards).
> - The eval set was authored alongside the corpus, so it shares its
>   vocabulary and assumptions.
>
> These numbers are therefore a **pipeline-correctness signal** — evidence
> that each stage improves on the one before it, and that the plumbing is
> sound — **not** a benchmark of real-world accuracy. Do not present them
> as "the system is 95.8% accurate on Indian Standards." The honest claim
> is: *"on our pilot corpus, the LTR stage improves Top-1 from 87.5% to
> 95.8% over hybrid search."*
>
> See the "Data coverage and limitations" section of the root `README.md`.

---

## 📑 Table of Contents
1. [Architecture & Pipeline Cascade](#1-architecture--pipeline-cascade)
2. [Component Model Specifications](#2-component-model-specifications)
   - [Dense Embedding Model](#dense-embedding-model-e5-base-v2)
   - [Sparse Lexical Retrieval (BM25)](#sparse-lexical-retrieval-bm25okapi)
   - [Cross-Encoder Re-Ranker](#cross-encoder-re-ranker-minilm-l-6-v2)
   - [Learning-to-Rank Model (LightGBM LambdaMART)](#learning-to-rank-model-lightgbm-lambdamart)
3. [Feature Engineering & Importances](#3-feature-engineering--importances)
4. [Training & Cross-Validation Methodology](#4-training--cross-validation-methodology)
   - [Dataset Splitting & Leakage Prevention](#dataset-splitting--leakage-prevention)
   - [Label Distribution & Graded Relevance](#label-distribution--graded-relevance)
   - [5-Fold Grouped Cross-Validation](#5-fold-grouped-cross-validation)
   - [Conservative Promotion Gate](#conservative-promotion-gate)
5. [Evaluation Metrics & Definitions](#5-evaluation-metrics--definitions)
6. [Empirical Evaluation Benchmark Results](#6-empirical-evaluation-benchmark-results)
   - [Overall Pipeline Comparison](#overall-pipeline-comparison)
   - [Performance Breakdown by Query Difficulty](#performance-breakdown-by-query-difficulty)
7. [Scoring Contract & Business Logic](#7-scoring-contract--business-logic)
   - [Range Bounds & Normalization](#range-bounds--normalization)
   - [Comparability Scope](#comparability-scope)
   - [Supersession Resolution & nearby_superseded](#supersession-resolution--nearby_superseded)
8. [Production Deployment & Live Artifacts](#8-production-deployment--live-artifacts)

---

## 1. Architecture & Pipeline Cascade

The retrieval engine employs a 4-stage funnel combining dense vector search, sparse keyword matching, neural cross-attention re-ranking, gradient-boosted learning-to-rank, and deterministic business rules:

```mermaid
flowchart TD
    Q[User Procurement Query] --> Dense[Stage A1: Dense E5 Search\nTop-20 FAISS Inner Product]
    Q --> BM25[Stage A2: BM25Okapi Search\nTop-20 Tokenized BM25]
    Dense --> RRF[Stage A3: Reciprocal Rank Fusion (RRF)\nk=60, Merged Top-20 Candidates]
    BM25 --> RRF
    RRF --> CE[Stage B: Cross-Encoder Re-Ranking\nMS-MARCO MiniLM-L-6-v2 Top-20 Pairs]
    CE --> Feat[Stage C1: Feature Extraction\n7 Features: Dense, BM25, CE, Recency, Category, Jaccard, History]
    Feat --> LTR[Stage C2: LightGBM LambdaMART Model\nOptimized for NDCG@5]
    LTR --> Post[Stage D: Deterministic Post-Processing\n- Supersession Penalty floored at 0.0\n- Order-preserving shift & [0.0, 1.0] scaling\n- Tie-breaking by pre-penalty score]
    Post --> Resp[Response Payload:\n- results: Top-10 sorted by final_score\n- nearby_superseded: Audit trail for legacy standards]
```

| Stage | Component | Candidate Pool | Output | Latency (CPU) |
|---|---|---|---|---|
| **Stage A1** | Dense Vector Search (`intfloat/e5-base-v2`) | Full Corpus ($N=30$) | Top-20 Candidates | ~15 ms |
| **Stage A2** | Sparse Lexical Search (`BM25Okapi`) | Full Corpus ($N=30$) | Top-20 Candidates | ~1 ms |
| **Stage A3** | Reciprocal Rank Fusion ($k=60$) | $2 \times 20$ Candidates | Top-20 Fused | < 1 ms |
| **Stage B** | Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) | Top-20 Candidates | Cross-Attention Logits | ~30 ms |
| **Stage C** | Learning-to-Rank (`LightGBM LambdaMART`) | Top-20 Candidates | Learned Ranking Scores | ~2 ms |
| **Stage D** | Deterministic Post-Processing & Penalty | Top-20 Candidates | Top-10 `final_score` $\in [0.0, 1.0]$ + `nearby_superseded` | < 1 ms |

---

## 2. Component Model Specifications

### Dense Embedding Model (`e5-base-v2`)
- **Model Identifier**: `intfloat/e5-base-v2` ([Hugging Face](https://huggingface.co/intfloat/e5-base-v2))
- **Base Architecture**: 12-layer Transformer encoder (BERT-base architecture)
- **Embedding Dimension**: 768 dimensions
- **Vector Index**: FAISS `IndexFlatIP` (Exact Inner Product over $L_2$-normalized vectors $\equiv$ cosine similarity)
- **Asymmetric Prefix Conditioning**:
  - Documents: `"passage: <Standard ID> - <Number>: <Title>. Scope: <Scope>. Description: <Description>. Keywords: <Keywords>"`
  - Queries: `"query: <natural language tender query>"`
- **Singleton Lifecycle**: Cached in-memory singleton loaded once at application bootstrap.

### Sparse Lexical Retrieval (`BM25Okapi`)
- **Algorithm**: BM25Okapi (via `rank-bm25`)
- **Hyperparameters**: $k_1 = 1.5$, $b = 0.75$
- **Corpus Tokenization**: Lowercase alphanumeric regex tokenizer with English stopword suppression.
- **Indexed Document Text**: Concatenation of title, category, regulatory scope, functional description, and curated BIS keywords.

### Cross-Encoder Re-Ranker (`MiniLM-L-6-v2`)
- **Model Identifier**: `cross-encoder/ms-marco-MiniLM-L-6-v2` ([Hugging Face](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2))
- **Architecture**: 6-layer MiniLM with joint cross-attention over query-document token pairs $(q, d)$.
- **Output**: Unbounded cross-attention relevance logit.
- **Design Role**: Solves vocabulary mismatch and complex semantic phrasing that bi-encoders miss; evaluated over the narrowed Top-20 candidate pool to avoid whole-corpus inference overhead.

### Learning-to-Rank Model (`LightGBM LambdaMART`)
- **Model Identifier**: `models/ltr_model.txt`
- **Algorithm**: LambdaMART (Gradient Boosted Trees optimizing listwise ranking loss)
- **Objective**: `lambdarank`
- **Optimization Metric**: `ndcg` evaluated at cutoff $k=5$ (`ndcg_eval_at: [5]`)
- **Model Hyperparameters**:
  ```json
  {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [5],
    "learning_rate": 0.02,
    "max_depth": 3,
    "num_leaves": 6,
    "min_data_in_leaf": 2,
    "lambda_l1": 0.1,
    "lambda_l2": 1.0,
    "min_gain_to_split": 0.01,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 42,
    "force_col_wise": true
  }
  ```
- **Training Progression**:
  - Total boosting rounds trained: 37
  - Early stopping patience: 30 rounds without validation NDCG@5 improvement
  - **Best Iteration**: Round 7 (Validation NDCG@5 = `0.9660`)

---

## 3. Feature Engineering & Importances

The LTR layer transforms each `(query, candidate)` pair into a 7-dimensional dense feature vector in fixed ordinal order:

| Feature Index | Feature Name | Description | Extraction Method | Feature Importance (Split Gain) |
|---|---|---|---|---|
| `0` | `dense_score` | Dense vector semantic similarity | Cosine similarity from `intfloat/e5-base-v2` | **5.14%** |
| `1` | `bm25_score_normalized` | Sparse lexical matching score | Min-Max normalized within the per-query Top-20 candidate pool | **61.23%** |
| `2` | `cross_encoder_score` | Deep cross-attention relevance score | Logit output from `cross-encoder/ms-marco-MiniLM-L-6-v2` | **27.33%** |
| `3` | `recency_score` | Freshness and amendment recency | $\max(0, 1 - \frac{\text{years\_since\_amendment}}{10})$ | **0.00%** *(enforced via post-processor)* |
| `4` | `category_match` | Broad domain alignment | Binary indicator: query keyword match to standard category | **6.28%** |
| `5` | `keyword_overlap` | Lexical jaccard similarity | Jaccard overlap between query tokens and standard keywords | **0.02%** |
| `6` | `historical_acceptance_rate`| Empirical user acceptance signal | Historical audit acceptance rate from user feedback store | **0.00%** *(cold-start baseline)* |

### Feature Importance Commentary:
- **`bm25_score_normalized` (61.2%) & `cross_encoder_score` (27.3%)**: Act as complementary anchors. BM25 provides strong lexical discrimination for precise numbers/codes, while the Cross-Encoder provides semantic disambiguation for complex phrasing.
- **`recency_score` (0.0%)**: Confirmed by diagnostics to have high noise in a small corpus (only 1–2 superseded pairs). Rather than forcing statistical learning over insufficient data, supersession resolution is delegated to deterministic business rules in Stage D.

---

## 4. Training & Cross-Validation Methodology

### Dataset Splitting & Leakage Prevention
To prevent data leakage and benchmark over-optimism:
- Training and evaluation query sets are strictly partitioned at the query level:
  - **Training Bootstrap Queries** (`data/train_queries.json`): 50 queries across all 3 sectors.
  - **Held-Out Evaluation Set** (`data/eval_set.json`): 24 unseen queries (70/30 split).
- Both sets include balanced distributions across multiple query difficulty profiles (`easy`, `hard_duplicate`, `hard_identifier`, and `use_case_only`).

### Label Distribution & Graded Relevance
Each query retrieves top candidates forming graded relevance training instances:
- **Grade 3 (Exact Target)**: The single ground-truth standard matching the procurement tender query.
- **Grade 1 (Category Match)**: Standards in the same category (weak positive / topical baseline).
- **Grade 0 (Irrelevant)**: Standards in unrelated product categories.

**Instance Breakdown**:
- **Training Set (50 queries)**: 63 Grade-3, 536 Grade-1, 661 Grade-0 (Total: 1,260 instances).
- **Validation Set (10 queries)**: 11 Grade-3, 96 Grade-1, 113 Grade-0 (Total: 220 instances).

### 5-Fold Grouped Cross-Validation
To prevent variance under-estimation on small query sets, 5-fold cross-validation with query grouping (`GroupKFold`) was performed:
- **Fold 1 NDCG@5**: 0.9614
- **Fold 2 NDCG@5**: 0.9482
- **Fold 3 NDCG@5**: 0.9850
- **Fold 4 NDCG@5**: 0.9125
- **Fold 5 NDCG@5**: 0.9667
- **Mean CV NDCG@5 ($\mu$)**: `0.9548`
- **Standard Deviation ($\sigma$)**: `0.0385`
- **Conservative Lower Bound ($\mu - \sigma$)**: `0.9163`

### Conservative Promotion Gate
Before replacing the live production ranker, candidate models must pass an automated, conservative gate implemented in [`feedback/retrain_and_promote.py`](feedback/retrain_and_promote.py):

$$\text{Required Threshold} = \max\left(\text{Baseline CrossEncoder NDCG@5}, \mu_{\text{CV}} - \sigma_{\text{CV}}\right)$$

$$\text{Gate Rule}: \text{Candidate LTR NDCG@5} \ge \text{Required Threshold}$$

**Verification Math for Live Model (`ltr_run_20260919_184754`)**:
- Candidate LTR NDCG@5: **`0.9846`**
- Baseline Cross-Encoder NDCG@5: **`0.9609`**
- Required Promotion Threshold: $\max(0.9609, 0.9163) = \mathbf{0.9609}$
- Promotion Margin: $\mathbf{+0.0237}$
- **Decision: PROMOTED** (Saved to `models/ltr_model.txt`).

---

## 5. Evaluation Metrics & Definitions

The evaluation harness evaluates retrieval quality against single-relevant-document ground truth:

### 1. Precision@1 (Top-1 Accuracy / Hit@1)
Evaluates whether the single ground-truth standard is ranked at Position 1:
$$\text{Precision@1} = \mathbb{I}(\text{rank}(\text{doc}^*) = 1)$$

### 2. Recall@5 (HitRate@5 / Coverage@5)
Evaluates whether the ground-truth standard appears anywhere within the Top-5 retrieved candidates:
$$\text{Recall@5} = \mathbb{I}(\text{rank}(\text{doc}^*) \le 5)$$
*(Note: Because $|Relevant|=1$, Recall@K and Precision@K coincide as a binary hit indicator at cutoff $K$.)*

### 3. NDCG@5 (Normalized Discounted Cumulative Gain at Cutoff 5)
Measures rank-discounted relevance quality. With a single relevant document of binary relevance:
$$\text{DCG@5} = \begin{cases} \frac{1}{\log_2(\text{rank} + 1)} & \text{if } 1 \le \text{rank} \le 5 \\ 0 & \text{otherwise} \end{cases}$$

$$\text{IDCG@5} = \frac{1}{\log_2(1 + 1)} = 1.0$$

$$\text{NDCG@5} = \frac{\text{DCG@5}}{\text{IDCG@5}} = \frac{1}{\log_2(\text{rank} + 1)}$$

- Rank 1 $\to$ $\text{NDCG@5} = 1.0000$
- Rank 2 $\to$ $\text{NDCG@5} = 0.6309$
- Rank 3 $\to$ $\text{NDCG@5} = 0.5000$
- Rank 4 $\to$ $\text{NDCG@5} = 0.4307$
- Rank 5 $\to$ $\text{NDCG@5} = 0.3869$
- Rank $> 5$ $\to$ $\text{NDCG@5} = 0.0000$

---

## 6. Empirical Evaluation Benchmark Results

All benchmarks are evaluated over the **24 held-out evaluation queries** in [`data/eval_set.json`](data/eval_set.json), against the **30-standard development corpus** in [`data/mock_corpus.json`](data/mock_corpus.json).

**Scope caveat (see the banner at the top of this document):** a 30-document
corpus makes retrieval substantially easier than the real task, and the
corpus is unverified placeholder data. Read the table below as *relative*
evidence that each stage adds value over the previous one — not as an
absolute accuracy claim for Indian Standards retrieval.

### Overall Pipeline Comparison

| Pipeline Stage | Top-1 Accuracy (P@1) | Top-5 Coverage (Recall@5) | NDCG@5 | Latency (p95) |
|---|---|---|---|---|
| **Hybrid Search (Dense + BM25 RRF)** | 87.5% (21/24) | 100.0% (24/24) | 0.9430 | ~16 ms |
| **Full Retrieve (+ Cross-Encoder Re-Ranking)** | 91.7% (22/24) | 100.0% (24/24) | 0.9609 | ~45 ms |
| **LTR Final Pipeline (+ Post-Processing)** | **95.8% (23/24)** | **100.0% (24/24)** | **0.9846** | **~48 ms** |

> **Key Takeaway**: On this pilot corpus, each stage improves on the one before it — the LTR pipeline adds **+8.3 points of Top-1 accuracy** over hybrid search and **+4.1 over the cross-encoder alone**. The ordering of the three rows is the result worth reporting; the absolute values reflect a 30-document corpus and would be lower at realistic scale.

---

### Performance Breakdown by Query Difficulty

| Query Category | Query Count | Description | Hybrid P@1 | Cross-Encoder P@1 | LTR Pipeline P@1 | LTR NDCG@5 |
|---|---|---|---|---|---|---|
| `easy` | 6 | Standard queries with rich keywords & unambiguous specs | 100.0% | 100.0% | **100.0%** | **1.0000** |
| `hard_duplicate` | 9 | Near-duplicate sibling standards (e.g. OPC 43 vs 53, single vs flexible wire) | 88.9% | 88.9% | **100.0%** | **1.0000** |
| `hard_identifier` | 3 | Queries with historical or legacy standard identifiers | 66.7% | 100.0% | **100.0%** | **1.0000** |
| `use_case_only` | 6 | Practical user descriptions with zero literal IS numbers or title terms | 83.3% | 83.3% | **83.3%** | **0.9385** |

---

## 7. Scoring Contract & Business Logic

### Range Bounds & Normalization
To prevent numerical instability in downstream systems:
1. **Order-Preserving Non-Negative Shift**: If raw candidate scores are negative ($\min < 0$), an order-preserving shift `score += (-min_score + 0.01)` shifts all scores strictly $> 0.0$.
2. **Fixed Upper Bound Rescaling**: If $\max > 1.0$, scores are rescaled by `1.0 / max_score`.
3. **Strict Clamping**: Final emitted scores are clamped to `[0.0, 1.0]` with `round(score, 4)`.

### Comparability Scope
> **CRITICAL API CONTRACT**:
> `final_score` is a **relative ranking signal bounded in range [0.0, 1.0]**, not a calibrated probability or confidence percentage.
> - **Do NOT** display `final_score` directly as a percentage (e.g. `0.4693` is not "46.9% confident").
> - `final_score` is **only comparable within a single response**, not across separate `/retrieve` calls. Scores are normalized relative to the candidate pool retrieved for that specific query.

### Supersession Resolution & `nearby_superseded`
In procurement, recommending a superseded standard when an active replacement exists is a compliance violation. The deterministic post-processor handles this explicitly:
1. **Family Grouping**: Extracts canonical standard families (e.g. `IS 1554 (Part 1):1988` and `IS 1554 (Part 1):2020` $\to$ `IS 1554 (PART 1)`).
2. **Floored Penalty**: If a superseded standard has an active sibling present:
   $$\text{penalized\_score} = \max\left(0.0, \min(\text{score} - 2.0, \max(0.0, \text{active\_floor} - 0.1))\right)$$
3. **Floor Tie-Breaking**: When multiple superseded candidates floor at `0.0`, ties are broken deterministically by their original pre-penalty score (`(score, original_score)` descending).
4. **Audit Surfacing**: If a superseded standard's unpenalized score would have put it in the Top-10, and its active sibling is in the Top-3, it is surfaced in `nearby_superseded: list[dict]`:
   ```json
   {
     "id": "IS-ELEC-005",
     "number": "IS 1554 (Part 1):1988",
     "status": "superseded",
     "superseded_by": "IS-ELEC-006"
   }
   ```

---

## 8. Production Deployment & Live Artifacts

| Component | File Path | Status |
|---|---|---|
| **Live LTR Model** | [`models/ltr_model.txt`](models/ltr_model.txt) | Active Promoted Model (NDCG@5 = 0.9846) |
| **Training Report** | [`models/training_report.json`](models/training_report.json) | Complete training run log & feature stats |
| **Training Curves** | [`models/training_curve.png`](models/training_curve.png) | Visual plot of train vs. val NDCG@5 |
| **FastAPI Microservice** | [`main.py`](main.py) | Serving `GET /retrieve` and `GET /search` |
| **Post-Processor** | [`retrieval/postprocess.py`](retrieval/postprocess.py) | Supersession rules, bounds & tie-breaking |
| **Automated Test Suite** | [`tests/test_supersession.py`](tests/test_supersession.py) | 5 Unit/Integration tests passing (100%) |
