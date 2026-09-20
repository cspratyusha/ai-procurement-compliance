/**
 * Catalogue-side mock data: parsed attributes, match bands, full standard
 * detail records, certification/QCO rules, BOQ line items, conflicts.
 *
 * Split from mock.js to keep the recommendation-response shapes separate from
 * the reference-data shapes — they come from different backend services
 * (retrieval pipeline vs. PostgreSQL catalogue).
 */

/** Match bands replace raw percentages — a retrieval score is not a measurement. */
export const BANDS = {
  strong:   { label: 'Strong match', cls: 'badge-ok',      hint: 'Scope and key attributes align directly' },
  probable: { label: 'Probable',     cls: 'badge-warn',    hint: 'Most attributes align; confirm scope before citing' },
  review:   { label: 'Needs review', cls: 'badge-neutral', hint: 'Partial overlap only — verify manually' },
};

export function bandFor(confidence) {
  if (confidence >= 0.85) return 'strong';
  if (confidence >= 0.6) return 'probable';
  return 'review';
}

/** What the system understood — editable, because a misread must be fixable. */
export const PARSED_ATTRS = [
  { id: 'p1', key: 'Product type',   value: 'Cable',                            confident: true },
  { id: 'p2', key: 'Material',       value: 'PVC insulated, copper conductor',  confident: true },
  { id: 'p3', key: 'Voltage rating', value: '1100 V',                           confident: true },
  { id: 'p4', key: 'Construction',   value: 'Single core',                      confident: true },
  { id: 'p5', key: 'Application',    value: 'Indoor panel wiring',              confident: false },
  { id: 'p6', key: 'End use',        value: 'Not specified',                    confident: false },
];

export const ATTR_SUGGESTIONS = {
  'Product type':   ['Cable', 'Conductor', 'Flexible cord', 'Busbar'],
  'Material':       ['PVC insulated, copper conductor', 'XLPE insulated, copper', 'PVC insulated, aluminium'],
  'Voltage rating': ['1100 V', '650 V', '3.3 kV', '11 kV'],
  'Construction':   ['Single core', 'Multi core', 'Armoured', 'Unarmoured'],
  'Application':    ['Indoor panel wiring', 'Outdoor', 'Underground', 'Marine'],
  'End use':        ['Not specified', 'Industrial', 'Domestic', 'Railway'],
};

/** Standard-type filters (right column of the recommendations screen). */
export const STD_TYPES = [
  { id: 'product',      label: 'Product specification' },
  { id: 'test',         label: 'Test method' },
  { id: 'terminology',  label: 'Terminology' },
  { id: 'safety',       label: 'Safety' },
  { id: 'installation', label: 'Installation' },
  { id: 'code',         label: 'Code of practice' },
];

export const BIS_DIVISIONS = [
  'Electrotechnical (ETD)',
  'Civil Engineering (CED)',
  'Mechanical Engineering (MED)',
  'Chemical (CHD)',
  'Food & Agriculture (FAD)',
  'Textile (TXD)',
];

export const STATUS_BADGE = {
  current:    { label: 'Current',        cls: 'badge-ok',   icon: 'check' },
  superseded: { label: 'Superseded',     cls: 'badge-crit', icon: 'alert' },
  withdrawn:  { label: 'Withdrawn',      cls: 'badge-crit', icon: 'x' },
  revision:   { label: 'Under revision', cls: 'badge-warn', icon: 'refresh' },
};

/* ------------------------- Standard detail ------------------------- */

