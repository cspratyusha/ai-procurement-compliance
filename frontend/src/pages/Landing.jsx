import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import './landing.css';

/**
 * What the engine does today is stated plainly; what is still being built is
 * labelled as such. A reviewer who tries a feature described here and finds
 * it missing discounts everything else on the page.
 */
const BENEFITS = [
  {
    icon: 'search',
    title: 'Matches on meaning, not keywords',
    body: 'Dense vector retrieval and BM25 run together, and a cross-encoder re-reads each candidate against the query. A description with none of the standard’s words in it still finds the right standard.',
    status: 'working',
  },
  {
    icon: 'shield',
    title: 'Says when it does not know',
    body: 'Coverage is a pilot corpus, not the full catalogue. A query outside it is reported as no match, with the nearest entries clearly labelled as references rather than recommendations.',
    status: 'working',
  },
  {
    icon: 'refresh',
    title: 'Flags superseded editions',
    body: 'Withdrawn standards are penalised in ranking and marked in the results, including replacements that carry a different standard number.',
    status: 'working',
  },
  {
    icon: 'layers',
    title: 'The whole cluster, not one hit',
    body: 'Normative references, test methods, terminology and installation standards surfaced as one connected set, alongside mandatory certification requirements.',
    status: 'planned',
  },
];

/**
 * Only figures we can actually demonstrate.
 *
 * Earlier drafts of this page claimed "1.4M API calls served monthly",
 * "11 portals integrated" and "22,418 standards indexed". None of that was
 * true of a prototype, and a reviewer who checks one inflated number stops
 * believing the rest of the page. Everything here is either measured on this
 * machine or a published fact about BIS.
 */
const STATS = [
  { value: '4', label: 'Retrieval stages', note: 'Dense, BM25, cross-encoder, learned ranker' },
  { value: '~200 ms', label: 'Typical query time', note: 'Measured locally on CPU' },
  { value: '45', label: 'Standards in the pilot corpus', note: 'Unverified placeholder data' },
  { value: '~22,000', label: 'Published Indian Standards', note: 'The full catalogue, for scale' },
];

