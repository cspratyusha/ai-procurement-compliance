# Project progress log

A running record of what has been built, tested, and left open. Newest entry
at the top.

---

## Phase L — Demo script and fresh-clone verification (2026-09-21)

**Goal:** the brief's Phase 10 — prove the project runs from a clean checkout,
and write a demo that can actually be performed.

### Fresh-clone verification, actually performed

The README claimed the project runs from a fresh clone. That claim had never
been tested, so it was a wish rather than a fact. It has now been done:

```
git clone <repo> /tmp/freshclone
```

- 308 tracked files.
- **The LightGBM models survive checkout intact** — 8,319 and 11,566 bytes,
  exactly matching their blobs. This is the Phase A bug not recurring: without
  `.gitattributes`, `core.autocrlf` would have inflated the first to 8,598
  bytes and broken it. Both load: 7 features / 7 trees and 7 features / 11
  trees.
- **`pytest` — 92 passed** in the clean clone, no extra setup.
- **`npm install && npm run build`** — clean.

### Demo script

`docs/demo-script.md`: a timed seven-minute walkthrough with a pre-flight
checklist, the questions judges tend to ask with honest answers, and a
troubleshooting section covering the two failure modes that actually bit
during development — a stale uvicorn holding port 8000, and Git Bash mangling
UTF-8 in Hindi test queries.

The script is built around leading with the limitations rather than hiding
them. Step 2 is the out-of-scope query, and the script says explicitly: *"This
is the most important thirty seconds of the demo. Do not skip it."* A tool
that is confidently wrong about a legal requirement is worse than no tool, and
showing the refusal is more convincing than showing another good answer.

### Every step verified against the running system

A demo script nobody has run is a wish too. All thirteen assertions were
checked in the browser against the live stack:

| | |
|---|---|
| Search returns cards with an ISI badge | 683 ms |
| "safety helmet" resolves to IS 2925:1984 | ok |
| "laptop computer" renders zero recommendations | ok |
| Heading changes to "Nearest text matches" | ok |
| IS 456 shows "6 in force" and "10 related" | ok |
| Outside-corpus citations shown and flagged | ok |
| Hindi chip shows the translation panel | ok |
| Tender builder carries the GeM disclaimer | ok |
| Generated clause cites the real 2003 QCO | ok |

### README finished

Added a capability table, the test commands with their real counts, the
fresh-clone result, and a pointer to the demo script. Clarified the corpus
startup command, which was written for one working directory and silently
wrong from the other.

### The brief is complete

Every phase of the original build plan is delivered, and every requirement in
the problem statement is met: semantic matching, allied standards, latest
version with amendments, certification flags, multilingual input, and a mock
procurement-portal demo.

**Tests: 92 backend + 22 end-to-end = 114.**

### Still open, honestly

These are data and scope items, not missing engineering:

- 28 of 45 standards have unverified certification status; 42 have
  unresearched amendments; 29 have no relationship data.
- The corpus is 45 standards against a real catalogue of ~22,000.
- Standards map is the last screen still on fixture data.
- OCR for scanned tenders, and UI chrome translation, are unbuilt.

---

## Phase K — Published amendments (2026-09-21)

**Goal:** the last unmet requirement in the problem statement — "shows the
latest published version and any amendments".

### Why this matters more than it sounds

An amendment can change the material, the test regime or the acceptance
criteria. A tender citing the base edition of a standard that has since been
amended can specify something no longer conformant. IS 456:2000 has **six**
amendments; a tender citing it bare is citing a 2000 document while the site
is built to a 2024 one.

### Researched, not generated

Read from BIS product manuals and published amendment documents:

| Standard | Amendments | Source |
|---|---|---|
| IS 694:2010 | **4** | BIS Product Manual PM/IS 694/3 (May 2020), "No. of Amendments: 4" |
| IS 456:2000 | **6** | Published amendment documents; No. 4 read in full |
| IS 800:2007 | **2** | Published amendment documents |

