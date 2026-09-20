# Project progress log

A running record of what has been built, tested, and left open. Newest entry
at the top.

---

## Phase E — Catalogue and detail wired; fixture screens labelled (2026-09-21)

**Goal:** wire the two screens that have real backing endpoints, and stop the
remaining fixture screens from passing as live.

### Lookup by IS number

`GET /standards/{id}` resolved internal ids only (`IS-ELEC-001`), but the UI
routes by IS number (`/app/standard/IS 694:2010`) — correctly, because
internal ids are reassigned whenever the corpus is rebuilt, so a URL built
from one breaks on the next rebuild. The endpoint now accepts either, and
normalises case, spacing and `(Part n)` casing so `is 694:2010` and
`IS 694 : 2010` resolve to the same standard.

### Two screens now live

- **Standards catalogue** (`/app/catalogue`) — lists the whole corpus from
  `GET /standards`, grouped by sector so partial coverage is visible at a
  glance, with client-side search over number, title, scope and keywords, a
  sector filter and a superseded toggle. It replaces a fixture browser whose
  side panel claimed graph data "loads incrementally from Neo4j".
- **Standard detail** (`/app/standard/:code`) — real scope, description,
  indexed terms, edition and amendment date from `GET /standards/{id}`, with
  a superseded warning and a link out to the BIS record. Sections the dataset
  cannot support (normative references, certification) carry a "Not yet
  built" badge and say plainly why they are empty, instead of rendering an
  empty panel that reads as a genuine "no references" answer.

### The other twelve screens are now labelled

Dashboard, BOQ, Builder, Standards map, Certification, Audit, Simulator,
Projects, Admin, Alerts, Settings and Compliance all render fixture data.
That is a fair way to show an intended workflow, but only while it is obvious
which is which — a dashboard reading "1,248 queries this month" is
indistinguishable from a live one until someone checks.

Each now carries a `DemoDataNotice` naming what is illustrative on that
screen and what would make it real, and pointing at the two screens that do
run against the engine. The three live screens deliberately do not have one.

### Tested

- **`pytest` — 43 passed** (was 40). New tests cover lookup by id and by IS
  number across three spellings, a 404 for a standard outside the corpus, and
  the catalogue listing plus its category filter.
- Browser-verified against the live backend: catalogue renders 30 standards
  in 3 sector groups, filtering to "cement" narrows to 7, clicking through
  loads the detail page, a direct IS-number URL resolves, and an unknown
  standard shows the honest "not in the current corpus" state.
- Badge presence asserted per route: present on fixture screens, absent on
  `/app/query` and `/app/catalogue`.
- **45 route-renders** (15 routes x desktop, mobile, dark) with zero console
  errors and zero horizontal overflow.

### A stale server nearly hid a real bug

The detail page appeared broken during verification — every lookup returned
"not in the current corpus". The cause was an old uvicorn process still
holding port 8000, so the newly started one exited and the browser kept
talking to code from two phases ago. Worth remembering when a change seems
not to take effect: check the port owner, not just the log.

### Still open

- Ten fixture screens remain unwired. The next candidates need backend work
  first: certification needs the compulsory-certification lists, the
  standards map needs relationship data.
- Query history is not persisted, so the dashboard cannot be made real yet.
- Document upload, multilingual query support and the related-standards graph
  remain unbuilt.

---

## Phase D — Canonical corpus made servable; two dangerous bugs found (2026-09-21)

**Goal:** let the engine actually serve the 45-standard consolidated corpus
built in Phase B, which until now existed only as a file nothing read.

### One switch, not a dozen edits

`load_corpus()` is called from a dozen places with no argument, so the corpus
is selected by environment variable and resolved in one place:

```
STANDARDS_CORPUS=canonical   -> data/standards_corpus.json (45 standards)
STANDARDS_CORPUS=mock        -> data/mock_corpus.json (30, still the default)
STANDARDS_CORPUS=/some/path  -> that file
```

`mock` remains the default so existing behaviour, the committed artifacts and
the test suite are unaffected.

### Artifacts are now per-corpus

Indexes and trained models are only valid for the corpus they were built
from. Both previously wrote to one fixed location, so building or training
against the canonical corpus silently overwrote the committed 30-standard
artifacts — the index-clobbering noted at the end of Phase B, and the same
flaw for models. Both now resolve to a per-corpus directory:

- `standards-retrieval/data/index/standards_corpus/` — FAISS + BM25
- `standards-retrieval/models/standards_corpus/` — trained ranker

