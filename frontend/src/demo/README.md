# Demo Mode

An automated guided tour that drives the real application, for recording a
product demo, or for showing a newcomer what StandEng actually does.

Click **Start Demo** on the homepage (next to "Open the engine"), or **Start
guided demo** in the account menu at the top right of any workbench screen,
and the application runs the whole path by itself: sign in, search, upload a bill of
quantities, collect standards, assemble and freeze a spec, open the audit
screen. No further clicks.

## What it is not

It is a layer on top of the app, not a change to it. Demo Mode:

- uses the application's own components, API calls, routing and auth, it
  never substitutes canned results for live ones;
- renders nothing at all until the first run, so the normal app carries no
  overlay and no listeners;
- never uses fixed screen coordinates. Every target is resolved from a
  selector at the moment it is needed, so the demo survives a re-layout, a
  different viewport, or a scroll position it did not predict;
- waits for real application state rather than guessing at delays. A slow
  backend makes the demo wait longer, never click early.

## Files

| File | What it holds |
|---|---|
| `demo.steps.js` | **The tour itself**, 12 acts, with all the narration. Edit this to change what the demo does or says. |
| `demo.config.js` | Credentials, timing, the sample file, and the target-selector table. |
| `demoEngine.js` | The controller: resolves targets, animates the cursor, dispatches real events, waits on app state. Framework-agnostic. |
| `DemoProvider.jsx` | React binding. Owns one engine, mirrors its state, exports `StartDemoButton`. |
| `DemoOverlay.jsx` | What is drawn: cursor, spotlight, dim veil, narration, HUD, progress, completion/error cards. |
| `useDemo.js` | The context and hook, split out so the provider hot-reloads. |
| `demo.css` | All demo styling, scoped to `.demo-*` and `html[data-demo]`. |

Plus two sample documents in `public/demo/` and `e2e/demo.spec.js` (the tests).

## Navigation is clicked, never teleported

Every screen change in the tour happens by **moving the cursor to the sidebar
link and pressing it**. A route that changes with no cursor near it is the
most confusing thing a demo can do, the viewer cannot tell what caused the
page to change, so it reads as a glitch rather than as navigation.

`goTo()` and `intro()` in `demo.steps.js` enforce this:

```js
...intro(
  { nav: 'nav-compliance', waitFor: 'compliance-title' },
  'Act 11 · Corpus health', ...
)
```

Nav targets are generated from each route (`/app/alerts` → `nav-alerts`), so a
new sidebar entry is addressable without editing `Shell.jsx` again. The only
screen reached without a nav click is the standard detail page, which has no
sidebar entry, and that one is opened by clicking the IS number on a result,
which is how a user reaches it too.

## What the tour covers

Twelve acts, following one tender through the whole job:

| Act | Screen | The point it makes |
|---|---|---|
| 1 | Landing → Sign in | Waits for the viewer to sign in with their own account |
| 2 | New query | Search by meaning, no IS number needed |
| 3 | Standard detail | Scope, edition, amendments, certification |
| 4 | Related standards map | A product needs a cluster, not one standard |
| 5 | Certification | Which standards are legally mandatory |
| 6 | Upload tender / BOQ | Ten line items, matched independently |
| 7 | Spec builder | The deliverable, its gaps, and the frozen audit record |
| 8 | Audit tender | Uploads a second document; finds real citation faults |
| 9 | Standards hygiene | Superseded editions across the corpus |
| 10 | Standards catalogue | What is and is not covered |
| 11 | Corpus health · Engine status | The honesty screens, and what is running |
| 12 | Usage | Counted, not projected |

A full pass takes about **3 minutes 45 seconds**, most of it the engine
genuinely retrieving.

## Customising

### Signing in

The tour never types a password, and there is no shared demo account. Started
signed out, it opens the sign-in page, says what it is waiting for, and waits
(up to ten minutes) while the viewer signs in with their own account; the sign-in
card stays usable under the tour's interaction lock (`data-demo-ignore`).
Started from inside the workbench, it skips this act. The corpus-health and
engine-status act is skipped for roles that do not have those screens.

