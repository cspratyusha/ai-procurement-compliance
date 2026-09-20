/**
 * Mock dataset standing in for the FastAPI backend.
 * Shapes mirror the response contracts in 05_Website_Workflow.md
 * so swapping in real endpoints is a fetch-layer change only.
 */

export const USER = {
  name: 'Demo User',
  email: 'demo@standeng.gov.in',
  role: 'PSE / Department Admin',
  org: 'Ministry of Heavy Industries',
  initials: 'DU',
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

export const PIPELINE_STAGES = [
  { id: 'parse', label: 'Parsing specification text' },
  { id: 'retrieve', label: 'Hybrid retrieval — dense + BM25' },
  { id: 'rerank', label: 'Cross-encoder re-ranking' },
  { id: 'expand', label: 'Graph expansion — allied standards' },
  { id: 'verify', label: 'Version & certification verification' },
  { id: 'explain', label: 'Generating grounded explanations' },
];

/* ---------------------------- Graph ---------------------------- */

export const GRAPH = {
  nodes: [
    { id: 'IS 694:2010', label: 'IS 694:2010', kind: 'primary', x: 50, y: 48, title: 'PVC Insulated Cables up to 1100 V' },
    { id: 'IS 8130:2013', label: 'IS 8130:2013', kind: 'normative', x: 21, y: 22, title: 'Conductors for Insulated Cables' },
    { id: 'IS 5831:1984', label: 'IS 5831:1984', kind: 'normative', x: 20, y: 72, title: 'PVC Insulation and Sheath of Cables' },
    { id: 'IS 10810', label: 'IS 10810', kind: 'test', x: 79, y: 24, title: 'Methods of Test for Cables' },
    { id: 'IS 1885 (P32)', label: 'IS 1885 (P32)', kind: 'terminology', x: 50, y: 12, title: 'Electrotechnical Vocabulary — Cables' },
    { id: 'IS 732:2019', label: 'IS 732:2019', kind: 'installation', x: 81, y: 70, title: 'Code of Practice for Electrical Wiring Installations' },
    { id: 'IS 17048:2018', label: 'IS 17048:2018', kind: 'overlap', x: 50, y: 88, title: 'Halogen-Free Flame Retardant Cables' },
    { id: 'BIS-CRS', label: 'BIS Product Cert.', kind: 'certification', x: 15, y: 47, title: 'Mandatory ISI Mark Scheme' },
  ],
  edges: [
    { from: 'IS 694:2010', to: 'IS 8130:2013', kind: 'normative' },
    { from: 'IS 694:2010', to: 'IS 5831:1984', kind: 'normative' },
    { from: 'IS 694:2010', to: 'IS 10810', kind: 'test' },
    { from: 'IS 694:2010', to: 'IS 1885 (P32)', kind: 'terminology' },
    { from: 'IS 694:2010', to: 'IS 732:2019', kind: 'installation' },
    { from: 'IS 694:2010', to: 'IS 17048:2018', kind: 'overlap' },
    { from: 'IS 694:2010', to: 'BIS-CRS', kind: 'certification' },
  ],
};

export const NODE_KINDS = {
  primary:       { label: 'Primary standard',    color: 'var(--ink)' },
  normative:     { label: 'Normative reference', color: 'var(--info)' },
  test:          { label: 'Test method',         color: 'var(--ok)' },
  terminology:   { label: 'Terminology',         color: 'var(--ink-faint)' },
  installation:  { label: 'Installation',        color: 'var(--accent)' },
  overlap:       { label: 'Overlapping scope',   color: 'var(--warn)' },
  certification: { label: 'Certification',       color: 'var(--crit)' },
};

/* ---------------------------- Audit ---------------------------- */

export const AUDIT_FINDINGS = [
  {
    id: 'f1',
    severity: 'critical',
    clauseRef: 'Clause 4.2 — Cable Specification',
    finding: 'Superseded standard cited',
    cited: 'IS 694:1990',
    correct: 'IS 694:2010 (Amd. 3, 2019)',
    impact: 'IS 694:1990 was superseded in 2010. The 1990 edition omits the revised conductor resistance limits and the current ISI marking requirement. Tenders citing it have been challenged at the inspection stage on grounds of an unenforceable acceptance criterion.',
    original: 'All cables shall conform to IS 694:1990 for working voltages up to 1100 V.',
    revised: 'All cables shall conform to IS 694:2010 (including Amendment No. 3, 2019) for working voltages up to and including 1100 V.',
  },
  {
    id: 'f2',
    severity: 'critical',
    clauseRef: 'Clause 4.5 — Quality Assurance',
    finding: 'Mandatory certification not referenced',
    cited: '—',
    correct: 'BIS Product Certification (ISI Mark)',
    impact: 'PVC insulated cable falls under the mandatory BIS certification scheme. Omitting the ISI mark requirement permits non-certified supply, which cannot be legally rejected at delivery if the tender did not require it.',
    original: 'Supplier shall furnish a test certificate for each lot.',
    revised: 'Supplier shall furnish a test certificate for each lot from an NABL-accredited laboratory. All cables shall bear a valid ISI mark under the BIS Product Certification Scheme; licence number shall be stated in the bid.',
  },
  {
    id: 'f3',
    severity: 'minor',
    clauseRef: 'Clause 4.3 — Conductor',
    finding: 'Allied standard missing',
    cited: '—',
    correct: 'IS 8130:2013',
    impact: 'Conductor class and resistance limits are undefined without IS 8130. Acceptance becomes subjective and disputes over conductor stranding are common at inspection.',
    original: 'Conductor shall be of electrolytic grade copper.',
    revised: 'Conductor shall be of electrolytic grade annealed copper conforming to IS 8130:2013, Class 2 stranded.',
  },
  {
    id: 'f4',
    severity: 'minor',
    clauseRef: 'Clause 6.1 — Testing',
    finding: 'Test method standard not cited',
    cited: '—',
    correct: 'IS 10810 (relevant parts)',
    impact: 'Without a named test method the buyer and supplier may apply different procedures to the same acceptance criterion.',
    original: 'Cables shall pass insulation resistance testing.',
    revised: 'Cables shall pass insulation resistance testing in accordance with IS 10810 (Part 43).',
  },
  {
    id: 'f5',
    severity: 'info',
    clauseRef: 'Clause 2.1 — Definitions',
    finding: 'Terminology standard available',
    cited: '—',
    correct: 'IS 1885 (Part 32)',
    impact: 'Citing the terminology standard removes ambiguity in defined terms. Advisory only — not a compliance gap.',
    original: 'Terms used in this document carry their ordinary technical meaning.',
    revised: 'Terms used in this document shall carry the meaning assigned in IS 1885 (Part 32) — Electrotechnical Vocabulary: Electric Cables.',
  },
];

export const SEVERITY = {
  critical: { label: 'Critical gap', badge: 'badge-crit',  color: 'var(--crit)' },
  minor:    { label: 'Minor',        badge: 'badge-warn',  color: 'var(--warn)' },
  info:     { label: 'Informational',badge: 'badge-info',  color: 'var(--info)' },
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

export const SUMMARY_TILES = [
  { id: 'queries', label: 'Queries this month', value: 1248, delta: '+12.4%', trend: 'up' },
  { id: 'gaps', label: 'Gaps identified', value: 87, delta: '-8.1%', trend: 'down' },
  { id: 'outdated', label: 'Outdated citations flagged', value: 34, delta: '-22.0%', trend: 'down' },
  { id: 'orphan', label: 'Orphan queries', value: 9, delta: '+2', trend: 'up' },
];

export const TREND_DATA = [
  { month: 'Apr', outdated: 62, gaps: 118, queries: 720 },
  { month: 'May', outdated: 58, gaps: 106, queries: 840 },
  { month: 'Jun', outdated: 51, gaps: 99, queries: 910 },
  { month: 'Jul', outdated: 44, gaps: 94, queries: 1020 },
  { month: 'Aug', outdated: 39, gaps: 90, queries: 1150 },
  { month: 'Sep', outdated: 34, gaps: 87, queries: 1248 },
];

export const CATEGORY_DATA = [
  { category: 'Electrical cables', queries: 318 },
  { category: 'Structural steel', queries: 264 },
  { category: 'Cement & concrete', queries: 211 },
  { category: 'Pipes & fittings', queries: 178 },
  { category: 'Safety equipment', queries: 142 },
  { category: 'Transformers', queries: 135 },
];

export const COMPLIANCE_DATA = [
  { name: 'Compliant', value: 68 },
  { name: 'Minor gaps', value: 22 },
  { name: 'Critical gaps', value: 10 },
];

export const DEPARTMENTS = [
  { dept: 'Electrical Wing', tenders: 142, outdated: 6, rate: 95.8 },
  { dept: 'Civil Works', tenders: 118, outdated: 14, rate: 88.1 },
  { dept: 'Mechanical', tenders: 96, outdated: 5, rate: 94.8 },
  { dept: 'IT Procurement', tenders: 74, outdated: 2, rate: 97.3 },
  { dept: 'Stores & Supply', tenders: 61, outdated: 7, rate: 88.5 },
];

/* --------------------------- Activity --------------------------- */

export const RECENT_QUERIES = [
  { id: 'q1', text: 'PVC insulated copper cable 1100 V single core', standard: 'IS 694:2010', confidence: 0.94, time: '18 min ago', status: 'accepted' },
  { id: 'q2', text: 'Structural steel plates for bridge girder fabrication', standard: 'IS 2062:2011', confidence: 0.91, time: '2 hours ago', status: 'accepted' },
  { id: 'q3', text: 'Ordinary portland cement 43 grade bulk supply', standard: 'IS 269:2015', confidence: 0.88, time: '4 hours ago', status: 'corrected' },
  { id: 'q4', text: 'Industrial safety helmet with chin strap', standard: 'IS 2925:1984', confidence: 0.83, time: 'Yesterday', status: 'accepted' },
  { id: 'q5', text: 'Bespoke composite insulator mounting bracket', standard: null, confidence: 0.31, time: 'Yesterday', status: 'orphan' },
];

export const AUDITED_TENDERS = [
  { id: 't1', name: 'Tender_HT_Cable_Supply_2026.pdf', findings: 5, critical: 2, time: '1 hour ago' },
  { id: 't2', name: 'Bridge_Steel_Procurement_Q3.docx', findings: 3, critical: 0, time: 'Yesterday' },
  { id: 't3', name: 'Substation_Equipment_Tender.pdf', findings: 8, critical: 3, time: '3 days ago' },
];

export const ALERTS = [
  { id: 'a1', kind: 'revision', title: 'IS 8112:2013 withdrawn — cite IS 269:2015', body: 'IS 269:2015 consolidated the grade-wise OPC standards; IS 8112:2013 (43 grade) and IS 12269:2013 (53 grade) stand withdrawn. 14 of your active tenders still cite IS 8112.', category: 'Cement & concrete', time: '2 hours ago', unread: true },
  { id: 'a2', kind: 'amendment', title: 'Amendment 4 issued to IS 694:2010', body: 'Amendment No. 4 revises Table 2 current ratings for single-core cables above 95 sq mm.', category: 'Electrical cables', time: 'Yesterday', unread: true },
  { id: 'a3', kind: 'certification', title: 'CRS scheme extended to 3 new categories', body: 'Compulsory Registration Scheme now covers LED luminaires, power adaptors and USB chargers.', category: 'Electrical equipment', time: '2 days ago', unread: true },
  { id: 'a4', kind: 'gap', title: 'Orphan query routed to standards committee', body: 'Query "composite insulator mounting bracket" found no confident match and has been flagged as a potential standards gap.', category: 'Electrical equipment', time: '4 days ago', unread: false },
];

export const SUBSCRIPTIONS = [
  { id: 's1', category: 'Electrical cables', standards: 48, active: true },
  { id: 's2', category: 'Structural steel', standards: 62, active: true },
  { id: 's3', category: 'Cement & concrete', standards: 39, active: true },
  { id: 's4', category: 'Pipes & fittings', standards: 54, active: false },
  { id: 's5', category: 'Safety equipment', standards: 31, active: true },
  { id: 's6', category: 'Transformers', standards: 27, active: false },
];

export const API_KEYS = [
  { id: 'k1', name: 'GeM Portal Integration', prefix: 'bis_live_7f3a', created: '12 Mar 2026', lastUsed: '4 min ago', calls: '1.2M' },
  { id: 'k2', name: 'State Portal — Karnataka', prefix: 'bis_live_c91d', created: '28 Jun 2026', lastUsed: '2 hours ago', calls: '184K' },
  { id: 'k3', name: 'Staging / Test', prefix: 'bis_test_2b64', created: '02 Sep 2026', lastUsed: 'Yesterday', calls: '9.4K' },
];

export const EXPLORER_STANDARDS = [
  { code: 'IS 694:2010', title: 'PVC Insulated Cables for Working Voltages up to 1100 V', category: 'Electrical cables', version: 'latest', cert: 'BIS' },
  { code: 'IS 8130:2013', title: 'Conductors for Insulated Electric Cables and Flexible Cords', category: 'Electrical cables', version: 'latest', cert: null },
  { code: 'IS 2062:2011', title: 'Hot Rolled Medium and High Tensile Structural Steel (Seventh Revision, reaffirmed 2016)', category: 'Structural steel', version: 'latest', cert: 'BIS' },
  { code: 'IS 269:2015', title: 'Ordinary Portland Cement — Specification (Sixth Revision)', category: 'Cement & concrete', version: 'latest', cert: 'BIS' },
  { code: 'IS 8112:2013', title: 'Ordinary Portland Cement, 43 Grade — withdrawn, see IS 269:2015', category: 'Cement & concrete', version: 'superseded', cert: null },
  { code: 'IS 456:2000', title: 'Plain and Reinforced Concrete — Code of Practice', category: 'Cement & concrete', version: 'latest', cert: null },
  { code: 'IS 10810', title: 'Methods of Test for Cables', category: 'Electrical cables', version: 'latest', cert: null },
  { code: 'IS 732:2019', title: 'Code of Practice for Electrical Wiring Installations', category: 'Electrical cables', version: 'latest', cert: null },
  { code: 'IS 2925:1984', title: 'Industrial Safety Helmets — Specification', category: 'Safety equipment', version: 'latest', cert: 'BIS' },
  { code: 'IS 1239 (Part 1):2004', title: 'Steel Tubes, Tubulars and Other Wrought Steel Fittings', category: 'Pipes & fittings', version: 'latest', cert: 'BIS' },
  { code: 'IS 17048:2018', title: 'Halogen-Free Flame Retardant Cables', category: 'Electrical cables', version: 'latest', cert: null },
];