### Query sets remapped

`data/consolidate.py` renumbers ids, so the training and eval sets had to be
remapped onto the canonical corpus. `data/remap_to_canonical.py` joins on the
**IS number**, which is stable across renumbering, and records
`correct_number` on every record so a future renumbering can be redone from
the number rather than from an id that may have moved. All 74 records (24
eval + 50 training) remapped with zero dangling references.

### Two dangerous bugs, found by retraining

**1. The trainer evaluated against the wrong eval set.** `ltr/train.py` had
the old `data/eval_set.json` hardcoded. Training against the canonical corpus
therefore learned canonical ids and was then scored against old ids, so
nearly every query counted as a miss:

| | NDCG@5 |
|---|---|
| reported | **0.2387** |
| after fixing the eval path | **0.9846** |

The 5-fold CV score during the same run was 0.9276, so the pipeline was
healthy throughout; only the final measurement was wrong. A gap that large
between CV and held-out score is the signature of a label mismatch rather
than a quality problem.

**2. A rejected experiment deleted the working model.** On gate rejection the
trainer called `unlink()` on the live model. So the bad measurement above did
not just report a failure — it took the committed, working
`ltr_model.txt` with it. It was only recoverable because it was in git.

Now archived to `ltr_model_previous.txt` instead of deleted. Serving still
degrades to `fallback_score()` as intended, but the previous model is one
rename away.

### Measured on the canonical corpus, after retraining

| Pipeline | P@1 | Recall@5 | NDCG@5 |
|---|---|---|---|
| Hybrid (dense + BM25 RRF) | 0.8750 | 1.0000 | 0.9382 |
| + Cross-encoder | 0.9167 | 1.0000 | 0.9609 |
| + LTR (retrained on 45) | **0.9583** | 1.0000 | **0.9846** |

**This revises the Phase B conclusion.** Phase B measured NDCG@5 0.9692 on 45
standards and read it as corpus-size difficulty. That measurement used the
*mock-corpus model* against the canonical corpus. With the ranker retrained
on the corpus it serves, performance returns to 0.9846 — so most of that drop
was model/corpus mismatch, not difficulty. The honest statement is now
narrower: **we have not yet demonstrated a corpus-size effect**, because both
measurements are at small scale.

### Better answers, as a side effect of more data

Queries the 30-standard corpus could not answer now resolve correctly,
because consolidation brought in PPE and structural sections:

| Query | 30 standards | 45 standards |
|---|---|---|
| "hot rolled structural steel angle" | `uncertain` — a steel *tube* standard | `strong` — **IS 808:1989** |
| "safety helmet for construction workers" | `none` — nothing relevant held | `strong` — **IS 2925:1984** |
| "banana" | `none` | `none` |

The confidence gate still correctly rejects nonsense.

### Tested

- **`pytest` — 40 passed** on the default corpus; no regression.
- Both corpora load and serve: `/health` reports `corpus_size` 30 or 45
  according to `STANDARDS_CORPUS`, with `ltr_model_loaded: true` in both.
- Building canonical indexes leaves the committed 30-standard indexes
  untouched, verified with `git status`.

### Still open

- `STANDARDS_CORPUS=mock` is still the default. Switching requires committing
  the canonical indexes and model, which is the natural next step.
- The confidence thresholds were tuned against the 30-standard corpus and
  have not been re-tuned for 45.
- 17 of 18 screens still render fixture data.

---

## Phase C — Frontend wired to the live engine (2026-09-21)

**Goal:** make the UI actually call the backend, stop presenting wrong
answers confidently, and remove unsupportable claims from the interface.

### The frontend was not connected to anything

`grep -r "fetch\|axios" frontend/src` returned nothing. All 19 screens ran on
hardcoded fixtures. `Query.jsx` faked a search with `setTimeout` timers and
then displayed the same canned `RECOMMENDATIONS` array regardless of what was
typed; its "no match" state triggered on *word count* (`< 3 words`), not on
any measure of relevance.

### Backend changes

- **CORS was missing entirely.** The browser blocks cross-origin POSTs, so the
  UI could not have called the API even if it had tried. Added
  `CORSMiddleware` with an explicit localhost origin list rather than `*`,
  since the service writes feedback logs.
- **Enriched `/retrieve` results** with `scope`, `category`, `status`,
  `version`, `last_amended` and `superseded_by`, so rendering a result card
  does not cost one extra request per result.
- **Added a confidence verdict** to the response: `confidence`
  (`strong` | `uncertain` | `none`), `confidence_reason`, and `corpus_size`.

