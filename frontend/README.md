# Standards Engine: Frontend

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

**Material You (Material Design 3), light scheme only.** Tonal surfaces from a violet seed,
organic radii, pill-shaped controls, and state layers (a translucent overlay) for hover and
press instead of colour swaps. All tokens live in [`src/styles/tokens.css`](src/styles/tokens.css);
the shared components (buttons, cards, chips, filled text fields, segmented buttons, tables) in
[`src/styles/app.css`](src/styles/app.css).

| Token group | Notes |
|---|---|
| Colour roles | MD3 roles from seed `#6750A4`: primary, secondary/tertiary containers, surface containers. Page background `#FFFBFE`, never pure white |
| Legacy aliases | Older names (`--surface`, `--ink`, `--line`…) map onto MD3 roles, so page styles restyle without renames |
| Shape | 8 / 12 / 16 / 24 / 28 / 48 px and full pills. Cards 24 px, hero containers 48 px, every button a pill |
| Elevation | `--e1`…`--e4`: soft, diffuse, low alpha. Cards separate by tone, not borders |
| Motion | `cubic-bezier(0.2, 0, 0, 1)`, 200 ms for controls, 300 ms for surfaces; reduced motion respected |
| Type | Roboto 400/500/700; Roboto Mono for IS numbers |

The homepage and sign-in page carry the expressive treatment (blurred organic shapes, glass
panels); workbench screens stay calm so dense data stays readable. The logo is
[`public/logo.svg`](public/logo.svg), a web copy of the root `logo.svg` cropped to the artwork
and recoloured to the theme.

**Shell.** The sidebar is a navigation drawer that folds to an 80 px rail (remembered per
browser). The top bar holds only the alerts bell and the account menu (email, organisation,
guided demo, sign out).

## Screens

Five top-level destinations in the left rail; everything else nests inside one.

| Route | Screen | Notes |
|---|---|---|
| `/` | Homepage | Hero with live corpus size, Start Demo, pipeline explainer |
| `/login` | Sign in | Credentials then role & organisation selection |
| `/app/query` | **Search** | AI-prompt composer (Enter sends, Shift+Enter new line, stop while searching), then a thread: the query as the user's turn, ranked cards as the response |
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

- **A, Quick lookup** (the primary demo path): query → ranked cards → detail → add branch from the map → builder → copy clause.
- **B, Full document analysis**: upload BOQ → per-item recommendations → accept each → one consolidated spec.
- **C, Audit an existing tender**: upload → status table → apply fixes → export review report.
- **D, Regional-language query**: Hindi/Tamil/Bengali input, with the interpreted English shown for confirmation.
- **E, Amendment watch**: subscriptions plus a revision feed on the Alerts screen.

## Designed states

Empty · parsing (staged) · low confidence (band, not a number) · no match (orphan refusal with nearest
categories) · conflict (two overlapping standards side by side, authoritative one marked) · superseded
(struck through, replacement named, never silently hidden) · partial document parse (unreadable BOQ
lines reported with a reason, not dropped).

## Notable implementation decisions

**The spec basket is the product.** Standards collected on any screen accumulate in a shared
store ([`src/state/SpecStore.jsx`](src/state/SpecStore.jsx)) and leave as clause text. The
basket is the signed-in user's active project, saved on the server half a second after each
edit, so it follows the user to another machine and survives cleared browser data.

**Match bands, not percentages.** A retrieval score is not a measurement. Cards show
strong / probable / needs-review; the underlying number stays internal.

**Parsed attributes are editable.** If the engine reads 1100V as 1100W the officer corrects it in
place and re-runs, rather than distrusting the whole result. Uncertain reads are marked, not hidden.

**Certification is its own screen.** Whether a product carries a mandatory obligation is a legally
distinct question from which standard describes it, and it traces to a named Quality Control Order.

**Gap warnings are rule-based.** A spec with no test method or no primary standard is flagged by
explicit rules, not inference, so the officer can see why.

**The cluster graph is hand-rolled inline SVG**, not `react-force-graph`, nodes inherit theme
tokens and cost nothing in bundle size. Every graph has a list/table equivalent.

**Recharts is lazily loaded**, only `/app/compliance` needs it, so the main bundle is ~430 kB
(~122 kB gzipped) rather than carrying 394 kB of charting on every route.

## Verification performed

- **Accessibility:** `e2e/accessibility.spec.js` runs axe-core (WCAG 2.1 A and AA) on all 18
  screens, desktop and mobile, after each has rendered its content: **0 violations** (36
  checks). The re-audit of the Material You design found and fixed faded text on the homepage
  and on references outside the catalogue (contrast), and an unnamed account button on phones.
  One exclusion, documented in the test: the homepage call-to-action pills, which axe measures
  against a blurred, blended backdrop it cannot model (white on #524083, 8:1, verified on the
  rendered page).
- **Bundle:** every screen except the entry pages loads on first visit; the main bundle is
  323 kB (98 kB gzipped), down from 512 kB, and the build no longer warns.
- **Render:** the redesigned homepage, sign-in, dashboard, search (idle, searching and
  results), audit and sidebar states were checked in screenshots at 1440 px and 390 px.
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
| IS 8112:2013 shown as current | **Withdrawn**, consolidated into IS 269:2015; kept in the catalogue so tenders citing it can be flagged |
| IS 2062:2011 shown as superseded | **Current** (7th revision, reaffirmed 2016) |
| IS 9968 (Part 1) "superseded by a 2023 edition" | No such edition, the 1988 first revision is current with 3 amendments; it is inapplicable on *scope* (elastomer vs PVC), which is the better example anyway |
| QCO cited as "Electric Wires… Order, 2003", notified 21 March | Correct title is **Electrical Wires, Cables, Appliances and Protection Devices and Accessories (Quality Control) Order, 2003**, S.O. 189(E), notified **17 February 2003** |

Verified against [BIS](https://bis.gov.in/PDF/cart/PM_694.pdf), the
[QCO gazette record](https://indiankanoon.org/doc/71444681/),
[IS 2062](https://law.resource.org/pub/in/bis/S10/is.2062.2011.pdf) and
[IS 9968](https://bis.gov.in/wp-content/uploads/2020/06/PM-9968-V2.pdf).

## Backend integration

Every screen calls the live FastAPI backend through [`src/api/client.js`](src/api/client.js),
which also holds the session token and sends it with every request. There is no sample data
in the frontend. Sector labels come from one map in [`src/data/sectors.js`](src/data/sectors.js),
and the few fixed interface lists (graph colours, dismiss reasons) from
[`src/data/ui.js`](src/data/ui.js).

**Accounts.** [`src/state/Auth.jsx`](src/state/Auth.jsx) holds the signed-in user and gates
every `/app` route; a 401 from any call signs the tab out. See the root README for roles,
first-run setup and API keys.

Not yet built: the Chrome extension overlay for GeM.

End-to-end tests sign in once in [`e2e/global-setup.js`](e2e/global-setup.js) with the account
named in [`e2e/auth.js`](e2e/auth.js). On an installation with no accounts it creates that
account as the administrator, so run the suite with the engine pointed at a throwaway
`ACCOUNTS_DB`.
