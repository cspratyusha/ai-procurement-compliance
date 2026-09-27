# Data

## The served corpus

**[`standards_corpus_full.json`](standards_corpus_full.json): 21,848 records,
19,597 distinct standards, 22 sectors.** This is what the site serves
(`STANDARDS_CORPUS=full`). It is built from the complete Public.Resource.Org
archive of the BIS catalogue on archive.org (the `gov.in.is.*` collection),
merged with the 96 curated records below.

| | Records |
|---|---|
| Published SCOPE clause, read from the standard (OCR) | 13,749 |
| Real number and title only, no usable scope clause | 8,003 |
| Curated pilot records | 96 |
| Of all records: current editions | 19,604 |
| Of all records: superseded by a newer edition in the corpus | 2,244 |

None of it is verified against BIS directly (`"verified": false` on every
record), and the archive is a snapshot, so standards published after it are
missing.

### How it is built

`run_full_ingest.ps1` runs the three stages unattended and logs to
`archive/full_ingest.log`:

```powershell
powershell -File data\run_full_ingest.ps1              # fetch, merge, index
powershell -File data\run_full_ingest.ps1 -From index   # resume a failed run
```

1. **Fetch** ([`ingest_archive.py`](ingest_archive.py)): lists the collection,
   turns each archive identifier into an IS designation (plain parts and
   sections, IS/ISO, IS/IEC, IS/ISO/IEC, IS/QC, ISO/IEC Guides, SP
   publications, supplements and tentative standards), downloads the text of
   each one into `archive/cache/` (reused on later runs), extracts the SCOPE
   clause and assigns a sector. A standard no sector rule matches is kept as
   `general` rather than dropped. Of the 22,024 items, 21,937 parse; the rest
   are archive records whose designation cannot be read reliably.
2. **Merge** ([`build_full_corpus.py`](build_full_corpus.py)): combines the
   ingest with the curated records (curated wins for the same number), keeps
   OCR-damaged records on number and title, marks each older archive edition
   superseded by the newest edition present, assigns ids, and re-points
   `eval_set_full.json` and `train_queries_full.json` at those ids. Ids are
   positional, so this remap is what keeps the query sets meaningful after a
   rebuild.
3. **Index** (`standards-retrieval/indexing/build.py`): rebuilds the FAISS and
   BM25 indexes for the full corpus.

Restart the API afterwards; it reads the corpus once, at startup.

### The allied-standards graph

[`extract_references.py`](extract_references.py) reads the cached text of
every standard and records the standards it cites, writing
`relationships/extracted_relationships.json` (88,623 links from 16,944
standards, about 28 MB):

```powershell
.venv\Scripts\python data\extract_references.py --sample 400   # report only
.venv\Scripts\python data\extract_references.py                # write
```

- **Where it reads:** the REFERENCES clause or referred-standards annex
  (where numbers usually appear without the "IS" prefix, so a number with an
  edition year is accepted), and explicit "IS" citations in the body.
- **What it excludes:** the standard citing itself, sentences about history
  ("supersedes", "revision of", "previously covered", "under revision"),
  numbers belonging to ISO/IEC and other bodies, and OCR artefacts (numbers
  glued to letters, the "© BIS" imprint, numbers higher than any IS).
- **How it resolves:** an exact edition when the corpus holds it, otherwise
  the current edition of the same standard (the cited edition is recorded);
  a standard the corpus does not hold is kept and flagged `outside_corpus`.
- **Evidence:** every link keeps the passage it was read from.
- **Measured:** it finds all 16 of the hand-read links whose text supports
  them (4 of the 20 checkable were added from domain knowledge and are not in
  the text), and about 97% of a random sample of links were read correctly.

The 25 hand-read links in `relationships/relationships.json` take precedence
wherever both describe the same pair. The API also reports standards whose
text was read and cites nothing, which is different from never read.

## The curated pilot corpus

**[`standards_corpus.json`](standards_corpus.json), 45 standards, 7 sectors.**
The corpus the project started from, still used by the end-to-end suite and
the demo script (`STANDARDS_CORPUS=canonical`). It is produced by
[`consolidate.py`](consolidate.py), which merges the three datasets that grew
independently earlier in the project. The certification, amendment and
relationship research is keyed to these records.

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

