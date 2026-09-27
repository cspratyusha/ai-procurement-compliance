/**
 * Turn the assembled specification into files an officer can use.
 *
 * Everything is built in the browser from the project as it stands: the
 * standards, their roles and edition status, the generated clause text, the
 * confirmed certification clauses and the freeze stamp. Nothing is sent
 * anywhere; each export is recorded in the user's activity trail by the caller.
 */

import { ROLE_LABEL } from './SpecStore';

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function stamp(date) {
  return new Date(date).toLocaleString('en-IN', { dateStyle: 'long', timeStyle: 'short' });
}

/** A self-contained HTML document. Word opens it as a .doc; browsers print it to PDF. */
export function specDocument({ project, list, clause, certClauses, frozen, user, org }) {
  const rows = list.map((i) => `
      <tr>
        <td class="mono">${esc(i.code)}</td>
        <td>${esc(i.title)}</td>
        <td>${esc(ROLE_LABEL[i.role] ?? i.role)}</td>
        <td>${i.version === 'superseded' ? 'Superseded edition' : 'Current'}</td>
      </tr>`).join('');

  const certs = certClauses.length
    ? `<h2>Certification clauses</h2>${certClauses.map((c) => `
      <p><strong class="mono">${esc(c.code)}</strong></p><blockquote>${esc(c.text)}</blockquote>`).join('')}`
    : '';

  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${esc(project)}</title>
<style>
  body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #1c1b1f; margin: 2cm; }
  h1 { font-size: 18pt; margin: 0 0 4pt; }
  h2 { font-size: 13pt; margin: 18pt 0 6pt; }
  .meta { color: #49454f; font-size: 9.5pt; margin: 0 0 12pt; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #cac4d0; padding: 5pt 7pt; text-align: left; vertical-align: top; }
  th { background: #f3edf7; }
  .mono { font-family: Consolas, 'Courier New', monospace; white-space: nowrap; }
  blockquote { margin: 0 0 8pt; padding: 6pt 10pt; border-left: 3pt solid #6750a4; background: #f7f2fa; white-space: pre-wrap; }
  .frozen { margin-top: 18pt; padding: 8pt 10pt; border: 1px solid #cac4d0; font-size: 9.5pt; }
</style></head>
<body>
  <h1>${esc(project)}</h1>
  <p class="meta">Prepared by ${esc(user?.name)}${org?.name ? `, ${esc(org.name)}` : ''} on ${esc(stamp(Date.now()))}. ${list.length} standard${list.length === 1 ? '' : 's'}.</p>
  <h2>Standards</h2>
  <table>
    <thead><tr><th>IS number</th><th>Title</th><th>Role</th><th>Edition</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <h2>Clause text</h2>
  <blockquote>${esc(clause)}</blockquote>
  ${certs}
  ${frozen ? `<div class="frozen">Frozen ${esc(stamp(frozen.at))}${frozen.label ? ` (${esc(frozen.label)})` : ''}. The editions listed were those current in the StandEng corpus at that time.</div>` : ''}
</body></html>`;
}

/** The machine-readable record, for a portal or an archive. */
export function specRecord({ project, list, clause, certClauses, frozen, user, org }) {
  return {
    project,
    exported_at: new Date().toISOString(),
    prepared_by: { name: user?.name ?? null, email: user?.email ?? null, organisation: org?.name ?? null },
    frozen: frozen ? { at: new Date(frozen.at).toISOString(), label: frozen.label ?? null } : null,
    standards: list.map((i) => ({
      number: i.code,
      title: i.title ?? null,
      role: i.role,
      edition: i.version === 'superseded' ? 'superseded' : 'current',
      added_from: i.addedFrom ?? null,
    })),
    clause_text: clause,
    certification_clauses: certClauses.map((c) => ({ number: c.code, text: c.text })),
  };
}

export function fileName(project, ext) {
  const base = (project || 'specification').replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-') || 'specification';
  return `${base}.${ext}`;
}

export function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Opens the document in a new window and starts the browser's print dialog (Save as PDF). */
export function printDocument(html) {
  const win = window.open('', '_blank');
  if (!win) return false;   // pop-up blocked
  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
  // A written document has usually finished loading already, so print on a
  // short timer rather than waiting for a load event that may not come.
  setTimeout(() => { try { win.print(); } catch { /* window closed */ } }, 300);
  return true;
}
