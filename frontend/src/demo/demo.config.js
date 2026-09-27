/**
 * Demo Mode, the single place to change what the demo does.
 *
 * Everything a presenter is likely to want to adjust lives in this file:
 * credentials, pacing, the sample document, the narration, and the step
 * sequence itself. The engine (demoEngine.js) and the overlay
 * (DemoOverlay.jsx) read from here and hold no content of their own.
 *
 * Nothing in this file is imported by the application proper. Demo Mode is a
 * layer on top: with it switched off, the app behaves exactly as it always has.
 */

/**
 * The sample document uploaded in the BOQ step.
 *
 * Served from `public/`, so `/demo/sample-boq.txt` resolves to
 * `frontend/public/demo/sample-boq.txt`. Swap in a PDF by dropping it in the
 * same folder and pointing `path` at it, `type` must match, because the
 * backend decides how to read a file from its extension and MIME type.
 *
 * The engine fetches this file and hands the resulting File object to the
 * page's real <input type="file">, so the application's own upload path runs
 * unchanged. No OS file picker is involved.
 */
export const DEMO_FILE = {
  path: '/demo/sample-boq.txt',
  name: 'Tender-BOQ-Substation-Works.txt',
  type: 'text/plain',
};

/**
 * The document uploaded in the audit step.
 *
 * A different job needs a different file. The BOQ above lists goods to be
 * matched against the corpus; this one is a specification that already cites
 * IS numbers, some of them wrong, an outdated edition, two undated
 * citations, which is exactly what the audit screen exists to catch.
 */
export const DEMO_AUDIT_FILE = {
  path: '/demo/sample-tender.txt',
  name: 'Tender-Spec-Section-7-Standards.txt',
  type: 'text/plain',
};

/**
 * Pacing, in milliseconds.
 *
 * Tuned for screen recording rather than for speed: a viewer needs time to
 * read a highlight before the cursor moves on. Raise `sectionPause` and
 * `afterClick` for a slower, more narrated feel; lower them for a shorter clip.
 */
export const DEMO_TIMING = {
  cursorMove: 900,      // travel time between two elements
  beforeClick: 550,     // settle on the target before pressing
  afterClick: 850,      // let the UI react before moving on
  typingSpeed: 55,      // per keystroke
  sectionPause: 1400,   // between phases of the story
  readPause: 2200,      // long enough to actually read a result
  captionIn: 350,
};

/** How long to wait for an application state before a step gives up. */
export const DEMO_WAIT_TIMEOUT = 90000;

/*
 * The demo sequence lives in `demo.steps.js`. It is deliberately NOT
 * re-exported here: that file imports DEMO_FILE and DEMO_AUDIT_FILE from this one,
 * so a re-export would close a cycle and leave those constants uninitialised
 * at module-evaluation time. Import it from './demo.steps' instead.
 */

/**
 * Where the engine looks for each target.
 *
 * Each key maps to an ordered list of selectors, tried in turn, the first
 * that resolves to a visible element wins. The `data-demo-target` attributes
 * come first because they are the stable contract; the fallbacks after them
 * mean a target still resolves on a screen that has not been annotated yet.
 *
 * To retarget a step, change the selector here rather than the sequence above.
 */
