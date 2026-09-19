# Standards Engine — Frontend

React frontend for the AI-powered recommendation engine that identifies applicable Indian
Standards for procurement specifications. Built against the screen-by-screen contract in
[`../Solution_details/05_Website_Workflow.md`](../Solution_details/05_Website_Workflow.md).

## Running

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build to dist/
npm run lint
```

## Design system

Minimal **matte** finish — flat surfaces, hairline borders, no gradients, glow or emoji.
Depth comes from a four-level elevation scale and tone, never from gloss.

| Token group | Notes |
|---|---|
| Neutrals | Warm-tinted ramp; page ground `#F4F3F0`, never pure white |
| Ink | Four steps, all ≥ 4.5:1 on every surface they appear on |
| Elevation | `--e1`…`--e4`: tight offsets, low alpha, stacked with a hairline |
| Accent | Restrained brass `#7A6029`, used sparingly for certification emphasis |
| Type | Inter variable with optical sizing; JetBrains Mono for IS numbers |

Headings use size-graded tracking (tighter as they grow); numeric columns are tabular.
Both light and dark themes are defined; the toggle persists to `localStorage`.

Identity is a **wordmark** (StandEng) rather than an icon mark.

## Screens

Five top-level destinations in the left rail; everything else nests inside one.

| Route | Screen | Notes |
|---|---|---|
| `/` | Landing | Single-column hero, pipeline explainer, trust markers |
| `/login` | Login | Credentials then role & organisation selection |
| `/app/query` | **Entry / recommendations** | Three columns: parsed attributes (editable) · ranked cards · filters |
| `/app/boq` | **Upload tender / BOQ** | Multi-item parse, per-item review, partial-parse reporting |
| `/app/builder` | **Spec builder** | Grouped basket, clause generation, gap warnings, export, freeze |
| `/app/map` | **Related standards map** | Depth toggle, branch-select, graph or list |
| `/app/standard/:code` | **Standard detail** | Version timeline, scope, normative + reverse references |
| `/app/certification` | **Certification** | Scheme, QCO provenance, marking rules, copy-ready clause |
| `/app/audit` | Tender audit | Track-changes redline, severity tags, impact estimates |
| `/app/projects` | My projects | Saved tenders, templates, recent activity |
| `/app/catalogue` | Standards catalogue | Search and browse the registry |
| `/app/simulator` | Scenario simulator | Parameter deltas against a base cluster |
| `/app/alerts` | Alerts | Amendment watch, subscriptions, channels |
| `/app/compliance` | Compliance dashboard | Org-wide charts (admin) |
| `/app/admin` | Admin console | Catalogue sync, flagged items, ranking feedback |
| `/app/settings` | Settings | Profile, org, API keys, audit trail |

## Workflows

- **A — Quick lookup** (the primary demo path): query → ranked cards → detail → add branch from the map → builder → copy clause.
- **B — Full document analysis**: upload BOQ → per-item recommendations → accept each → one consolidated spec.
- **C — Audit an existing tender**: upload → status table → apply fixes → export review report.
- **D — Regional-language query**: Hindi/Tamil/Bengali input, with the interpreted English shown for confirmation.
- **E — Amendment watch**: subscriptions plus a revision feed on the Alerts screen.

## Designed states

Empty · parsing (staged) · low confidence (band, not a number) · no match (orphan refusal with nearest
categories) · conflict (two overlapping standards side by side, authoritative one marked) · superseded
(struck through, replacement named — never silently hidden) · partial document parse (unreadable BOQ
lines reported with a reason, not dropped).

## Notable implementation decisions

**The spec basket is the product.** Standards collected on any screen accumulate in a shared
store ([`src/state/SpecStore.jsx`](src/state/SpecStore.jsx)) and leave as clause text. It persists
to `localStorage`, so a refresh or a standard opened in a new tab does not discard a
half-assembled specification.

**Match bands, not percentages.** A retrieval score is not a measurement. Cards show
strong / probable / needs-review; the underlying number stays internal.

**Parsed attributes are editable.** If the engine reads 1100V as 1100W the officer corrects it in
place and re-runs, rather than distrusting the whole result. Uncertain reads are marked, not hidden.

**Certification is its own screen.** Whether a product carries a mandatory obligation is a legally
distinct question from which standard describes it, and it traces to a named Quality Control Order.

**Gap warnings are rule-based.** A spec with no test method or no primary standard is flagged by
explicit rules, not inference, so the officer can see why.

**The cluster graph is hand-rolled inline SVG**, not `react-force-graph` — nodes inherit theme
tokens and cost nothing in bundle size. Every graph has a list/table equivalent.

**Recharts is lazily loaded** — only `/app/compliance` needs it, so the main bundle is ~430 kB
(~122 kB gzipped) rather than carrying 394 kB of charting on every route.

## Verification performed

- **Accessibility:** axe-core WCAG 2.1 A/AA — **0 violations** across all 18 routes in both
  themes (36 checks). Fixes made to reach this: `--ink-faint` (3.08:1 → 4.67:1 worst case),
  the accent on its soft background (4.06:1 → 4.96:1), superseded timeline entries (now carry
  meaning via strikethrough rather than opacity), and horizontally scrollable table regions
  (now keyboard focusable with a region label naming each table).
- **Render:** all 18 routes paint with no console or page errors, light and dark.
- **Responsive:** no horizontal overflow at 375/768/1024/1440. Two-column layouts use a
  `.split` class rather than inline templates so the collapse rule reliably applies.
- **Navigation:** mobile drawer verified to open, close and reopen via the toggle, the scrim
  and the Escape key.
- **Flows:** Workflow A (query → detail → map branch → builder → clause) and Workflow B
  (BOQ upload → per-item accept) exercised end to end, no runtime errors.
- `npm run lint` (0 errors) and `npm run build` both clean.

## Data accuracy

Sample data was checked against the live BIS catalogue rather than written from memory.
Four errors were found and corrected:

| Was | Now |
|---|---|
| IS 8112:2013 shown as current | **Withdrawn** — consolidated into IS 269:2015; kept in the catalogue so tenders citing it can be flagged |
| IS 2062:2011 shown as superseded | **Current** (7th revision, reaffirmed 2016) |
| IS 9968 (Part 1) "superseded by a 2023 edition" | No such edition — the 1988 first revision is current with 3 amendments; it is inapplicable on *scope* (elastomer vs PVC), which is the better example anyway |
| QCO cited as "Electric Wires… Order, 2003", notified 21 March | Correct title is **Electrical Wires, Cables, Appliances and Protection Devices and Accessories (Quality Control) Order, 2003**, S.O. 189(E), notified **17 February 2003** |

Verified against [BIS](https://bis.gov.in/PDF/cart/PM_694.pdf), the
[QCO gazette record](https://indiankanoon.org/doc/71444681/),
[IS 2062](https://law.resource.org/pub/in/bis/S10/is.2062.2011.pdf) and
[IS 9968](https://bis.gov.in/wp-content/uploads/2020/06/PM-9968-V2.pdf).

## Backend integration

All data is mocked in [`src/data/mock.js`](src/data/mock.js) (pipeline responses) and
[`src/data/catalogue.js`](src/data/catalogue.js) (standard detail, certification, BOQ), with shapes matching the
response contracts in the workflow doc. Swapping in the real FastAPI endpoints
(`/v1/recommend`, `/v1/audit`, `/v1/standards/{code}/cluster`) is a fetch-layer change — no
component restructuring needed.

Not yet built (out of scope for this pass): the Chrome extension overlay, real authentication,
and live document parsing.