### How the confidence gate works, and why not `final_score`

`final_score` is rescaled per response, so the top hit always scores well
even when every candidate is irrelevant — "banana" and "PVC copper wire"
both produce a confident-looking top score. It cannot separate the two.

The cross-encoder logit is an absolute relevance estimate and is comparable
across queries. Measured on the corpus:

| | cross-encoder logit of top hit |
|---|---|
| in-scope queries | +2.8 … +9.6 (one outlier at −4.0) |
| out-of-scope queries | −6.7 … −11.2 |

Thresholds are set at `>= 0` for `strong` and `<= -6` for `none`, with the
gap between them reported as `uncertain` rather than forced into a binary.
The in-scope outlier ("hot rolled structural steel angle") lands in that
middle band, which is the honest answer for it.

### Frontend changes

- New `src/api/client.js`: the single place that talks to the backend.
  Distinguishes offline / timeout / HTTP failures, with a 45 s timeout
  because a cold start loads two transformer models.
- `Query.jsx` rewritten against the live API. The fake pipeline animation is
  gone. Kept the existing visual design — it was well built.
- When the backend reports `confidence: "none"`, the heading changes from
  "Recommended standards" to **"Nearest text matches"**, the recommendation
  list is emptied, and everything moves into a reference section labelled
  "not recommendations".
- On `confidence: "uncertain"` the top candidate is still shown above the
  caution banner, with the rest demoted. A first pass filtered on the
  cross-encoder sign here too, which emptied the list whenever every
  candidate scored negative — the user got a warning and nothing to act on.
  Caught during the full-stack run-through with "hot rolled structural steel
  angle", a query the 30-standard corpus genuinely cannot answer well
  (it holds steel *tubes*, no structural angle).
- Backend-unreachable state is surfaced *before* searching, with the command
  needed to start it. The UI never silently falls back to mock data — a demo
  that looks identical whether or not the engine is running is worse than one
  that admits the engine is down.

### Removed unsupportable claims from the landing page

It advertised **"1.4M API calls served monthly"**, **"11 portals
integrated"**, **"22,418 standards indexed"**, **"94% Top-1 retrieval
accuracy"** and **"0 unexplained answers"**. None of that was true. Replaced
with figures that are measured or checkable (4 retrieval stages, ~200 ms
typical query, 45 standards in the pilot corpus, ~22,000 published Indian
Standards for scale), plus a prototype disclosure in the hero. Feature claims
describing unbuilt functionality are now marked "In progress".

### Two UI bugs found and fixed

1. `.notice` blocks clipped their text: flex children default to
   `min-width: auto` and refuse to shrink below content width.
2. The fixed-position spec-basket tab sat on top of page content at the right
   edge. Reserved a gutter for it on viewports wide enough to show it.

### Tested

- **`pytest` — 40 passed** (was 37), including three new tests: in-scope
  queries stay `strong`, out-of-scope queries report `none` with a reason,
  and results carry the presentation fields. The response-shape contract test
  was updated deliberately, not loosened.
- **Browser-verified against the running backend** (Playwright, Chromium):
  - in-scope query renders 5 real result cards from the live corpus
  - `"safety helmet for construction workers"` renders the no-match banner and
    **0 recommendation cards** — the Phase A regression is fixed
  - **no console errors** on landing, dashboard or query
  - no horizontal overflow at 390 px; dark mode renders correctly
- Measured in-browser: **162–224 ms** per query against the live engine.
- **Full-stack run-through from cold start**, both servers restarted from
  scratch: all 17 routes render with zero console errors, zero failed
  requests and no horizontal overflow; verified at 390 px, 768 px and
  1440 px, in light and dark themes. Empty input disables the submit button,
  example chips run a search, and "New query" clears the form and results.
- **Backend-down path verified** by aborting requests to the API: the UI warns
  on load that the engine is not running, explains the failure after a failed
  search, and offers a retry rather than showing a blank screen.

### Still open

- Only `Query.jsx` is wired. The other 18 screens still render fixtures, and
  are not yet labelled as such in the UI.
- The pipeline still serves the 30-standard `mock_corpus.json`; switching to
  the 45-standard consolidated corpus needs the LTR model retrained against it.
- Confidence thresholds are tuned on ~12 probe queries against a 30-standard
  corpus. They will need re-tuning as the corpus grows.
- Certification logic, related-standards graph, multilingual query support and
  document upload remain unbuilt.

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
