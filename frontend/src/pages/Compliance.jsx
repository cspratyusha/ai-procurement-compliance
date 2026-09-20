import { useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts';
import Icon from '../components/Icon';
import { StatTile } from '../components/Primitives';
import {
  SUMMARY_TILES, TREND_DATA, CATEGORY_DATA, COMPLIANCE_DATA, DEPARTMENTS,
} from '../data/mock';
import DemoDataNotice from '../components/DemoDataNotice';

/* Matte, theme-aware chart palette. Read at render so the theme toggle applies. */
const readVar = (name, fallback) => {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
};

const COMPLIANCE_TONE = ['var(--ok)', 'var(--warn)', 'var(--crit)'];

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

export default function Compliance() {
  const [period, setPeriod] = useState('6m');
  const [dept, setDept] = useState('All departments');

  const axis = readVar('--ink-faint', '#94938D');
  const grid = readVar('--line', '#E3E1DC');
  const ink = readVar('--ink', '#171717');

  const axisProps = {
    stroke: axis,
    tick: { fill: axis, fontSize: 11 },
    tickLine: false,
    axisLine: { stroke: grid },
  };

  return (
    <div className="container page">
      <DemoDataNotice
        what="Compliance scores and the charts on this page are sample data."
      />
      <div className="page-head">
        <div>
          <h1 className="page-title">Compliance dashboard</h1>
          <p className="page-sub">
            Org-wide standards hygiene across {DEPARTMENTS.length} departments. Figures come from
            pre-aggregated metrics refreshed hourly; drill-downs query the audit log directly.
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--s2)' }}>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={dept}
            onChange={(e) => setDept(e.target.value)}
            aria-label="Filter by department"
          >
            <option>All departments</option>
            {DEPARTMENTS.map((d) => <option key={d.dept}>{d.dept}</option>)}
          </select>
          <div className="seg" role="group" aria-label="Time period">
            {['3m', '6m', '12m'].map((p) => (
              <button key={p} onClick={() => setPeriod(p)} aria-pressed={period === p}>
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="stack stack-5">
        <section className="grid grid-4">
          {SUMMARY_TILES.map((t) => <StatTile key={t.id} {...t} />)}
        </section>

        <section className="grid split" style={{ "--rail": "1fr" }}>
          <div className="card card-flush">
            <div className="card-head">
              <div className="stack stack-2">
                <h2 className="card-title">Gap and outdated-citation trend</h2>
                <span className="xs faint">Lower is better · last 6 months</span>
              </div>
              <span className="badge badge-ok"><Icon name="trend" size={12} /> Improving</span>
            </div>
            <div className="card-body">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={TREND_DATA} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={grid} vertical={false} />
                  <XAxis dataKey="month" {...axisProps} />
                  <YAxis {...axisProps} />
                  <Tooltip content={<ChartTooltip />} cursor={{ stroke: grid }} />
                  <Legend
                    wrapperStyle={{ fontSize: 11, color: axis, paddingTop: 8 }}
                    iconType="plainline"
                  />
                  <Line
                    type="monotone" dataKey="gaps" name="Gaps found"
                    stroke={ink} strokeWidth={1.8} dot={{ r: 2.5, fill: ink }} activeDot={{ r: 4 }}
                  />
                  <Line
                    type="monotone" dataKey="outdated" name="Outdated citations"
                    stroke={readVar('--crit', '#99392F')} strokeWidth={1.8}
                    strokeDasharray="4 3"
                    dot={{ r: 2.5 }} activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Tender compliance</h2>
            </div>
            <div className="card-body stack stack-4">
              {COMPLIANCE_DATA.map((c, i) => (
                <div key={c.name} className="stack stack-2">
                  <div className="row-between">
                    <span className="small">{c.name}</span>
                    <span className="small strong tabular">{c.value}%</span>
                  </div>
                  <div className="meter" role="meter" aria-valuenow={c.value} aria-valuemin={0} aria-valuemax={100} aria-label={c.name}>
                    <div className="meter-fill" style={{ width: `${c.value}%`, background: COMPLIANCE_TONE[i] }} />
                  </div>
                </div>
              ))}
              <hr className="divider" />
              <p className="xs muted">
                Compliant tenders cite current editions of every applicable standard and include
                required certification clauses.
              </p>
            </div>
          </div>
        </section>

        <section className="grid split" style={{ "--rail": "1.2fr" }}>
          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">Most-queried categories</h2>
            </div>
            <div className="card-body">
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={CATEGORY_DATA}
                  layout="vertical"
                  margin={{ top: 0, right: 16, left: 8, bottom: 0 }}
                >
                  <CartesianGrid stroke={grid} horizontal={false} />
                  <XAxis type="number" {...axisProps} />
                  <YAxis
                    type="category"
                    dataKey="category"
                    width={120}
                    {...axisProps}
                  />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: readVar('--surface-hover', '#EFEEEA') }} />
                  <Bar dataKey="queries" name="Queries" radius={[0, 2, 2, 0]} maxBarSize={18}>
                    {CATEGORY_DATA.map((_, i) => (
                      <Cell key={i} fill={ink} fillOpacity={1 - i * 0.11} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card card-flush">
            <div className="card-head">
              <h2 className="card-title">By department</h2>
              <button className="btn btn-ghost btn-sm">
                <Icon name="download" size={13} /> Export
              </button>
            </div>
            <div className="scroll-x" tabIndex={0} role="region" aria-label="Compliance by department">
              <table className="table table-hover">
                <caption className="sr-only">Compliance rate by department</caption>
                <thead>
                  <tr>
                    <th scope="col">Department</th>
                    <th scope="col">Tenders</th>
                    <th scope="col">Outdated</th>
                    <th scope="col">Compliance</th>
                  </tr>
                </thead>
                <tbody>
                  {DEPARTMENTS.map((d) => (
                    <tr key={d.dept}>
                      <td className="small">{d.dept}</td>
                      <td className="small tabular">{d.tenders}</td>
                      <td className="small tabular">
                        {d.outdated > 10
                          ? <span className="badge badge-crit">{d.outdated}</span>
                          : d.outdated}
                      </td>
                      <td>
                        <div className="row" style={{ gap: 'var(--s3)', minWidth: 110 }}>
                          <div className="meter grow" style={{ minWidth: 48 }}>
                            <div
                              className="meter-fill"
                              style={{
                                width: `${d.rate}%`,
                                background: d.rate >= 94 ? 'var(--ok)' : 'var(--warn)',
                              }}
                            />
                          </div>
                          <span className="xs tabular strong nowrap">{d.rate}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