Amendment No. 4 to IS 456 was extracted from the published PDF, so its
summary is real clause-level content: *"Revises clauses 5.3 and 5.3.4
(aggregates and batching), 5.4 (water, to permit treated water) and 5.4.3
(sea water)."*

### A count without dates stays a count

BIS states IS 694:2010 has four amendments but the sources read did not give
their numbers or dates. Listing four entries with plausible-looking dates
would be fabrication, so the count is reported and the list stays empty:

> IS 694:2010, incorporating all 4 published amendments

Where individual amendments *are* known, the citation names the latest:

> IS 456:2000, incorporating all 6 amendments, latest (Amendment No. 6, June 2024)

Dates from secondary sources are marked `likely` and the UI shows them as
"unconfirmed date" next to the confirmed one — the same three-way honesty as
certification's `none` / `not_verified`.

### The corpus dates were placeholders

The corpus records `last_amended` for 42 of 45 standards. Checked against
reality, these are invented: IS 800:2007 carries `2019-10-10`, which matches
neither of its real amendments (January 2012 and one undated). The researched
data now takes precedence in the citation, and the corpus field is left alone
rather than silently "corrected" with more guesses.

### Tested

- **`pytest` — 92 passed** (was 84). Eight new tests, the important ones being
  that a count without dates does not become invented dates, that an
  unresearched standard reports `checked: false` rather than "no amendments",
  and that a citation omits an unknown date instead of printing "None".
- **Playwright — 22 passed.**
- Browser-verified: IS 456 shows "6 in force" with the full history and
  clause-level summary on No. 4; IS 694 shows "4 in force" with the
  count-only citation; IS 17048 says amendments have not been checked.

### Still open

- 42 of 45 standards have unresearched amendments.
- Standards map screen still fixture data.
- No demo script; no fresh-clone verification.
- OCR for scanned tenders; UI chrome i18n.

---

## Phase J — Tender builder, and a committed end-to-end suite (2026-09-21)

**Goal:** the problem statement's "demoed as if embedded inside a procurement
portal", and a regression suite that actually protects the honesty guarantees.

### Tender builder

A simplified tender form with live recommendations beside it. As the official
types the item description, the engine searches in the background (debounced
900 ms) and offers the standards that belong in the specification. Accepting
one assembles a conformance clause:

> **2. CONFORMANCE** — The item shall conform in all respects to IS 694:2010,
> in the latest edition in force on the date of supply, including all amendments.
>
> **3. CERTIFICATION** — IS 694:2010 falls under mandatory BIS certification.
> The supplier shall hold a valid BIS licence and the goods shall bear the
> Standard Mark (ISI). The licence number shall be quoted in the bid.
> Governing order: Electrical Wires, Cables, Appliances and Protection Devices
> and Accessories (Quality Control) Order, 2003.

That is a paste-ready clause citing a real QCO, assembled from the standards
the official accepted — not from what the engine happened to suggest.

A superseded standard in the accepted set adds its own NOTE clause, because an
official pasting this into a live tender needs to know.

The screen states plainly that it is not connected to GeM. The pattern is
demonstrated; the integration is not claimed.

### End-to-end suite

Playwright runs have been ad-hoc all along. They are now committed as
`frontend/e2e/journey.spec.js`, run with `npm run test:e2e` against a live
backend — deliberately unmocked, because the failures worth catching here are
integration failures: missing CORS, a stale server, a response shape the UI
cannot render.

**11 tests x desktop and mobile = 22 passing.** Two of them exist specifically
to stop the honesty guarantees regressing:

- an out-of-scope query must render **zero** recommendation cards in the
  browser, whatever the API returned;
- fixture screens must carry the "Illustrative screen" label and live screens
  must not — asserted per route, both directions.

The rest cover search, the certification badge surviving the round trip, Hindi
translation being shown rather than applied silently, catalogue filtering,
the allied-standards cluster, a standard outside the corpus, the tender
clause, and a sweep asserting no route logs a console error or scrolls
horizontally.