### The sample documents

Two, because the tour demonstrates two different jobs:

```js
// Act 6, a bill of quantities: goods to be matched against the corpus.
export const DEMO_FILE = {
  path: '/demo/sample-boq.txt',              // under frontend/public/
  name: 'Tender-BOQ-Substation-Works.txt',   // the filename the app displays
  type: 'text/plain',
};

// Act 8, a specification that already cites IS numbers, to be audited.
export const DEMO_AUDIT_FILE = {
  path: '/demo/sample-tender.txt',
  name: 'Tender-Spec-Section-7-Standards.txt',
  type: 'text/plain',
};
```

`sample-tender.txt` deliberately contains three faults the audit catches: an
outdated edition (`IS 694:1990`), and two undated citations (`IS 383`,
`IS 1239`). Editing it changes what the audit act finds, so keep at least one
real fault or that act has nothing to show.

A step uploads whichever file it names:

```js
{ action: 'upload', target: 'audit-file', file: DEMO_AUDIT_FILE }
```

To use a PDF instead: drop `sample.pdf` into `frontend/public/demo/`, then set
`path: '/demo/sample.pdf'` and `type: 'application/pdf'`. The backend reads
`.pdf`, `.docx`, `.xlsx`, `.xls` and `.txt`.

### How the upload is shown

A browser will not let a script open the operating system's file picker, and
nothing here tries to. Done silently, though, that reads as nothing happening:
a viewer sees a click on "Select file" and then, with no visible cause, a
filename.

So the engine draws **its own file chooser**, moves the cursor onto the file,
selects it, and clicks Open, then hands the `File` to the page's own
`<input type="file">` and lets the page's own `onChange` run. The application
processes it exactly as it processes a manual selection.

The panel carries a **Demo Mode** tag rather than being styled to impersonate
the OS dialog. A viewer should never be misled about which part of what they
are watching is the product.

### Prefilled fields

Wiping a field in one frame reads as a scripted reset, so `type` selects any
existing value, holds it long enough to register, deletes it, pauses on the
empty field, and only then types.

### Timing

```js
export const DEMO_TIMING = {
  cursorMove: 900,      // travel time between two elements
  beforeClick: 550,     // settle on the target before pressing
  afterClick: 850,      // let the UI react before moving on
  typingSpeed: 55,      // per keystroke (jittered, so it is not metronomic)
  sectionPause: 1400,   // between phases of the story
  readPause: 2200,
  captionIn: 350,
};
```

Raise `afterClick` and the `wait` steps for a slower, more narrated recording;
lower them for a shorter clip. A full pass currently runs about 2–3 minutes,
most of which is the engine genuinely retrieving.

### The sequence

`demoSteps` in **`demo.steps.js`** is a flat, ordered array. Three helpers keep
it readable:

```js
say(act, text, sub, detail, ms)          // narration plus a beat
point(target, ms)                        // move, highlight, dwell
press(target, opts)                      // move, highlight, click
intro(to, waitTarget, act, text, ...)    // navigate, wait, THEN narrate
```

`intro()` matters: captioning before navigating describes the new screen while
the old one is still on camera. Every act transition goes through it so that
cannot happen.

Each entry is one action:

| Action | Fields | Does |
|---|---|---|
| `caption` | `text`, `sub?` | narration, lower left |
| `moveTo` | `target` | glide the cursor to an element |
| `highlight` | `target`, `pad?` | spotlight it, dimming everything else |
| `click` | `target` | ripple, then a real click |
| `type` | `target`, `text`, `speed?` | keystroke-by-keystroke |
| `wait` | `ms` | a deliberate pause |
| `waitFor` | `target` or `until`, `timeout?` | wait for real app state |
| `scrollTo` | `target`, `block?` | smooth-scroll into view and settle |
| `upload` | `target`, `file?` | hand the demo file to a file input |
| `navigate` | `to` | route change via react-router |
| `skipIf` | `when`, `to` | jump to a `label` when a condition holds |
| `label` | `name` | a jump destination |
| `finish` | – | end of demo |

