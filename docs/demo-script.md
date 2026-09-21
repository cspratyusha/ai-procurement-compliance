# Demo script

A seven-minute walkthrough. Every number here was measured on this build; if
something in the demo contradicts this document, trust the running system and
fix the document.

---

## Before you start

Two terminals, both from the repository root.

**Terminal 1 — the engine**

```bash
STANDARDS_CORPUS=canonical .venv/Scripts/python -m uvicorn main:app \
  --port 8000 --app-dir standards-retrieval
```

Wait for `Application startup complete` — about 20 seconds while the embedding
and cross-encoder models load. Confirm:

```bash
curl http://localhost:8000/health
# {"status":"ok","corpus_size":45,"ltr_model_loaded":true}
```

**Terminal 2 — the interface**

```bash
cd frontend && npm run dev
```

**Optional, for the explanation step:** `ollama serve` with
`qwen2.5:7b-instruct` pulled. Run one throwaway query with "Explain why each
standard matched" ticked *before the demo* so the model is warm — the first
call takes ~60 seconds, later ones ~2.5.

**Checklist**

- [ ] `/health` reports `corpus_size: 45` and `ltr_model_loaded: true`
- [ ] http://localhost:5173 loads
- [ ] Explanation model warmed (if demoing it)
- [ ] Browser zoom at 100%, one window, no other tabs

---

## 0. The problem (45 seconds)

> A procurement official writing a tender for electrical cable needs to cite
> the right Indian Standard. There are about 22,000 of them. Cite the wrong
> one and the tender specifies the wrong goods; cite a withdrawn edition and
> you have specified something that can no longer lawfully be supplied; miss
> the mandatory certification and you have a legal problem.
>
> Today that knowledge lives in the heads of a few experienced officials.

---

## 1. Search by meaning (1 minute)

Go to **New query**. Type — do not paste, let them watch it type:

```
PVC insulated copper cable for indoor panel wiring
```

Results in roughly **200 ms**.

> This is not keyword search. The query does not contain "IS 694" or the words
> in that standard's title. Four stages run here: dense vector retrieval and
> BM25 keyword search in parallel, fused, then a cross-encoder re-reads each
> candidate against the query, then a LightGBM ranker trained on this corpus.

Point at the **ISI mark required** badge on IS 694:2010, then the banner:

> That is not a guess. It comes from the BIS Scheme I list: the Electrical
> Wires, Cables, Appliances and Protection Devices and Accessories (Quality
> Control) Order, 2003, gazette S.O. 189(E). Seventeen of our forty-five
> standards have a verified certification status; thirteen are mandatory.

---

## 2. It says when it does not know (1 minute)

**This is the most important thirty seconds of the demo. Do not skip it.**

Click **New query**, then type:

```
safety helmet for construction workers
```

That one works — IS 2925:1984. Now type something genuinely outside the
corpus:

```
laptop computer for the office
```

> The heading changed. It no longer says "Recommended standards" — it says
> "Nearest text matches", and the list below is labelled "not recommendations".
>
> Our corpus covers forty-five standards across seven sectors. IT equipment is
> not one of them, and rather than offering the closest cable standard as
> though it were an answer, the engine says so.
>
> It decides this from the cross-encoder relevance score, which is comparable
> across queries. In-scope queries score around +3 to +9; out-of-scope ones
> sit at −7 to −11. The bands do not overlap.

> A tool that is confidently wrong about a legal requirement is worse than no
> tool. This is the difference between a demo and something an official could
> actually use.

---

## 3. The whole cluster, not one hit (1 minute)

Search `ordinary portland cement 43 grade`, open **IS 456:2000** from the
results — or go straight to
http://localhost:5173/app/standard/IS%20456:2000

Scroll to **Amendments**:

> Six amendments in force. A tender citing "IS 456:2000" bare is citing a
> document from the year 2000 while the site is being built to a 2024 one.
> Here is the citation to paste instead.
>
> Amendment No. 4 shows what it changed — clauses 5.3, 5.3.4, 5.4, 5.4.3 —
> because we read the published amendment document. The other dates came from
> secondary sources, so they are marked "unconfirmed".

Scroll to **Allied standards**:

> Ten related standards, grouped by why they are related. These come from the
> referred-standards annex of IS 456 itself — the cement it permits, the
> aggregate, the reinforcement.
>
> Three are greyed and marked "Not in this corpus". IS 383 for aggregate is a
> real dependency we do not hold. We show it anyway, because hiding it would
> produce exactly the incomplete citation this feature exists to prevent.

---

## 4. Any language (45 seconds)

Back to **New query**. Click the **हिन्दी** example chip.

> `घर की वायरिंग के लिए तांबे का तार` — copper wire for house wiring.

Point at the translation panel:

> It shows what you typed and what it actually searched for. It does not
> translate behind your back, because a wrong translation quietly returning
> the wrong standard is the failure that matters.
>
> Six languages: English, Hindi, Tamil, Bengali, Marathi, Telugu. Translation
> runs locally — no API key, no internet.

Worth stating plainly if asked:

> Without translation a Hindi query scores −8 on the cross-encoder and is
> correctly rejected as no-match. With it, the same query scores +4 and
> returns what the English phrasing returns.

---

## 5. Upload a real tender (1 minute)

Click **Upload tender** and choose
`standards-retrieval/tests/fixtures/sample_tender.pdf`.

> A three-page tender: eligibility criteria, terms and conditions, technical
> specification, delivery schedule.

Point at the extraction panel:

> It found the TECHNICAL SPECIFICATION section and ignored the rest — the
> earnest money deposit, the arbitration clause, the signature block. A tender
> is mostly boilerplate by volume, and feeding all of it to the engine means
> searching the cover page.
>
> "Show the text that was searched" — you can check what it read.

The results include the cable standards *and* the cement standard, because the
tender's third line item is cement.

---

## 6. Inside a procurement portal (1 minute 30)

Go to **Tender builder**.

> This is how it would sit inside GeM. We have no integration access, and the
> screen says so — we are demonstrating the pattern, not claiming the
> integration.

Type into the item description:

```
PVC insulated single core copper conductor cable 1.5 sq mm 1100 V for concealed conduit wiring
```

Standards appear on the right as you type. Set quantity `500`, click
**Accept** on IS 694:2010.

Read the generated clause aloud — this is the payoff:

> **CONFORMANCE** — The item shall conform in all respects to IS 694:2010, in
> the latest edition in force on the date of supply, including all amendments.
>
> **CERTIFICATION** — IS 694:2010 falls under mandatory BIS certification. The
> supplier shall hold a valid BIS licence and the goods shall bear the
> Standard Mark. The licence number shall be quoted in the bid. Governing
> order: Electrical Wires, Cables, Appliances and Protection Devices and
> Accessories (Quality Control) Order, 2003.

> That is paste-ready, and the Quality Control Order in it is real.

---

## 7. Optional — plain-language explanations (30 seconds)

Only if the model is warm. Tick **Explain why each standard matched** and
search `ordinary portland cement 43 grade`.

> A local 7B model, running on this laptop's GPU. No API key.
>
> It correctly separates 43-grade from 53-grade cement.

Then state the boundary, because it is the interesting part:

> The model never decides anything. It only describes candidates retrieval
> already chose. Every IS number it returns is checked against that list and
> discarded if it invented one — there is a test for exactly that. On an
> out-of-scope query it is not called at all, so a no-match never acquires a
> fluent explanation of why the wrong standards almost fit.

---

## 8. Close (30 seconds)

> Forty-five standards, seven sectors, and we say so on the front page. The
> BIS catalogue has about twenty-two thousand.
>
> What is built is the pipeline: four-stage retrieval, a confidence gate that
> refuses to answer outside its coverage, certification and amendment data
> read from BIS sources, an allied-standards graph read from the standards
> themselves, six languages, document upload, and a local LLM that is not
> allowed to invent anything.
>
> Scaling that is a data exercise, not an engineering one. Every screen that
> shows sample data says "Illustrative screen — not live data" on it.

---

## Questions you will be asked

**"How many standards is this really?"**
Forty-five, across seven sectors. It is stated on the landing page and in the
README. The data is realistic but unverified against the BIS catalogue —
except the certification, amendment and relationship data, which was read from
BIS sources and is cited.

**"What is the AI here?"**
Four models. A sentence-transformer (e5-base-v2) for dense retrieval, a
cross-encoder (ms-marco-MiniLM) for re-ranking, a LightGBM LambdaMART ranker
trained on this corpus, and NLLB-200 for translation — plus an optional local
7B LLM for explanations. All run locally. No API keys, no cloud.

**"What is your accuracy?"**
NDCG@5 of 0.9846 and Top-1 of 95.8% on 24 held-out queries — but read that
carefully. It is measured on a 45-standard corpus, where retrieval is an easy
problem. It shows the pipeline is correctly built and that each stage improves
on the last. It is not a claim about the full catalogue, and the README says
so.

**"Why not just use ChatGPT?"**
A language model asked which standard applies will produce a plausible IS
number, and it may not exist. This system retrieves from a fixed corpus and
refuses when it has no match. Where we do use an LLM, it is confined to prose
and every standard number it emits is validated against the retrieved set.

**"Is this connected to GeM?"**
No, and the tender builder says so on screen. We have no integration access.
The API is the integration surface — `POST /retrieve` returns everything a
portal needs.

**"What would you do with more time?"**
Expand the corpus, in that order of priority. The pipeline is built; the
limiting factor is data. Then OCR for scanned tenders, which many real ones
are.

---

## If something breaks

**Results look stale or a change did not take effect.** A previous uvicorn is
probably still holding port 8000, so the new one exited silently. Check the
port owner, not the log.

**Hindi returns nothing sensible from a terminal test.** Git Bash mangles
UTF-8 on the command line. Test through the browser or a Python client.

**Explanations time out.** The first call loads the model (~60 s). Warm it
before the demo. If Ollama is not running, the checkbox does not appear and
everything else works unchanged.

**The engine is unreachable.** The UI says so on the query screen before you
type, with the command to start it. Do not mistake that for a broken frontend.
