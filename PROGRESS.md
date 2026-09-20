# Project progress log

A running record of what has been built, tested, and left open. Newest entry
at the top.

---

## Phase B — Consolidation: one backend, one dataset (2026-09-20)

**Goal:** remove the duplicated backend and merge the three competing
datasets into a single source of truth.

### Backend consolidation

`app/services/standards_retrieval/` was a vendored copy of
`standards-retrieval/` that had already drifted (8 files differing, including
a *different* trained LTR model at 14,088 bytes vs 8,319).

- Archived the full tree on branch
  `archive/app-standards-retrieval-duplicate` before deleting, so nothing is
  unrecoverable.
- **Removed 56 files / 10,529 lines** from `main`.
- `app/services/retrieval_service.py` was the only consumer (8 imports). It
  now imports the canonical pipeline via a new small shim,
  `app/services/standards_retrieval_path.py`, which puts `standards-retrieval/`
  on `sys.path`. That directory has a hyphen in its name so it cannot be
  imported as a package, and its modules import one another by bare name.
- Verified the shim resolves all 8 import targets against the canonical tree.

`app/` still needs `pydantic_settings` plus a running Postgres and Neo4j to
start, which is unchanged from before and out of scope here. It is the
documented upgrade path, not the demo path.

### Dataset consolidation

Wrote `data/consolidate.py`, which merges:

| Source | Records | Ids |
|---|---|---|
| `standards-retrieval/data/mock_corpus.json` | 30 | `IS-ELEC-001` |
| `data/raw/standards.json` | 18 | `std_001` |
| `data/seed_standards.json` | 10 | *(different schema)* |

into **`data/standards_corpus.json` — 45 unique standards across 7 sectors**
(58 input records; 12 appeared in more than one source). Identity is the
normalized IS number; on conflict the record with the richer scope +
description wins, since those are the embedded fields.

The three sources used three different category vocabularies. The script maps
them onto one and **raises on any unmapped value** rather than guessing — this
caught four categories from `seed_standards.json` that would otherwise have
been silently mis-sectored.

Also regenerated the eval set as `data/eval_set_consolidated.json`; all 24
queries remapped cleanly onto the new ids via IS number.

### Two real data problems found by the validator

1. `IS 226:1975` and `IS 1139:1966` are superseded but their replacements
   (`IS 2062:2011`, `IS 1786:2008`) live in a *different standard family*, so
   the family-matching heuristic in `retrieval/postprocess.py` cannot connect
   them. Added an explicit `CROSS_FAMILY_SUPERSESSION` map and a
   `superseded_by_number` field; the validator now fails if a declared
   replacement is absent from the corpus.
2. The `Standard` pydantic model types `last_amended` as a required `str`,
   so records without an amendment date must emit `""`, not `null`.

### Tested

- `python data/consolidate.py --check` — validation passes, 0 problems.
- Consolidated corpus **loads into the existing pipeline** unmodified
  (45 standards, 40 active / 5 superseded).
- Rebuilt both indexes over 45 standards successfully.
- **`pytest` — 37 passed, 0 failed** (unchanged).

### The important measurement

Re-running the benchmark on 45 standards instead of 30:

| Pipeline | 30 | 45 |
|---|---|---|
| Hybrid | 0.9430 | 0.9382 |
| + Cross-encoder | 0.9609 | 0.9609 |
| + LTR | **0.9846** | **0.9692** |

LTR Top-1 fell from **95.8% to 91.7%**. Adding 15 standards measurably
degraded the scores. This is direct evidence that the headline numbers track
corpus size rather than real-world accuracy, and it is worth stating plainly
in the submission rather than letting a judge discover it.

### Still open

- **Frontend is still not connected to any backend** — 0 network calls. This
  is now the single highest-value remaining task (Phase C).
- No low-confidence / no-match handling: an out-of-scope query such as
  "safety helmet for construction workers" still returns a cable standard as
  its top hit.
- `indexing/build.py --corpus` writes indexes to a fixed location regardless
  of which corpus was built, overwriting the committed defaults the tests
  rely on. Output should follow the corpus choice.
- The pipeline still defaults to the 30-standard `mock_corpus.json`. Switching
  the default to the consolidated corpus means retraining the LTR model
  against it, which is deliberately left as its own step.
- Certification logic, related-standards graph, multilingual support and
  document upload remain unbuilt.

---

## Phase A — Backend made runnable, artifact corruption fixed (2026-09-20)

**Goal:** get the existing retrieval backend actually running on a developer
machine, and establish an honest baseline of what works.

### What was wrong