export const STANDARD_DETAIL = {
  'IS 694:2010': {
    code: 'IS 694:2010',
    title: 'PVC Insulated Cables for Working Voltages up to and including 1100 V',
    edition: '4th revision, 2010',
    division: 'Electrotechnical (ETD 09)',
    committee: 'ETD 09 — Power Cables Sectional Committee',
    status: 'current',
    type: 'product',
    role: 'primary',
    amendment: 'Amd. 3 (2019)',
    scopePlain:
      'Covers PVC insulated cables with copper or aluminium conductors for working voltages up to and including 1100 V, used in fixed wiring installations and for flexible connections.',
    scopeOfficial:
      'This standard prescribes the requirements for polyvinyl chloride insulated cables, with or without sheath, having copper or aluminium conductors, for working voltages up to and including 1100 V, and for use at conductor temperatures not exceeding 70 degrees Celsius.',
    timeline: [
      { ed: 'IS 694:1964', year: '1964', state: 'superseded' },
      { ed: 'IS 694:1977', year: '1977', state: 'superseded' },
      { ed: 'IS 694:1990', year: '1990', state: 'superseded' },
      { ed: 'IS 694:2010', year: '2010', state: 'current' },
      { ed: 'Amd. 1', year: '2012', state: 'amendment' },
      { ed: 'Amd. 2', year: '2016', state: 'amendment' },
      { ed: 'Amd. 3', year: '2019', state: 'amendment' },
    ],
    normative: [
      { code: 'IS 8130:2013', title: 'Conductors for insulated electric cables', role: 'primary' },
      { code: 'IS 5831:1984', title: 'PVC insulation and sheath of electric cables', role: 'primary' },
      { code: 'IS 10810',     title: 'Methods of test for cables', role: 'test' },
    ],
    reverse: [
      { code: 'IS 732:2019', title: 'Code of practice for electrical wiring installations' },
      { code: 'IS 1255:1983', title: 'Installation of underground cables' },
    ],
    certification: 'BIS Product Certification (ISI Mark) — mandatory',
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 8130:2013': {
    code: 'IS 8130:2013',
    title: 'Conductors for Insulated Electric Cables and Flexible Cords',
    edition: '1st revision, 2013',
    division: 'Electrotechnical (ETD 09)',
    committee: 'ETD 09 — Power Cables Sectional Committee',
    status: 'current',
    type: 'product',
    role: 'primary',
    amendment: 'Amd. 1 (2016)',
    scopePlain:
      'Specifies construction, dimensions and electrical resistance limits for conductors used in insulated cables and flexible cords, by class and material.',
    scopeOfficial:
      'This standard covers the requirements of conductors used in insulated electric cables and flexible cords, including classes of stranding, nominal cross-sectional areas and maximum DC resistance at 20 degrees Celsius.',
    timeline: [
      { ed: 'IS 8130:1984', year: '1984', state: 'superseded' },
      { ed: 'IS 8130:2013', year: '2013', state: 'current' },
      { ed: 'Amd. 1', year: '2016', state: 'amendment' },
    ],
    normative: [{ code: 'IS 10810', title: 'Methods of test for cables', role: 'test' }],
    reverse: [
      { code: 'IS 694:2010', title: 'PVC insulated cables up to 1100 V' },
      { code: 'IS 7098 (Part 1)', title: 'XLPE insulated cables' },
    ],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 10810': {
    code: 'IS 10810',
    title: 'Methods of Test for Cables (Parts 1 to 59)',
    edition: 'Multi-part, 1984-1988',
    division: 'Electrotechnical (ETD 09)',
    committee: 'ETD 09 — Power Cables Sectional Committee',
    status: 'revision',
    type: 'test',
    role: 'test',
    amendment: 'Under revision',
    scopePlain:
      'A multi-part series defining how cable properties are measured — insulation resistance, tensile strength, flammability, smoke density and others. Cited to make acceptance criteria testable.',
    scopeOfficial:
      'This series prescribes methods of test for electric cables, each part covering a specific test procedure, apparatus, sampling and reporting requirement.',
    timeline: [
      { ed: 'Parts 1-43', year: '1984', state: 'current' },
      { ed: 'Parts 44-59', year: '1988', state: 'current' },
      { ed: 'Revision in progress', year: '2026', state: 'revision' },
    ],
    normative: [],
    reverse: [
      { code: 'IS 694:2010', title: 'PVC insulated cables up to 1100 V' },
      { code: 'IS 8130:2013', title: 'Conductors for insulated electric cables' },
    ],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 732:2019': {
    code: 'IS 732:2019',
    title: 'Code of Practice for Electrical Wiring Installations',
    edition: '4th revision, 2019',
    division: 'Electrotechnical (ETD 20)',
    committee: 'ETD 20 — Electrical Installation Sectional Committee',
    status: 'current',
    type: 'code',
    role: 'installation',
    amendment: null,
    scopePlain:
      'Gives installation practice for electrical wiring in buildings — cable selection, protection, earthing and testing on completion.',
    scopeOfficial:
      'This code covers the design, selection, erection, inspection and testing of electrical installations in buildings for voltages not exceeding 1100 V AC.',
    timeline: [
      { ed: 'IS 732:1989', year: '1989', state: 'superseded' },
      { ed: 'IS 732:2019', year: '2019', state: 'current' },
    ],
    normative: [{ code: 'IS 694:2010', title: 'PVC insulated cables up to 1100 V', role: 'primary' }],
    reverse: [],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 1885 (P32)': {
    code: 'IS 1885 (Part 32)',
    title: 'Electrotechnical Vocabulary — Electric Cables',
    edition: '1993',
    division: 'Electrotechnical (ETD 09)',
    committee: 'ETD 09 — Power Cables Sectional Committee',
    status: 'current',
    type: 'terminology',
    role: 'terminology',
    amendment: null,
    scopePlain:
      'Defines the terms used across cable standards, so that a defined term means the same thing in a tender as it does in the standard.',
    scopeOfficial: 'This part covers terms and definitions relating to electric cables, cords and their components.',
    timeline: [{ ed: 'IS 1885 (Part 32):1993', year: '1993', state: 'current' }],
    normative: [],
    reverse: [{ code: 'IS 694:2010', title: 'PVC insulated cables up to 1100 V' }],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 5831:1984': {
    code: 'IS 5831:1984',
    title: 'PVC Insulation and Sheath of Electric Cables',
    edition: '1984',
    division: 'Electrotechnical (ETD 09)',
    committee: 'ETD 09 — Power Cables Sectional Committee',
    status: 'current',
    type: 'product',
    role: 'primary',
    amendment: 'Amd. 2 (1997)',
    scopePlain:
      'Specifies the PVC compound used for insulation and sheathing — composition, mechanical properties and ageing behaviour.',
    scopeOfficial: 'This standard prescribes requirements for polyvinyl chloride compounds used as insulation and sheath of electric cables.',
    timeline: [
      { ed: 'IS 5831:1970', year: '1970', state: 'superseded' },
      { ed: 'IS 5831:1984', year: '1984', state: 'current' },
      { ed: 'Amd. 2', year: '1997', state: 'amendment' },
    ],
    normative: [],
    reverse: [{ code: 'IS 694:2010', title: 'PVC insulated cables up to 1100 V' }],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 269:2015': {
    code: 'IS 269:2015',
    title: 'Ordinary Portland Cement — Specification',
    edition: 'Sixth revision, 2015 (reaffirmed 2020)',
    division: 'Civil Engineering (CED 02)',
    committee: 'CED 02 — Cement and Concrete Sectional Committee',
    status: 'current',
    type: 'product',
    role: 'primary',
    amendment: 'Amd. 2',
    scopePlain:
      'Covers Ordinary Portland Cement in all three grades — 33, 43 and 53. The 2015 revision consolidated the separate grade-wise standards into one, so every OPC bag now carries the IS 269 mark with the grade printed on it.',
    scopeOfficial:
      'This standard covers the manufacture, chemical and physical requirements, sampling and testing of ordinary Portland cement of 33 grade, 43 grade and 53 grade.',
    timeline: [
      { ed: 'IS 269:1989', year: '1989', state: 'superseded' },
      { ed: 'IS 8112:2013 (43 grade)', year: '2013', state: 'superseded' },
      { ed: 'IS 269:2015', year: '2015', state: 'current' },
      { ed: 'Reaffirmed', year: '2020', state: 'amendment' },
    ],
    normative: [
      { code: 'IS 4031 (Part 1)', title: 'Methods of physical tests for hydraulic cement', role: 'test' },
      { code: 'IS 3535:1986', title: 'Methods of sampling hydraulic cement', role: 'test' },
    ],
    reverse: [
      { code: 'IS 456:2000', title: 'Plain and reinforced concrete — code of practice' },
    ],
    certification: 'BIS Product Certification (ISI Mark) — mandatory',
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 8112:2013': {
    code: 'IS 8112:2013',
    title: 'Ordinary Portland Cement, 43 Grade — Specification',
    edition: 'Second revision, 2013',
    division: 'Civil Engineering (CED 02)',
    committee: 'CED 02 — Cement and Concrete Sectional Committee',
    status: 'withdrawn',
    type: 'product',
    role: 'primary',
    amendment: null,
    supersededBy: 'IS 269:2015',
    scopePlain:
      'Withdrawn. The grade-wise OPC standards were consolidated into IS 269:2015; cite that standard instead. Retained here so that tenders citing IS 8112 can be identified and corrected.',
    scopeOfficial:
      'This standard covered the requirements for 43 grade ordinary Portland cement. It stands withdrawn following the sixth revision of IS 269.',
    timeline: [
      { ed: 'IS 8112:1989', year: '1989', state: 'superseded' },
      { ed: 'IS 8112:2013', year: '2013', state: 'superseded' },
      { ed: 'Withdrawn — see IS 269:2015', year: '2015', state: 'revision' },
    ],
    normative: [],
    reverse: [],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },

  'IS 17048:2018': {
    code: 'IS 17048:2018',
    title: 'Halogen-Free Flame Retardant (HFFR) Cables',
    edition: '2018',
    division: 'Electrotechnical (ETD 09)',
    committee: 'ETD 09 — Power Cables Sectional Committee',
    status: 'current',
    type: 'product',
    role: 'safety',
    amendment: null,
    scopePlain:
      'Covers cables that emit no halogen acid gas when burning — used where smoke toxicity matters, such as tunnels and crowded buildings.',
    scopeOfficial: 'This standard covers halogen-free flame retardant cables for working voltages up to and including 1100 V.',
    timeline: [{ ed: 'IS 17048:2018', year: '2018', state: 'current' }],
    normative: [{ code: 'IS 10810', title: 'Methods of test for cables', role: 'test' }],
    reverse: [],
    certification: null,
    bisUrl: 'https://www.services.bis.gov.in',
  },
};