### A test-selector bug, not a product bug

The out-of-scope test first failed on a strict-mode violation: "not
recommendations" appears twice on that screen, in the banner and in the
reference-list heading. Both are correct — the duplication is the point — so
the assertion was changed to check presence rather than uniqueness.

### Tested

- **`pytest` — 84 passed**; **Playwright — 22 passed** (11 x 2 projects).
- Manual browser check of the tender builder: 5 live suggestions for a cable
  spec, clause generated with quantity and certification, out-of-scope
  description suppressed.

### Still open

- Amendment lists: the corpus records `last_amended` as a date but not the
  individual amendments. The problem statement asks for amendments.
- Standards map screen still fixture data.
- No demo script; no fresh-clone verification.
- OCR for scanned tenders; UI chrome i18n.

---

## Phase I — LLM explanation layer, local via Ollama (2026-09-21)

**Goal:** the brief's Phase 3 — a plain-language reason per result — built so
that it cannot damage the trustworthiness of everything around it.

### Hardware

Checked before choosing a model: i9-13900HX (24 cores), RTX 4060 laptop GPU
(8 GB VRAM), 15.7 GB RAM, 100 GB free. Installed Ollama 0.34.2 and pulled
**qwen2.5:7b-instruct** — fits in VRAM, strong at constrained JSON.

### The design rule

The LLM **only describes candidates it was given**. It never chooses which
standards are returned, never reorders them, and contributes nothing to the
certification or supersession verdicts. Retrieval and curated data stay
authoritative.

This matters because the product's value is being trustworthy about legal
requirements. A fabricated IS number reaching a tender document is the worst
output this system could produce, so:

- Ollama's JSON mode constrains decoding, which is what makes a 7B model
  reliable enough to parse without a retry loop (3/3 valid on first probe).
- **Every returned IS number is checked against the candidate list.** Anything
  else is discarded and logged. A model that helpfully adds "IS 9999:2020"
  gets that line dropped while the legitimate explanations survive.
- Only the top 5 candidates are sent, so a long result list cannot become a
  long prompt.
- Any failure — unreachable, timeout, unparseable — returns no explanations
  rather than an error. The search already succeeded; explanations are a
  bonus on top of it.

### Off by default

`explain` is opt-in per request. Without it, a query is ~380 ms. With it,
~2.5 s warm. The results are byte-identical either way; only prose is added.
`explanations_available` tells the UI whether to offer the checkbox at all, so
a machine without Ollama simply never sees it.

### Quality, observed

The explanations are genuinely discriminating:

- *"This fits the requirement as it specifies 43 grade ordinary Portland cement."* (IS 8112)
- *"This does not fit as it specifies 53 grade cement, not 43 grade."* (IS 12269)
- *"This does not fit the requirement as it is for submersible pump cables intended for borewells."* (IS 14257)

It correctly separates 43-grade from 53-grade cement and rejects an
irrelevant cable — the kind of distinction a procurement official actually
needs to see stated.

### A bug the out-of-scope test caught

The first implementation generated explanations for a query the confidence
gate had already marked `none`. The guard read `confidence != "none"` where
`confidence` is the dict returned by `assess_confidence`, so it was always
true. A "banana" query was getting three fluent explanations of why cable
standards did not match it — directly undercutting the "these are not
recommendations" framing.

Fixed to `confidence["level"] != "none"`. Out-of-scope queries now skip the
LLM entirely and return in 176 ms instead of 2.4 s.

### Tested

- **`pytest` — 84 passed** (was 74). Ten new tests, most of them on the
  hallucination guard: invented numbers discarded while valid ones survive,
  prose-wrapped JSON salvaged, unparseable output yielding nothing, model
  failure degrading to empty, malformed entries skipped individually,
  overlong reasons trimmed, and the top-5 cap enforced.
- End-to-end against the live model: cold 3.3 s, warm 2.3-2.5 s, out-of-scope
  176 ms with zero explanations.
