/**
 * The demo engine.
 *
 * Runs a sequence of steps from demo.config.js against the live application:
 * it resolves targets to real DOM nodes, animates a synthetic cursor between
 * them, and drives the app through the same events a real user produces.
 *
 * Three rules shape the design:
 *
 *   1. No coordinates. Every target is resolved from a selector at the moment
 *      it is needed, so the demo survives a re-layout, a different viewport,
 *      or a scroll position it did not predict.
 *
 *   2. No faked application state. Clicks are real clicks, typed text goes in
 *      through React's own change events, and the uploaded file reaches the
 *      page's own <input type="file">. The demo never calls into application
 *      internals or substitutes canned results for live ones.
 *
 *   3. Wait for the app, not the clock. `waitFor` polls the real DOM. A slow
 *      backend makes the demo wait longer, never click early.
 *
 * The engine is framework-agnostic, a plain class. React talks to it through
 * the `useDemo` hook, which subscribes to its state changes.
 */

import {
  DEMO_TARGETS,
  DEMO_CONDITIONS,
  DEMO_TIMING,
  DEMO_WAIT_TIMEOUT,
  DEMO_FILE,
} from './demo.config';
// Imported from its own module rather than through the config's re-export, so
// there is no cycle between the two files.
import { demoSteps as defaultSteps } from './demo.steps';

/** Cursor offset from the element's centre, so the pointer tip sits on it. */
const TIP_OFFSET = { x: -2, y: -2 };

const raf = () => new Promise(requestAnimationFrame);

/** easeInOutCubic, slow start, quick middle, soft landing. Reads as human. */
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/**
 * How progress is counted.
 *
 * Not in engine steps: one act is a caption plus a wait plus several cursor
 * moves, so a step count jumps unevenly and tells a viewer nothing. Acts are
 * counted instead, the captions that carry an `act` heading, which is exactly
 * what a viewer perceives as "where am I in this tour".
 */
const isAct = (step) => step.action === 'caption' && Boolean(step.act);

export class DemoEngine {
  constructor({ steps = defaultSteps, navigate, onState } = {}) {
    this.steps = steps;
    this.navigate = navigate;
    this.onState = onState;

    this.state = {
      running: false,
      paused: false,
      finished: false,
      stepIndex: 0,      // index into this.steps, for logging and recovery
      act: 0,            // acts completed, what the HUD shows
      total: steps.filter(isAct).length,
      caption: null,
      error: null,
      // Cursor is kept in state so React renders it; the engine mutates it
      // through setState so there is one source of truth.
      cursor: { x: 0, y: 0, visible: false, pressing: false },
      ripple: null,
      spotlight: null,
      picker: null,        // the demo's own file-chooser panel, when shown
      log: [],
    };

    this._abort = null;
    this._resumeWaiters = [];
    this._skip = false;      // set by skip(); cleared as each step begins
    this._skipped = [];      // steps stepped over this run, for the summary
    this._absent = new Set();// targets proved missing on the current screen
  }

  /**
   * Cut the current step short.
   *
   * For a presenter mid-recording: a long narration beat or a slow retrieval
   * can be skipped without stopping the demo. Deliberately only shortens
   * *waiting*, the click, the typing and the cursor travel still happen, so
   * skipping cannot desynchronise the demo from the application.
   */
  skip() {
    if (!this.state.running) return;
    this._skip = true;
    this.resume();
    this._log('info', 'Skipped ahead');
  }

  // ──────────────────────────── state plumbing ────────────────────────────

  _set(patch) {
    this.state = { ...this.state, ...patch };
    this.onState?.(this.state);
  }

  _log(level, message) {
    // Kept short: this is a presenter's breadcrumb trail, not an audit log.
    const entry = { level, message, at: Date.now() };
    this._set({ log: [...this.state.log.slice(-40), entry] });
    const line = `[demo] ${message}`;
    if (level === 'error') console.error(line);
    else if (level === 'warn') console.warn(line);
    else console.info(line);
  }

  // ─────────────────────────── lifecycle control ──────────────────────────

