import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { EmptyState } from '../components/Primitives';
import { getCorpusHealth, getStats, getAlerts, ApiError } from '../api/client';
import './query.css';   // .notice — shared with the query screen

/**
 * Corpus health — how complete the data the engine serves actually is.
 *
 * This screen was a compliance dashboard: six-month gap trends, tender
 * compliance percentages, and a per-department table with rates like 95.8%.
 * All of it was invented, and none of it could be made real — those figures
 * need a tender auditor and user accounts, neither of which is built. They
 * were removed rather than relabelled.
 *
 * What is here instead is the question this project can actually answer, and
 * it is arguably the more useful one for a standards body: not "how compliant
 * are our tenders" but "how much of this corpus do we actually know things
 * about". Every figure is a count over records that exist.
 *
 * The ratio is the honest unit throughout. Thirteen confirmed certification
 * records is meaningless alone; thirteen out of forty-five, with twenty-eight
 * unverified, is a statement someone can act on. So researched counts are
 * always rendered against the total they are out of, and the unverified
 * remainder is never styled as if it were a pass.
 */

const readVar = (name, fallback) => {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

const SECTOR_ACRONYMS = { ppe: 'PPE' };
function sectorLabel(key) {
  if (!key) return 'Uncategorised';
  if (SECTOR_ACRONYMS[key]) return SECTOR_ACRONYMS[key];
  return key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      <span className="xs strong">{label}</span>
      {payload.map((p) => (
        <span key={p.dataKey} className="xs muted">
          {p.name}: <span className="strong tabular" style={{ color: p.color }}>{p.value}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * A count against the total it is out of.
 *
 * `tone` colours the bar but never the label: a low certification-coverage
 * figure is a fact about research effort, not a failure, and colouring it red
 * would editorialise data that is simply incomplete.
 */
function CoverageBar({ label, value, total, tone = 'var(--ink)', hint }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="stack stack-2">
      <div className="row-between">
        <span className="small">{label}</span>
        <span className="small tabular strong">
          {value.toLocaleString('en-IN')}
          <span className="xs faint"> / {total.toLocaleString('en-IN')}</span>
        </span>
      </div>
      <div
        className="meter"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={label}
      >
        <div className="meter-fill" style={{ width: `${pct}%`, background: tone }} />
      </div>
      {hint && <span className="xs faint">{hint}</span>}
    </div>
  );
}

export default function Compliance() {
  const [state, setState] = useState('loading'); // loading | ready | error
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    Promise.all([
      getCorpusHealth({ signal }),
      getStats({ signal }),
      getAlerts({ signal }),
    ])
      .then(([h, s, a]) => {
        setHealth(h);
        setStats(s);
        setAlerts(a);
        setState('ready');
      })
      .catch((err) => {
        if (signal.aborted) return;
        setError(err instanceof ApiError ? err : new ApiError('Could not load corpus health.'));
        setState('error');
      });

    return () => controller.abort();
  }, []);

  const ink = readVar('--ink', '#171717');
  const axis = readVar('--ink-faint', '#94938D');
  const grid = readVar('--line', '#E3E1DC');

  const axisProps = {
    stroke: axis,
    tick: { fill: axis, fontSize: 11 },
    tickLine: false,
    axisLine: { stroke: grid },
  };

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1 className="page-title" data-demo-target="compliance-title">Corpus health</h1>
          <p className="page-sub">
            How complete the data behind the engine is — what has been researched, and
            what has not. Every figure is a count over records that exist.
          </p>
        </div>
        <Link to="/app/alerts" className="btn btn-secondary">
          <Icon name="alert" size={15} />
          Standards hygiene
        </Link>
      </div>

      {state === 'loading' && (
        <div className="stack stack-3" aria-busy="true">
          <div className="grid grid-4">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 96 }} />)}
          </div>
          <div className="skeleton" style={{ height: 260 }} />
        </div>
      )}

      {state === 'error' && (
        <div className="card">
          <EmptyState
            icon="alert"
            title="Could not load corpus health"
            body={
              `${error?.message ?? 'The standards engine did not respond.'} ` +
              'No figures are shown rather than stale or invented ones.'
            }
            action={
              <button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
                Retry
              </button>
            }
          />
        </div>
      )}

      {state === 'ready' && (
        <div className="stack stack-5">
          <section className="grid grid-4">
            <div className="card stack stack-3">
              <span className="xs faint">Standards served</span>
              <span className="tabular" style={{ fontSize: 'var(--fs-xl)', fontWeight: 600, letterSpacing: '-0.03em' }}>
                {health.corpus_size.toLocaleString('en-IN')}
              </span>
              <span className="xs muted">Across {health.sectors.length} sectors</span>
            </div>
            <div className="card stack stack-3">
              <span className="xs faint">Active editions</span>
              <span className="tabular" style={{ fontSize: 'var(--fs-xl)', fontWeight: 600, letterSpacing: '-0.03em' }}>
                {health.active.toLocaleString('en-IN')}
              </span>
              <span className="xs muted">{health.superseded} marked superseded</span>
            </div>
            <div className="card stack stack-3">
              <span className="xs faint">Needs attention</span>
              <span
                className="tabular"
                style={{
                  fontSize: 'var(--fs-xl)', fontWeight: 600, letterSpacing: '-0.03em',
                  color: alerts.critical_count > 0 ? 'var(--crit)' : undefined,
                }}
              >
                {alerts.critical_count}
              </span>
              <span className="xs muted">Superseded, replacement known</span>
            </div>
            <div className="card stack stack-3">
              <span className="xs faint">Searches served</span>
              <span className="tabular" style={{ fontSize: 'var(--fs-xl)', fontWeight: 600, letterSpacing: '-0.03em' }}>
                {stats.queries_total.toLocaleString('en-IN')}
              </span>
              <span className="xs muted">
                {stats.no_match_queries} outside coverage
              </span>
            </div>
          </section>

          <section className="grid split" style={{ '--rail': '1fr' }}>
            <div className="card card-flush">
              <div className="card-head">
                <div className="stack stack-2">
                  <h2 className="card-title">Metadata coverage</h2>
                  <span className="xs faint">
                    Counted against the {health.corpus_size.toLocaleString('en-IN')} standards served
                  </span>
                </div>
              </div>
              <div className="card-body stack stack-4">
                <CoverageBar
                  label="Certification confirmed"
                  value={health.certification_mandatory}
                  total={health.corpus_size}
                  tone="var(--ok)"
                  hint="A mandatory BIS scheme positively confirmed against a QCO"
                />
                <CoverageBar
                  label="Certification not verified"
                  value={health.certification_not_verified}
                  total={health.corpus_size}
                  tone="var(--warn)"
                  hint="Status unknown — explicitly not a clearance"
                />
                <CoverageBar
                  label="Amendments researched"
                  value={health.amendments_researched}
                  total={health.corpus_size}
                  tone="var(--info)"
                  hint={`${health.amendments_total} published amendments recorded across them`}
                />
                <hr className="divider" />
                <p className="xs muted">
                  Certification and amendment research was done when the corpus was smaller
                  and did not scale with it. A standard with no record has not been checked,
                  which is not a statement that it is clean — the engine reports this
                  per-record rather than implying coverage it does not have.
                </p>
              </div>
            </div>

            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Standards by sector</h2>
              </div>
              <div className="card-body">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={health.sectors.slice(0, 8).map((s) => ({
                      ...s, label: sectorLabel(s.category),
                    }))}
                    layout="vertical"
                    margin={{ top: 0, right: 16, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid stroke={grid} horizontal={false} />
                    <XAxis type="number" {...axisProps} allowDecimals={false} />
                    <YAxis type="category" dataKey="label" width={130} {...axisProps} />
                    <Tooltip
                      content={<ChartTooltip />}
                      cursor={{ fill: readVar('--surface-hover', '#EFEEEA') }}
                    />
                    <Bar dataKey="standards" name="Standards" radius={[0, 2, 2, 0]} maxBarSize={18}>
                      {health.sectors.slice(0, 8).map((_, i) => (
                        <Cell key={i} fill={ink} fillOpacity={1 - i * 0.09} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          <section className="grid split" style={{ '--rail': '1fr' }}>
            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Most-searched sectors</h2>
                <span className="xs faint">From served searches</span>
              </div>
              {stats.categories.length === 0 ? (
                <div className="card-body">
                  <EmptyState
                    icon="search"
                    title="No searches recorded yet"
                    body="This ranks sectors by the top result of each search the engine serves."
                  />
                </div>
              ) : (
                <div className="card-body">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={stats.categories.map((c) => ({
                        ...c, label: sectorLabel(c.category),
                      }))}
                      layout="vertical"
                      margin={{ top: 0, right: 16, left: 8, bottom: 0 }}
                    >
                      <CartesianGrid stroke={grid} horizontal={false} />
                      <XAxis type="number" {...axisProps} allowDecimals={false} />
                      <YAxis type="category" dataKey="label" width={130} {...axisProps} />
                      <Tooltip
                        content={<ChartTooltip />}
                        cursor={{ fill: readVar('--surface-hover', '#EFEEEA') }}
                      />
                      <Bar dataKey="queries" name="Searches" radius={[0, 2, 2, 0]} maxBarSize={18}>
                        {stats.categories.map((_, i) => (
                          <Cell key={i} fill={readVar('--accent', '#7A6A4F')} fillOpacity={1 - i * 0.11} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className="card card-flush">
              <div className="card-head">
                <h2 className="card-title">Where the gaps are</h2>
              </div>
              <div className="card-body stack stack-4">
                <div className="stack stack-2">
                  <div className="row-between">
                    <span className="small">Searches outside coverage</span>
                    <span className="small tabular strong">{stats.no_match_queries.toLocaleString('en-IN')}</span>
                  </div>
                  <span className="xs faint">
                    Queries the engine judged the corpus could not answer. The clearest
                    signal of which sectors to expand next.
                  </span>
                </div>
                <hr className="divider" />
                <div className="stack stack-2">
                  <div className="row-between">
                    <span className="small">Superseded, replacement known</span>
                    <span className="small tabular strong">{alerts.critical_count.toLocaleString('en-IN')}</span>
                  </div>
                  <span className="xs faint">
                    A tender citing one of these should be updated before it is issued.
                  </span>
                </div>
                <hr className="divider" />
                <div className="stack stack-2">
                  <div className="row-between">
                    <span className="small">Never checked for amendments</span>
                    <span className="small tabular strong" style={{ color: 'var(--warn)' }}>
                      {alerts.coverage.amendments_unchecked.toLocaleString('en-IN')}
                    </span>
                  </div>
                  <span className="xs faint">
                    Not a statement that they have none — only that nobody has looked.
                  </span>
                </div>
                <Link to="/app/alerts" className="btn btn-secondary btn-sm">
                  Review findings <Icon name="chevronRight" size={13} />
                </Link>
              </div>
            </div>
          </section>

          <p className="xs faint">
            Counted from the served corpus and the engine's query log. Tender compliance
            rates and per-department figures are not shown because the tender auditor and
            user accounts that would produce them are not built.
          </p>
        </div>
      )}
    </div>
  );
}
