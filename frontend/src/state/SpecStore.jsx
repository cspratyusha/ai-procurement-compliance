import { createContext, useContext, useReducer, useCallback, useMemo, useEffect } from 'react';

/**
 * The spec basket — the product's actual deliverable.
 *
 * Standards collected across query / detail / map screens accumulate here,
 * grouped by role, and leave as clause text plus a frozen audit record.
 * Deliberately app-wide: the officer adds from one screen and assembles on another.
 */

const SpecContext = createContext(null);

const STORAGE_KEY = 'bis-spec-basket';

const blank = {
  items: {},          // code -> { code, title, role, version, addedFrom, addedAt }
  order: [],          // insertion order; reorderable in the builder
  dismissed: {},      // code -> reason (feeds the LTR training signal)
  frozen: null,       // { at, label } once the officer freezes the recommendation
  project: null,      // active project/tender name
};

/**
 * The basket must survive a reload. An officer who refreshes, opens a standard
 * in a new tab, or comes back after lunch should not lose a half-assembled
 * specification — losing it is exactly the kind of thing that stops a tool
 * being trusted for real work.
 */
function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return blank;
    const parsed = JSON.parse(raw);
    // Guard against a shape change between versions.
    if (!parsed || typeof parsed !== 'object' || !parsed.items || !Array.isArray(parsed.order)) {
      return blank;
    }
    return { ...blank, ...parsed };
  } catch {
    return blank;  // storage blocked or corrupt — start clean rather than crash
  }
}

function persist(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage blocked (private window, quota) — the basket still works in-session */
  }
}

function reducer(state, action) {
  switch (action.type) {
    case 'add': {
      const { code } = action.item;
      if (state.items[code]) return state;
      return {
        ...state,
        items: { ...state.items, [code]: { ...action.item, addedAt: Date.now() } },
        order: [...state.order, code],
        frozen: null, // any change invalidates a freeze
      };
    }

    case 'addMany': {
      const items = { ...state.items };
      const order = [...state.order];
      action.items.forEach((it) => {
        if (items[it.code]) return;
        items[it.code] = { ...it, addedAt: Date.now() };
        order.push(it.code);
      });
      return { ...state, items, order, frozen: null };
    }

    case 'remove': {
      const items = { ...state.items };
      delete items[action.code];
      return {
        ...state,
        items,
        order: state.order.filter((c) => c !== action.code),
        frozen: null,
      };
    }

    case 'move': {
      const order = [...state.order];
      const from = order.indexOf(action.code);
      if (from === -1) return state;
      const to = Math.max(0, Math.min(order.length - 1, from + action.delta));
      if (to === from) return state;
      order.splice(to, 0, order.splice(from, 1)[0]);
      return { ...state, order, frozen: null };
    }

    case 'dismiss':
      return {
        ...state,
        dismissed: { ...state.dismissed, [action.code]: action.reason },
      };

    case 'undismiss': {
      const dismissed = { ...state.dismissed };
      delete dismissed[action.code];
      return { ...state, dismissed };
    }

    case 'freeze':
      return { ...state, frozen: { at: Date.now(), label: action.label } };

    case 'setProject':
      return { ...state, project: action.name };

    case 'clear':
      return { ...blank };

    default:
      return state;
  }
}

/** Roles group the basket in the builder, and drive gap warnings. */
export const ROLE_ORDER = ['primary', 'test', 'safety', 'installation', 'terminology', 'certification'];

export const ROLE_LABEL = {
  primary: 'Primary product standard',
  test: 'Test methods',
  safety: 'Safety',
  installation: 'Installation',
  terminology: 'Terminology',
  certification: 'Certification',
};

