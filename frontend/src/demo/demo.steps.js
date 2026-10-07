/**
 * The demo sequence, what the tour actually does, in order.
 *
 * Split out of demo.config.js because it is the part that changes most: a
 * presenter reorders acts, rewrites narration, or drops a screen without ever
 * touching the credentials, timing or selector tables next door.
 *
 * ── The story ───────────────────────────────────────────────────────────────
 *
 * A newcomer should leave understanding the problem, not just the buttons. So
 * the tour follows one tender through the whole job, in the order a
 * procurement officer would actually do it:
 *
 *   1  sign in                    role-scoped access
 *   2  search by meaning          the core claim: no IS number needed
 *   3  read one standard          scope, edition, certification
 *   4  the related cluster        a product needs a set, not one standard
 *   5  certification              which standards are legally mandatory
 *   6  upload a BOQ               many line items, matched independently
 *   7  assemble and freeze        the deliverable, plus its audit record
 *   8  audit a tender             checking citations a document already makes
 *   9  standards hygiene          superseded editions across the corpus
 *  10  the catalogue              what is and is not covered
 *  11  corpus health + engine     the honesty screens, and what is running
 *  12  usage                      counted, not projected
 *
 * ── Captions ────────────────────────────────────────────────────────────────
 *
 * Each caption has up to four parts:
 *
 *   act     which chapter of the tour this is
 *   text    what is happening, in one line
 *   sub     how it works
 *   detail  why it matters, the line that makes a viewer care
 *
 * ── Actions ─────────────────────────────────────────────────────────────────
 *
 *   caption, moveTo, highlight, click, type, wait, waitFor, scrollTo,
 *   upload, navigate, skipIf, label, finish
 *
 * Any step may carry `optional: true`, which turns a missing target from a
 * demo-stopping error into a logged skip. Screens whose content depends on
 * live data use it, because an empty state is a legitimate outcome there.
 *
 * `target` is always a key in DEMO_TARGETS, never a coordinate.
 */

import { DEMO_FILE, DEMO_AUDIT_FILE } from './demo.config';

/** A caption plus the beat needed to read it. */
const say = (act, text, sub, detail, ms = 2600) => [
  { action: 'caption', act, text, sub, detail },
  ...(ms > 0 ? [{ action: 'wait', ms }] : []),
];

/** The full look-at-this gesture on one element. */
const point = (target, ms = 1500) => [
  { action: 'moveTo', target },
  { action: 'highlight', target },
  { action: 'wait', ms },
];

/** Move, highlight, click. */
const press = (target, opts = {}) => [
  { action: 'moveTo', target },
  { action: 'highlight', target },
  { action: 'click', target, ...opts },
];

/**
 * Change screens the way a user does, by clicking the sidebar link.
 *
 * A route that changes with no cursor anywhere near it is the single most
 * confusing thing a demo can do: the viewer has no idea what caused the page
 * to change, so it reads as the demo glitching rather than as navigation.
 *
 * So the cursor travels to the nav item, highlights it, and clicks. The route
 * change is then a consequence of something the viewer watched happen.
 *
 * `navTarget` is a sidebar link; `waitTarget` is something on the destination
 * screen that proves it arrived. Screens with no nav entry of their own (a
 * standard's detail page, reached by clicking a result) pass `null` and fall
 * back to a direct route change, but those are always preceded by a click on
 * the thing that would have opened them.
 */
const goTo = (navTarget, to, waitTarget) => [
  ...(navTarget
    ? [
      { action: 'moveTo', target: navTarget },
      { action: 'highlight', target: navTarget },
      { action: 'click', target: navTarget },
    ]
    : [{ action: 'navigate', to }]),
  ...(waitTarget
    ? [{ action: 'waitFor', target: waitTarget, timeout: 8000, optional: true }]
    : []),
];

/**
 * Open a screen, then narrate it, in that order.
 *
 * Captioning before navigating describes the new screen while the old one is
 * still on camera. That is the one sequencing mistake that looks broken rather
 * than merely rushed, so every act transition goes through this helper and
 * cannot get it wrong.
 *
 * Pass `nav` to arrive by clicking the sidebar (preferred); omit it only where
 * no sidebar entry leads to the screen.
 */
const intro = (
  { nav = null, to, waitFor: waitTarget },
  act, text, sub, detail, ms = 2800,
) => [
  ...goTo(nav, to, waitTarget),
  ...say(act, text, sub, detail, ms),
];


