# Data

## The canonical corpus

**[`standards_corpus.json`](standards_corpus.json) — 45 standards, 7 sectors.**
This is the single source of truth. It is produced by
[`consolidate.py`](consolidate.py), which merges the three datasets that grew
independently earlier in the project.

```bash
python data/consolidate.py --check   # validate, write nothing
python data/consolidate.py           # write standards_corpus.json
```

### ⚠️ This is not verified BIS data

The IS numbers and titles are realistic, but **none of them have been checked
against the BIS catalogue**. Every record carries `"verified": false`. Scope
and description text was written for semantic-search development, not copied
from the standards themselves. Do not present this as authoritative.

### What was merged

| Source | Records | Id scheme | Fate |
|---|---|---|---|
| `../standards-retrieval/data/mock_corpus.json` | 30 | `IS-ELEC-001` | merged |
| `raw/standards.json` | 18 | `std_001` | merged |
| `seed_standards.json` | 10 | *(different schema)* | merged |
| **`standards_corpus.json`** | **45** | `IS-ELEC-001` | **canonical** |

58 input records → 45 unique standards. 12 appeared in more than one source;
each record's `sources` field records where it came from.

The three sources shared only **three** IS numbers between the two largest,
and used three different category vocabularies (`Electrical Cables & Wires`,
`electrical_cables`, `Electrical & Energy`). `consolidate.py` maps all of them
onto one snake_case vocabulary and fails loudly on any value it does not
recognize, rather than silently inventing a sector.

### Merge rules

- **Identity** is the normalized IS number — case, spacing and `Part` casing
  are normalized so `IS 1554 (part 1):1988` and `IS 1554 (Part 1):1988` are
  recognized as one standard.
- **On conflict**, the record with the longer `scope` + `description` wins,
  because those are the fields the retrieval pipeline embeds. Keywords from
  the losing record are kept.
- **Status** (`active` / `superseded`) is preserved — `retrieval/postprocess.py`
  derives supersession penalties from it.

### Cross-family supersession

`postprocess.py` detects supersession by matching standard *families*
(`IS 1554 (Part 1):1988` → `IS 1554 (Part 1):2020`). Two standards in this
corpus are replaced by a different number entirely, which that heuristic
cannot see:

| Withdrawn | Replaced by |
|---|---|
| `IS 226:1975` | `IS 2062:2011` |
| `IS 1139:1966` | `IS 1786:2008` |

These are declared in `CROSS_FAMILY_SUPERSESSION` in `consolidate.py` and
surface as `superseded_by_number`. Like everything else here, they are
unverified. `consolidate.py --check` fails if a declared replacement is not
present in the corpus.

## Evaluation set

[`eval_set_consolidated.json`](eval_set_consolidated.json) — the original 24
evaluation queries with `correct_id` remapped onto the canonical ids. All 24
remapped cleanly. Each entry also carries `correct_number` so the mapping
survives any future re-numbering.

## Measured effect of consolidating

Rebuilding the indexes over 45 standards instead of 30, NDCG@5 on the same 24
queries:

| Pipeline | 30 standards | 45, old model | 45, retrained |
|---|---|---|---|
| Hybrid (dense + BM25 RRF) | 0.9430 | 0.9382 | 0.9382 |
| + Cross-encoder | 0.9609 | 0.9609 | 0.9609 |
| + LTR | **0.9846** | 0.9692 | **0.9846** |

The middle column served the **mock-corpus ranker** over the canonical corpus.
That mismatch, not corpus difficulty, accounts for most of the drop: with the
ranker retrained on the corpus it serves, the score returns to 0.9846.

So the honest reading is narrower than it first appeared: **a corpus-size
effect has not been demonstrated here** — both corpora are small enough that
retrieval stays easy. The reason to expect decline at realistic scale
(~22,000 standards) is that near-duplicate standards become far more common,
not anything these numbers show.

What the numbers *do* establish is that each stage improves on the one before
it, consistently across both corpora.

### A larger corpus answers more queries

Consolidation brought PPE and structural sections into scope, so queries the
30-standard corpus could not answer now resolve:

| Query | 30 standards | 45 standards |
|---|---|---|
| "hot rolled structural steel angle" | `uncertain` — returned a steel *tube* standard | `strong` — IS 808:1989 |
| "safety helmet for construction workers" | `none` | `strong` — IS 2925:1984 |
| "banana" | `none` | `none` |

## Selecting a corpus

`STANDARDS_CORPUS` picks which corpus the engine loads, indexes and trains
against. It is read in one place (`standards-retrieval/data_loader.py`),
because `load_corpus()` is called from a dozen sites with no argument.

```bash
STANDARDS_CORPUS=canonical   # data/standards_corpus.json (45 standards)
STANDARDS_CORPUS=mock        # data/mock_corpus.json (30) — the default
STANDARDS_CORPUS=/some/path  # that file
```

Artifacts are kept **per corpus**, because an index or a trained ranker is
only valid for the corpus it was built from:

| | mock (default) | canonical |
|---|---|---|
| Indexes | `standards-retrieval/data/` | `standards-retrieval/data/index/standards_corpus/` |
| Model | `standards-retrieval/models/` | `standards-retrieval/models/standards_corpus/` |

## Rebuilding indexes and retraining

```bash
cd standards-retrieval

# Indexes
STANDARDS_CORPUS=canonical PYTHONPATH=. python indexing/build.py

# Ranker (uses the matching query sets automatically)
STANDARDS_CORPUS=canonical PYTHONPATH=. python ltr/train.py
```

Training ends at a promotion gate: a candidate is only written to the live
model path if it beats both the cross-encoder baseline and a conservative
lower bound from 5-fold CV. On rejection the previous model is moved to
`ltr_model_previous.txt` rather than deleted.

**If you change the corpus, remap the query sets first.** Both reference
standards by id, and `consolidate.py` renumbers ids:

```bash
python data/remap_to_canonical.py --check   # report
python data/remap_to_canonical.py           # write
```

Training the ranker against a mismatched query set produces a model whose
labels point at the wrong standards. It shows up as a large gap between the
cross-validation score and the held-out score — see Phase D in
[`../PROGRESS.md`](../PROGRESS.md) for a worked example (CV 0.93, held-out
0.24).

## Other files

| Path | Purpose |
|---|---|
| `raw/` | Original scraped/authored inputs — kept for provenance |
| `seed_standards.json` | Earlier seed dataset, superseded by the canonical corpus |
| `derived/` | Generated index artifacts |
| `schema.sql` | Relational schema for the Postgres ingestion path in `app/` |
| `certification/`, `raw/certification_rules.json` | Placeholder certification rules — **not** from the official BIS lists |