export function SpecProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, undefined, load);

  // Mirror every change to storage so a reload restores the basket.
  useEffect(() => { persist(state); }, [state]);

  const add = useCallback((item) => dispatch({ type: 'add', item }), []);
  const addMany = useCallback((items) => dispatch({ type: 'addMany', items }), []);
  const remove = useCallback((code) => dispatch({ type: 'remove', code }), []);
  const move = useCallback((code, delta) => dispatch({ type: 'move', code, delta }), []);
  const dismiss = useCallback((code, reason) => dispatch({ type: 'dismiss', code, reason }), []);
  const undismiss = useCallback((code) => dispatch({ type: 'undismiss', code }), []);
  const freeze = useCallback((label) => dispatch({ type: 'freeze', label }), []);
  const setProject = useCallback((name) => dispatch({ type: 'setProject', name }), []);
  const clear = useCallback(() => dispatch({ type: 'clear' }), []);

  const list = useMemo(
    () => state.order.map((c) => state.items[c]).filter(Boolean),
    [state.order, state.items]
  );

  const grouped = useMemo(() => {
    const g = {};
    ROLE_ORDER.forEach((r) => { g[r] = []; });
    list.forEach((it) => { (g[it.role] ||= []).push(it); });
    return g;
  }, [list]);

  /**
   * Gap warnings. Deliberately rule-based, not inferred — an officer needs to
   * know *why* something is flagged, and these are defensible rules.
   */
  const gaps = useMemo(() => {
    const out = [];
    if (list.length === 0) return out;

    const has = (r) => (grouped[r] || []).length > 0;
    const isElectrical = list.some((i) =>
      /cable|conductor|wiring|electr|luminaire|transformer/i.test(`${i.code} ${i.title}`)
    );

    if (!has('primary')) {
      out.push({
        severity: 'critical',
        text: 'No primary product standard selected — the specification has nothing to conform to.',
      });
    }
    if (!has('test')) {
      out.push({
        severity: 'warn',
        text: 'No test method standard selected. Acceptance criteria will not be measurable at inspection.',
      });
    }
    if (isElectrical && !has('safety') && !has('installation')) {
      out.push({
        severity: 'warn',
        text: 'Electrical item with no safety or installation standard selected.',
      });
    }
    const superseded = list.filter((i) => i.version === 'superseded');
    if (superseded.length) {
      out.push({
        severity: 'critical',
        text: `${superseded.map((s) => s.code).join(', ')} ${superseded.length === 1 ? 'is' : 'are'} superseded — replace before export.`,
      });
    }
    return out;
  }, [list, grouped]);

  const value = useMemo(
    () => ({
      ...state, list, grouped, gaps,
      count: list.length,
      has: (code) => !!state.items[code],
      add, addMany, remove, move, dismiss, undismiss, freeze, setProject, clear,
    }),
    [state, list, grouped, gaps, add, addMany, remove, move, dismiss, undismiss, freeze, setProject, clear]
  );

  return <SpecContext.Provider value={value}>{children}</SpecContext.Provider>;
}

export function useSpec() {
  const ctx = useContext(SpecContext);
  if (!ctx) throw new Error('useSpec must be used inside SpecProvider');
  return ctx;
}

/** Clause text generation — the thing the officer actually pastes. */
export function buildClause(list) {
  if (!list.length) return '';

  const byRole = {};
  list.forEach((i) => { (byRole[i.role] ||= []).push(i); });

  const lines = [];
  const primary = byRole.primary || [];
  const tests = byRole.test || [];
  const safety = byRole.safety || [];
  const install = byRole.installation || [];
  const certs = byRole.certification || [];

  if (primary.length) {
    const refs = primary
      .map((p) => `${p.code}${p.amendment ? ` including ${p.amendment}` : ''}`)
      .join(' and ');
    lines.push(`1. The item shall conform in all respects to ${refs}.`);
  }
  if (tests.length) {
    lines.push(
      `${lines.length + 1}. All type and routine tests shall be carried out in accordance with ${tests.map((t) => t.code).join(', ')}. Test certificates from an NABL-accredited laboratory shall be furnished with each supply lot.`
    );
  }
  if (safety.length) {
    lines.push(`${lines.length + 1}. The item shall additionally comply with ${safety.map((s) => s.code).join(', ')}.`);
  }
  if (install.length) {
    lines.push(`${lines.length + 1}. Installation shall follow ${install.map((s) => s.code).join(', ')}.`);
  }
  if (certs.length) {
    lines.push(
      `${lines.length + 1}. The item shall bear a valid marking under ${certs.map((c) => c.scheme || c.code).join(', ')}. The licence number shall be stated in the bid.`
    );
  }
  return lines.join('\n\n');
}
