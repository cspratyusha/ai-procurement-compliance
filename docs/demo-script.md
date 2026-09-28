# Demo script

An eight-minute walkthrough on the full catalogue. Every example here was run
on this build; if something in the demo contradicts this document, trust the
running system and fix the document.

The built-in guided demo is separate: **Start Demo** on the homepage, or
**Start guided demo** in the account menu, drives the live app by itself and
covers the same ground. Use it when you want to talk rather than click.

---

## Before you start

Two terminals, both from the repository root.

**Terminal 1, the engine**

```powershell
$env:STANDARDS_CORPUS = 'full'
.venv\Scripts\python -m uvicorn main:app --port 8000 --app-dir standards-retrieval
```

Wait for `Application startup complete`, about 20 seconds while the models
load. Confirm:

```powershell
curl http://localhost:8000/health
# {"status":"ok","corpus_size":31372, ...}
```

**Terminal 2, the interface**

```powershell
cd frontend; npm run dev
```

Open http://localhost:5173 and **sign in** with your account (on a fresh
installation the sign-in page sets up the first administrator).

**Optional, for the explanation step:** Ollama running with
`qwen2.5:7b-instruct`. The engine loads it at startup; without it the
explanation option simply does not appear.

**Checklist**

- [ ] `/health` reports `corpus_size: 31372`
- [ ] Signed in, the dashboard loads
- [ ] Browser zoom at 100%, one window, no other tabs

---

## 0. The problem (45 seconds)

> A procurement officer writing a tender has to cite the right Indian
> Standards. BIS lists over 22,000 as current. Cite the wrong one and the tender
> specifies the wrong goods; cite a withdrawn edition and it specifies
> something that can no longer lawfully be supplied; miss a mandatory
> certification and an uncertified supplier can win the contract.
>
> Today that knowledge lives in the heads of a few experienced officials.

---

## 1. Search by meaning (1 minute)

Go to **New query**. Type, do not paste:

```
PVC insulated copper cable for indoor panel wiring
```

Results in well under a second.

> The query does not contain "IS 694" or the words of its title. Dense vectors
> and BM25 keyword search run together, a cross-encoder re-reads every
> candidate against the query, and the best comes first.

Point at **ISI mark required** on IS 694, then the banner:

> Read from BIS's own list of products under compulsory certification, with
> the order that imposes it: the Electrical Wires, Cables, Appliances and
> Protection Devices and Accessories (Quality Control) Order. The link opens
> the order itself.

---

## 2. Buyers do not write like standards (1 minute)

New query:

```
laptop for office use
```

> "Laptop" appears in no Indian Standard title. The engine adds the standards'
> own words, "information technology equipment safety", and says so in the blue
> note, the way it shows a translation. It finds IS 13252. It says "uncertain"
> and why: the catalogue holds that standard on its number and title only, so
> the match cannot be confirmed from its scope.
>
> The shield note is BIS: laptops are under compulsory registration, CRS, to
> IS/IEC 62368-1. BIS names products in everyday words, so the engine checks
> those lists too.

Then a tender line as a schedule of rates writes it:

```
Providing ISI mark G.I. pipe 25 mm medium class, excluding GST
```

> GI, MS, DI, RCC, OPC, TMT, XLPE, MCB, M25: tenders are written in short forms,
> often with full stops, and padded with rates and taxes. This finds IS 1239
> (Part 1), the standard for galvanized steel tubes, and ignores the GST.

Office furniture, the most common GeM purchase:

```
office chair
```

> IS 17631, work chairs, and the shield note: ISI mark compulsory under the
> Furniture (Quality Control) Order, 2025.

---

## 3. It says when it does not know (45 seconds)

**Do not skip this.**

```
insurance cover for office vehicles
```

> "No close match". Services have no Indian Standard, and rather than offering
> the nearest vehicle standard as an answer, it says so and labels the list
> "nearest text matches, not recommendations".

> A tool that is confidently wrong about a legal requirement is worse than no
> tool.

---

## 4. One standard, in full (1 minute)

Open IS 694:2010 from the first search (the IS number is a link), or go to
http://localhost:5173/app/standard/IS%20694:2010

- **Amendments:** the official count from BIS's record for the standard, with
  dates read from the amendment slips in the standard's own copy, and the
  citation to paste ("including all amendments").
- **Allied standards:** what IS 694 depends on, read from its own references
  clause, each with the sentence it came from: IS 8130 for conductors, IS 5831
  for insulation, IS 10810 for tests; and **related product standards**, the
  cable standards closest in scope (IS 1554, IS 7098), which it does not cite
  but a buyer has to choose between.
- **Certification:** ISI mark compulsory, with the order and a link.

For **safety standards**, open IS 374:2019 (ceiling fans): it cites IS 302,
the appliance safety standard, grouped as such.

Then open a withdrawn edition, e.g.
http://localhost:5173/app/standard/IS%2010258:2002

> BIS lists this edition as withdrawn and replaced by the 2023 edition. The
> page says "cite IS 10258:2023 instead", even though the catalogue does not
> hold the new edition's text.

---

## 5. Certification (45 seconds)

Go to **Certification**.