/* ------------------------- Conflicts ------------------------- */

export const CONFLICTS = [
  {
    id: 'c1',
    a: 'IS 694:2010',
    b: 'IS 17048:2018',
    overlap: 'Both cover cables rated up to 1100 V for building wiring.',
    difference:
      'IS 694 specifies conventional PVC insulation. IS 17048 specifies halogen-free flame retardant compounds for installations where smoke toxicity is a stated requirement.',
    authoritative: 'IS 694:2010',
    when: 'Cite IS 17048 instead only where the tender explicitly requires halogen-free performance (tunnels, metros, hospitals, high-occupancy buildings).',
  },
];

/* ------------------------- Certification ------------------------- */

export const CERTIFICATION = {
  'IS 694:2010': {
    mandatory: true,
    scheme: 'BIS Product Certification (ISI Mark)',
    schemeCode: 'Scheme-I, BIS (Conformity Assessment) Regulations 2018',
    order: 'Electrical Wires, Cables, Appliances and Protection Devices and Accessories (Quality Control) Order, 2003',
    orderDate: 'S.O. 189(E), notified 17 February 2003',
    marking: [
      'ISI mark with the licence number (CM/L-xxxxxxx) on the cable surface at intervals not exceeding 1 metre.',
      'Manufacturer name or registered trade mark.',
      'Voltage grade, conductor size and number of cores.',
      'Year of manufacture.',
    ],
    verify: 'Licence validity is verifiable on the BIS licence-search portal using the CM/L number.',
    clause:
      'The cables offered shall bear a valid ISI mark under the BIS Product Certification Scheme against IS 694:2010, in accordance with the Electrical Wires, Cables, Appliances and Protection Devices and Accessories (Quality Control) Order, 2003. The bidder shall furnish a copy of the valid BIS licence (CM/L number) with the bid, and the licence shall remain valid through the delivery period. Material not bearing a valid ISI mark shall be liable to rejection at the consignee end.',
  },

  'IS 269:2015': {
    mandatory: true,
    scheme: 'BIS Product Certification (ISI Mark)',
    schemeCode: 'Scheme-I, BIS (Conformity Assessment) Regulations 2018',
    order: 'Cement (Quality Control) Order, 2003',
    orderDate: 'Notified 17 February 2003',
    supersedes: 'IS 8112:2013 (43 grade) and IS 12269:2013 (53 grade), both withdrawn',
    marking: [
      'ISI mark with licence number on every bag.',
      'Grade designation — 33, 43 or 53 grade — printed on the bag.',
      'Week and year of packing.',
      'Net quantity.',
    ],
    verify: 'Licence validity verifiable on the BIS licence-search portal using the CM/L number.',
    clause:
      'Ordinary Portland Cement supplied shall conform to IS 269:2015, 43 grade, and shall bear a valid ISI mark under the BIS Product Certification Scheme in accordance with the Cement (Quality Control) Order, 2003. Note: IS 269:2015 consolidated the grade-wise standards; IS 8112:2013 stands withdrawn. A copy of the valid BIS licence shall be furnished with the bid.',
  },

  'IS 8130:2013': { mandatory: false, note: 'Component standard — certification attaches to the finished cable under IS 694, not to the conductor separately.' },
  'IS 10810':     { mandatory: false, note: 'Test method standard. No product certification scheme attaches to a test method.' },
  'IS 732:2019':  { mandatory: false, note: 'Code of practice. Compliance is demonstrated by installation inspection, not by product marking.' },
};