  async start() {
    if (this.state.running) return;

    this._abort = new AbortController();
    const { signal } = this._abort;

    document.documentElement.setAttribute('data-demo', 'running');

    this._skipped = [];
    this._absent = new Set();
    this._set({
      running: true,
      paused: false,
      finished: false,
      stepIndex: 0,
      act: 0,
      error: null,
      caption: null,
      spotlight: null,
      log: [],
      // Start the cursor low and centre-left, like a hand resting on a mouse.
      cursor: {
        x: window.innerWidth * 0.5,
        y: window.innerHeight * 0.78,
        visible: true,
        pressing: false,
      },
    });

    this._log('info', `Demo started, ${this.steps.length} steps`);

    try {
      await this._run(signal);
      if (!signal.aborted) {
        this._set({
          finished: true,
          running: false,
          spotlight: null,
          picker: null,
          skipped: this._skipped.length,
        });
        this._log(
          'info',
          this._skipped.length
            ? `Demo complete, ${this._skipped.length} step(s) skipped`
            : 'Demo complete',
        );
        document.documentElement.setAttribute('data-demo', 'finished');
      }
    } catch (err) {
      if (signal.aborted) return;   // a Stop is not a failure
      // A step that cannot recover stops the demo and says why, rather than
      // leaving a half-dimmed screen and a cursor parked on nothing.
      this._log('error', err.message);
      this._set({
        running: false,
        error: err.message,
        spotlight: null,
        caption: null,
        picker: null,
      });
      document.documentElement.removeAttribute('data-demo');
    }
  }

  pause() {
    if (!this.state.running || this.state.paused) return;
    this._set({ paused: true });
    this._log('info', 'Paused');
  }

  resume() {
    if (!this.state.running || !this.state.paused) return;
    this._set({ paused: false });
    this._log('info', 'Resumed');
    // Release anything blocked in _gate().
    const waiters = this._resumeWaiters;
    this._resumeWaiters = [];
    waiters.forEach((fn) => fn());
  }

  /**
   * Hand control back to the user immediately.
   *
   * Everything the demo added to the page is removed here: the dim layer, the
   * spotlight, the cursor, the caption. The application is left exactly as the
   * demo found it, on whatever screen it had reached.
   */
  stop() {
    this._abort?.abort();
    this.resume();   // unblock any pending gate so the loop can unwind
    this._set({
      running: false,
      paused: false,
      spotlight: null,
      caption: null,
      ripple: null,
      picker: null,
      cursor: { ...this.state.cursor, visible: false, pressing: false },
    });
    document.documentElement.removeAttribute('data-demo');
    this._log('info', 'Stopped, control returned to you');
  }

  dismissError() {
    this._set({ error: null, finished: false });
  }

  // ──────────────────────────── the step loop ─────────────────────────────

  async _run(signal) {
    let i = 0;

    while (i < this.steps.length) {
      if (signal.aborted) return;

      const step = this.steps[i];
      await this._gate(signal);
      if (signal.aborted) return;

      this._set({
        stepIndex: i,
        ...(isAct(step) ? { act: this.state.act + 1 } : {}),
      });
      this._skip = false;

      // A caption starts a new act, so give every target another chance:
      // absence on the previous screen says nothing about this one.
      if (isAct(step)) this._absent.clear();

      // Already known missing on this screen? Skip without re-polling. Three
      // steps address each element (move, highlight, click), and re-proving
      // the same absence for each is what makes a gap feel like a freeze.
      if (step.target && this._absent.has(step.target)) {
        this._log('warn', `Skipped ${this._describe(step)}, target absent on this screen`);
        i += 1;
        continue;
      }

      try {
        const jump = await this._execute(step, signal);

        // A skipIf whose condition held returns the label to jump to.
        if (jump) {
          const at = this.steps.findIndex(
            (s) => s.action === 'label' && s.name === jump,
          );
          if (at === -1) {
            this._log('warn', `No label "${jump}", continuing in order`);
          } else {
            this._log('info', `Skipping ahead to "${jump}"`);
            i = at + 1;
            continue;
          }
        }
      } catch (err) {
        if (signal.aborted) return;

        // Recovery policy: keep going.
        //
        // A demo is usually being recorded, and losing a four-minute take to
        // one late-rendering element or one slow API call is far worse than a
        // single skipped beat that nobody watching would notice. So a failed
        // step is logged and stepped over, and the run reports at the end how
        // many it skipped.
        //
        // `resilient: false` opts a step back into stopping the demo, for the
        // few cases where continuing would be incoherent rather than merely
        // imperfect.
        this._skipped.push({ step: this._describe(step), reason: err.message });
        if (step.target && /never appeared|absent/.test(err.message)) {
          this._absent.add(step.target);
        }

        if (step.resilient === false) {
          throw new Error(`${this._describe(step)}, ${err.message}`);
        }

        this._log('warn', `Skipped ${this._describe(step)}, ${err.message}`);

        // Leave nothing of the failed step on screen: a ring or a caption
        // pointing at an element that never appeared is what actually reads
        // as broken.
        this._set({ spotlight: null, picker: null });
      }

      i += 1;
    }
  }

