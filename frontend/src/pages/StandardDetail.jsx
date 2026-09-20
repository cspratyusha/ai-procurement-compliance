import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import { getStandard, getRelated, getAmendments, ApiError } from '../api/client';
import './detail.css';

const SECTOR_LABEL = {
  electrical_cables: 'Electrical cables',
  electrical_installations: 'Electrical installations',
  cement_building_materials: 'Cement & building materials',
  steel_pipes_fittings: 'Steel pipes & fittings',
  structural_steel: 'Structural steel',
  plastic_pipes: 'Plastic pipes',
  ppe: 'Personal protective equipment',
};

const sectorLabel = (slug) => SECTOR_LABEL[slug] ?? (slug || '—').replace(/_/g, ' ');

/** BIS publishes the official record; we link to it rather than reproduce it. */
const bisSearchUrl = (number) =>
  `https://www.bis.gov.in/know-your-standard/?lang=en&q=${encodeURIComponent(number)}`;

export default function StandardDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const decoded = decodeURIComponent(code);

  const [standard, setStandard] = useState(null);
  const [related, setRelated] = useState(null);
  const [amendments, setAmendments] = useState(null);
  const [state, setState] = useState('loading'); // loading | ready | missing | error
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    setError(null);

    getStandard(decoded, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        setStandard(data);
        setState('ready');
        // Secondary: the page is usable without it, so it must not gate render.
        getRelated(data.number, { signal: controller.signal })
          .then((r) => { if (!controller.signal.aborted) setRelated(r); })
          .catch(() => { /* leave the section in its unknown state */ });
        getAmendments(data.number, { signal: controller.signal })
          .then((a) => { if (!controller.signal.aborted) setAmendments(a); })
          .catch(() => { /* leave the section in its unknown state */ });
      })
      .catch((err) => {
        if (controller.signal.aborted || err.name === 'AbortError') return;
        if (err instanceof ApiError && err.status === 404) {
          setState('missing');
        } else {
          setError(err);
          setState('error');
        }
      });

    return () => controller.abort();
  }, [decoded]);

  if (state === 'loading') {
    return (
      <div className="container page" aria-busy="true">
        <div className="stack stack-4">
          <div className="skeleton" style={{ height: 30, width: 220 }} />
          <div className="skeleton" style={{ height: 18, width: '55%' }} />
          <div className="skeleton" style={{ height: 240 }} />
        </div>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="container page">
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load this standard"
            body={error?.message ?? 'The standards engine did not respond.'}
            action={<Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse catalogue</Link>}
          />
        </div>
      </div>
    );
  }

  if (state === 'missing') {
    return (
      <div className="container page">
        <div className="card">
          <EmptyState
            icon="search"
            title="Not in the current corpus"
            body={`${decoded} is not among the standards loaded by the engine. The pilot corpus covers a few sectors only — see the coverage note in the README.`}
            action={<Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse what is covered</Link>}
          />
        </div>
      </div>
    );
  }

  const isSuperseded = standard.status === 'superseded';
  const statusBadge = isSuperseded
    ? { cls: 'badge-crit', icon: 'alert', label: 'Superseded' }
    : { cls: 'badge-ok', icon: 'check', label: 'Current' };

  const basketItem = {
    code: standard.number,
    title: standard.title,
    role: 'primary',
    version: isSuperseded ? 'superseded' : 'latest',
    amendment: standard.last_amended || undefined,
    addedFrom: 'detail page',
  };

  return (
    <div className="container page">
      <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)} style={{ marginBottom: 'var(--s4)' }}>
        <Icon name="chevronLeft" size={14} /> Back
      </button>

      <div className="page-head">
        <div className="stack stack-3" style={{ minWidth: 0 }}>
          <div className="row wrap" style={{ gap: 'var(--s2)' }}>
            <h1 className="mono" style={{ fontSize: 'var(--fs-lg)', fontWeight: 600 }}>{standard.number}</h1>
            <span className={`badge ${statusBadge.cls}`}>
              <Icon name={statusBadge.icon} size={12} />{statusBadge.label}
            </span>
            {standard.category && (
              <span className="badge badge-neutral">{sectorLabel(standard.category)}</span>
            )}
          </div>
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--ink-soft)', maxWidth: '62ch' }}>
            {standard.title}
          </p>
          <span className="xs faint">
            {standard.version || 'Edition not recorded'}
            {standard.last_amended ? ` · amended ${standard.last_amended}` : ''}
          </span>
        </div>

        <div className="row" style={{ gap: 'var(--s2)' }}>
          <a
            href={bisSearchUrl(standard.number)}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary"
          >
            <Icon name="external" size={15} /> Look up on BIS
          </a>
          <AddButton item={basketItem} size="md" />
        </div>
      </div>

      <div className="grid split" style={{ '--rail': '320px' }}>
        <div className="stack stack-4">
          {isSuperseded && (
            <div className="notice notice-warn">
              <Icon name="alert" size={15} />
              <div className="stack stack-2">
                <span className="xs strong">This edition has been superseded</span>
                <span className="xs">
                  Citing it in a live tender risks procuring to a withdrawn specification.
                  Check the BIS record for the current edition before use.
                </span>
              </div>
            </div>
          )}

          <section className="card stack stack-4">
            <span className="eyebrow">Scope</span>
            <p className="small" style={{ color: 'var(--ink-soft)' }}>{standard.scope}</p>
            {standard.description && (
              <>
                <hr className="divider" />
                <div className="stack stack-2">
                  <span className="xs faint">Where it applies</span>
                  <p className="small" style={{ color: 'var(--ink-soft)' }}>{standard.description}</p>
                </div>
              </>
            )}
          </section>

          {standard.keywords?.length > 0 && (
            <section className="card stack stack-3">
              <span className="eyebrow">Indexed terms</span>
              <div className="row wrap" style={{ gap: 5 }}>
                {standard.keywords.map((k) => (
                  <span key={k} className="badge badge-neutral">{k}</span>
                ))}
              </div>
              <p className="xs muted">
                These terms feed the keyword half of the search index.
              </p>
            </section>
          )}

          <section className="card stack stack-4">
            <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
              <span className="eyebrow">Amendments</span>
              {amendments?.count > 0 && (
                <span className="badge badge-warn">{amendments.count} in force</span>
              )}
            </div>

            {amendments === null && <div className="skeleton" style={{ height: 48 }} />}

            {amendments && !amendments.checked && (
              <p className="xs muted">{amendments.note}</p>
            )}

            {amendments?.checked && (
              <>
                <div className="stack stack-2">
                  <span className="xs faint">Cite this standard as</span>
                  <blockquote className="clause xs" style={{ margin: 0 }}>
                    {amendments.citation}
                  </blockquote>
                </div>

                {amendments.amendments.length > 0 ? (
                  <div className="stack stack-2">
                    {amendments.amendments.map((a) => (
                      <div key={a.number} className="row" style={{ gap: 'var(--s3)', alignItems: 'flex-start' }}>
                        <span className="badge badge-neutral mono" style={{ flexShrink: 0 }}>
                          No. {a.number}
                        </span>
                        <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                          <span className="xs">
                            {a.readable_date || 'Date not recorded'}
                            {a.confidence === 'likely' && (
                              <span className="xs faint"> · unconfirmed date</span>
                            )}
                          </span>
                          {a.summary && <span className="xs muted">{a.summary}</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="xs muted">{amendments.note}</p>
                )}
              </>
            )}
          </section>

          <section className="card stack stack-4">
            <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
              <span className="eyebrow">Allied standards</span>
              {related?.total > 0 && (
                <span className="badge badge-neutral">{related.total} related</span>
              )}
            </div>

            {related === null && (
              <div className="skeleton" style={{ height: 60 }} />
            )}

            {related && !related.researched && (
              <p className="xs muted">
                No relationships have been recorded for this standard yet. That is not
                the same as having none — the referred-standards annex has not been
                read for it. Check the standard itself before assuming it stands alone.
              </p>
            )}

            {related?.depends_on?.map((group) => (
              <div key={group.type} className="stack stack-3">
                <div className="stack stack-2">
                  <span className="small strong">{group.heading}</span>
                  {group.explanation && <span className="xs muted">{group.explanation}</span>}
                </div>
                <div className="stack">
                  {group.standards.map((item) =>
                    item.outside_corpus ? (
                      <div key={item.number} className="ref-row" style={{ opacity: 0.72 }}>
                        <Icon name="minus" size={13} />
                        <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                          <span className="row wrap" style={{ gap: 6 }}>
                            <span className="mono xs strong">{item.number}</span>
                            <span className="badge badge-neutral">Not in this corpus</span>
                          </span>
                          <span className="xs faint">{item.title}</span>
                          {item.note && <span className="xs faint">{item.note}</span>}
                        </span>
                      </div>
                    ) : (
                      <Link
                        key={item.number}
                        to={`/app/standard/${encodeURIComponent(item.number)}`}
                        className="ref-row"
                      >
                        <Icon name="chevronRight" size={13} />
                        <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
                          <span className="mono xs strong">{item.number}</span>
                          <span className="xs faint">{item.title}</span>
                          {item.note && <span className="xs faint">{item.note}</span>}
                        </span>
                      </Link>
                    ),
                  )}
                </div>
              </div>
            ))}

            {related?.referenced_by?.length > 0 && (
              <div className="stack stack-3">
                <div className="stack stack-2">
                  <span className="small strong">Referenced by</span>
                  <span className="xs muted">
                    Standards in this corpus that cite {standard.number}.
                  </span>
                </div>
                <div className="stack">
                  {related.referenced_by.map((item) => (
                    <Link
                      key={item.number}
                      to={`/app/standard/${encodeURIComponent(item.number)}`}
                      className="ref-row"
                    >
                      <Icon name="chevronRight" size={13} />
                      <span className="mono xs strong">{item.number}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>

        <div className="stack stack-4">
          <div className="card stack stack-3">
            <span className="eyebrow">Catalogue record</span>
            {[
              ['Internal id', standard.id],
              ['Status', statusBadge.label],
              ['Edition', standard.version || '—'],
              ['Latest amendment', standard.last_amended || 'None recorded'],
              ['Sector', sectorLabel(standard.category)],
            ].map(([k, v]) => (
              <div key={k} className="stack stack-2">
                <span className="xs faint">{k}</span>
                <span className="small mono">{v}</span>
              </div>
            ))}
          </div>

          <div className="card stack stack-3">
            <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
              <span className="eyebrow">Certification</span>
              <span className="badge badge-neutral">Not yet built</span>
            </div>
            <p className="xs muted">
              Mandatory certification requirements (BIS Product Certification / ISI mark,
              CRS, Hallmarking) are not yet mapped in this dataset. Check the official
              compulsory-certification lists on the BIS site before relying on a tender.
            </p>
            <a
              href="https://www.bis.gov.in/product-certification/products-under-compulsory-certification/"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary btn-sm"
            >
              <Icon name="external" size={14} /> BIS compulsory certification
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