- **Identity** is the normalized IS number, case, spacing and `Part` casing
  are normalized so `IS 1554 (part 1):1988` and `IS 1554 (Part 1):1988` are
  recognized as one standard.
- **On conflict**, the record with the longer `scope` + `description` wins,
  because those are the fields the retrieval pipeline embeds. Keywords from
  the losing record are kept.
- **Status** (`active` / `superseded`) is preserved, `retrieval/postprocess.py`
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

[`eval_set_consolidated.json`](eval_set_consolidated.json), the original 24
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
effect has not been demonstrated here**, both corpora are small enough that
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
| "hot rolled structural steel angle" | `uncertain`, returned a steel *tube* standard | `strong`, IS 808:1989 |
| "safety helmet for construction workers" | `none` | `strong`, IS 2925:1984 |
| "banana" | `none` | `none` |

## Selecting a corpus

`STANDARDS_CORPUS` picks which corpus the engine loads, indexes and trains
against. It is read in one place (`standards-retrieval/data_loader.py`),
because `load_corpus()` is called from a dozen sites with no argument.

```bash
STANDARDS_CORPUS=full        # data/standards_corpus_full.json (21,848), what the site serves
STANDARDS_CORPUS=canonical   # data/standards_corpus.json (45 standards)
STANDARDS_CORPUS=mock        # data/mock_corpus.json (30), the default
STANDARDS_CORPUS=/some/path  # that file
```

Artifacts are kept **per corpus**, because an index or a trained ranker is
only valid for the corpus it was built from:

| | mock (default) | canonical | full |
|---|---|---|---|
| Indexes | `standards-retrieval/data/` | `standards-retrieval/data/index/standards_corpus/` | `standards-retrieval/data/index/standards_corpus_full/` |
| Model | `standards-retrieval/models/` | `standards-retrieval/models/standards_corpus/` | not trained yet |

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
cross-validation score and the held-out score, see Phase D in
[`../PROGRESS.md`](../PROGRESS.md) for a worked example (CV 0.93, held-out
0.24).

## Other files

| Path | Purpose |
|---|---|
| `raw/` | Original scraped/authored inputs, kept for provenance |
| `seed_standards.json` | Earlier seed dataset, superseded by the canonical corpus |
| `derived/` | Generated index artifacts |
| `schema.sql` | Relational schema for the Postgres ingestion path in `app/` |
| `certification/bis_compulsory.json` | BIS's lists of products under compulsory certification (Scheme I ISI, Scheme II CRS, Scheme X): 904 entries, 749 standards, each with its order, gazette notification, link and in-force or deferred status. Rebuilt by `certification/parse_bis_compulsory.py` from the saved BIS pages |
| `certification/certification_rules.json` | Hand-researched rules: codes of practice checked as needing no certification, and withdrawn editions. BIS's lists win where both exist |
| `raw/certification_rules.json` | Earlier placeholder rules, kept for provenance only |
| `amendments/extracted_amendments.json` | Amendment slips read from every standard's archived text by `extract_amendments.py`: 21,820 copies read, 3,428 with amendments (5,424 amendments, 4,112 dated), each with the year its copy is current to. A slip counts only if it names the standard it is bound into |
| `amendments/amendments.json` | Amendments researched by hand from BIS documents for 3 standards; these win over the text |
| `amendments/bis_kys.json` | BIS's Know Your Standard record for 33,761 standards (all 34,300 pages, read 28 September 2026): title, withdrawn flag, replacement, amendment count. 5,548 standards have amendments, 8,937 in all. Fetched by `bis_kys.py fetch` into `archive/kys_cache/` (not committed) and merged by `bis_kys.py combine`. This official count wins over both files above |
| `apply_bis_status.py` | Writes BIS's withdrawn status and replacement into `standards_corpus_full.json` (`withdrawn`, `superseded_by_number`, `withdrawal_note`, `status_source: "bis"`). Last run: 19,719 editions matched, 7,141 withdrawn, 5,767 newly marked superseded, 2,129 with no BIS record |
| `archive/` | The archive ingest output, its text cache, and pipeline logs (logs and `backup/` are not committed) |
| `run_full_ingest.ps1` | Fetch, merge and index the full corpus in one run |
