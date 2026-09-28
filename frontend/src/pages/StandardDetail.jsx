import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { AddButton } from '../components/SpecBasket';
import { CertificationBadge } from '../components/CertificationBadge';
import { getStandard, getRelated, getAmendments, getCertification, ApiError } from '../api/client';
import './detail.css';
import { sectorLabel as labelFor } from '../data/sectors';

const sectorLabel = (slug) => labelFor(slug, '–');

/** BIS publishes the official record; we link to it rather than reproduce it. */
const bisSearchUrl = (number) =>
  `https://www.bis.gov.in/know-your-standard/?lang=en&q=${encodeURIComponent(number)}`;

/**
 * The sidebar's one-line summary, read from the same amendment record as the
 * Amendments card so the two never disagree.
 */
function latestAmendment(amendments, standard) {
  if (!amendments) return standard.last_amended || '…';
  if (!amendments.checked) return 'Not checked';
  if (!amendments.count) return 'None';
  const last = amendments.amendments[amendments.amendments.length - 1];
  const dated = [...amendments.amendments].reverse().find((a) => a.readable_date);
  if (last && dated && dated.number === last.number) return `No. ${last.number}, ${dated.readable_date}`;
  return `No. ${amendments.count}${dated ? ` (latest dated: No. ${dated.number}, ${dated.readable_date})` : ''}`;
}

/** One allied standard: linked when the corpus holds it, flagged when not. */
function RefRow({ item }) {
  const evidence = item.evidence ? `Read from the standard's text: "${item.evidence}"` : undefined;
  const body = (
    <span className="stack stack-2 grow" style={{ minWidth: 0 }}>
      <span className="row wrap" style={{ gap: 6 }}>
        <span className="mono xs strong">{item.number}</span>
        {item.outside_corpus && <span className="badge badge-neutral">Not in this corpus</span>}
        {item.status === 'superseded' && <span className="badge badge-warn">Superseded</span>}
        {item.method === 'extracted' && <span className="ref-source" title={evidence}>from text</span>}
        {item.method === 'similar_scope' && (
          <span className="ref-source" title="Found by comparing scope text. This standard does not cite it.">
            similar scope
          </span>
        )}
      </span>
      {item.title
        ? <span className="xs faint">{item.title}</span>
        : item.evidence && <span className="xs faint ref-evidence">&ldquo;{item.evidence}&rdquo;</span>}
      {item.note && <span className="xs faint">{item.note}</span>}
    </span>
  );

  if (item.outside_corpus) {
    return (
      <div className="ref-row is-outside" title={evidence}>
        <Icon name="minus" size={13} />
        {body}
      </div>
    );
  }
  return (
    <Link to={`/app/standard/${encodeURIComponent(item.number)}`} className="ref-row" title={evidence}>
      <Icon name="chevronRight" size={13} />
      {body}
    </Link>
  );
}