  _describe(step) {
    const what = step.target ?? step.until ?? step.to ?? step.when ?? '';
    return `step ${this.state.stepIndex + 1} (${step.action}${what ? ` "${what}"` : ''})`;
  }

  /** Blocks while paused. Every step passes through here first. */
  _gate(signal) {
    if (!this.state.paused || signal.aborted) return Promise.resolve();
    return new Promise((resolve) => {
      this._resumeWaiters.push(resolve);
      signal.addEventListener('abort', () => resolve(), { once: true });
    });
  }

  /** Pause-aware, abort-aware, skip-aware sleep. */
  async _sleep(ms, signal) {
    const step = 60;
    let left = ms;
    while (left > 0) {
      if (signal.aborted || this._skip) return;
      await this._gate(signal);
      const slice = Math.min(step, left);
      await new Promise((r) => setTimeout(r, slice));
      left -= slice;
    }
  }

  // ───────────────────────────── the actions ──────────────────────────────

  async _execute(step, signal) {
    switch (step.action) {
      case 'label':
        return null;

      case 'caption':
        this._set({
          caption: {
            act: step.act,
            text: step.text,
            sub: step.sub,
            detail: step.detail,
          },
        });
        await this._sleep(DEMO_TIMING.captionIn, signal);
        return null;

      case 'wait':
        await this._sleep(step.ms ?? DEMO_TIMING.sectionPause, signal);
        return null;

      case 'skipIf': {
        const cond = DEMO_CONDITIONS[step.when];
        if (!cond) throw new Error(`unknown condition "${step.when}"`);
        return cond() ? step.to : null;
      }

      case 'navigate':
        // The outgoing screen's ring must not survive into the new one.
        this._set({ spotlight: null });
        this._log('info', `Navigating to ${step.to}`);
        this.navigate?.(step.to);
        // One frame for React to commit, then settle.
        await raf();
        await this._sleep(step.settle ?? 700, signal);
        return null;

      case 'moveTo': {
        const el = await this._require(step.target, signal);
        await this._scrollIntoView(el, step.block, signal);
        await this._moveCursorTo(el, step.duration, signal);
        await this._sleep(step.pause ?? DEMO_TIMING.beforeClick, signal);
        return null;
      }

      case 'highlight': {
        const el = await this._require(step.target, signal);
        await this._scrollIntoView(el, step.block, signal);

        // Keep the pointer and the ring together. A ring appearing far from
        // the cursor reads as a jump cut; following it is what a presenter's
        // hand does anyway.
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const away = Math.hypot(cx - this.state.cursor.x, cy - this.state.cursor.y);
        if (step.follow !== false && away > Math.max(220, r.height)) {
          await this._moveCursorTo(el, DEMO_TIMING.cursorMove, signal);
        }

        this._spotlight(el, step.pad);
        await this._sleep(step.pause ?? 450, signal);
        return null;
      }

      case 'scrollTo': {
        const el = await this._require(step.target, signal);
        await this._scrollIntoView(el, step.block ?? 'center', signal, true);
        return null;
      }

      case 'click': {
        const el = await this._require(step.target, signal);
        await this._scrollIntoView(el, step.block, signal);
        await this._moveCursorTo(el, undefined, signal);
        await this._sleep(DEMO_TIMING.beforeClick, signal);
        await this._click(el, signal);
        await this._sleep(DEMO_TIMING.afterClick, signal);
        return null;
      }

      case 'type': {
        const el = await this._require(step.target, signal);
        await this._scrollIntoView(el, step.block, signal);
        await this._type(el, step.text, step.speed, signal);
        await this._sleep(step.pause ?? 400, signal);
        return null;
      }

      case 'upload': {
        const input = await this._require(step.target, signal);
        await this._upload(input, step.file ?? DEMO_FILE, signal);
        return null;
      }

      case 'waitFor':
        await this._waitFor(step, signal);
        return null;

      case 'finish':
        this._set({ spotlight: null });
        return null;

      default:
        throw new Error(`unknown action "${step.action}"`);
    }
  }

