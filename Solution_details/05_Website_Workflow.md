# Website Workflow (User Journey) — Frontend ↔ Backend

## 1. Journey Map

```
LANDING PAGE
     │
     ▼
LOGIN / SIGNUP ──▶ (first login) ROLE & ORG SETUP
     │
     ▼
DASHBOARD HOME ─────┬──────────┬──────────┬──────────┬──────────┐
     │              │          │          │          │          │
     ▼              ▼          ▼          ▼          ▼          ▼
NEW SPEC       AUDIT       STANDARDS   SCENARIO   COMPLIANCE   ALERTS &
QUERY          TENDER      EXPLORER    SIMULATOR  DASHBOARD    SETTINGS
     │              │          │          │          │          │
     ▼              ▼          ▼          ▼          ▼          ▼
RESULT VIEW    GAP REPORT  GRAPH VIEW  DELTA VIEW  CHARTS      SUBSCRIPTIONS
     │              │                                              │
     ▼              ▼                                              ▼
ACCEPT/EDIT    REDLINE FIX                                    NOTIFICATIONS
     │              │
     └──────┬───────┘
            ▼
     EXPORT / SAVE TO TENDER  +  LOGGED TO AUDIT TRAIL
```

---

## 2. Screen-by-Screen Flow

### 2.1 Login & Authentication

**Frontend**
- Login screen: official email / government ID, or SSO if integrated with departmental identity systems.
- First-time login prompts role selection and organisation association.

**Backend**
- Auth service validates credentials against the user store.
- Issues a JWT containing user ID, role, and organisation ID.
- Loads the org profile (subscribed categories, integration settings, permission scope).
- Role determines which navigation items render and which API scopes are permitted.

**Roles**

| Role | Scope |
|---|---|
| Procurement Officer | Own queries, audits, spec generation |
| PSE / Department Admin | All of the above + org-wide compliance dashboard + user management |
| Agency Integrator | API key management, integration configuration, usage analytics |
| Private Org User | Recommendation, audit, certification lookup (no org dashboard unless enabled) |

---

### 2.2 Dashboard Home

**Frontend renders**
- Recent queries and audited tenders
- Pending alerts (revisions affecting subscribed categories)
- Quick-action cards: *New Specification*, *Audit Tender*, *Standards Explorer*, *Scenario Simulator*, *Compliance Dashboard* (role-gated)
- Summary tiles: queries this month, gaps found, outdated citations flagged

**Backend**
- A single aggregated summary endpoint returns recent activity, alert queue, and role-appropriate org statistics in one payload — avoiding multiple round trips on page load.
- Statistics are read from pre-computed aggregates (refreshed by a scheduled job), not recomputed live.

---

### 2.3 New Specification Query

**Frontend**
- Input area: type a product description, paste a spec excerpt, upload a file, or use the microphone for voice input.
- Optional filters: product category, sector, language.
- Submit → loading state showing pipeline stages (retrieving → expanding → verifying).

**Backend**
- Runs the full recommendation pipeline (see `04_System_Workflow.md`).
- Returns structured JSON with ranked standards, scores, explanations, cluster graph, flags, and draft clause.

**Frontend result view — per recommendation card**
- Standard number and title
- Confidence score badge
- "Why recommended" explanation
- Version badge (Latest / Superseded, with plain-language diff on expand)
- Certification tag (BIS / CRS / Hallmarking, if applicable)
- Overlap warning, if a competing-scope standard exists
- Trust score indicator, where dispute-history data is available
- Expandable **allied standards cluster** — rendered as an interactive graph
- Actions: Accept · Reject · Correct (search & substitute) · Copy generated clause

**On user action**
- Action posted to the backend, appended to the audit trail, and stored as an LTR training label.

**Orphan case**
- If no candidate clears the confidence threshold, the UI explicitly states no confident match was found, shows nearest neighbours as reference only (clearly labelled non-recommendations), and offers a "Report as standards gap" action.

---

### 2.4 Audit Tender Mode