export const DEMO_TARGETS = {
  // Landing
  'landing-cta':      ['[data-demo-target="landing-cta"]', '.hero-cta a.btn-primary'],
  'landing-signin':   ['[data-demo-target="landing-signin"]', '.landing-nav a.btn-secondary'],

  // Login
  email:              ['[data-demo-target="email"]', '#email'],
  password:           ['[data-demo-target="password"]', '#password'],
  'sign-in':          ['[data-demo-target="sign-in"]', '.auth-card button[type="submit"]'],

  // Query
  'query-input':      ['[data-demo-target="query-input"]', '#spec'],
  'query-submit':     ['[data-demo-target="query-submit"]', 'form.card button[type="submit"]'],
  'query-results':    ['[data-demo-target="query-results"]'],
  'query-top-result': [
    '[data-demo-target="query-results"] article.rec',
    'article.rec',
  ],
  // The IS number on the top result, clicking it is how a user opens the
  // detail screen, which has no sidebar entry of its own.
  'query-first-link': [
    '[data-demo-target="query-results"] article.rec a.build-link',
    'article.rec a.build-link',
  ],
  'query-add-first':  [
    '[data-demo-target="query-results"] article.rec .rec-foot button.btn-primary',
    'article.rec .rec-foot button.btn-primary',
  ],

  // BOQ upload
  'boq-dropzone':     ['[data-demo-target="boq-dropzone"]', '.dropzone'],
  'boq-select':       ['[data-demo-target="boq-select"]', '.dropzone button.btn-primary'],
  'boq-file':         ['[data-demo-target="boq-file"]', 'input[type="file"]'],
  'boq-running':      ['[data-demo-target="boq-running"]'],
  'boq-results':      ['[data-demo-target="boq-results"]'],
  'boq-summary':      ['[data-demo-target="boq-summary"]'],
  'boq-first-item':   ['[data-demo-target="boq-results"] article.card'],
  'boq-accept-first': ['[data-demo-target="boq-results"] button.btn-primary.btn-sm'],

  // One standard in full
  'detail-title':     ['[data-demo-target="detail-title"]'],

  // The related-standards cluster
  'map-title':        ['[data-demo-target="map-title"]'],

  // Certification
  'cert-title':       ['[data-demo-target="cert-title"]'],

  // Spec builder
  'builder-title':    ['[data-demo-target="builder-title"]', '.page-title'],
  'builder-list':     ['[data-demo-target="builder-list"]'],
  'builder-gaps':     ['[data-demo-target="builder-gaps"]'],
  'builder-freeze':   ['[data-demo-target="builder-freeze"]'],

  // Audit
  'audit-title':      ['[data-demo-target="audit-title"]', '.page-title'],
  'audit-dropzone':   ['[data-demo-target="audit-dropzone"]', '.dropzone'],
  'audit-select':     ['[data-demo-target="audit-select"]', '.dropzone button.btn-primary'],
  'audit-file':       ['[data-demo-target="audit-file"]', 'input[type="file"]'],
  'audit-running':    ['[data-demo-target="audit-running"]'],
  'audit-results':    ['[data-demo-target="audit-results"]'],
  'audit-summary':    ['[data-demo-target="audit-summary"]'],
  'audit-findings':   ['[data-demo-target="audit-findings"]'],
  'audit-first-finding': ['[data-demo-target="audit-findings"] article.card'],

  // My projects
  'projects-title':   ['[data-demo-target="projects-title"]'],

  // Standards hygiene
  'alerts-title':     ['[data-demo-target="alerts-title"]'],

  // Catalogue
  'catalogue-title':  ['[data-demo-target="catalogue-title"]'],
  'catalogue-search': ['[data-demo-target="catalogue-search"]', '#cat-search'],

  // Corpus health and engine status
  'compliance-title': ['[data-demo-target="compliance-title"]'],
  'admin-title':      ['[data-demo-target="admin-title"]'],

  // Dashboard
  'dashboard-title':  ['[data-demo-target="dashboard-title"]', '.page-title'],

  // Sidebar navigation. Clicking these is how the demo changes screens: a
  // page that changes with no visible cause reads as the demo glitching.
  'nav-query':        ['[data-demo-target="nav-query"]'],
  'nav-boq':          ['[data-demo-target="nav-boq"]'],
  'nav-builder':      ['[data-demo-target="nav-builder"]'],
  'nav-map':          ['[data-demo-target="nav-map"]'],
  'nav-certification':['[data-demo-target="nav-certification"]'],
  'nav-audit':        ['[data-demo-target="nav-audit"]'],
  'nav-projects':     ['[data-demo-target="nav-projects"]'],
  'nav-dashboard':    ['[data-demo-target="nav-dashboard"]'],
  'nav-alerts':       ['[data-demo-target="nav-alerts"]'],
  'nav-catalogue':    ['[data-demo-target="nav-catalogue"]'],
  'nav-compliance':   ['[data-demo-target="nav-compliance"]'],
  'nav-admin':        ['[data-demo-target="nav-admin"]'],

  // The application's own failure states. Waits name these as an acceptable
  // alternative outcome, so a backend that errors does not hang the demo.
  'any-error':        [
    '.notice-crit',
    '[role="alert"]',
    '.card .empty-title',
  ],

  // The demo's own file-chooser panel (drawn by the overlay, not the app).
  'demo-picker-file': ['[data-demo-target="demo-picker-file"]'],
  'demo-picker-open': ['[data-demo-target="demo-picker-open"]'],
};

/**
 * Conditions the sequence can branch or wait on.
 *
 * These read the live URL and DOM rather than any demo-owned state, so
 * "logged in" means what the application actually shows, not what the demo
 * assumed three steps ago.
 */
export const DEMO_CONDITIONS = {
  // The workbench shell only renders for a signed-in session, so its
  // presence is what "logged in" means.
  isLoggedIn: () => !!document.querySelector('.shell'),
  onWorkbench: () => window.location.pathname.startsWith('/app') && !!document.querySelector('.shell'),
  // Administrators have the corpus-health and engine-status entries.
  notAdmin: () => !document.querySelector('[data-demo-target="nav-admin"]'),
};
