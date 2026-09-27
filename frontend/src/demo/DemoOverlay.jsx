/**
 * Everything Demo Mode draws on screen.
 *
 * One fixed, pointer-events-none layer above the application: the synthetic
 * cursor, the spotlight ring, the dim veil, the narration panel, the control
 * bar and the progress indicator. It reads demo state and renders it, no
 * logic about the sequence lives here.
 *
 * Nothing in this file renders at all when the demo has never run, so the
 * normal application carries no overlay, no listeners and no extra paint.
 */

import { useDemo } from './useDemo';

/** The pointer itself, an arrow drawn to read as a real macOS/Windows cursor. */
function DemoCursor({ cursor }) {
  if (!cursor?.visible) return null;

  return (
    <div
      className={`demo-cursor ${cursor.pressing ? 'is-pressing' : ''}`}
      style={{ transform: `translate3d(${cursor.x}px, ${cursor.y}px, 0)` }}
      aria-hidden="true"
    >
      <span className="demo-cursor-glow" />
      <svg width="26" height="26" viewBox="0 0 26 26" className="demo-cursor-arrow">
        {/* Outline first, fill over it, legible on any background. */}
        <path
          d="M5 2.2 L5 19.4 L9.7 15.1 L12.6 22.4 L16.1 20.9 L13.2 13.8 L19.6 13.4 Z"
          fill="#ffffff"
          stroke="rgba(20,18,14,0.55)"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path
          d="M6.4 5.2 L6.4 16.4 L9.9 13.2 L12.5 19.8 L14.2 19.1 L11.5 12.5 L16.4 12.2 Z"
          fill="#1b1a17"
        />
      </svg>
    </div>
  );
}