export default function Landing({ theme, onToggleTheme }) {
  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="container row-between">
          <span className="wordmark">StandEng</span>
          <div className="row" style={{ gap: 'var(--s2)' }}>
            <button
              className="btn-icon"
              onClick={onToggleTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={18} />
            </button>
            <Link to="/login" className="btn btn-secondary btn-sm">Sign in</Link>
          </div>
        </div>
      </header>

      {/* Swiss 12-column grid: editorial left column, live resolution right.
          Asymmetric by design — the product's whole claim is that one query
          resolves into a cluster, so the hero shows that happening. */}
      <section className="hero">
        <div className="container hero-grid">

          <div className="hero-lede">
            <p className="hero-kicker">
              <span className="hero-rule" aria-hidden="true" />
              Bureau of Indian Standards
            </p>

            <h1 className="hero-title">
              One product.
              <span className="hero-line-2">A cluster of standards.</span>
            </h1>

            <p className="hero-sub">
              A tender rarely cites one standard correctly. Describe what you are procuring
              in plain language and get the applicable Indian Standards, ranked by meaning,
              with superseded editions flagged.
            </p>

            <p className="xs muted" style={{ maxWidth: '52ch' }}>
              Prototype built for the Smart India Hackathon. It currently searches a pilot
              corpus of 45 standards across seven sectors — realistic but unverified data,
              not the full BIS catalogue.
            </p>

            <div className="hero-cta">
              <Link to="/login" className="btn btn-primary btn-lg">
                Open the engine
                <Icon name="arrowRight" size={16} />
              </Link>
              <a href="#how" className="btn btn-secondary btn-lg">How it works</a>
            </div>

            <dl className="hero-facts">
              {[
                ['45', 'standards in pilot corpus'],
                ['4-stage', 'retrieval pipeline'],
                ['~200 ms', 'typical query'],
              ].map(([v, l]) => (
                <div key={l} className="hero-fact">
                  <dt className="hero-fact-v tabular">{v}</dt>
                  <dd className="hero-fact-l">{l}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="hero-panel" aria-hidden="true">
            <div className="hero-panel-head">
              <span className="xs faint">Specification</span>
              <span className="xs faint mono">resolved in 1.2s</span>
            </div>

            <p className="hero-query mono">
              PVC insulated copper cable, single core, 1100&nbsp;V, indoor panel wiring
            </p>

            <div className="hero-arrow">
              <span className="hero-arrow-line" />
              <span className="xs faint">resolves to</span>
              <span className="hero-arrow-line" />
            </div>

            <ol className="hero-cluster">
              {[
                { code: 'IS 694:2010', role: 'Primary standard', tag: 'Strong', tone: 'ok', lead: true },
                { code: 'IS 8130:2013', role: 'Conductors — normative', tag: 'Strong', tone: 'ok' },
                { code: 'IS 5831:1984', role: 'Insulation — normative', tag: 'Strong', tone: 'ok' },
                { code: 'IS 10810', role: 'Test methods', tag: 'Probable', tone: 'warn' },
                { code: 'IS 732:2019', role: 'Installation practice', tag: 'Probable', tone: 'warn' },
              ].map((r) => (
                <li key={r.code} className={`hero-node ${r.lead ? 'is-lead' : ''}`}>
                  <span className="hero-node-mark" />
                  <span className="hero-node-code mono">{r.code}</span>
                  <span className="hero-node-role">{r.role}</span>
                  <span className={`badge badge-${r.tone}`}>{r.tag}</span>
                </li>
              ))}
            </ol>

            <div className="hero-cert">
              <Icon name="shield" size={14} />
              <span className="xs">
                Mandatory: BIS Product Certification (ISI Mark) — QCO 2003
              </span>
            </div>
          </div>

        </div>
      </section>

      <section className="strip">
        <div className="container grid grid-4">
          {STATS.map((s) => (
            <div key={s.label} className="stack stack-2 center">
              <span className="strip-value tabular">{s.value}</span>
              <span className="xs faint">{s.label}</span>
              {s.note && <span className="xs faint" style={{ opacity: 0.7 }}>{s.note}</span>}
            </div>
          ))}
        </div>
      </section>

      <section id="how" className="section">
        <div className="container">
          <div className="center stack stack-3" style={{ marginBottom: 'var(--s8)' }}>
            <span className="eyebrow">Why it is different</span>
            <h2 className="section-title">Built for decisions that get audited</h2>
          </div>

          <div className="grid grid-4">
            {BENEFITS.map((b) => (
              <article key={b.title} className="card stack stack-4">
                <span className="benefit-icon"><Icon name={b.icon} size={19} /></span>
                <div className="row wrap" style={{ gap: 'var(--s2)' }}>
                  <h3 style={{ fontSize: 'var(--fs-md)' }}>{b.title}</h3>
                  {b.status === 'planned' && (
                    <span className="badge badge-neutral" title="Not built yet">In progress</span>
                  )}
                </div>
                <p className="small muted">{b.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-sunk">
        <div className="container">
          <div className="center stack stack-3" style={{ marginBottom: 'var(--s7)' }}>
            <span className="eyebrow">Pipeline</span>
            <h2 className="section-title">Retrieval first. Generation last.</h2>
            <p className="small muted" style={{ maxWidth: '62ch', margin: '0 auto' }}>
              The language model never decides which standard applies. It explains and drafts over
              data that has already been retrieved and verified — which structurally prevents the
              confident-wrong-answer failure mode.
            </p>
          </div>

          <ol className="steps">
            {[
              { n: '01', t: 'Hybrid retrieval', d: 'Dense embeddings, BM25 keyword search and metadata filters run together.' },
              { n: '02', t: 'Re-ranking', d: 'A cross-encoder refines the shortlist for precision.' },
              { n: '03', t: 'Graph expansion', d: 'Neo4j traversal pulls the allied standards cluster.' },
              { n: '04', t: 'Deterministic checks', d: 'Version state and certification rules resolve in SQL, not inference.' },
              { n: '05', t: 'Grounded explanation', d: 'The model writes the rationale and clause text over verified data only.' },
            ].map((s) => (
              <li key={s.n} className="step">
                <span className="step-n mono">{s.n}</span>
                <div className="stack stack-2">
                  <span className="strong small">{s.t}</span>
                  <span className="xs muted">{s.d}</span>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section">
        <div className="container cta-band">
          <div className="stack stack-4 center">
            <h2 className="section-title">Start with a single specification</h2>
            <p className="small muted" style={{ maxWidth: '54ch' }}>
              Paste a product description and see the full standards cluster in seconds.
            </p>
            <Link to="/login" className="btn btn-primary btn-lg">
              Open the engine
              <Icon name="arrowRight" size={16} />
            </Link>
          </div>
        </div>
      </section>

      <footer className="landing-foot">
        <div className="container row-between wrap" style={{ gap: 'var(--s4)' }}>
          <div className="row">
            <span className="wordmark wordmark-sm">StandEng</span>
            <span className="xs muted">AI-powered Indian Standards for procurement</span>
          </div>
          <span className="xs faint">Prototype interface · Demonstration data</span>
        </div>
      </footer>
    </div>
  );
}