/* ------------------------- BOQ line items ------------------------- */

export const BOQ_ITEMS = [
  {
    id: 'li1', sr: 1, parsed: true,
    text: 'PVC insulated copper cable, single core, 1100 V, 2.5 sq mm, for internal panel wiring',
    qty: '4,500 m', category: 'Electrical cables',
    standards: ['IS 694:2010', 'IS 8130:2013', 'IS 10810'], band: 'strong', status: 'pending',
  },
  {
    id: 'li2', sr: 2, parsed: true,
    text: 'Ordinary Portland Cement, 43 grade, in 50 kg bags',
    qty: '820 bags', category: 'Cement & concrete',
    standards: ['IS 269:2015', 'IS 4031 (Part 1)'], band: 'strong', status: 'pending',
  },
  {
    id: 'li3', sr: 3, parsed: true,
    text: 'MS structural steel angle section, 50x50x6 mm',
    qty: '12.4 MT', category: 'Structural steel',
    standards: ['IS 2062:2011', 'IS 808:1989'], band: 'probable', status: 'pending',
  },
  {
    id: 'li4', sr: 4, parsed: true,
    text: 'Industrial safety helmet, non-vented, with ratchet chin strap',
    qty: '240 nos', category: 'Safety equipment',
    standards: ['IS 2925:1984'], band: 'probable', status: 'pending',
  },
  {
    id: 'li5', sr: 5, parsed: false,
    text: 'Supply and fixing of bespoke composite bracket assembly as per attached drawing No. TD/2026/114-R2',
    qty: '38 nos', category: null, standards: [], band: null, status: 'unparsed',
    reason: 'Line refers to an external drawing not included in the upload. No product attributes could be extracted.',
  },
  {
    id: 'li6', sr: 6, parsed: false,
    text: '[OCR low confidence] galvani..d ..eet, thickness 1.6mm',
    qty: '?', category: null, standards: [], band: null, status: 'unparsed',
    reason: 'Scanned page quality too low for reliable OCR. Re-upload this page or enter the item manually.',
  },
];

