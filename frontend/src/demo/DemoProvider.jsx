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

  const running = Boolean(state?.running);
  const finished = Boolean(state?.finished);

  // Escape stops the demo. A presenter whose demo goes wrong on camera needs
  // one key, not a hunt for the right button.
  useEffect(() => {
    if (!running) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); engine.stop(); }
      if (e.key === ' ' && e.target === document.body) {
        e.preventDefault();
        if (state?.paused) engine.resume();
        else engine.pause();
      }
      // Cut a long beat short without losing the demo.
      if (e.key === 'ArrowRight') { e.preventDefault(); engine.skip(); }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [running, state?.paused, engine]);

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
  }), [state, running, finished, engine]);

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
