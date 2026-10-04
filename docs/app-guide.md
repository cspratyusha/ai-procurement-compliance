# App Guide

How to use the BIS Standards Recommendation Engine, screen by screen: what each
section is, why someone would use it, what to type, and what the results mean.

---

## What the app does, in one paragraph

A procurement officer writing a tender has to name the right Indian Standards
(IS numbers) for every item: the product standard, the standards it depends
on, the latest edition, and whether BIS certification is compulsory. This app
does that. You describe the item (or upload the tender), and it recommends the
applicable standards, shows their allied standards, flags old editions, tells
you if certification is mandatory, and writes the tender clause for you.

## The usual way to use it

1. **Search** the item on **New query**, or upload the whole tender on **Upload tender / BOQ**.
2. **Add** the right standards to your basket (the active project).
3. Check **Certification** for anything that needs the ISI mark, CRS or hallmarking.
4. Open **Spec builder** to get the finished clause text and export it.
5. Before issuing, run the draft through **Audit** to catch old or wrong citations.

---

## The sidebar

| Section | In one line |
|---|---|
| New query | Describe a product, get the standards for it |
| Upload tender / BOQ | Upload a tender or bill of quantities; every item is searched separately |
| Spec builder | Your collected standards turned into tender clause text |
| Tender builder | Type an item description and see standards appear as you type |
| Related standards map | A picture of the standards connected to one standard |
| Certification | Is BIS certification compulsory for this product? |
| Audit | Check a draft tender's IS citations for problems |
| My projects | Your saved specifications (baskets) |
| Dashboard | Usage figures for this installation |
| Corpus health | How complete the data is (admins only) |
| Standards hygiene | Old editions and amendments across the whole catalogue |
| Standards catalogue | Browse every standard the app knows |
| Settings | Profile, password, organisation members, API keys, activity |
| Engine status | Technical health of the engine (admins only) |

---

## New query (the main screen)

**Why use it:** you know what you are buying and need the IS standards for it.

**What to type:** describe the product the way you would in a tender. Examples:

- `PVC insulated copper cable, single core, 1100 V, for house wiring`
- `43 grade ordinary portland cement`
- `laptop for office use`
- `G.I. pipe 25 mm medium class`
- A description in Hindi, Tamil, Bengali or another supported language

Short forms used in tenders (OPC, TMT, GI, DI, HDPE, AAC, RMC and others) are
understood.

**Buttons in the search box:**

- **Upload (paperclip):** search from a document instead of typing (PDF, Word, Excel, text, even scanned PDFs).
- **Language:** leave it on automatic, or pick the language you typed in. 13 languages are supported. The query is translated to English before searching.
- **Explain matches:** when switched on, a local AI model writes one sentence per result saying why it matches. It arrives a few seconds after the results.

**What you see in the results:**

- **Translated from ... / You typed / Searched for:** shown when your query was not in English. Check the translation matches what you meant.
- **Also searched for:** the app added the standards' own technical words to yours (for example "laptop" becomes "information technology equipment safety"). This is why a plain-language query still finds the right standard.
- **BIS lists this product under compulsory certification:** the product needs the ISI mark, CRS registration or hallmarking. It names the order and links to it.
- **Confidence:**
  - **Strong / Match:** the app is confident in the top result.
  - **Uncertain:** a possible match; read the standard before using it.
  - **No match:** the catalogue has no standard close to your description. The results shown are only the nearest text, not recommendations.
- **Each result card:** the IS number, title, whether it is the current edition, its role (primary standard, test method and so on), and **Why it matches**.
- **Add:** puts the standard into your basket (the active project) for the Spec builder.
- **Dismiss:** removes a wrong result and asks why. Your reason helps improve the ranking.

Click any IS number to open its **standard page** (below).

---

## Standard page (opens when you click an IS number)

Everything about one standard:

- **Status:** Current, Superseded (a newer edition exists) or Withdrawn by BIS. If it is old, a yellow box names the edition to cite instead.
- **Scope:** what the standard covers, taken from the published standard. If it says "a summary written for this catalogue", the text is not the standard's own words. If it says "held on its number and official title only", the scope text is not available.
- **Certification:** whether BIS certification is mandatory, under which order.
- **Amendments:** how many amendments BIS lists, with dates.
- **Allied standards:** what this standard depends on, grouped as normative references, material specifications, test methods, safety standards, terminology, installation practice and related products. A tender that cites only the main standard and not these is often incomplete.
- **Look up on BIS:** opens BIS's own page for the standard.

---

## Upload tender / BOQ

**Why use it:** you already have a tender or a bill of quantities (BOQ) with
many items, and want standards for each one without typing them one by one.

**How:** upload a PDF, Word or Excel file (the Excel BOQs that CPPP publishes
work). The app finds each line item ("Item 1: ... Qty ...") and searches each
one separately, so one item's words do not crowd out another's. Open an item
to see its standards and add them to your basket.

If the document has no numbered items, use **Search it as a single
specification instead**.

---

## Spec builder

**Why use it:** to turn the standards you collected into text you can paste
into a tender.

- **Collected standards:** everything you added, grouped by role. You can reorder them.
- **Gap warnings:** for example, a product standard added without its test method. A **critical** gap blocks export until you fix it.
- **Generated clause text:** ready-to-paste tender wording naming each standard.
- **Certification clauses:** the legal wording for ISI, CRS or hallmarking, naming the order.
- **Export:** Word document, print or save as PDF, copy the clause text, or a JSON record for other systems.
- **Audit record (Freeze):** saves the recommendation with a timestamp, so you can later show exactly what was recommended and when.

---

## Tender builder

**Why use it:** a quicker way to write one item. Type the item description and
quantity; suitable standards and certification obligations appear alongside as
you type, with a specification clause you can copy.

---

## Related standards map

**Why use it:** to see, as a diagram, every standard connected to one standard.

**What to type:** an IS number or title, for example `IS 694` (PVC cables) or
`IS 456` (concrete). The chosen standard sits in the middle; the standards it
cites are around it, coloured by type (material, test method, safety and so
on). **Cited by** lists the standards that cite it. **Add a branch** expands
another standard on the same map.

---

## Certification

**Why someone uses it:** before buying a product, an officer must know whether
the law requires BIS certification for it. If a Quality Control Order (QCO)
covers the product, the supplier must hold a BIS licence (ISI mark) or
registration (CRS), and the tender must demand it. Buying an uncertified
product that an order covers is not allowed.

**What to search in the box ("IS number, product or order"):**

- **An IS number:** `IS 694`, `IS 1417`, `IS 4151`, to check that standard.
- **A product name:** `helmet`, `cement`, `LED lamp`, `pressure cooker`, `furniture`, `gold`.
- **An order name:** `Steel`, `Electrical Wires`, `Furniture`, to see everything one order covers.

If your number is not in the list, a **Check IS ...** button appears. It
checks that number anyway and tells you it has no compulsory certification (or
that the app does not hold it).

**The filter buttons:**

- **ISI:** Scheme I, the ISI mark. The manufacturer holds a BIS licence (cement, steel, cables, helmets and many more).
- **CRS:** Scheme II, Compulsory Registration Scheme, mostly electronics and IT (LED lamps, laptops, power adapters).
- **Scheme X:** certification for certain machinery and electrical equipment.
- **Hallmarking:** gold jewellery and artefacts (compulsory in notified districts); silver is voluntary.
- **Deferred:** named in an order whose enforcement BIS has postponed, so **not yet mandatory**.

**What the right side shows after you pick a standard:**

- A plain-language explanation of the position.
- **Scheme, Statutory order** (with a link to the order), **Gazette notification**, and how BIS lists the standard.
- **Products as BIS lists them.**
- **Copy-ready tender clause:** wording that names the standard and the order, so the requirement is enforceable as written. **Add clause to spec** sends it to the Spec builder.

A standard not on these lists has no compulsory certification, unless an order
notified after the date the lists were read adds it (the date is shown at the top).

---

## Audit

**Why use it:** to check a draft tender someone else wrote (or an old tender
being reused) before it is issued.

**How:** upload the draft. Every IS number it cites is checked. Findings:

- **Critical (fix before issuing):** for example, citing an edition that has been replaced or withdrawn. The finding names the edition to cite instead.
- **Minor (should be corrected):** for example, amendments in force that the tender should mention, or an undated citation.
- **Advisory:** worth knowing, not a defect.
- **No issue found:** citations that are fine.
- **What the cited standards depend on:** allied standards the tender leaves out (for example, it cites IS 694 for cable but not IS 8130 for the conductor).

The audit checks what the tender cites. It does not decide what the tender
should have cited; use New query for that.

---

## My projects

Each project is one specification you are building, saved to your account.
The **active** project is the basket that New query, the catalogue and the map
add to. Create a new project for each tender, rename or delete old ones, and
see **Gaps in this set** for the active one.

---

## Dashboard (Usage)

Figures for the whole installation, counted from real searches (nothing is
estimated):

- **Searches served:** total searches, and how many in the last 7 days.
- **Found a match:** percentage of searches where the app found a standard close to the description.
- **No match in corpus:** searches with no suitable standard. These show products the catalogue may not cover (possible gaps).
- **Median response:** typical time the engine takes to answer, in milliseconds.
- **Quick actions:** shortcuts to common tasks.
- **Recent searches:** the latest searches, the top standard each returned, and its verdict (Match, Uncertain, No match).
- **Most searched sectors:** which areas (cement, cables, pipes...) people search most.
- **Officer decisions:** how many results officers **accepted** (added to a spec), **dismissed** or **corrected**, and the acceptance rate. These decisions also help improve the ranking.

Your own searches and decisions are under **Settings, Activity**.

---

## Standards hygiene

A scan of the whole catalogue for **superseded editions** (a newer edition
replaced it; marked "Replaced") and **amendments in force** ("Check before
citing"). Use it to learn which commonly cited standards have changed. It is
computed from BIS's records, not a live alert feed.

## Standards catalogue

Every standard the app can search (about 31,000 editions). Type an IS number,
title or keyword to filter, and click one to open its standard page. If a
standard is not listed here, the app cannot recommend it.

## Corpus health (admins only)

How complete the data is: how many standards have scope text, amendment data,
certification status and allied-standard links, by sector, and where the gaps
are.

## Engine status (admins only)

Technical view: which data and models the engine is running, ranking feedback,
data completeness and coverage gaps.

## Settings

- **Profile and password.**
- **Role and access:** your role (admin or member).
- **Organisation and members (admins):** add colleagues to your organisation.
- **API keys:** keys that let another system (for example a procurement portal such as GeM) use the engine. Give each key a name saying what uses it. The endpoint reference shows how to call it.
- **Activity trail:** a record of what has been done in the workspace.

## Scenario simulator (not in the sidebar, at /app/simulator)

Describe an item, then add a condition (for example "rated for 11 kV" or
"for outdoor use") and see which standards come into play, drop out or change
priority.

---

## Words you will see

| Term | Meaning |
|---|---|
| IS number | An Indian Standard's code, e.g. IS 694:2010 (the part after the colon is the edition year) |
| Edition | A version of a standard; a newer edition replaces an older one |
| Superseded | Replaced by a newer edition. Cite the newer one |
| Withdrawn | Cancelled by BIS. Cannot be enforced in a tender |
| Amendment | An official correction or change to a standard, issued after publication |
| Allied standards | Standards a standard depends on: materials, test methods, safety, terminology, installation |
| QCO | Quality Control Order: a government order making BIS certification compulsory for a product |
| ISI mark | BIS product certification (Scheme I) |
| CRS | Compulsory Registration Scheme (Scheme II), mostly electronics |
| Hallmarking | BIS certification of purity for gold and silver articles |
| Deferred | Named in an order but enforcement postponed, so not yet mandatory |
| BOQ | Bill of quantities: the list of items and quantities in a tender |
| Corpus / catalogue | All the standards the app holds and can search |

## Limits to keep in mind

- Standards BIS published after October 2025 are not in the data yet.
- The top result is right most of the time, not always. Check the standard before issuing a tender, especially when the verdict is **Uncertain**.
- Machine translation can be wrong. The screen always shows what was actually searched.