/* ------------------------- Projects & templates ------------------------- */

export const PROJECTS = [
  { id: 'pr1', name: 'HT Cable Supply 2026',           items: 7,  updated: '18 min ago', status: 'draft',     owner: 'Demo User' },
  { id: 'pr2', name: 'Substation Equipment Tender',    items: 14, updated: 'Yesterday',   status: 'in-review', owner: 'Demo User' },
  { id: 'pr3', name: 'Bridge Steel Procurement Q3',    items: 9,  updated: '3 days ago',  status: 'approved',  owner: 'R. Sharma' },
  { id: 'pr4', name: 'Office Block Electrical Fit-out',items: 22, updated: '1 week ago',  status: 'draft',     owner: 'M. Iyer' },
];

export const PROJECT_STATUS = {
  draft:       { label: 'Draft',       cls: 'badge-neutral' },
  'in-review': { label: 'In review',   cls: 'badge-warn' },
  approved:    { label: 'Approved',    cls: 'badge-ok' },
};

export const TEMPLATES = [
  { id: 'tm1', name: 'Standard LT cable supply',        items: 4, uses: 38 },
  { id: 'tm2', name: 'RCC civil works — cement & steel', items: 6, uses: 27 },
  { id: 'tm3', name: 'PPE / safety equipment bundle',    items: 5, uses: 19 },
];