/** Bytes as a short human string, for the file row. */
function readableSize(bytes) {
  if (!Number.isFinite(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * The demo's own file chooser.
 *
 * A browser will not let script open the real file picker, so a silent upload
 * gives a viewer a filename with no visible cause. This panel supplies the
 * missing beat: the cursor moves onto the file, selects it, and clicks Open.
 *
 * It is labelled as the demo's own panel rather than styled to impersonate the
 * operating system's dialog, a viewer should never be misled about which part
 * of what they are watching is the product.
 */
function DemoFilePicker({ picker }) {
  if (!picker) return null;

  return (
    <div className={`demo-picker ${picker.opening ? 'is-opening' : ''}`} role="presentation">
      <div className="demo-picker-bar">
        <span className="demo-picker-title">Choose a file</span>
        <span className="demo-picker-tag">Recording</span>
      </div>

      <div className="demo-picker-body">
        <p className="demo-picker-path">Documents / Tenders / 2026</p>

        <div
          className={`demo-picker-row ${picker.selected ? 'is-selected' : ''}`}
          data-demo-target="demo-picker-file"
        >
          <svg width="26" height="30" viewBox="0 0 26 30" aria-hidden="true">
            <path
              d="M3 1h13l7 7v21a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1Z"
              fill="#fff" stroke="rgba(20,18,14,.35)" strokeWidth="1.2"
            />
            <path d="M16 1v7h7" fill="none" stroke="rgba(20,18,14,.35)" strokeWidth="1.2" />
          </svg>
          <span className="demo-picker-meta">
            <span className="demo-picker-name">{picker.name}</span>
            <span className="demo-picker-size">{readableSize(picker.size)}</span>
          </span>
        </div>
      </div>

      <div className="demo-picker-foot">
        <span className="demo-picker-cancel">Cancel</span>
        <span
          className={`demo-picker-open ${picker.selected ? 'is-ready' : ''}`}
          data-demo-target="demo-picker-open"
        >
          Open
        </span>
      </div>
    </div>
  );
}

export default function DemoOverlay() {
  const demo = useDemo();
  const state = demo?.state;

  // Never rendered before the first run, the idle app is untouched.
  if (!state || (!state.running && !state.finished && !state.error)) return null;

  const {
    cursor, ripple, spotlight, caption, picker, running, paused, finished, error,
  } = state;

  // Progress is counted in acts, the captioned chapters a viewer sees go by
  // not in engine steps, which advance unevenly and mean nothing to them.
  const done = Math.min(state.act ?? 0, state.total);
  const pct = state.total ? Math.round((done / state.total) * 100) : 0;

  return (
    <div className="demo-layer" data-demo-ignore="true">
      {/* Dim veil + spotlight cut-out. Two box-shadows make the hole:
          a huge spread shadow darkens everything outside the ring. */}
      {running && (
        <div className={`demo-veil ${spotlight ? 'has-focus' : ''}`}>
          {spotlight && (
            <div
              className="demo-spotlight"
              style={{
                top: spotlight.top,
                left: spotlight.left,
                width: spotlight.width,
                height: spotlight.height,
                borderRadius: spotlight.radius,
              }}
            />
          )}
        </div>
      )}

      {/* The file chooser sits above the veil, so it is never dimmed. */}
      {running && <DemoFilePicker picker={picker} />}

      {/* The click ripple, anchored where the press landed. */}
      {ripple && (
        <span
          key={ripple.id}
          className="demo-ripple"
          style={{ top: ripple.y, left: ripple.x }}
          aria-hidden="true"
        />
      )}

      <DemoCursor cursor={cursor} />

      {/* Narration */}
      {running && caption && (
        <div className="demo-caption" role="status" aria-live="polite">
          {caption.act && <p className="demo-caption-act">{caption.act}</p>}
          <p className="demo-caption-text">{caption.text}</p>
          {caption.sub && <p className="demo-caption-sub">{caption.sub}</p>}
          {caption.detail && <p className="demo-caption-detail">{caption.detail}</p>}
        </div>
      )}

      {/* Indicator + controls. The only interactive part of the overlay. */}
      {running && (
        <div className="demo-hud">
          <div className="demo-hud-head">
            <span className={`demo-badge ${paused ? 'is-paused' : ''}`}>
              <span className="demo-badge-dot" aria-hidden="true" />
              {paused ? 'Recording Paused' : 'Recording'}
            </span>
            <span className="demo-hud-step">
              {done} / {state.total}
            </span>
          </div>

          <div className="demo-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <span className="demo-progress-fill" style={{ width: `${pct}%` }} />
          </div>

          <div className="demo-hud-actions">
            {paused ? (
              <button type="button" className="demo-btn is-primary" onClick={demo.resume}>
                Resume
              </button>
            ) : (
              <button type="button" className="demo-btn" onClick={demo.pause}>
                Pause
              </button>
            )}
            <button
              type="button"
              className="demo-btn"
              onClick={demo.skip}
              title="Cut the current pause short"
            >
              Skip
            </button>
            <button type="button" className="demo-btn is-stop" onClick={demo.stop}>
              Stop
            </button>
          </div>
          <p className="demo-hud-hint">Space pauses · → skips · Esc stops</p>
        </div>
      )}

      {/* Completion card */}
      {finished && (
        <div className="demo-toast is-done" role="status">
          <div className="demo-toast-body">
            <strong>Demo complete</strong>
            <span>
              That is the whole path, query, upload, assemble, freeze, audit.
              The application is yours again.
            </span>
          </div>
          <div className="demo-toast-actions">
            <button type="button" className="demo-btn is-primary" onClick={demo.start}>
              Replay
            </button>
            <button type="button" className="demo-btn" onClick={demo.dismissError}>
              Close
            </button>
          </div>
        </div>
      )}

      {/* Failure card. The demo stops, the app keeps working, and the message
          names the step so the sequence can be fixed. */}
      {error && (
        <div className="demo-toast is-error" role="alert">
          <div className="demo-toast-body">
            <strong>Demo Mode stopped</strong>
            <span>{error}</span>
            <span className="demo-toast-note">
              The application itself is unaffected, carry on normally.
            </span>
          </div>
          <div className="demo-toast-actions">
            <button type="button" className="demo-btn is-primary" onClick={demo.start}>
              Try again
            </button>
            <button type="button" className="demo-btn" onClick={demo.dismissError}>
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