Any step may carry `optional: true`, which turns a missing target from a
demo-stopping error into a logged skip. Use it for anything conditional, an
export button that needs a non-empty basket, for instance.

Reordering the acts is a matter of moving blocks in this array. Nothing else
needs to change.

### Targets

Steps name a key, never a selector:

```js
export const DEMO_TARGETS = {
  email:    ['[data-demo-target="email"]', '#email'],
  'sign-in':['[data-demo-target="sign-in"]', '.auth-card button[type="submit"]'],
  // ...
};
```

Selectors are tried in order; the first that resolves to a *visible* element
wins. The `data-demo-target` attribute is the stable contract, and the
fallback after it means a target still resolves on a screen nobody has
annotated yet. To retarget a step, change the selector here, not the sequence.

Attributes currently in the app:

```
landing-cta  landing-signin
email  password  sign-in
query-input  query-submit  query-results
boq-dropzone  boq-select  boq-file  boq-running  boq-results  boq-summary
builder-title  builder-list  builder-freeze
audit-title  audit-dropzone  audit-select
dashboard-title
```

### Waiting on application state

`waitFor` takes either a `target` (wait for it to appear) or an `until`
naming a condition in `DEMO_CONDITIONS`:

```js
export const DEMO_CONDITIONS = {
  isLoggedIn:  () => !!document.querySelector('.shell'),
  onWorkbench: () => window.location.pathname.startsWith('/app') && !!document.querySelector('.shell'),
  notAdmin:    () => !document.querySelector('[data-demo-target="nav-admin"]'),
};
```

These read the live URL and DOM, so "logged in" means what the application
actually shows (the workbench shell renders only for a signed-in session),
not what the demo assumed three steps ago. That is also how the demo skips
the sign-in act when it is started from inside the app:

```js
{ action: 'skipIf', when: 'isLoggedIn', to: 'workbench' },
```

## Controls

While running: **Pause**, **Resume**, **Skip**, **Stop**, an act counter and a
progress bar, bottom right. `Space` pauses, `→` skips, `Esc` stops.

- **Skip** cuts the current pause short, useful mid-recording when a
  narration beat or a slow retrieval is taking longer than the take allows. It
  only shortens *waiting*; clicks, typing and cursor travel still happen, so
  skipping cannot desynchronise the demo from the application.
- **Stop** returns control instantly, the lock, the dimming, the cursor and
  the narration all go at once, leaving the app on whatever screen it reached.

Progress is counted in **acts** (the captioned chapters a viewer sees), not
engine steps, which advance unevenly and mean nothing to a viewer.

User input is blocked while the demo drives, so a stray click cannot ruin a
take. This is `pointer-events: none` on the app root, which blocks hit-testing
for real input devices but not the engine's own dispatched events.

## When a step fails

A required target that never appears stops the demo, shows a card naming the
step and the cause, and hands control back. The application underneath is
untouched and stays usable. Every step is also logged to the console with a
`[demo]` prefix, so a failed recording can be diagnosed from the log.

## Tests

```bash
# needs the backend on :8000 and the dev server on :5173
npx playwright test e2e/demo.spec.js --project=desktop
```

Ten tests, asserting consequences rather than appearances:

- the idle app carries no demo layer at all;
- signed out, the tour **never types a password**, waits on the sign-in page,
  and carries on once the viewer signs in;
- the cursor animates rather than teleporting;
- Pause holds the typing and Resume continues it;
- Stop returns control immediately;
- sign-in is skipped when started from inside the app;
- screens change by **clicking the sidebar**, not by silent route changes;
- the full sequence visits **all twelve acts** start to finish with no
  interaction, including **both** visible file picks and both real uploads;
- a missing target fails gracefully without breaking the app.

The full-sequence test takes about four minutes because it waits on two real
retrieval calls.
