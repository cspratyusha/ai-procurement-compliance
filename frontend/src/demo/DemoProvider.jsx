/**
 * Demo Mode's React binding.
 *
 * Owns one DemoEngine instance for the app's lifetime, mirrors its state into
 * React, and renders the overlay. Mounted inside the router so the engine can
 * navigate through react-router rather than reloading the page.
 *
 * With the demo idle this provider renders its children and one small Start
 * Demo control, and touches nothing else. It adds no wrappers around the app
 * and no listeners to application elements.
 */

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { DemoEngine } from './demoEngine';
import { DemoContext, useDemo } from './useDemo';
import DemoOverlay from './DemoOverlay';
import './demo.css';

/** Keys that type, activate, move focus or scroll: the demo's job while it runs. */
const DRIVING_KEYS = /^(Enter|Tab|Backspace|Delete|Arrow\w+|PageUp|PageDown|Home|End)$/;

export function DemoProvider({ children }) {
  const navigate = useNavigate();
  const [state, setState] = useState(null);

  // The engine outlives re-renders. `navigate` is re-bound through a ref so a
  // new router callback never orphans a running demo.
  const navRef = useRef(navigate);
  useEffect(() => { navRef.current = navigate; }, [navigate]);

  // Created once, lazily, and never replaced, a second engine would mean two
  // cursors racing each other over the same page.
  const [engine] = useState(() => new DemoEngine({
    navigate: (to) => navRef.current(to),
    onState: setState,
  }));

  useEffect(() => {
    setState(engine.state);
    // A demo left running through a hot reload or an unmount would keep the
    // page dimmed with nothing driving it.
    return () => engine.stop();
  }, [engine]);

  // Whether the presenter has hidden the control panel. Kept across runs, so
  // a second take starts the way the first one was set up.
  const [hudHidden, setHudHidden] = useState(false);

  const running = Boolean(state?.running);
  const finished = Boolean(state?.finished);

  // The keyboard, while the demo drives.
  //
  // Escape stops the demo: a presenter whose demo goes wrong on camera needs
  // one key, not a hunt for the right button. Space pauses, → skips.
  //
  // Every other real keystroke is held back from the app too. The engine
  // leaves focus on whatever it last clicked or typed into, so a presenter's
  // Space used to press that button again, or type into the demo's query.
  // The exceptions are fields under `data-demo-ignore`, the sign-in card the
  // viewer types into while the tour waits, and the demo's own controls.
  // Synthetic events are the engine's own typing and always pass.
  useEffect(() => {
    if (!running) return undefined;
    const onKey = (e) => {
      if (!e.isTrusted || e.ctrlKey || e.metaKey || e.altKey) return;
      const down = e.type === 'keydown';

      if (e.key === 'Escape') {
        if (down) { e.preventDefault(); engine.stop(); }
        return;
      }

      const t = e.target instanceof Element ? e.target : null;
      const exempt = Boolean(t?.closest('[data-demo-ignore="true"]'));
      const editing = Boolean(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)));
      // The viewer typing their own credentials into the sign-in card.
      if (exempt && editing) return;

      // H hides and shows the control panel, so a take can be recorded clean.
      if (e.key === 'h' || e.key === 'H') {
        e.preventDefault();
        e.stopPropagation();
        if (down && !e.repeat) setHudHidden((hidden) => !hidden);
        return;
      }

      const control = e.key === ' ' || e.key === 'ArrowRight';
      // The demo's own buttons keep Enter and Tab.
      if (exempt && !control) return;
      // Function keys (F11 for a full-screen recording) are the browser's.
      if (!control && e.key.length !== 1 && !DRIVING_KEYS.test(e.key)) return;

      e.preventDefault();
      e.stopPropagation();
      if (!down || e.repeat) return;
      if (e.key === ' ') {
        if (engine.state.paused) engine.resume();
        else engine.pause();
      }
      // Cut a long beat short without losing the demo.
      if (e.key === 'ArrowRight') engine.skip();
    };
    window.addEventListener('keydown', onKey, true);
    window.addEventListener('keyup', onKey, true);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('keyup', onKey, true);
    };
  }, [running, engine]);

  const api = useMemo(() => ({
    state,
    running,
    finished,
    start: () => engine.start(),
    pause: () => engine.pause(),
    resume: () => engine.resume(),
    skip: () => engine.skip(),
    stop: () => engine.stop(),
    dismissError: () => engine.dismissError(),
    subscribeCursor: engine.subscribeCursor,
    hudHidden,
    hideHud: () => setHudHidden(true),
    showHud: () => setHudHidden(false),
  }), [state, running, finished, engine, hudHidden]);

  return (
    <DemoContext.Provider value={api}>
      {children}
      <DemoOverlay />
    </DemoContext.Provider>
  );
}

/**
 * The Start Demo button.
 *
 * Rendered by the pages that offer to start a tour. It hides itself while the
 * demo is running, because the running demo has its own control bar.
 */
export function StartDemoButton({ className = 'btn btn-secondary', label = 'Start Demo' }) {
  const demo = useDemo();
  const start = useCallback(() => demo?.start(), [demo]);

  if (!demo || demo.running) return null;

  return (
    <button
      type="button"
      className={className}
      onClick={start}
      data-demo-ignore="true"
      title="Play an automatic guided tour of the application"
    >
      <span className="demo-start-dot" aria-hidden="true" />
      {label}
    </button>
  );
}