- Browser-verified: both the language selector and the explanation toggle are
  visible, 4 of 5 cards carry explanations, no console errors.

### Still open

- Standards map screen still fixture data.
- No committed end-to-end test suite (Playwright runs have been ad-hoc).
- No demo script; no fresh-clone verification.
- OCR for scanned tenders; UI chrome i18n.

---

## Phase H — Allied standards, and a visibility fix (2026-09-21)

**Goal:** build the related-standards cluster the problem statement asks for,
and fix the language selector nobody could find.

### The language selector was there, but hidden

Reported as missing. It was rendering, but the label was `sr-only` and it sat
in the bottom toolbar reading "Detect language" — easy to read as part of the
upload controls rather than as a language choice. Moved above the input with a
visible **"Query language"** label and the hint "Type in any listed language —
it is translated before searching".

Worth recording as a lesson: a Playwright assertion that an element exists is
not evidence that a user will find it.

### Allied standards, read from the standards themselves

The problem statement asks for the applicable *cluster*, not one hit. A tender
citing IS 694 for cable but omitting IS 8130 for the conductor and IS 10810
for test methods is incomplete — that incompleteness is what this surfaces.

Relationships were read from the referred-standards annexes and materials
clauses of the standards themselves, via publicly hosted copies. **25
relationships across 16 standards**, each recorded only where the source
actually cites the target, with the clause noted where known:

| Source | Cites |
|---|---|
| IS 456:2000 | IS 269, IS 1489 (Parts 1 & 2), IS 1786, IS 2062, IS 383, IS 432 (Part 1), IS 3812 |
| IS 694:2010 | IS 8130 (conductor), IS 5831 (insulation), IS 10810 (test methods) |
| IS 800:2007 | IS 2062, IS 808 |
| IS 732:2019 | IS 694, IS 3854, IS 3043 |

Nothing is inferred. Six relation types (normative reference, material spec,
test method, terminology, installation, related product), each with an
explanation the UI shows, so "why is this here" is answered on the page.

### Citations outside the corpus are shown, not hidden

Nine cited standards — IS 8130, IS 5831, IS 10810, IS 383 and others — are
real dependencies the pilot corpus does not hold. They are listed with their
titles and flagged "Not in this corpus" rather than omitted.

Omitting them would silently truncate the cluster and produce exactly the
incomplete citation the feature exists to prevent. This is the same principle
as `not_verified` in Phase F: absence of data must never read as absence of
the thing.

### Reverse edges

`referenced_by` is derived rather than authored, so IS 2062 correctly shows
that IS 456, IS 800, IS 808 and IS 1786 all cite it, without those four edges
being written twice.

### Tested

- **`pytest` — 74 passed** (was 66). Eight new tests: grouped clusters for
  cement and cable, materials kept separate from test methods, outside-corpus
  entries present and flagged, derived reverse edges, an unresearched standard
  reporting `researched: false`, and a data check that every non-flagged
  target actually exists in the corpus.
- Browser-verified: IS 456 shows "10 related" across grouped sections with
  clickable entries; IS 694 shows 4; IS 17048 shows the unresearched message.
  No console errors.
- **48 route-renders** clean.

### Still open

- 29 of 45 standards have no relationship data. The annexes have not been read
  for them; the UI says so rather than implying they stand alone.
- The Standards map screen is still fixture data — it now has a real data
  source to be wired to.
- OCR for scanned tenders; translating results back into the query language;
  UI chrome i18n.

---

## Phase G — Multilingual queries (2026-09-21)

**Goal:** let an official describe what they need in Hindi, Tamil, Bengali,
Marathi or Telugu and get the same standards an English query returns.

### Measured first, then built

Before writing anything, I checked whether the existing English-only stack
already coped with Hindi. It does not:

| Query | cross-encoder score | result |
|---|---|---|
| "copper wire for house wiring" | **+3.5** | IS 694:2010 (correct) |
| "घर की वायरिंग के लिए तांबे का तार" | **−8.4** | IS 456:2000 (wrong) |

