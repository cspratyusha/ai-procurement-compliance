import Icon from './Icon';

/**
 * Marks a screen whose content is illustrative rather than computed.
 *
 * Most screens in this prototype render fixture data from `src/data/`. That is
 * a reasonable way to show an intended workflow, but only while it is obvious
 * which is which: a dashboard of invented figures that looks identical to a
 * live one costs the whole demo its credibility the moment someone notices.
 *
 * Screens backed by the live engine (`/app/query`, `/app/catalogue`,
 * `/app/standard/:code`) must not use this.
 *
 * @param {string} what   Plain-language description of the fixture content.
 * @param {string} [next] What would make this screen real.
 */
export default function DemoDataNotice({ what, next }) {
  return (
    <div className="notice notice-info" role="note" style={{ marginBottom: 'var(--s5)' }}>
      <Icon name="info" size={15} />
      <div className="stack stack-2">
        <span className="small strong">Illustrative screen — not live data</span>
        <span className="xs">{what}</span>
        {next && <span className="xs">{next}</span>}
        <span className="xs">
          The <a href="/app/query">search</a> and{' '}
          <a href="/app/catalogue">catalogue</a> screens run against the real engine.
        </span>
      </div>
    </div>
  );
}
