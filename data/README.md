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

Rebuilding the indexes over 45 standards instead of 30 and re-running the
benchmark:

| Pipeline | 30 standards | 45 standards |
|---|---|---|
| Hybrid (dense + BM25 RRF) | 0.9430 | 0.9382 |
| + Cross-encoder | 0.9609 | 0.9609 |
| + LTR | **0.9846** | **0.9692** |

LTR Top-1 accuracy fell from 95.8% to 91.7%. **Adding 15 standards measurably
lowered the scores**, which is the clearest available evidence that the
headline numbers are a function of corpus size rather than of real-world
accuracy. Expect further decline as the corpus approaches realistic scale
(BIS publishes ~22,000 standards).

## Rebuilding indexes

The retrieval indexes are built from whichever corpus you point at:

```bash
cd standards-retrieval
PYTHONPATH=. python indexing/build.py --corpus ../data/standards_corpus.json
```

**Caution:** `indexing/build.py` always writes to
`standards-retrieval/data/` (`faiss.index`, `bm25.pkl`, …), overwriting the
committed indexes that the test suite expects. After building against the
consolidated corpus, restore them with:

```bash
git checkout -- standards-retrieval/data/
```

Making the output location follow the corpus choice is tracked in
[`../PROGRESS.md`](../PROGRESS.md).

## Other files

| Path | Purpose |
|---|---|
| `raw/` | Original scraped/authored inputs — kept for provenance |
| `seed_standards.json` | Earlier seed dataset, superseded by the canonical corpus |
| `derived/` | Generated index artifacts |
| `schema.sql` | Relational schema for the Postgres ingestion path in `app/` |
| `certification/`, `raw/certification_rules.json` | Placeholder certification rules — **not** from the official BIS lists |