export const demoSteps = [
  // ═══════════════════════ Opening ════════════════════════════════════════
  ...say(
    'Welcome',
    'StandEng finds the Indian Standards a tender should cite.',
    'A guided tour, you do not need to click anything.',
    'A tender rarely cites the right standards. Get one wrong and the '
      + 'specification is unenforceable at inspection, or the tender is '
      + 'challenged years after it was written.',
    3600,
  ),

  // Already signed in? Skip straight to the workbench.
  { action: 'skipIf', when: 'isLoggedIn', to: 'workbench' },

  ...intro(
    { to: '/', waitFor: 'landing-cta' },
    'Act 1 · Sign in',
    'The engine searches the published Indian Standards it holds, by meaning.',
    'Every figure it shows is counted from its own corpus, never implied.',
    'Coverage is stated plainly throughout this product. A tool that '
      + 'overstates what it knows cannot be trusted with a tender.',
    3200,
  ),
  ...press('landing-cta'),

  // ═══════════════════════ Act 1, role-scoped sign-in ════════════════════
  // The tour never types a password. There is no shared demo account: the
  // viewer signs in with their own, and the tour carries on from there.
  // Short and optional: a viewer already signed in is sent straight on to
  // the workbench, and there is no form to wait for.
  { action: 'waitFor', target: 'email', timeout: 5000, optional: true },
  ...say(
    'Act 1 · Sign in',
    'Sign in with your account to continue the tour.',
    'Accounts are created by your administrator, or at first-run setup.',
    'Access is role-based: officers search and assemble specifications, '
      + 'administrators manage members, integrators hold API keys. Everything '
      + 'you do is recorded in your own activity trail.',
    0,
  ),
  // Not skippable: every act after this one needs a signed-in session.
  { action: 'waitFor', until: 'onWorkbench', timeout: 600000, skippable: false },

  // ═══════════════════════ Act 2, search by meaning ══════════════════════
  { action: 'label', name: 'workbench' },
  ...say(
    'Act 2 · Search',
    'This is the workbench.',
    'Five destinations in the rail; everything else nests inside one of them.',
    'Every screen from here on is reached by clicking that rail, so you can '
      + 'follow exactly where the demo goes.',
    2800,
  ),

  ...intro(
    { nav: 'nav-query', waitFor: 'query-input' },
    'Act 2 · Search',
    'Describe the product the way a tender describes it.',
    'No IS number, no keywords, just the requirement.',
    'This is the core claim: a description sharing none of the standard’s '
      + 'own words still finds the right standard.',
    2800,
  ),
  ...press('query-input'),
  {
    action: 'type',
    target: 'query-input',
    // Deliberately not one of the example cards under the search box (or the
    // landing page's cable): typing a suggestion the viewer can already see
    // proves nothing. Its top result is IS 2082, compulsory under a 2023 QCO,
    // which the narration below names, so change both together.
    text: 'Electric storage water heater for staff quarters bathrooms, 25 litre',
  },
  { action: 'wait', ms: 800 },
  ...press('query-submit'),

  ...say(
    'Act 2 · Search',
    'Four retrieval stages are running.',
    'Dense vectors and BM25 together, then a cross-encoder re-reads every candidate.',
    'Typically under half a second. The first search after a cold start also loads '
      + 'the models, so the demo waits for the real result rather than '
      + 'guessing at a duration.',
    0,
  ),
  { action: 'waitFor', target: 'query-results', orTarget: 'any-error', timeout: 300000 },
  { action: 'scrollTo', target: 'query-results', block: 'start' },
  ...say(
    'Act 2 · Search',
    'The applicable standards, ranked by meaning.',
    'Strong match, probable, or needs review, scored per result.',
    'Superseded editions are flagged, weak matches are kept below the fold, '
      + 'and a query outside coverage is reported as no match rather than '
      + 'answered badly.',
    0,
  ),
  { action: 'highlight', target: 'query-top-result' },
  { action: 'wait', ms: 3400 },

  ...say(
    'Act 2 · Search',
    'And this one is legally mandatory.',
    'ISI mark required, the banner names the order that makes it so.',
    'The Electrical Appliances for Domestic Water Heating (Quality Control) '
      + 'Order, 2023. A specification that omits it lets an uncertified '
      + 'supplier win the contract lawfully.',
    3800,
  ),

  ...say(
    'Act 2 · Search',
    'Accepting a standard collects it in the spec basket.',
    'The basket follows you across every screen in the app.',
    'Both the acceptance and everything passed over are logged: that is what '
      + 'the learned ranker will be trained on, the rejections as much as the picks.',
    0,
  ),
  { action: 'scrollTo', target: 'query-top-result', block: 'start' },
  ...press('query-add-first', { optional: true }),
  { action: 'wait', ms: 1800 },

  // ═══════════════════════ Act 3, one standard in full ═══════════════════
  ...say(
    'Act 3 · One standard',
    'Every result opens into the full record.',
    'The IS number is a link, this is where it goes.',
    null,
    2400,
  ),
  // Reached by clicking the result's own link, not by changing the route:
  // the detail screen has no sidebar entry of its own.
  ...press('query-first-link', { optional: true }),
  { action: 'waitFor', target: 'detail-title', timeout: 8000, optional: true },
  ...say(
    'Act 3 · One standard',
    'Scope text, edition, amendments, certification status.',
    'Amendments come from BIS’s own record and the slips in the standard’s copy.',
    'A withdrawn edition names the one that replaced it. The scope text is '
      + 'read from the published document by OCR, so the page says where each '
      + 'fact came from.',
    4000,
  ),

  // ═══════════════════════ Act 4, the cluster ════════════════════════════
  ...intro(
    { nav: 'nav-map', waitFor: 'map-title' },
    'Act 4 · The cluster',
    'One product needs a set of standards, not one.',
    'Normative references, test methods, terminology, installation practice.',
    'Cite the product standard alone and there is no test method, so the '
      + 'acceptance criteria cannot be measured at inspection.',
    3600,
  ),
  ...say(
    'Act 4 · The cluster',
    'Citations outside the corpus are shown, not hidden.',
    'Flagged as unopenable rather than dropped silently from the graph.',
    'A truncated cluster that looks complete is worse than one that admits '
      + 'where it ends.',
    3400,
  ),

  // ═══════════════════════ Act 5, certification ══════════════════════════
  ...intro(
    { nav: 'nav-certification', waitFor: 'cert-title' },
    'Act 5 · Certification',
    'Which standards carry a legal certification requirement.',
    'Read from BIS’s own compulsory lists: ISI, CRS and Scheme X.',
    'Hundreds of products, each linked to the Quality Control Order that '
      + 'imposes it. Orders whose enforcement is deferred are shown as not yet mandatory.',
    4000,
  ),

  // A buyer types "laptop", the standard says "information technology
  // equipment", and BIS lists laptops by name. Shown here because the answer
  // is a certification one.
  ...intro(
    { nav: 'nav-query', waitFor: 'query-input' },
    'Act 5 · Everyday words',
    'Buyers do not write the way standards do.',
    'Type “laptop”, and the standard says “information technology equipment”.',
    'The engine adds the standards’ own words to yours and says so, and '
      + 'checks BIS’s compulsory lists, which name products in everyday words.',
    2800,
  ),
  ...press('query-input'),
  { action: 'type', target: 'query-input', text: 'laptop for office use' },
  { action: 'wait', ms: 600 },
  ...press('query-submit'),
  // Results without an expansion notice are an answer too: waiting on the
  // notice alone would hold the demo for five minutes if the engine found
  // nothing to add.
  {
    action: 'waitFor',
    target: 'query-expansion',
    orTarget: ['query-results', 'any-error'],
    timeout: 300000,
  },
  { action: 'highlight', target: 'query-expansion', optional: true },
  ...say(
    'Act 5 · Everyday words',
    'The standards’ own term, added and shown.',
    'Also searched for: information technology equipment safety.',
    null,
    2600,
  ),
  { action: 'highlight', target: 'query-bis-products', optional: true },
  ...say(
    'Act 5 · Everyday words',
    'And BIS lists laptops under compulsory registration.',
    'CRS, to IS/IEC 62368-1, with the order that requires it.',
    'Tender abbreviations work the same way: OPC, TMT, GI pipe, XLPE, MCB.',
    3800,
  ),

  // ═══════════════════════ Act 5b, any language, or spoken ═══════════════
  // Hindi for "copper wire for house wiring". The everyday words map to IS
  // 694's own, as in English; the narration names IS 694, so change both.
  ...say(
    'Act 5 · Any language',
    'An official can write in their own language.',
    'Thirteen languages: English and twelve Indian ones, translated on this machine.',
    'The engine shows what was typed and what it actually searched, because a '
      + 'wrong translation quietly returning wrong standards is the failure to guard against.',
    2600,
  ),
  ...press('query-input'),
  { action: 'type', target: 'query-input', text: 'घर की वायरिंग के लिए तांबे का तार' },
  { action: 'wait', ms: 600 },
  ...press('query-submit'),
  {
    action: 'waitFor',
    target: 'query-translation',
    orTarget: ['query-results', 'any-error'],
    timeout: 300000,
  },
  { action: 'highlight', target: 'query-translation', optional: true },
  ...say(
    'Act 5 · Any language',
    'Translated, then searched: IS 694, the house wiring cable, ISI mark required.',
    'What was typed and what was searched, side by side.',
    null,
    3000,
  ),
  // Shown, not used: the tour cannot speak, and a browser asks before it
  // opens the microphone. Absent when the engine has no speech model.
  { action: 'moveTo', target: 'query-mic', optional: true },
  { action: 'highlight', target: 'query-mic', optional: true },
  ...say(
    'Act 5 · Any language',
    'Or say it: the microphone turns speech into the query.',
    'Transcribed on this engine by Whisper; no audio leaves the machine.',
    'The words land in the box to check before searching: a misheard grade '
      + 'would otherwise search for the wrong product unseen.',
    3400,
  ),

  // ═══════════════════════ Act 6, upload a BOQ ═══════════════════════════
  ...intro(
    { nav: 'nav-boq', waitFor: 'boq-dropzone' },
    'Act 6 · Upload',
    'A real tender is not one product.',
    'A bill of quantities runs to dozens of line items.',
    'Flatten it into a single search and the first item’s vocabulary '
      + 'dominates the ranking, the cable wins and the cement silently loses.',
    3400,
  ),
  ...say(
    'Act 6 · Upload',
    'So each line item is detected and searched separately.',
    'PDF, Word, Excel or text, up to 10 MB.',
    'Items are recognised by how the document numbers them, “Item 3:”, '
      + '“3.”, or a bullet.',
    0,
  ),
  ...point('boq-dropzone', 1600),
  ...press('boq-select'),

  // The engine draws its own chooser here, so the pick is visible on camera.
  { action: 'upload', target: 'boq-file' },
  ...say(
    'Act 6 · Upload',
    'Reading the document…',
    DEMO_FILE.name,
    'A browser cannot let a script open the operating system’s file '
      + 'dialog, so the demo shows its own, then hands the file to the '
      + 'page’s real upload component. The application processes it '
      + 'exactly as it would yours.',
    0,
  ),

  // ═══════════════════════ Act 6b, wait on real processing ═══════════════
  // A short document can finish before the progress card ever paints, so the
  // results end this wait too, rather than it running out its 20 seconds.
  {
    action: 'waitFor',
    target: 'boq-running',
    orTarget: ['boq-results', 'any-error'],
    timeout: 20000,
    optional: true,
  },
  ...say(
    'Act 6 · Upload',
    'One independent retrieval per line item.',
    'Same ranking, confidence gate and supersession rules as a typed query.',
    'A longer BOQ takes proportionally longer. The demo waits for the real '
      + 'result, there is no fixed timer anywhere in this step.',
    0,
  ),
  { action: 'waitFor', target: 'boq-results', orTarget: 'any-error', timeout: 300000 },
  { action: 'scrollTo', target: 'boq-summary', block: 'start' },
  ...say(
    'Act 6 · Upload',
    'Ten line items read from one document.',
    'Each item is searched on its own, so one cannot crowd out another.',
    'An item outside coverage is reported as no match, with its nearest text matches '
      + 'labelled as references, they cannot be accepted into a spec at all.',
    0,
  ),
  { action: 'highlight', target: 'boq-summary' },
  { action: 'wait', ms: 3600 },

  ...say(
    'Act 6 · Upload',
    'Every item carries its own verdict.',
    'Match, uncertain, or no match, decided per line, never for the document.',
    null,
    0,
  ),
  { action: 'scrollTo', target: 'boq-first-item', block: 'start' },
  { action: 'highlight', target: 'boq-first-item' },
  { action: 'wait', ms: 3200 },

  ...say(
    'Act 6 · Upload',
    'Accepting an item adds its standards to the spec.',
    'Each one tagged with the BOQ item it came from.',
    null,
    0,
  ),
  ...press('boq-accept-first', { optional: true }),
  { action: 'wait', ms: 2000 },

  // ═══════════════════════ Act 7, assemble and freeze ════════════════════
  ...intro(
    { nav: 'nav-builder', waitFor: 'builder-title' },
    'Act 7 · Assemble',
    'The collected standards become the deliverable.',
    'Grouped by role, reorderable, exportable as tender clause text.',
    null,
    2600,
  ),
  ...say(
    'Act 7 · Assemble',
    'Gaps are flagged before the tender goes out.',
    'No test method selected. No safety standard for an electrical item.',
    'Each warning names a specific hole in the specification, the kind that '
      + 'otherwise surfaces at inspection, when it is far more expensive.',
    0,
  ),
  { action: 'highlight', target: 'builder-gaps', optional: true },
  { action: 'wait', ms: 3600 },

  ...say(
    'Act 7 · Assemble',
    'Each entry records where it came from.',
    '“Added from recommendations” · “Added from BOQ item 1”.',
    'Two different routes into one specification, and the provenance of each '
      + 'is kept for the audit trail.',
    0,
  ),
  { action: 'highlight', target: 'builder-list', optional: true },
  { action: 'wait', ms: 3400 },

  ...say(
    'Act 7 · Assemble',
    'Freezing stamps the editions that are current today.',
    'Edition and amendment state of every collected standard.',
    'If one is revised next month there is a defensible record of what was '
      + 'correct when this tender was drafted. That is the question an audit '
      + 'asks years later.',
    0,
  ),
  { action: 'scrollTo', target: 'builder-freeze', block: 'center' },
  ...press('builder-freeze', { optional: true }),
  { action: 'wait', ms: 2600 },

  // ═══════════════════════ Act 8, audit a tender ═════════════════════════
  ...intro(
    { nav: 'nav-audit', waitFor: 'audit-dropzone' },
    'Act 8 · Audit',
    'The reverse job: checking a tender someone else wrote.',
    'Every IS number the document cites, checked against the corpus.',
    'Superseded editions naming their replacement, amendments in force the '
      + 'citation omits, and citations with no edition year at all.',
    3400,
  ),

  // The audit act uploads for real, exactly as the BOQ act does. Pointing at
  // the button and moving on left the screen's whole purpose undemonstrated.
  ...say(
    'Act 8 · Audit',
    'Uploading a specification that already cites standards.',
    'Section 7 of a real tender, eleven IS numbers.',
    'Three of them are wrong in ways a reader would not notice: an outdated '
      + 'edition, and two citations with no year at all.',
    0,
  ),
  ...point('audit-dropzone', 1400),
  ...press('audit-select'),
  { action: 'upload', target: 'audit-file', file: DEMO_AUDIT_FILE },

  ...say(
    'Act 8 · Audit',
    'Extracting the text, then every IS number in it.',
    DEMO_AUDIT_FILE.name,
    null,
    0,
  ),
  // No wait on a "running" state here: extraction on a text document is fast
  // enough that the spinner may never render, and a waitFor on a state that
  // never appears would leave this caption on screen past its moment.
  { action: 'waitFor', target: 'audit-results', orTarget: 'any-error', timeout: 300000 },
  { action: 'scrollTo', target: 'audit-summary', block: 'start' },
  ...say(
    'Act 8 · Audit',
    'Twelve citations checked, and what to do about each.',
    'Severity-tagged: critical, minor, advisory, plus the ones that are fine.',
    'Seven were clean. The notice under the tiles is the important part: '
      + 'no findings is not a pass, because what the tender *should* cite '
      + 'was never assessed.',
    0,
  ),
  { action: 'highlight', target: 'audit-summary' },
  { action: 'wait', ms: 4000 },

  ...say(
    'Act 8 · Audit',
    'The findings name the fix, not just the fault.',
    '“Cite IS 383:2016 explicitly.” · “Confirm the current edition with BIS.”',
    'An audit that only flags problems leaves the officer to research every '
      + 'one. Naming the correction is the difference between a report and a '
      + 'usable worklist.',
    0,
  ),
  { action: 'scrollTo', target: 'audit-first-finding', block: 'start' },
  { action: 'highlight', target: 'audit-first-finding', optional: true },
  { action: 'wait', ms: 3800 },

  ...say(
    'Act 8 · Audit',
    'And what the cited standards themselves depend on.',
    'Read from each standard’s own references and “shall be tested as per” clauses.',
    'A tender citing IS 694 but not IS 8130 leaves the cable’s conductor '
      + 'undefined. Each gap is shown with the sentence it was read from, '
      + 'grouped under the standard that needs it.',
    0,
  ),
  { action: 'scrollTo', target: 'audit-dependencies', block: 'start', optional: true },
  { action: 'highlight', target: 'audit-dependencies', optional: true },
  { action: 'wait', ms: 4200 },

  ...say(
    'Act 8 · Audit',
    'What it does not do matters just as much.',
    'It checks the citations a document makes, and what those standards require.',
    'It cannot judge whether the tender cites the right product standard for '
      + 'its goods in the first place. So a document with no findings has not '
      + 'passed, and one citing nothing produces no findings while being the worst case.',
    4200,
  ),

  // ═══════════════════════ Act 9, standards hygiene ══════════════════════
  ...intro(
    { nav: 'nav-projects', waitFor: 'projects-title' },
    'Act 9 · Hygiene',
    'Three more screens, under My projects.',
    'Standards hygiene, corpus health, and the engine itself.',
    null,
    2600,
  ),
  ...intro(
    { nav: 'nav-alerts', waitFor: 'alerts-title' },
    'Act 9 · Hygiene',
    'Superseded editions across the whole corpus.',
    'Computed from the standards data, not a notification feed.',
    'Where the corpus holds the active replacement it is named; where it does '
      + 'not, the finding says so instead of guessing.',
    3800,
  ),

  // ═══════════════════════ Act 10, coverage ══════════════════════════════
  ...intro(
    { nav: 'nav-catalogue', waitFor: 'catalogue-search' },
    'Act 10 · Coverage',
    'The full catalogue, browsable by sector.',
    'Every standard the engine holds, grouped by sector.',
    null,
    2400,
  ),
  ...press('catalogue-search', { optional: true }),
  {
    action: 'type', target: 'catalogue-search', text: 'cement', optional: true,
  },
  // Let the filtered list actually render before describing it.
  { action: 'wait', ms: 1800 },
  ...say(
    'Act 10 · Coverage',
    'Every standard in the catalogue, searched on the server as you type.',
    'Search by IS number, title or keyword, narrowed by sector.',
    'This screen is also the honest answer to “is my product covered?”, '
      + 'worth asking before trusting any search result, because a sector '
      + 'that is not listed here cannot be recommended from.',
    4000,
  ),

  // ═══════════════════════ Act 11, the honesty screens ═══════════════════
  // Administrator screens: other roles do not have them in the sidebar.
  { action: 'skipIf', when: 'notAdmin', to: 'usage' },
  ...intro(
    { nav: 'nav-compliance', waitFor: 'compliance-title' },
    'Act 11 · Corpus health',
    'How complete the corpus’s own metadata is.',
    'Certification confirmed vs unverified; amendments researched vs unchecked.',
    'Always as a ratio against the total, because 17 confirmed records means '
      + 'nothing without the total they are out of.',
    4000,
  ),

  ...intro(
    { nav: 'nav-admin', waitFor: 'admin-title' },
    'Act 11 · Engine status',
    'What this instance is actually running.',
    'Corpus size, model state, feedback counts, read from the engine at load.',
    'Including its own degraded states: if the learned ranker fails to load, '
      + 'the screen says so and names the likely cause rather than quietly '
      + 'serving heuristic results.',
    4200,
  ),

  // ═══════════════════════ Act 12, counted usage, and close ══════════════
  { action: 'label', name: 'usage' },
  ...intro(
    { nav: 'nav-dashboard', waitFor: 'dashboard-title' },
    'Act 12 · Usage',
    'Every figure here is counted, not projected.',
    'Searches served, match rate, median response, acceptance rate.',
    'Read from the engine’s own append-only logs. A rate with no '
      + 'decisions behind it renders as a dash, never as 0%, those are '
      + 'different statements.',
    4000,
  ),

  ...say(
    'That is the whole path',
    'Search → read → cluster → upload → assemble → freeze → audit.',
    'With the spec basket carrying your work across every screen.',
    'Every recommendation logged with its query, the candidates shown, their '
      + 'scores, the editions in force, and what you decided.',
    4000,
  ),
  { action: 'finish' },
];