**Frontend**
- Upload existing draft tender document.
- Progress indicator while parsing.

**Backend**
- Extracts all referenced standards, checks freshness and certification, traverses the graph for missing companions, compiles a severity-tagged gap report, and generates impact estimates.

**Frontend gap report view**
- **Redline / track-changes view** over the original document — additions, deletions, and version corrections shown inline.
- Severity tags: Critical Gap · Minor · Informational.
- Each finding expands to show the impact estimate in plain language.
- One-click "Apply fix" inserts the corrected clause into the working copy.
- Export corrected document.

---

### 2.5 Standards Explorer

**Frontend**
- Search or browse by category.
- Interactive graph visualisation of a standard and its relationships (normative refs, test methods, safety, supersession chain).
- Click any node to open its detail panel: scope, version history, amendments, certification linkage.

**Backend**
- Serves graph sub-queries from Neo4j and metadata from PostgreSQL on node expansion, loading incrementally rather than shipping the whole graph.

---

### 2.6 Scenario Simulator

**Frontend**
- Starts from an existing query result.
- Parameter controls: environment (indoor/outdoor/marine), load rating, usage duration, safety class, etc.
- Adjusting a parameter re-runs the pipeline and renders a **delta view**: standards added, standards removed, standards whose version requirement changed — highlighted against the base cluster.

**Backend**
- Parameters injected as structured context alongside the original query; pipeline re-executed; response diffed against the cached base result.

---

### 2.7 Compliance Dashboard (Admin roles)

**Frontend**
- Charts: percentage of tenders citing outdated standards, most-queried categories, gap trends over time, certification compliance rate, orphan-query volume.
- Filterable by department, time period, product category.
- Drill-down from any chart to the underlying tender list.

**Backend**
- Served from pre-aggregated metrics tables refreshed by a scheduled job.
- Drill-downs query the logging store directly with role-scoped filters.

---

### 2.8 Alerts & Settings

**Frontend**
- Notification bell with unread count.
- Subscription manager: select product categories to monitor.
- Notification channel preferences (in-app / email).
- API key management (Agency Integrator role).

**Backend**
- Subscriptions stored in PostgreSQL.
- Background scheduler matches newly detected revisions against subscriptions and dispatches via the Notification Service.

---

## 3. Chrome Extension Flow (Parallel Journey)

```
Official opens GeM / state portal tender form
     │
     ▼
Extension detects specification text field
     │
     ▼
Official types product description
     │
     ▼
Extension sends text to REST API (authenticated via stored token)
     │
     ▼
Inline suggestion panel appears beside the field
   • top standard recommendations with confidence
   • certification flag
   • "insert clause" button
     │
     ▼
Official clicks insert → clause text written directly into the form field
     │
     ▼
Action logged to audit trail via API
```

**Why this matters:** the official never leaves the portal. Integration friction — the main reason government tools go unadopted — is eliminated.

---

## 4. Frontend ↔ Backend Interaction Summary

| User Action | Frontend Sends | Backend Does | Frontend Receives |
|---|---|---|---|
| Login | Credentials | Validate, issue JWT, load role/org | Token + role + nav scope |
| Load dashboard | Token | Aggregate recent activity + alerts + stats | Single summary payload |
| Submit query | Query text/file/voice + filters | Full recommendation pipeline | Ranked cluster + explanations + clause |
| Accept/reject/correct | Action + recommendation ID | Log to audit trail + LTR training set | Confirmation |
| Upload tender | Document | Parse, audit, gap-analyse, generate redline | Gap report + redline diff |
| Adjust simulator parameter | Base query ID + parameters | Re-run pipeline, diff vs base | Delta cluster view |
| Open dashboard charts | Token + filters | Read pre-aggregated metrics | Chart datasets |
| Manage subscriptions | Category selections | Persist subscriptions | Updated preferences |
| Expand graph node | Node ID | Neo4j sub-query + PostgreSQL metadata | Sub-graph + node details |
