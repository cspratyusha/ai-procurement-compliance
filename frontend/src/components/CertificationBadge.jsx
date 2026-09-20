import Icon from './Icon';

/**
 * Mandatory BIS certification status for a standard.
 *
 * Three states, and the UI must keep them distinct:
 *
 *   ISI / CRS / Hallmark  a confirmed legal requirement
 *   none                  checked, and nothing applies
 *   not_verified          nobody checked — NOT a clearance
 *
 * Collapsing the last two would tell a procurement official that no
 * certification is needed when the truth is that we never looked, which is the
 * failure that actually costs someone money.
 */

const SCHEME_LABEL = {
  ISI: 'BIS certification required (ISI mark)',
  CRS: 'BIS registration required (CRS)',
  Hallmark: 'BIS Hallmarking required',
};

/** Compact badge for a result card. */
export function CertificationBadge({ certification }) {
  if (!certification) return null;
  const { scheme, mandatory } = certification;

  if (mandatory) {
    return (
      <span className="badge badge-accent" title={certification.explanation}>
        <Icon name="shield" size={11} />
        {scheme === 'ISI' ? 'ISI mark required' : `${scheme} required`}
      </span>
    );
  }

  if (scheme === 'none') {
    return (
      <span className="badge badge-neutral" title={certification.explanation}>
        No certification scheme
      </span>
    );
  }

  return (
    <span className="badge badge-neutral" title={certification.explanation}>
      Certification unverified
    </span>
  );
}

/**
 * Full-width banner for a confirmed requirement.
 *
 * Informational rather than alarming: this is a routine procurement fact, not
 * an error. It names the Quality Control Order so the official can cite it.
 */
export function CertificationBanner({ certification, isNumber }) {
  if (!certification?.mandatory) return null;

  return (
    <div className="notice notice-info" role="note">
      <Icon name="shield" size={15} />
      <div className="stack stack-2">
        <span className="small strong">
          {SCHEME_LABEL[certification.scheme] ?? 'Certification required'}
          {isNumber ? ` — ${isNumber}` : ''}
        </span>
        <span className="xs">{certification.explanation}</span>
        {certification.qco && (
          <span className="xs">
            <strong>Governing order:</strong> {certification.qco}
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