> Every product on BIS's compulsory lists, ISI, CRS and Scheme X: about 750
> standards, each with its order and a link. Filter to **Deferred**:
>
> The Electrical Equipment order names circuit breakers, contactors and
> switches, but a 2025 order defers all of them except small breakers. They
> are shown as not yet mandatory. Reading the list without that order would
> tell a buyer something the law does not.

Filter to **Hallmarking**:

> Gold jewellery and artefacts, IS 1417: hallmarking compulsory under the
> Hallmarking Order, in the 392 districts its latest amendment lists, with the
> order's exemptions. Silver, IS 2112: hallmarking available but voluntary, so
> the tender clause is offered as optional.

Type any IS number to check it, e.g. `IS 383:2016`: "not on BIS's compulsory
lists", with the date the lists were read.

---

## 6. Audit a tender (1 minute 30)

Go to **Audit** and upload `frontend/public/demo/sample-tender.txt`.

> Every IS number in the document, checked: an outdated edition with its
> replacement named, citations with no year, amendments not cited.

Scroll to **What the cited standards depend on**:

> And what the cited standards themselves require that the tender leaves out,
> read from each standard's references and "shall be tested as per" clauses.
> A tender citing IS 694 but not IS 8130 leaves the conductor undefined.

State the limit plainly:

> It cannot tell whether the tender cites the right product standard in the
> first place. No findings is not a pass.

Then **Upload tender / BOQ** with `frontend/public/demo/sample-boq.xlsx`:

> A bill of quantities in Excel, as CPPP publishes them: each row is matched
> on its own, with its quantity.

---

## 7. Any language (30 seconds)

**New query**, click the **हिन्दी** chip (`घर की वायरिंग के लिए तांबे का तार`,
copper wire for house wiring).

> It shows what you typed and what it searched for. Thirteen languages, English
> and twelve Indian ones, translated on this machine, no internet. Type in a
> script it does not support and it says so rather than returning nothing.

---

## 8. Optional: plain-language explanations (30 seconds)

If Ollama is running, the **Why it matches** notes fill in under each result a
few seconds after the results appear.

> A local 7B model on this laptop. It only describes candidates retrieval
> already chose; any IS number it writes that was not retrieved is discarded,
> and on a no-match it is not called at all.

---

## 9. Close (30 seconds)

> 99% of the standards BIS lists as current. Certification from BIS's own
> compulsory lists and its hallmarking order, amendments and edition status
> from BIS's record for each standard, allied standards of all six kinds read
> from the standards themselves, a tender and BOQ audit, thirteen languages,
> an API and a widget for portals, and everything runs on your own machine.

---

## Questions you will be asked

**"How many standards?"**
31,372 records, 25,919 distinct standards: 99% of the 22,224 standards BIS
lists as current. 13,845 carry the scope clause read from the published
document; the rest are held on their number and official title from BIS's
record, and say so. Certification covers BIS's full compulsory lists (about
750 standards) and its hallmarking order; amendment counts and edition status
come from BIS's record for each standard.

**"What is the AI here?"**
A sentence-transformer (e5-base-v2) for meaning, BM25 for exact terms, a
cross-encoder for re-ranking, NLLB-200 for translation, and an optional local
7B model for explanations. All local. No API keys, no cloud.

**"What is your accuracy?"**
On 30 product queries written before they were run and never tuned on, the
right standard is in the top five for all 30 and first for 23. On 27 real
tender lines from a state schedule of rates, the standard the line cites is in
the top five for 21 and first for 17. On 236 held-out queries written from the
standards' titles, Recall@5 0.94 and P@1 0.83 (the standard, in any edition).
The confidence gate was calibrated on 35 genuinely out-of-scope queries.

**"Why not just use ChatGPT?"**
Asked which standard applies, a language model produces a plausible IS number
that may not exist, or a withdrawn edition. This retrieves from a fixed
catalogue, checks BIS's lists, and refuses when it has no match. Where a
language model is used, every IS number it writes is checked against what was
retrieved.

**"Is it connected to GeM?"**
Not to GeM itself: GeM has no public interface for third parties. Any portal
can integrate two ways: its backend calls `POST /retrieve` with an API key
from Settings ([docs/integration-guide.md](integration-guide.md)), or its
specification page adds one script tag and gets the recommendations under the
text field (`/widget/demo.html` shows it on a sample form).

**"Is it secure?"**
Accounts with hashed passwords and tokens, role-based access, throttled
sign-in, an activity trail per user, and organisations cannot see each
other's work.

**"What is not done?"**
Standards published after October 2025 (on BIS's new portal), dates for
amendments known only from BIS's count, the scope text of the records held on
number and title only, and hosting: it runs on this machine today.

---

## If something breaks

**Results look stale or a change did not take effect.** A previous uvicorn may
still hold port 8000. Check the port owner, not the log. If the interface looks
out of date, restart `npm run dev`: a dev server left running for days can
stop picking up file changes.

**Explanations do not appear.** Ollama is not running or the model is still
loading; everything else works unchanged.

**The engine is unreachable.** The sign-in page and the query screen say so.
Do not mistake that for a broken frontend.