/* ------------------------- Language samples ------------------------- */

export const LANG_SAMPLES = {
  hi: { raw: 'वायरिंग के लिए तांबे का तार', english: 'Copper wire for wiring', detected: 'Hindi' },
  ta: { raw: 'மின் கம்பி',                   english: 'Electrical cable',      detected: 'Tamil' },
  bn: { raw: 'তামার তার',                    english: 'Copper wire',           detected: 'Bengali' },
};

/* ------------------------- Admin console ------------------------- */

export const CATALOGUE_SYNC = {
  lastSync: '19 Sep 2026, 04:00 IST',
  totalStandards: 22418,
  newThisMonth: 34,
  amendedThisMonth: 112,
  withdrawnThisMonth: 8,
  sources: [
    { name: 'BIS Standards Catalogue',       status: 'ok',    last: '04:00 today' },
    { name: 'BIS Amendment Feed',            status: 'ok',    last: '04:00 today' },
    { name: 'QCO / Gazette Notifications',   status: 'stale', last: '3 days ago' },
    { name: 'Dispute & Rejection Records',   status: 'ok',    last: 'Weekly — 15 Sep' },
  ],
  flagged: [
    { id: 'fl1', code: 'IS 10810',              issue: 'Users report Part numbering unclear for smoke density tests', count: 7 },
    { id: 'fl2', code: 'IS 9968 (Part 1):1988', issue: 'Repeatedly surfaced despite being superseded',                count: 4 },
  ],
  acceptance: [
    { band: 'Strong match', accepted: 94, rejected: 6 },
    { band: 'Probable',     accepted: 71, rejected: 29 },
    { band: 'Needs review', accepted: 38, rejected: 62 },
  ],
};

export const DISMISS_REASONS = [
  'Wrong product scope',
  'Superseded edition',
  'Not applicable to this use case',
  'Already covered by another standard',
  'Other',
];
