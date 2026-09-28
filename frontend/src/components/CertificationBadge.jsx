import Icon from './Icon';

/**
 * Mandatory BIS certification status for a standard, read from BIS's lists of
 * products under compulsory certification.
 *
 * `status` keeps materially different answers apart, and the UI must too:
 *
 *   in_force        an order in force requires certification (ISI, CRS, Scheme X, Hallmark)
 *   deferred        named in an order whose enforcement is deferred: not yet mandatory
 *   voluntary       a BIS scheme covers the product, no order makes it compulsory
 *                   (silver hallmarking)
 *   related_listed  not listed itself, but a parent/general part or successor is
 *   checked_none    checked by hand: no scheme applies
 *   not_listed      not on BIS's compulsory lists as read on the retrieval date
 *   not_verified    the lists could not be read: NOT a clearance
 */

export const SCHEME_LABEL = {
  ISI: 'BIS certification required (ISI mark)',
  CRS: 'BIS registration required (CRS)',
  'Scheme X': 'BIS certification required (Scheme X)',
  Hallmark: 'BIS Hallmarking required',
};

export const SCHEME_DESCRIPTION = {
  ISI: 'Scheme I, Standard Mark (ISI), under a BIS licence',
  CRS: 'Scheme II, Compulsory Registration Scheme',
  'Scheme X': 'Scheme X, BIS certificate of conformity',
  Hallmark: 'BIS hallmarking: BIS logo, purity grade and HUID',
};

const SHORT = {
  ISI: 'ISI mark required',
  CRS: 'CRS registration required',
  'Scheme X': 'BIS certificate required',
  Hallmark: 'Hallmark required',
};

/** Compact badge for a result card. */
export function CertificationBadge({ certification }) {
  if (!certification) return null;
  const { scheme, mandatory, status } = certification;
  const title = certification.explanation;

  if (mandatory) {
    return (
      <span className="badge badge-accent" title={title}>
        <Icon name="shield" size={11} />
        {SHORT[scheme] ?? `${scheme} required`}
      </span>
    );
  }
  if (status === 'deferred') {
    return <span className="badge badge-warn" title={title}>Certification deferred</span>;
  }
  if (status === 'voluntary') {
    return (
      <span className="badge badge-neutral" title={title}>
        {scheme === 'Hallmark' ? 'Hallmarking voluntary' : 'Certification voluntary'}
      </span>
    );
  }
  if (status === 'related_listed') {
    return <span className="badge badge-warn" title={title}>Check related certification</span>;
  }
  if (status === 'checked_none' || status === 'not_listed' || scheme === 'none') {
    return <span className="badge badge-neutral" title={title}>No compulsory certification</span>;
  }
  return <span className="badge badge-neutral" title={title}>Certification unverified</span>;
}

/**
 * Banner for a result that needs attention: an obligation in force, a
 * deferred one, a related listing that may apply, or a voluntary scheme a
 * tender may choose to require. Names the order so the official can cite and
 * check it.
 */
export function CertificationBanner({ certification, isNumber }) {
  if (!certification) return null;
  const { mandatory, status } = certification;
  if (!mandatory && !['deferred', 'related_listed', 'voluntary'].includes(status)) return null;

  const heading = mandatory
    ? (SCHEME_LABEL[certification.scheme] ?? 'Certification required')
    : status === 'deferred'
      ? 'Named in a certification order, enforcement deferred'
      : status === 'voluntary'
        ? (certification.scheme === 'Hallmark'
          ? 'BIS hallmarking available, not compulsory'
          : 'BIS certification available, not compulsory')
        : 'A related standard is under compulsory certification';

  return (
    <div className={`notice ${mandatory || status === 'voluntary' ? 'notice-info' : 'notice-warn'}`} role="note">
      <Icon name={mandatory ? 'shield' : status === 'voluntary' ? 'info' : 'alert'} size={15} />
      <div className="stack stack-2">
        <span className="small strong">
          {heading}
          {isNumber ? `, ${isNumber}` : ''}
        </span>
        <span className="xs">{certification.explanation}</span>
        {certification.qco && (
          <span className="xs">
            <strong>Governing order:</strong>{' '}
            {certification.qco_url
              ? <a href={certification.qco_url} target="_blank" rel="noreferrer">{certification.qco}</a>
              : certification.qco}
            {certification.gazette ? ` (${certification.gazette})` : ''}
          </span>
        )}
      </div>
    </div>
  );
}

/** Warning that a corpus entry names an edition that was never published. */
export function DataWarning({ warning }) {
  if (!warning) return null;
  return (
    <div className="notice notice-warn" role="note">
      <Icon name="alert" size={15} />
      <div className="stack stack-2">
        <span className="small strong">Check this edition</span>
        <span className="xs">{warning}</span>
      </div>
    </div>
  );
}