  // ──────────────────────── target resolution ─────────────────────────────

  /**
   * Resolve a target key to a visible element.
   *
   * Selectors are tried in the order the config lists them. A file input is
   * deliberately allowed to be invisible, the app hides it by design and the
   * upload step needs it anyway.
   */
  _find(key) {
    const selectors = DEMO_TARGETS[key];
    if (!selectors) throw new Error(`no selector configured for target "${key}"`);

    for (const selector of selectors) {
      for (const el of document.querySelectorAll(selector)) {
        if (el.type === 'file') return el;
        const rect = el.getBoundingClientRect();
        const styles = getComputedStyle(el);
        const visible =
          rect.width > 0 &&
          rect.height > 0 &&
          styles.visibility !== 'hidden' &&
          styles.display !== 'none' &&
          Number(styles.opacity) > 0.05;
        if (visible) return el;
      }
    }
    return null;
  }

  /**
   * Poll for a target until it appears, or throw when the budget runs out.
   *
   * The default budget is deliberately short. Every step that needs an
   * element is preceded by a `waitFor` on the screen that owns it, so if it is
   * not there within a couple of seconds it is not coming, and a long retry
   * on each of a run of doomed steps is what makes a demo look frozen rather
   * than merely imperfect.
   */
  async _require(key, signal, timeout = 2500) {
    const deadline = Date.now() + timeout;
    let el = this._find(key);
    while (!el) {
      if (signal.aborted) throw new Error('aborted');
      if (Date.now() > deadline) {
        throw new Error(`target "${key}" never appeared`);
      }
      await this._sleep(150, signal);
      el = this._find(key);
    }
    return el;
  }

  /**
   * Wait for real application state.
   *
   * Either a `target` that must appear in the DOM, or a named condition from
   * DEMO_CONDITIONS. This is what keeps the demo honest about a slow backend:
   * a cold model load makes it wait, not click early.
   */
  async _waitFor(step, signal) {
    const timeout = step.timeout ?? DEMO_WAIT_TIMEOUT;
    const deadline = Date.now() + timeout;
    const label = step.target ?? step.until;

    // `orTarget` lets a wait finish on the application's own failure state as
    // well as its success state. A search whose backend errors renders an
    // error card and never renders results; without this the demo would wait
    // out the whole timeout for a panel that is not coming.
    const satisfied = step.until
      ? DEMO_CONDITIONS[step.until]
      : () => Boolean(
        this._find(step.target)
        || (step.orTarget && this._find(step.orTarget)),
      );

    if (step.until && !satisfied) throw new Error(`unknown condition "${step.until}"`);

    if (satisfied()) return;

    this._log('info', `Waiting for ${label}…`);
    while (!satisfied()) {
      if (signal.aborted) throw new Error('aborted');
      if (Date.now() > deadline) {
        throw new Error(`timed out after ${Math.round(timeout / 1000)}s waiting for ${label}`);
      }
      await this._sleep(200, signal);
    }
    this._log('info', `${label} ready`);
  }

  // ─────────────────────────── cursor movement ────────────────────────────

  /**
   * Glide the cursor to an element's centre over `duration`.
   *
   * The target is re-measured on every frame, so a layout that shifts mid-move
   * (a result list expanding, an image loading) does not leave the cursor
   * pointing at where the element used to be.
   */
  async _moveCursorTo(el, duration = DEMO_TIMING.cursorMove, signal) {
    const from = { x: this.state.cursor.x, y: this.state.cursor.y };
    const target = () => {
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2 + TIP_OFFSET.x, y: r.top + r.height / 2 + TIP_OFFSET.y };
    };

    // A first-ever move has no meaningful origin; drop in near the target.
    const start = performance.now();
    const total = Math.max(120, duration);