/** Long reference lists (a code can cite 80 standards) collapse after a dozen. */
function CollapsibleList({ items, render, initial = 12 }) {
  const [open, setOpen] = useState(false);
  const shown = open ? items : items.slice(0, initial);
  return (
    <div className="stack">
      {shown.map(render)}
      {items.length > initial && (
        <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setOpen((v) => !v)}>
          {open ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
    </div>
  );
}

export default function StandardDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const decoded = decodeURIComponent(code);

  const [standard, setStandard] = useState(null);
  const [related, setRelated] = useState(null);
  const [amendments, setAmendments] = useState(null);
  const [certification, setCertification] = useState(null);   // null while loading, { failed } on error
  const [state, setState] = useState('loading'); // loading | ready | missing | error
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    setError(null);
    setCertification(null);

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
        getCertification(data.number, { signal: controller.signal })
          .then((c) => { if (!controller.signal.aborted) setCertification(c); })
          .catch(() => { if (!controller.signal.aborted) setCertification({ failed: true }); });
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
            body={`${decoded} is not among the standards loaded by the engine. It may be newer than the published archive the corpus was built from.`}
            action={<Link to="/app/catalogue" className="btn btn-secondary btn-sm">Browse what is covered</Link>}
          />
        </div>
      </div>
    );
  }

  const isSuperseded = standard.status === 'superseded';
  const statusBadge = isSuperseded
    ? { cls: 'badge-crit', icon: 'alert', label: standard.withdrawn ? 'Withdrawn' : 'Superseded' }
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
            <h1
              className="mono"
              data-demo-target="detail-title"
              style={{ fontSize: 'var(--fs-lg)', fontWeight: 600 }}
            >
              {standard.number}
            </h1>
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
                <span className="xs strong">
                  {standard.withdrawn
                    ? (standard.superseded_by_number
                      ? (standard.replacement_source === 'bis_newer_edition'
                        ? 'Withdrawn by BIS; a newer edition is in force'
                        : 'Withdrawn by BIS and replaced')
                      : 'Withdrawn by BIS; no replacement named')
                    : 'This edition has been superseded'}
                </span>
                <span className="xs">
                  {standard.superseded_by_number ? (
                    <>
                      {standard.replacement_source === 'bis_newer_edition' ? (
                        <>
                          BIS&rsquo;s record for this edition names no replacement, but BIS lists{' '}
                          <Link to={`/app/standard/${encodeURIComponent(standard.superseded_by_number)}`} className="mono strong">
                            {standard.superseded_by_number}
                          </Link>{' '}
                          as the edition in force. Cite it instead.
                        </>
                      ) : (
                        <>
                          Cite{' '}
                          <Link to={`/app/standard/${encodeURIComponent(standard.superseded_by_number)}`} className="mono strong">
                            {standard.superseded_by_number}
                          </Link>{' '}
                          instead{standard.status_source === 'bis' ? ', according to BIS’s record for this edition' : ''}.
                        </>
                      )}
                      {' '}If the catalogue does not hold that edition, check its requirements on BIS before citing it.
                    </>
                  ) : standard.withdrawn ? (
                    <>
                      BIS&rsquo;s record names no replacement, and BIS lists no newer edition
                      {standard.withdrawal_note ? ` (BIS: ${standard.withdrawal_note})` : ''}. A withdrawn
                      standard cannot be enforced as a requirement: specify it directly or find a current
                      standard that covers it. Standards BIS published after October 2025 are on its new
                      portal and not in these records, so check there too.
                    </>
                  ) : (
                    'Citing it in a live tender risks procuring to a withdrawn specification. Check the BIS record for the current edition before use.'
                  )}
                </span>
              </div>
            </div>
          )}

          <section className="card stack stack-4">
            <span className="eyebrow">Scope</span>
            {standard.scope ? (
              <>
                <p className="small" style={{ color: 'var(--ink-soft)' }}>{standard.scope}</p>
                {standard.provenance === 'scope_written' && (
                  <p className="xs muted" data-testid="scope-written-note">
                    A summary written for this catalogue, not the standard&rsquo;s own scope clause. Its
                    number and title are checked against BIS&rsquo;s record; read the published standard
                    for the exact scope before relying on it for a tender.
                  </p>
                )}
              </>
            ) : (
              <p className="small muted">
                This standard is held on its number and official title only: its scope text is not in
                the catalogue, so it is found by its title alone. Read the published standard before
                relying on it for a tender.
              </p>
            )}
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
                <span className="badge badge-warn">
                  {amendments.status === 'found_in_text'
                    ? `At least ${amendments.count}`
                    : amendments.status === 'official' ? `${amendments.count} issued` : `${amendments.count} in force`}
                </span>
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
                            {a.readable_date || (a.confidence === 'implied'
                              ? 'Known from a later amendment; date not in the copy'
                              : a.confidence === 'listed_by_bis' ? 'Listed by BIS; date not in the sources read' : 'Date not recorded')}
                            {a.confidence === 'likely' && (
                              <span className="xs faint"> · unconfirmed date</span>
                            )}
                          </span>
                          {a.summary && <span className="xs muted amend-excerpt">{a.summary}</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
                <p className="xs muted">{amendments.note}</p>
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
                the same as having none: its text has not been read for citations.
                Check the standard itself before assuming it stands alone.
              </p>
            )}

            {related?.researched && related.total === 0 && related.text_read && (
              <p className="xs muted">
                The text of {standard.number} was read and cites no other Indian Standard.
              </p>
            )}

            {related?.depends_on?.map((group) => (
              <div key={group.type} className="stack stack-3">
                <div className="stack stack-2">
                  <span className="small strong">
                    {group.heading} <span className="faint">· {group.standards.length}</span>
                  </span>
                  {group.explanation && <span className="xs muted">{group.explanation}</span>}
                </div>
                <CollapsibleList
                  items={group.standards}
                  render={(item) => <RefRow key={item.number} item={item} />}
                />
              </div>
            ))}

            {related?.referenced_by?.length > 0 && (
              <div className="stack stack-3">
                <div className="stack stack-2">
                  <span className="small strong">
                    Referenced by <span className="faint">· {related.referenced_by_total ?? related.referenced_by.length}</span>
                  </span>
                  <span className="xs muted">
                    Standards in this corpus that cite {standard.number}.
                    {related.referenced_by_total > related.referenced_by.length &&
                      ` Showing the first ${related.referenced_by.length} of ${related.referenced_by_total.toLocaleString('en-IN')}.`}
                  </span>
                </div>
                <CollapsibleList
                  items={related.referenced_by}
                  render={(item) => <RefRow key={item.number} item={item} />}
                />
              </div>
            )}

            {related?.text_read && related.total > 0 && (
              <p className="xs faint">
                Links marked <em>from text</em> were read automatically from the standards&rsquo;
                own reference clauses and citations; hover one to see the passage. The text is OCR
                of a scanned document, so check a link against the standard before relying on it.
              </p>
            )}
          </section>
        </div>

        <div className="stack stack-4">
          <div className="card stack stack-3">
            <span className="eyebrow">Catalogue record</span>
            {[
              ['Internal id', standard.id],
              ['Status', statusBadge.label],
              ['Edition', standard.version || '–'],
              ['Latest amendment', latestAmendment(amendments, standard)],
              ['Sector', sectorLabel(standard.category)],
            ].map(([k, v]) => (
              <div key={k} className="stack stack-2">
                <span className="xs faint">{k}</span>
                <span className="small mono">{v}</span>
              </div>
            ))}
          </div>

          <div className="card stack stack-3" data-demo-target="detail-certification">
            <div className="row-between wrap" style={{ gap: 'var(--s2)' }}>
              <span className="eyebrow">Certification</span>
              {certification && !certification.failed && <CertificationBadge certification={certification} />}
            </div>

            {certification === null && <div className="skeleton" style={{ height: 48 }} />}

            {certification?.failed && (
              <p className="xs muted">
                The certification status could not be loaded. That is not a clearance: check
                BIS&rsquo;s compulsory-certification lists before relying on a tender.
              </p>
            )}

            {certification && !certification.failed && (
              <>
                <p className="xs">{certification.explanation}</p>
                {certification.qco && (
                  <span className="xs">
                    <strong>Order:</strong>{' '}
                    {certification.qco_url
                      ? <a href={certification.qco_url} target="_blank" rel="noopener noreferrer">{certification.qco}</a>
                      : certification.qco}
                    {certification.gazette ? ` (${certification.gazette})` : ''}
                  </span>
                )}
                {certification.products?.length > 0 && (
                  <span className="xs muted">
                    <strong>Products as BIS lists them:</strong> {certification.products.join('; ')}
                  </span>
                )}
                {certification.related?.length > 0 && (
                  <span className="xs">
                    <strong>Listed instead:</strong>{' '}
                    {certification.related.map((n, i) => (
                      <span key={n}>
                        {i > 0 && ', '}
                        <Link to={`/app/certification/${encodeURIComponent(n)}`} className="mono">{n}</Link>
                      </span>
                    ))}
                  </span>
                )}
                <Link
                  to={`/app/certification/${encodeURIComponent(certification.listed_as || standard.number)}`}
                  className="btn btn-secondary btn-sm"
                >
                  <Icon name="shield" size={14} /> Open in Certification
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