The confidence gate from Phase C correctly reported those as no-match, so
Hindi queries returned nothing useful rather than returning nonsense — but
they returned nothing useful.

### Why translation rather than a multilingual embedder

The brief suggested `paraphrase-multilingual-mpnet-base-v2`. Swapping the
embedding model means rebuilding every index and retraining the ranker against
new vectors, and it would still leave the cross-encoder monolingual.
Translating in front of a pipeline that already scores 0.9846 is one step, and
it is reversible.

Model: **facebook/nllb-200-distilled-600M** — open weights, local, no API key,
consistent with the free/open-source constraint. IndicTrans2 was the brief's
suggestion but its distilled checkpoint is 1.8 GB and needs a separate
toolkit; NLLB is a single `transformers` call.

### Measured after

| Language | Query | Searched as | Top result | Confidence |
|---|---|---|---|---|
| Hindi | घर की वायरिंग के लिए तांबे का तार | Copper wire for home wiring | IS 694 (Part 2):2016 | strong |
| Hindi | श्रमिकों के लिए सुरक्षा हेलमेट | Safety helmet for workers | IS 2925:1984 | strong |
| Tamil | குடிநீர் விநியோகத்திற்கான எஃகு குழாய் | Steel pipe for drinking water supply | IS 4984:2016 | strong |
| Bengali | শ্রমিকদের জন্য নিরাপত্তা হেলমেট | Safety helmets for workers | IS 2925:1984 | strong |
| Marathi | बांधकामासाठी पोर्टलँड सिमेंट | Portland cement for construction | IS 12269:2019 | strong |

All five reach `strong` confidence and return the standard the English
phrasing returns. English stays on the fast path at ~280 ms; translated
queries add roughly 400–3000 ms depending on length.

### The translation is shown, not hidden

A wrong machine translation silently producing wrong standards is the failure
mode that matters here, so `/retrieve` returns a `translation` object and the
UI shows both what the user typed and what was actually searched, with the
caveat that it is machine translation. The user can see the engine understood
"copper wire for home wiring" and judge whether that is what they meant.

### Degradation

A failed or unavailable translator falls back to searching the original text
and says so, rather than returning an error. Poor results with an explanation
beat no results. The model loads lazily on first non-English query, so an
English-only session never pays for it.

Devanagari serves both Hindi and Marathi and script detection cannot separate
them, so an explicit language choice always overrides detection.

### Tested

- **`pytest` — 66 passed** (was 57). Nine new tests: script detection across
  four scripts, English bypassing the translator entirely, explicit language
  overriding detection, and — most importantly — that a dead translator
  degrades to the original query instead of raising.
- Browser-verified: selector lists all six languages, the Hindi example chip
  returns IS 694 with the translation panel visible, no console errors.
- **48 route-renders** (16 routes x desktop, mobile, dark) clean.

### A debugging note

Hindi appeared broken through `curl` for several attempts — the query arrived
as `?? ?? ???????`. Git Bash was mangling UTF-8 in the command line before it
reached the server; the code was correct throughout. Non-ASCII payloads need
`--data-binary @file` with the file written as UTF-8, or a Python client.

### Still open

- UI chrome (labels, buttons) is English-only. Only queries and results are
  multilingual; i18next for static strings is not wired.
- Results are returned in English. Translating explanations back into the
  query language is the natural next step.
- OCR for scanned tenders; related-standards graph.

---

## Phase F — Certification data and tender upload (2026-09-21)

**Goal:** add the two features that most distinguish this from a generic
search demo — mandatory certification flags, and accepting a tender document
instead of typed text.

### Certification data, read from BIS

I read the BIS Scheme I (ISI Mark) product list and cross-checked the
Quality Control Order notifications, rather than asking for it to be supplied.
No scraper was written: the pages were read, not crawled.