    for (;;) {
      if (signal.aborted) return;
      await this._gate(signal);

      const t = Math.min(1, (performance.now() - start) / total);
      const e = ease(t);
      const to = target();

      // A gentle arc rather than a straight line, a real hand does not move
      // in a perfect segment. The bow is perpendicular to the travel, scaled
      // by distance and faded out at both ends.
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const dist = Math.hypot(dx, dy);
      const bow = Math.min(46, dist * 0.12) * Math.sin(Math.PI * e);
      const nx = dist ? -dy / dist : 0;
      const ny = dist ? dx / dist : 0;

      this._set({
        cursor: {
          ...this.state.cursor,
          visible: true,
          x: from.x + dx * e + nx * bow,
          y: from.y + dy * e + ny * bow,
        },
      });

      if (t >= 1) break;
      await raf();
    }

    const end = target();
    this._set({ cursor: { ...this.state.cursor, x: end.x, y: end.y } });
  }

  /**
   * Keep the spotlight box on an element, in viewport coordinates.
   *
   * Clamped to the viewport, because a target taller than the screen, a long
   * results list, say, would otherwise put the ring off-screen in both
   * directions and dim nothing at all, which reads as a broken highlight.
   */
  _spotlight(el, pad = 8) {
    const r = el.getBoundingClientRect();
    const radius = Math.min(14, Number.parseFloat(getComputedStyle(el).borderRadius) || 6);
    const m = 10;   // never let the ring sit flush against the viewport edge

    const top = Math.max(m, r.top - pad);
    const left = Math.max(m, r.left - pad);
    const bottom = Math.min(window.innerHeight - m, r.bottom + pad);
    const right = Math.min(window.innerWidth - m, r.right + pad);

    this._set({
      spotlight: {
        top,
        left,
        width: Math.max(0, right - left),
        height: Math.max(0, bottom - top),
        radius: radius + pad / 2,
      },
    });
  }

  /**
   * Bring an element into view and wait for the scroll to settle.
   *
   * Smooth scrolling has no completion event, so this watches the element's
   * own position until it stops changing, more reliable than a fixed delay,
   * and it returns immediately when nothing needed to move.
   */
  async _scrollIntoView(el, block = 'center', signal, force = false) {
    const inView = () => {
      const r = el.getBoundingClientRect();
      const margin = 80;
      return r.top >= margin && r.bottom <= window.innerHeight - margin;
    };

    if (!force && inView()) return;

    el.scrollIntoView({ behavior: 'smooth', block, inline: 'nearest' });

    let last = null;
    let still = 0;
    const deadline = Date.now() + 2500;

    while (Date.now() < deadline) {
      if (signal.aborted) return;
      await this._sleep(80, signal);
      const y = Math.round(el.getBoundingClientRect().top);
      if (last !== null && Math.abs(y - last) < 1) {
        if (++still >= 2) break;
      } else {
        still = 0;
      }
      last = y;
    }

    // The spotlight was measured before the scroll; re-measure it after.
    if (this.state.spotlight) this._spotlight(el);
  }

  // ────────────────────────────── interaction ─────────────────────────────

  /**
   * Click an element the way a pointer does.
   *
   * The full pointer/mouse sequence goes out rather than a bare `.click()`,
   * because components listening for pointerdown or mousedown (and React's
   * synthetic events) should see the same thing a real user produces.
   */
  async _click(el, signal) {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;

    this._set({
      cursor: { ...this.state.cursor, pressing: true },
      ripple: { x, y, id: Date.now() },
    });

    const opts = {
      bubbles: true,
      cancelable: true,
      clientX: x,
      clientY: y,
      view: window,
    };

    el.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerType: 'mouse', isPrimary: true }));
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    // Focus before mouseup, as a browser does, so focus-driven UI settles.
    if (typeof el.focus === 'function') el.focus({ preventScroll: true });

    await this._sleep(110, signal);

    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerType: 'mouse', isPrimary: true }));
    el.click();

    this._set({ cursor: { ...this.state.cursor, pressing: false } });
    setTimeout(() => this._set({ ripple: null }), 650);
  }

  /**
   * Type into a controlled React input, one character at a time.
   *
   * React tracks the previous value on the DOM node, so assigning `.value`
   * directly makes it treat the change as already-seen and ignore the event.
   * Setting it through the prototype's own setter is the documented way
   * around that, and is what testing libraries do.
   */
  async _type(el, text, speed = DEMO_TIMING.typingSpeed, signal) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setValue = Object.getOwnPropertyDescriptor(proto, 'value').set;

    el.focus({ preventScroll: true });

    // A field the app prefills has to be cleared, and the clearing has to be
    // visible: wiping it in one frame looks like a scripted reset. So the
    // existing value is selected, held long enough to read as deliberate, then
    // deleted, what a person does before retyping a field.
    if (el.value) {
      el.select?.();
      await this._sleep(420, signal);

      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
      setValue.call(el, '');
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Backspace', bubbles: true }));

      // A beat on the empty field, so the viewer sees it was emptied.
      await this._sleep(320, signal);
    }

    for (const ch of text) {
      if (signal.aborted) return;
      await this._gate(signal);

      el.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true }));
      setValue.call(el, el.value + ch);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keyup', { key: ch, bubbles: true }));

      // Vary the interval a little. Perfectly even keystrokes read as a macro.
      const jitter = speed * (0.65 + Math.random() * 0.7);
      // A space is where a real typist hesitates.
      await this._sleep(ch === ' ' ? jitter * 1.5 : jitter, signal);
    }

    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  /**
   * Hand the demo file to the page's own file input, visibly.
   *
   * Two problems are solved here, and they pull in opposite directions.
   *
   * The functional one: a browser will not let script open the OS file
   * picker, and nothing here tries to. The file is fetched from `public/`,
   * wrapped in a DataTransfer so the input receives a genuine FileList, and
   * the input's own change handler runs, the same handler a manual selection
   * triggers. From the application's point of view, the user picked a file.
   *
   * The recording one: done silently, that reads as nothing happening. A
   * viewer sees a click on "Select file" and then, with no visible cause, a
   * filename. So the engine draws its own file-chooser panel, moves the
   * cursor onto the file, and clicks it. The panel is plainly the demo's own
   * it is captioned as such rather than dressed up as the operating
   * system's, because a fake OS dialog in a product video is a lie about how
   * the software behaves.
   */
  async _upload(input, spec, signal) {
    this._log('info', `Providing ${spec.name} to the upload component`);

    let file;
    try {
      const res = await fetch(spec.path, { signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      file = new File([blob], spec.name, {
        type: spec.type || blob.type || 'application/octet-stream',
      });
    } catch (err) {
      if (signal.aborted) throw new Error('aborted');
      throw new Error(
        `could not load the demo file from ${spec.path} (${err.message}). ` +
        'Check the file exists in frontend/public and that DEMO_FILE.path matches.',
      );
    }

    // Show the chooser, with the file's real size read off the blob.
    this._set({
      picker: {
        name: spec.name,
        size: file.size,
        type: spec.type,
        selected: false,
        opening: true,
      },
    });
    await this._sleep(620, signal);
    this._set({ picker: { ...this.state.picker, opening: false } });

    // Move the cursor onto the row, the way a person reaches for the file.
    const row = await this._require('demo-picker-file', signal, 6000);
    await this._moveCursorTo(row, 780, signal);
    await this._sleep(420, signal);

    // Select it: the row highlights and the Open button becomes the target.
    const r = row.getBoundingClientRect();
    this._set({
      picker: { ...this.state.picker, selected: true },
      ripple: { x: r.left + r.width / 2, y: r.top + r.height / 2, id: Date.now() },
    });
    await this._sleep(700, signal);

    const open = await this._require('demo-picker-open', signal, 6000);
    await this._moveCursorTo(open, 620, signal);
    await this._sleep(380, signal);

    const o = open.getBoundingClientRect();
    this._set({
      cursor: { ...this.state.cursor, pressing: true },
      ripple: { x: o.left + o.width / 2, y: o.top + o.height / 2, id: Date.now() + 1 },
    });
    await this._sleep(180, signal);
    this._set({ cursor: { ...this.state.cursor, pressing: false } });

    // The panel closes, and only then does the file reach the application,     // so the upload starts exactly when the viewer sees the dialog dismissed.
    // The spotlight goes with it: it was measured against a row that no longer
    // exists, and would otherwise hang over the page as an empty ring.
    this._set({ picker: null, spotlight: null });
    await this._sleep(260, signal);

    const dt = new DataTransfer();
    dt.items.add(file);
    Object.defineProperty(input, 'files', {
      configurable: true,
      get: () => dt.files,
    });

    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    await this._sleep(500, signal);
  }
}
