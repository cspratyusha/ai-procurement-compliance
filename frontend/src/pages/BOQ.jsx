import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { useSpec } from '../state/SpecStore';
import { BOQ_ITEMS, BANDS, STANDARD_DETAIL } from '../data/catalogue';

/**
 * Workflow B — full document analysis.
 * Upload → detected line items → per-item recommendations → consolidated export.
 * The officer can leave and come back, so progress is explicit and resumable.
 */
export default function BOQ() {
  const spec = useSpec();
  const [phase, setPhase] = useState('idle');   // idle | parsing | working
  const [items, setItems] = useState(BOQ_ITEMS);
  const [openItem, setOpenItem] = useState('li1');
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const upload = () => {
    setPhase('parsing');
    timer.current = setTimeout(() => setPhase('working'), 2000);
  };

  const parsed = items.filter((i) => i.parsed);
  const unparsed = items.filter((i) => !i.parsed);
  const done = items.filter((i) => i.status === 'accepted').length;
  const pct = parsed.length ? Math.round((done / parsed.length) * 100) : 0;

  const accept = (item) => {
    spec.addMany(
      item.standards.map((code) => ({
        code,
        title: STANDARD_DETAIL[code]?.title || code,
        role: STANDARD_DETAIL[code]?.role || 'primary',
        version: 'latest',
        addedFrom: `BOQ item ${item.sr}`,
      }))
    );
    setItems((p) => p.map((i) => (i.id === item.id ? { ...i, status: 'accepted' } : i)));
    const next = parsed.find((i) => i.status === 'pending' && i.id !== item.id);
    setOpenItem(next?.id || null);
  };

  const skip = (item) =>
    setItems((p) => p.map((i) => (i.id === item.id ? { ...i, status: 'skipped' } : i)));

  if (phase === 'idle') {
    return (
      <div className="container page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Upload tender or BOQ</h1>
            <p className="page-sub">
              Drop a full tender document or bill of quantities. Each line item is detected and
              matched separately, then exported as one consolidated specification.
            </p>
          </div>
        </div>
        <div className="card">
          <div className="dropzone">
            <span className="dropzone-icon"><Icon name="upload" size={26} strokeWidth={1.4} /></span>
            <p className="strong">Drop a tender, BOQ or spec file</p>
            <p className="small muted" style={{ maxWidth: '46ch' }}>
              PDF, DOCX or XLSX. Scanned documents are processed with OCR — pages that cannot be
              read reliably are reported rather than guessed at.
            </p>
            <button className="btn btn-primary" onClick={upload} style={{ marginTop: 'var(--s3)' }}>
              Select file
            </button>
            <p className="xs faint" style={{ marginTop: 'var(--s2)' }}>
              Demo build — loads a sample 6-line BOQ.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (phase === 'parsing') {
    return (
      <div className="container page">
        <div className="card stack stack-5" aria-live="polite">
          <div className="row" style={{ gap: 'var(--s3)' }}>
            <Icon name="file" size={18} />
            <span className="small strong grow">Tender_Electrical_Works_2026.xlsx</span>
            <span className="spinner" />
          </div>
          <div className="stack stack-3">
            {['Reading document structure', 'Detecting line items', 'Extracting product attributes per item', 'Matching standards for each item'].map((s) => (
              <div key={s} className="row" style={{ gap: 'var(--s3)' }}>
                <div className="skeleton" style={{ width: 14, height: 14, borderRadius: '50%' }} />
                <span className="small muted">{s}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Tender_Electrical_Works_2026.xlsx</h1>
          <p className="page-sub">
            {items.length} line items detected · {parsed.length} matched · {unparsed.length} need manual entry.
            Work through them in any order — progress is saved.
          </p>
        </div>
        <Link to="/app/builder" className="btn btn-primary">
          Consolidated spec ({spec.count})
          <Icon name="arrowRight" size={15} />
        </Link>
      </div>

      <div className="stack stack-4">
        <div className="li-progress">
          <span className="xs faint nowrap">Progress</span>
          <div className="meter grow" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Line items reviewed">
            <div className="meter-fill" style={{ width: `${pct}%`, background: 'var(--ok)' }} />
          </div>
          <span className="xs tabular strong nowrap">{done} of {parsed.length}</span>
        </div>

        {unparsed.length > 0 && (
          <div className="notice notice-warn">
            <Icon name="alert" size={15} />
            <div className="stack stack-2">
              <span className="xs strong">{unparsed.length} line items could not be parsed</span>
              <span className="xs">
                These are listed below with the reason. They are not silently dropped — an
                unreadable line is reported so it can be entered by hand.
              </span>
            </div>
          </div>
        )}

        {parsed.map((item) => {
          const band = item.band ? BANDS[item.band] : null;
          const open = openItem === item.id;
          const accepted = item.status === 'accepted';
          const skipped = item.status === 'skipped';

          return (
            <article key={item.id} className={`li-row ${accepted ? 'is-done' : ''}`} style={{ flexDirection: 'column', gap: 'var(--s3)' }}>
              <div className="row" style={{ width: '100%', alignItems: 'flex-start', gap: 'var(--s4)' }}>
                <span className="li-sr tabular">{item.sr}</span>

                <div className="stack stack-2 grow" style={{ minWidth: 0 }}>
                  <span className="small strong">{item.text}</span>
                  <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                    <span className="xs faint">{item.qty}</span>
                    {item.category && <span className="badge badge-neutral">{item.category}</span>}
                    {band && <span className={`badge ${band.cls}`}>{band.label}</span>}
                    {accepted && <span className="badge badge-ok"><Icon name="check" size={11} />Accepted</span>}
                    {skipped && <span className="badge badge-neutral">Skipped</span>}
                  </div>
                </div>

                <button
                  className="btn btn-ghost btn-sm nowrap"
                  onClick={() => setOpenItem(open ? null : item.id)}
                  aria-expanded={open}
                >
                  <Icon name={open ? 'chevronDown' : 'chevronRight'} size={14} />
                  {item.standards.length} standard{item.standards.length === 1 ? '' : 's'}
                </button>
              </div>

              {open && (
                <div className="stack stack-3 fade-in" style={{ width: '100%', paddingLeft: 42 }}>
                  <div className="stack stack-2">
                    {item.standards.map((code) => {
                      const det = STANDARD_DETAIL[code];
                      return (
                        <div key={code} className="row" style={{ gap: 'var(--s3)', padding: 'var(--s2) var(--s3)', border: '1px solid var(--line)', borderRadius: 'var(--r)' }}>
                          <span className="mono xs strong nowrap">{code}</span>
                          <span className="xs muted grow">{det?.title || 'Catalogue record'}</span>
                          {det && (
                            <Link to={`/app/standard/${encodeURIComponent(code)}`} className="btn btn-ghost btn-sm">
                              Detail
                            </Link>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {!accepted && (
                    <div className="row" style={{ gap: 'var(--s2)' }}>
                      <button className="btn btn-primary btn-sm" onClick={() => accept(item)}>
                        <Icon name="check" size={14} /> Accept and add to spec
                      </button>
                      <button className="btn btn-secondary btn-sm" onClick={() => skip(item)}>
                        Skip this item
                      </button>
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}

        {unparsed.map((item) => (
          <article key={item.id} className="li-row is-unparsed">
            <span className="li-sr tabular">{item.sr}</span>
            <div className="stack stack-3 grow" style={{ minWidth: 0 }}>
              <span className="small" style={{ color: 'var(--ink-muted)' }}>{item.text}</span>
              <div className="notice notice-warn">
                <Icon name="alert" size={14} />
                <span className="xs">{item.reason}</span>
              </div>
              <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                <Link to="/app/query" className="btn btn-secondary btn-sm">
                  Enter manually
                </Link>
                <button className="btn btn-ghost btn-sm">Re-upload page</button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