**17 of 45 standards now have a verified status, 13 of them mandatory**,
spanning every sector in the corpus. Each carries its governing order and
gazette number, e.g. IS 694:2010 → *Electrical Wires, Cables, Appliances and
Protection Devices and Accessories (Quality Control) Order, 2003, S.O. No.
189(E) dated 17 Feb 2003*.

Stored in `data/certification/certification_rules.json`, which records its own
source URL and retrieval date.

### Three answers, not two

`scheme` is `ISI` / `CRS` / `Hallmark` / `none` / `not_verified`, and the last
two must never collapse:

| | meaning |
|---|---|
| `none` | Checked — no scheme applies (e.g. a code of practice) |
| `not_verified` | Nobody checked. **Not** a clearance |

Telling a procurement official "no certification required" when the truth is
"we never looked" is the failure that costs someone money. The BIS list runs
to ~221 rows and could only be read in sections, so absence from what was read
is weak evidence and is recorded as such.

### A data problem this surfaced

Cross-checking revealed that **IS 8112:2018 and IS 12269:2019 do not exist**.
IS 8112 (43 grade OPC) and IS 12269 (53 grade OPC) were both merged into
IS 269:2015 and withdrawn in October 2016. The placeholder corpus invented
later editions of withdrawn standards.

Rather than quietly deleting them, `/retrieve` now returns a `data_warning` on
these entries and the UI shows it, which is the honest treatment of known-bad
data and a good demonstration of the supersession problem the product exists
to solve.

### Tender document upload

`POST /extract` accepts PDF, DOCX or TXT, extracts the text, builds a search
query from it and runs the normal pipeline.

The hard part is not getting text out — it is getting the *right* text out. A
tender is mostly boilerplate by volume (EMD, eligibility, arbitration,
signature blocks), so feeding the whole document to an embedding model that
truncates at a few hundred tokens means searching the cover page. So:

1. Find a recognised heading — "technical specification", "scope of supply",
   "bill of quantities" and similar — and take that section.
2. Within it, keep paragraphs carrying technical markers (`sq mm`, `1100 V`,
   `IS 694`, `grade 43`) and drop boilerplate.
3. Cap at 2000 characters on a word boundary.

**Filtering by paragraph, not by line, matters.** Extracted text wraps
mid-sentence, so "Item 3: Ordinary Portland Cement, 43 grade, for the civil
works associated with" carries no technical marker on its own physical line.
The first implementation filtered line-by-line and silently dropped the cement
from a three-item tender. Caught by a test that checks both products survive.

Scanned PDFs have no text layer. Rather than searching an empty string, the
API returns 422 explaining that the file needs OCR, which is not built.

Limits are enforced server-side, not just in the browser: 10 MB, and
`.pdf`/`.docx`/`.txt` only.

### UI

- Result cards carry a certification badge; confirmed requirements get a full
  banner naming the QCO, in an informational colour rather than an alarming one.
- Upload sits beside the search button. After upload, a panel shows which
  section was read, how much text, and an expandable view of exactly what was
  searched — the extraction step is visible rather than invisible.

### Tested

- **`pytest` — 57 passed** (was 43). 14 new tests: certification lookup
  including the `none` vs `not_verified` distinction and that every rule points
  at a real standard; extraction across PDF/DOCX/TXT, the wrapped-line
  regression, scanned-PDF rejection, oversize and unsupported-type guards.
- End-to-end: uploading the sample tender returns **IS 694:2010 with its ISI
  flag** as top hit, plus the cement standards for its third line item.
- **48 route-renders** (16 routes x desktop, mobile, dark): no console errors,
  no overflow.

### Note on the LLM

There is still **no LLM in this project and no API key is needed**. Retrieval,
ranking, certification and extraction are all local. The brief's Phase 3 LLM
layer (plain-language explanations, allied-standard classification) remains
unbuilt; it is additive, not required for the core product.

### Still open

- 28 of 45 standards have unverified certification status.
- OCR for scanned tenders.
- Related-standards graph, multilingual query support.

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
