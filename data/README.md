# Data

## The served corpus

**[`standards_corpus_full.json`](standards_corpus_full.json): 31,349 records
(editions), 25,915 standards, 22 sectors.** This is what the site serves
(`STANDARDS_CORPUS=full`). It is built from the complete Public.Resource.Org
archive of the BIS catalogue on archive.org (the `gov.in.is.*` collection),
the editions BIS's Know Your Standard records list as current that the
archive lacks, and the pilot records that survived checking against BIS.

| | Records |
|---|---|
| Published SCOPE clause, read from the standard (OCR), `published_text_ocr` | 13,791 |
| Real number and title only, no usable scope clause, `number_and_title_only` | 17,528 |
| Number and title checked against BIS, scope a written summary, `scope_written` | 30 |
| Of all records: current editions | 22,452 |
| Of all records: superseded or withdrawn | 8,897 |

Every edition is either listed by BIS's own record or published in the
archive (`tests/test_pilot_verification.py` fails otherwise). Standards BIS
published after its old portal closed in October 2025 are missing.

**The pilot records.** The project began with 96 hand-made records, and 23
of them named editions BIS does not list (IS 8112:2018, when BIS merged
IS 8112 into IS 269:2015; IS 12894:2020, when the current edition is
IS 12894:2002). Served, they ranked first for everyday searches and made the
real current editions look superseded. `build_full_corpus.py` now keeps a
pilot record only when BIS lists that exact edition or the archive holds the
published standard, and every dropped number is listed in
[`pilot_corrections.json`](pilot_corrections.json) with the real standard it
stood for, where links, certification rules and query labels were moved.
The 73 kept take their title from the published standard or BIS
(`pilot_title` keeps the old one), their scope from the published text where
the archive has it, and otherwise keep a written summary labelled
`scope_written`, which the standard's page says is not the standard's own
words. Where the pilot had put a number on the wrong product the real one
wins: IS 14257 (the pilot's pump cables) now carries its published scope as
BIS's motor vehicle battery standard, and IS 12231 (the pilot's soil and
waste pipes, BIS's pump suction pipes) keeps no scope. The pilot's written
descriptions, amendment dates and keywords are gone.

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
   ingest with the pilot records that pass checking against BIS (see above), keeps
   OCR-damaged records on number and title, marks each older archive edition
   superseded by the newest edition present, assigns ids, and re-points
   `eval_set_full.json` and `train_queries_full.json` at those ids. Ids are
   positional, so this remap is what keeps the query sets meaningful after a
   rebuild.
3. **Index** (`standards-retrieval/indexing/build.py`): rebuilds the FAISS and
   BM25 indexes for the full corpus.

Restart the API afterwards; it reads the corpus once, at startup.

Between merge and index, `add_bis_standards.py` and `apply_bis_status.py`
bring in BIS's own record (below), and both re-point the query sets again,
since the ids of BIS's records are assigned after the merge.

The extractor was improved after the texts were fetched, so
`ingest_archive.py --rescope` re-reads every cached text and re-extracts its
scope without downloading anything. Most OCR renderings run clause 1's
heading into the text ("1 SCOPE This standard prescribes ..."), which only a
heading on a line of its own used to match; those fell through to the first
"This standard specifies ..." sentence anywhere near the top, often in the
foreword. The rescope of 4 October 2026 found a scope clause for 2,896
standards that had none and corrected 2,865 (IS 10500, drinking water, had
been searched as "the acceptable limits and the permissible limits in the
absence of alternate source").

### Keeping up with BIS

BIS's Know Your Standard pages stop at 1 October 2025; what BIS has published,
withdrawn or amended since is on its new standards portal
(standards.bis.gov.in), whose pages read a public JSON API.
[`bis_portal.py`](bis_portal.py) reads it in three resumable steps,
`published` (every standard published or revised in a date range, by
department), `details` (each standard's current record: withdrawn and when,
and every amendment with its year) and `combine`, into
`amendments/bis_portal.json`. That record is overlaid on the Know Your
Standard one before `add_bis_standards.py` and `apply_bis_status.py` read it,
so a revision supersedes the older edition by the same rules as before.

The engine runs all of it itself, while it is running: at startup, if the
last complete refresh is more than a week old (`BIS_REFRESH_DAYS`), a
background thread runs the portal steps, the merge and the index, and the
engine swaps in the new corpus when they finish, without a restart
([`standards-retrieval/bis_refresh.py`](../standards-retrieval/bis_refresh.py)).
There is no scheduled task. It re-reads any record older than 30 days, which
is how withdrawals and new amendments are noticed; the corpus and index are
backed up first and put back if a step fails or the engine is closed mid-way.
`BIS_AUTO_REFRESH=0` turns it off; `python standards-retrieval/bis_refresh.py`
runs one by hand.

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
STANDARDS_CORPUS=full        # data/standards_corpus_full.json (31,349), what the site serves
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
| `certification/bis_compulsory.json` | BIS's lists of products under compulsory certification (Scheme I ISI, Scheme II CRS, Scheme X): 904 entries, 749 standards, each with its order, gazette notification, link and in-force or deferred status. Rebuilt by `certification/parse_bis_compulsory.py --fetch`, which the engine's refresh runs: it reads BIS's English pages and keeps the previous list if a page no longer parses |
| `certification/certification_rules.json` | Hand-researched rules: codes of practice checked as needing no certification, and withdrawn editions. BIS's lists win where both exist |
| `certification/hallmarking.json` | BIS hallmarking: gold jewellery and artefacts (IS 1417) compulsory under the Hallmarking of Gold Jewellery and Gold Artefacts Order, 2020 (S.O. 205(E)), in the 392 districts of its Annexure as last substituted by S.O. 4345(E) on 3 August 2026, with the order's exemptions; silver (IS 2112) voluntary. Every fact cites the gazette notification it was read from; the notifications are saved in `certification/source/hallmarking/` |
| `raw/certification_rules.json` | Earlier placeholder rules, kept for provenance only |
| `amendments/extracted_amendments.json` | Amendment slips read from every standard's archived text by `extract_amendments.py`: 21,820 copies read, 3,428 with amendments (5,424 amendments, 4,112 dated), each with the year its copy is current to. A slip counts only if it names the standard it is bound into |
| `amendments/amendments.json` | Amendments researched by hand from BIS documents for 3 standards; these win over the text |
| `amendments/bis_kys.json` | BIS's Know Your Standard record for 33,761 standards (all 34,300 pages, read 28 September 2026): title, withdrawn flag, replacement, amendment count. 5,548 standards have amendments, 8,937 in all. Fetched by `bis_kys.py fetch` into `archive/kys_cache/` (not committed) and merged by `bis_kys.py combine`, which repairs the double-encoded text in 1,556 of BIS's titles. This official count wins over both files above |
| `pilot_corrections.json` | The 23 pilot editions BIS does not list, each with the reason and the real standard it stood for (`by`, null where the number belongs to another standard). The build refuses to drop a pilot record not explained here, and query labels naming one follow it to `by` |
| `add_bis_standards.py` | Adds the editions BIS lists as current that the archive never had, as records on number and official title only (`provenance: number_and_title_only`, source BIS's page, ids `IS-BIS-nnnnn` so no existing id shifts). Last run (4 October 2026, with the portal overlaid): 11,198 added (7,225 standards not held at all, 3,973 newer editions of standards held only in an older one, 1,674 of them published after the Know Your Standard snapshot); 106 entries with a malformed number were left out. A newer edition is searched with the scope clause of the edition it revises where that is held (2,845, `provenance: scope_from_previous_edition`, `scope_edition`). Run after `build_full_corpus.py`, before `apply_bis_status.py` |
| `apply_bis_status.py` | Writes BIS's withdrawn status and replacement into `standards_corpus_full.json` (`withdrawn`, `superseded_by_number`, `withdrawal_note`, `status_source: "bis"`). Where BIS's record names no replacement but BIS lists a newer edition as current, that edition is named (`replacement_source: "bis_newer_edition"`, 1,212 editions). Also replaces broken archive titles with BIS's official title (3,866) and repairs double-encoded text, keeping the original as `archive_title`. Last run: 29,243 editions matched, 7,141 withdrawn, 2,129 with no BIS record |
| `bis_portal.py`, `amendments/bis_portal.json` | BIS's new standards portal: the 1,681 standards published or revised from 1 October 2025 to 4 October 2026 (763 new, 918 revisions), and each served edition's current record (withdrawn and when, amendments with their years). Per-standard records are cached in `archive/portal_cache/` (not committed). Overlaid on `bis_kys.json` by `add_bis_standards.py`, `apply_bis_status.py` and the amendments layer, as BIS's newer record |
| `archive/bis_refresh_state.json`, `archive/bis_refresh.log` | When the engine's last BIS refresh completed, and what each run did (not committed) |
| `bis_scopes.json` | The SCOPE clause of 1,417 of the 1,681 standards BIS published since October 2025, read by `bis_portal.py scopes` from the document BIS's portal links (born-digital; only the clause is kept, the document is not stored). Used by `add_bis_standards.py` before the previous edition's scope |
| `bis_summaries.json` | BIS's plain-language summaries (one page each, published on its portal), read by `bis_portal.py summaries`: 497 so far, found for 7 in 10 standards under compulsory certification and about 1 in 150 of those held on title only. Attached by `apply_bis_status.py`: the opening is searched (`description`), the whole shown (`bis_summary`) |
| `translation_glossary.json` | Procurement words per language whose literal translation goes wrong, and English loanwords the translator mangles in an Indian script (40 of 240 in a fixed test), replaced by their English form before a query is translated (`standards-retrieval/translation.py`) |
| `benchmark_heldout_queries.json` | A second multilingual set, 8 other items in 12 languages, written before the word list to judge it on items it was not made from |
| `benchmark_queries.json` | The fixed buyer-language benchmark (52 English queries, 8 items in each of 12 Indian languages), run by `standards-retrieval/eval/benchmark.py` |
| `benchmark_results/` | Per-query benchmark results (`--out`), kept so a later run can be compared query by query. `2026-10-04_before.json` is the corpus as committed on 28 September, scored with the current labels; `2026-10-04_after.json` is this rebuild. `2026-10-05_*`: both multilingual sets before the translation word list and after it, the summaries and the new scope clauses |
| `text_repair.py` | Undoes text encoded as UTF-8 and read as Windows-1252 ("â€“" for an en dash), which BIS's own records carry; used by `bis_kys.py` and `apply_bis_status.py` |
| `archive/` | The archive ingest output, its text cache, and pipeline logs (logs and `backup/` are not committed) |
| `run_full_ingest.ps1` | Fetch, merge and index the full corpus in one run |