The retrieval backend could not start or be tested on this machine at all:

1. **Corrupt LightGBM model.** `models/ltr_model.txt` failed to load with
   `[LightGBM] [Fatal] Model format error, expect a tree here`, which aborted
   the Python interpreter (not a catchable exception).

   Root cause: the LightGBM text format encodes **byte offsets** in its
   `tree_sizes=` header. The repository blob is clean LF (8,319 bytes), but
   with `core.autocrlf=true` Git rewrote it to CRLF on checkout (8,598 bytes
   — exactly 279 extra bytes for 279 line endings), shifting every offset.
   The file looked fine in the repo and was broken on every Windows clone.

   Fixed by adding [`.gitattributes`](.gitattributes) marking model and index
   artifacts as binary, and normalizing the affected working-tree files.
   Four artifacts were affected across the duplicated trees.

2. **Circular import.** `ltr/__init__` → `ltr.train` → `feedback.retrain_and_promote`
   → `feedback/__init__` → back to `ltr.train`, leaving it partially
   initialized. Broke collection of 5 test modules.

   Fixed by deferring the single `promotion_decision` import in
   `ltr/train.py` to its one call site.

3. **Missing dependency.** `matplotlib` is imported at module scope in
   `ltr/train.py` but absent from `requirements.txt`. Because the trainer sits
   on the API's import chain, this broke the serving path too.

4. **No usable Python.** Default `python` on this machine is 3.14, which has
   no wheels for torch/faiss/lightgbm. Python 3.11.9 is the only viable
   interpreter present. No virtualenv existed anywhere in the repo.

### What was done

- Created `.venv` on Python 3.11.9 with the full retrieval stack (CPU-only
  torch to avoid the 2.5 GB CUDA download).
- Added `.gitattributes`; normalized corrupted model artifacts.
- Fixed the circular import.
- Wrote the root `README.md` (did not exist) and this file (did not exist).
- Reframed the accuracy claims in `MODEL_AND_EVALUATION.md` — see below.

### Tested

- **`pytest tests/` — 37 passed, 0 failed.** Previously: 6 collection errors
  and 3 modules hard-aborting the interpreter.
- **API smoke test passes.** `/health` returns
  `{"status":"ok","corpus_size":30,"ltr_model_loaded":true}`.
- **Measured latency** (not estimated): cold start ~17 s (model loading);
  `/retrieve` queries **165–317 ms** on CPU.
- **Eval numbers reproduce exactly** as documented:

  | Pipeline | P@1 | R@5 | NDCG@5 |
  |---|---|---|---|
  | Hybrid (dense + BM25 RRF) | 0.8750 | 1.0000 | 0.9430 |
  | + Cross-encoder | 0.9167 | 1.0000 | 0.9609 |
  | + LTR | 0.9583 | 1.0000 | 0.9846 |

  The pipeline is genuinely well-built and each stage measurably improves the
  last. The caveat is the corpus, not the code — see below.

### Honesty pass on metrics

The metrics are real and reproducible, but they are measured on a
**30-standard corpus of unverified placeholder data** against 24 queries
written alongside it. Added prominent scope banners to
`MODEL_AND_EVALUATION.md` and a "Data coverage and limitations" section to
`README.md` so the numbers cannot be read as a real-world accuracy claim.

### Known-good observation worth keeping

A query for `"safety helmet for construction workers"` (PPE — outside the
corpus) returns a *cable* standard as its top hit at score 0.31. The system
has no low-confidence threshold, so it presents a confident-looking wrong
answer. **This must be fixed before any demo** — see Phase C.

### Still open

- Frontend is **not connected to any backend** — 0 network calls, 100%
  hardcoded mock data.
- `app/services/standards_retrieval/` is a **stale duplicate** of
  `standards-retrieval/` (~6,300 lines, 8 files already drifted, including a
  different LTR model). Agreed to consolidate onto `standards-retrieval/`;
  needs coordination with the teammate who owns `app/`.
- Three mutually incompatible datasets (18 / 10 / 30 standards, different ID
  schemes, only 3 IS numbers in common). No single source of truth.
- No low-confidence / no-match handling.
- Certification logic, related-standards graph, multilingual support, and
  document upload are not built.

---
### Minor issue noted, not yet fixed

Running the test suite **rewrites** `standards-retrieval/data/faiss.index`
(same size and header, ~26 KB of differing float bytes — the index is
regenerated nondeterministically). This makes a committed binary artifact
show up as modified after every test run. Either the index should be built
into a temp directory during tests, or it should not be committed at all.

---
