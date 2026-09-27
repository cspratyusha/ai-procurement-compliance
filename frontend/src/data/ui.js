/**
 * Interface vocabulary: fixed labels and colours the screens share.
 *
 * Nothing here is data about standards, users or usage. Those all come from
 * the engine. The mock dataset that used to live beside this file is gone.
 */

/** Colour and label for each kind of node in the allied-standards graph. */
export const NODE_KINDS = {
  primary:       { label: 'Primary standard',    color: 'var(--ink)' },
  normative:     { label: 'Normative reference', color: 'var(--info)' },
  test:          { label: 'Test method',         color: 'var(--ok)' },
  terminology:   { label: 'Terminology',         color: 'var(--ink-faint)' },
  installation:  { label: 'Installation',        color: 'var(--accent)' },
  overlap:       { label: 'Overlapping scope',   color: 'var(--warn)' },
  certification: { label: 'Certification',       color: 'var(--crit)' },
};

/** Why an officer dismissed a result. Sent with the feedback that trains the ranker. */
export const DISMISS_REASONS = [
  'Wrong product scope',
  'Superseded edition',
  'Not applicable to this use case',
  'Already covered by another standard',
  'Other',
];
