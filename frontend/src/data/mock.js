/**
 * What remains of the mock dataset.
 *
 * This file used to stand in for the whole backend. Most of it is gone,
 * deleted as each screen was wired to the engine: the dashboard's query
 * counts, the compliance trends and department table, the alerts feed, the
 * hand-authored relationship graph, the audit findings, the BOQ line items,
 * the project list and the catalogue-sync console.
 *
 * They were deleted rather than kept "just in case", because a plausible
 * fixture sitting next to a live screen is an invitation to render it again.
 *
 * What is left is in three groups:
 *
 *   USER, ROLES, API_KEYS   the demo identity and the screens that still
 *                           need accounts, which are not built
 *   NODE_KINDS              a colour palette for the cluster graph, not data
 *   RECOMMENDATIONS,        fixtures for the simulator, which is still
 *   SIM_PARAMS, SIM_DELTAS  labelled as illustrative and honest about it
 */

export const USER = {
  name: 'Arun',
  email: 'demo@gmail.com',
  role: 'PSE / Department Admin',
  org: 'Ministry of Heavy Industries',
  initials: 'A',
};

export const ROLES = [
  { id: 'officer', label: 'Procurement Officer', scope: 'Own queries, audits, spec generation' },
  { id: 'admin', label: 'PSE / Department Admin', scope: 'Org-wide dashboard + user management' },
  { id: 'integrator', label: 'Agency Integrator', scope: 'API keys, integration config, usage analytics' },
  { id: 'private', label: 'Private Org User', scope: 'Recommendation, audit, certification lookup' },
];

/* ------------------------- Recommendations ------------------------- */

export const RECOMMENDATIONS = [
  {
    id: 'r1',
    code: 'IS 694:2010',
    title: 'PVC Insulated Cables for Working Voltages up to and including 1100 V',
    confidence: 0.94,
    version: 'latest',
    published: '2010',
    amendment: 'Amd. 3 (2019)',
    certification: 'BIS Product Certification (ISI Mark)',
    scheme: 'Mandatory',
    trustScore: 0.88,
    disputes: 2,
    why: 'Query specifies PVC insulation, copper conductor and a 1100 V working voltage — all three are defining scope terms of this standard. Clause 3 (conductor), Clause 5 (insulation) and Table 2 (current rating) matched directly against the submitted description.',
    matched: ['PVC insulated', 'copper conductor', '1100 V', 'single core'],
    overlap: null,
    clause: 'All PVC insulated cables shall conform to IS 694:2010 (including Amendment No. 3) for working voltages up to and including 1100 V. Conductors shall be of electrolytic grade annealed copper conforming to IS 8130:2013. Cables shall bear a valid ISI mark under BIS Product Certification Scheme.',
  },
  {
    id: 'r2',
    code: 'IS 8130:2013',
    title: 'Conductors for Insulated Electric Cables and Flexible Cords',
    confidence: 0.86,
    version: 'latest',
    published: '2013',
    amendment: 'Amd. 1 (2016)',
    certification: null,
    scheme: null,
    trustScore: 0.91,
    disputes: 0,
    why: 'Normative reference of IS 694:2010. Specifies conductor construction, resistance limits and class designation — required to make the conductor requirement in the primary standard testable.',
    matched: ['copper conductor', 'annealed', 'class 2 stranded'],
    overlap: null,
    clause: 'Conductors shall conform to IS 8130:2013, Class 2 stranded, electrolytic grade annealed copper, with maximum conductor resistance at 20 °C as specified in Table 2 of the said standard.',
  },
  {
    id: 'r3',
    code: 'IS 10810 (Part 1 to 59)',
    title: 'Methods of Test for Cables',
    confidence: 0.79,
    version: 'latest',
    published: '1984–1988',
    amendment: 'Under revision',
    certification: null,
    scheme: null,
    trustScore: 0.74,
    disputes: 5,
    why: 'Test method standard referenced normatively by IS 694 for insulation resistance, tensile and elongation, and high-voltage tests. Cited to make acceptance criteria measurable at the inspection stage.',
    matched: ['insulation resistance', 'test method'],
    overlap: {
      with: 'IS 17048:2018',
      note: 'IS 17048 covers halogen-free test methods that partially overlap Parts 58–59. For standard PVC cable procurement IS 10810 remains authoritative; cite IS 17048 only where halogen-free performance is specified.',
    },
    clause: 'All type and routine tests shall be carried out in accordance with the relevant parts of IS 10810. Test certificates from an NABL-accredited laboratory shall be furnished with each supply lot.',
  },
  {
    id: 'r4',
    code: 'IS 9968 (Part 1):1988',
    title: 'Elastomer Insulated Cables for Working Voltages up to and including 1100 V',
    confidence: 0.41,
    version: 'latest',
    published: '1988 (First Revision)',
    amendment: 'Amd. 3',
    certification: null,
    scheme: null,
    trustScore: 0.52,
    disputes: 11,
    why: 'Surfaced as a lower-confidence neighbour because it also covers cables rated to 1100 V. However this standard governs elastomer (rubber) insulation, and the query specifies PVC — the scope does not match. Current edition, but not applicable here.',
    matched: ['flexible', 'cable'],
    overlap: null,
    clause: null,
  },
];

/* ---------------------------- Graph ---------------------------- */

export const NODE_KINDS = {
  primary:       { label: 'Primary standard',    color: 'var(--ink)' },
  normative:     { label: 'Normative reference', color: 'var(--info)' },
  test:          { label: 'Test method',         color: 'var(--ok)' },
  terminology:   { label: 'Terminology',         color: 'var(--ink-faint)' },
  installation:  { label: 'Installation',        color: 'var(--accent)' },
  overlap:       { label: 'Overlapping scope',   color: 'var(--warn)' },
  certification: { label: 'Certification',       color: 'var(--crit)' },
};

/* -------------------------- Simulator -------------------------- */

export const SIM_PARAMS = [
  { id: 'environment', label: 'Operating environment', options: ['Indoor', 'Outdoor', 'Marine', 'Underground'], value: 'Indoor' },
  { id: 'voltage', label: 'Voltage class', options: ['Up to 1100 V', '3.3 kV', '11 kV', '33 kV'], value: 'Up to 1100 V' },
  { id: 'fire', label: 'Fire performance', options: ['Standard', 'Flame retardant', 'Halogen-free (HFFR)'], value: 'Standard' },
  { id: 'duty', label: 'Duty cycle', options: ['Continuous', 'Intermittent', 'Emergency/standby'], value: 'Continuous' },
];

export const SIM_DELTAS = {
  Outdoor: {
    added: [{ code: 'IS 7098 (Part 1):1988', reason: 'UV and weather exposure requires cross-linked polyethylene insulation options.' }],
    changed: [{ code: 'IS 694:2010', reason: 'Sheath colour and UV stabilisation clauses now apply (Clause 8.3).' }],
    removed: [],
  },
  Marine: {
    added: [
      { code: 'IS 15733:2007', reason: 'Marine environment mandates corrosion-resistant construction.' },
      { code: 'IS 10418:1982', reason: 'Shipboard cable drum and installation requirements.' },
    ],
    changed: [{ code: 'IS 8130:2013', reason: 'Tinned copper conductor required instead of plain annealed copper.' }],
    removed: [{ code: 'IS 1885 (P32)', reason: 'Superseded in this context by marine-specific vocabulary in IS 15733.' }],
  },
  Underground: {
    added: [{ code: 'IS 1255:1983', reason: 'Code of practice for installation of underground cables.' }],
    changed: [{ code: 'IS 694:2010', reason: 'Armouring requirement triggered for direct burial.' }],
    removed: [],
  },
  'Halogen-free (HFFR)': {
    added: [{ code: 'IS 17048:2018', reason: 'Halogen-free flame retardant cable requirements become directly applicable.' }],
    changed: [{ code: 'IS 10810', reason: 'Parts 58–59 (halogen acid gas, smoke density) added to the test regime.' }],
    removed: [],
  },
  'Flame retardant': {
    added: [{ code: 'IS 10810 (Part 61)', reason: 'Flammability test for bunched cables applies.' }],
    changed: [],
    removed: [],
  },
  '11 kV': {
    added: [{ code: 'IS 7098 (Part 2):2011', reason: 'XLPE insulated cables for 3.3 kV to 33 kV — replaces the 1100 V standard entirely.' }],
    changed: [],
    removed: [{ code: 'IS 694:2010', reason: 'Scope limited to 1100 V; no longer applicable at this voltage class.' }],
  },
  '3.3 kV': {
    added: [{ code: 'IS 7098 (Part 2):2011', reason: 'Medium-voltage XLPE cable standard applies above 1100 V.' }],
    changed: [],
    removed: [{ code: 'IS 694:2010', reason: 'Scope limited to 1100 V.' }],
  },
  '33 kV': {
    added: [{ code: 'IS 7098 (Part 2):2011', reason: 'Medium-voltage XLPE cable standard applies above 1100 V.' }],
    changed: [],
    removed: [{ code: 'IS 694:2010', reason: 'Scope limited to 1100 V.' }],
  },
};

/* -------------------------- Dashboard -------------------------- */

/*
 * The dashboard, compliance and alerts fixtures were deleted, not moved.
 *
 * They were: SUMMARY_TILES, TREND_DATA, CATEGORY_DATA, COMPLIANCE_DATA,
 * DEPARTMENTS, ALERTS and SUBSCRIPTIONS -- invented query counts, six-month
 * trends and per-department compliance rates like 95.8%.
 *
 * Those three screens now read from the engine: /stats for usage, /alerts for
 * superseded editions and amendments in force, /corpus-health for metadata
 * coverage. Keeping plausible-looking replacements here would invite them
 * back into a screen that has since been made real, which is the failure mode
 * this whole file's honesty discipline exists to prevent.
 *
 * Figures that no data source can back -- tender gap counts, department
 * compliance rates -- were not recreated anywhere. They need the tender
 * auditor and user accounts, and the screens say so.
 *
 * RECENT_QUERIES and AUDITED_TENDERS below are kept because Projects.jsx
 * still uses them and is still labelled as illustrative. They are fixtures
 * for a fixture screen, which is the arrangement this file is for.
 */

export const API_KEYS = [
  { id: 'k1', name: 'GeM Portal Integration', prefix: 'bis_live_7f3a', created: '12 Mar 2026', lastUsed: '4 min ago', calls: '1.2M' },
  { id: 'k2', name: 'State Portal — Karnataka', prefix: 'bis_live_c91d', created: '28 Jun 2026', lastUsed: '2 hours ago', calls: '184K' },
  { id: 'k3', name: 'Staging / Test', prefix: 'bis_test_2b64', created: '02 Sep 2026', lastUsed: 'Yesterday', calls: '9.4K' },
];
