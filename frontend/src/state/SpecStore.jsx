import { createContext, useContext, useReducer, useCallback, useMemo, useEffect, useRef, useState } from 'react';
import { useAuth } from './Auth';
import {
  getActiveProject, saveProject, createProject as apiCreateProject, activateProject,
} from '../api/client';

/**
 * The spec basket, the product's actual deliverable.
 *
 * Standards collected across query / detail / map screens accumulate here,
 * grouped by role, and leave as clause text plus a frozen audit record.
 * Deliberately app-wide: the officer adds from one screen and assembles on another.
 *
 * The basket is the signed-in user's *active project*, saved on the server.
 * It follows them to another machine and survives cleared browser data, and
 * My projects lists every specification they have started. Changes are saved
 * half a second after the last edit, and `saveState` says whether the latest
 * edit has reached the server, so the screen never implies a save that failed.
 */

const SpecContext = createContext(null);

// Where the basket lived before accounts. Read once, to carry a basket built
// before this version into the user's first project, then removed.
const LEGACY_KEY = 'bis-spec-basket';
const SAVE_DELAY_MS = 500;

const blank = {
  items: {},          // code -> { code, title, role, version, addedFrom, addedAt }
  order: [],          // insertion order; reorderable in the builder
  dismissed: {},      // code -> reason (feeds the LTR training signal)
  frozen: null,       // { at, label } once the officer freezes the recommendation
  project: null,      // active project/tender name
  projectId: null,    // server id of the active project
  loaded: false,      // true once the active project has come from the server
  rev: 0,             // bumped by every edit, so hydration is never saved back
  savedRev: 0,        // the last rev the server has
};

const EDITS = new Set(['add', 'addMany', 'remove', 'move', 'dismiss', 'undismiss', 'freeze', 'setProject', 'clear']);

function specOf(state) {
  return { items: state.items, order: state.order, dismissed: state.dismissed, frozen: state.frozen };
}

function hydrate(project) {
  const spec = project.spec ?? {};
  return {
    ...blank,
    items: spec.items && typeof spec.items === 'object' ? spec.items : {},
    order: Array.isArray(spec.order) ? spec.order : [],
    dismissed: spec.dismissed && typeof spec.dismissed === 'object' ? spec.dismissed : {},
    frozen: spec.frozen ?? null,
    project: project.name,
    projectId: project.id,
    loaded: true,
  };
}

function takeLegacyBasket() {
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    if (!raw) return null;
    localStorage.removeItem(LEGACY_KEY);
    const parsed = JSON.parse(raw);
    if (!parsed?.items || !Array.isArray(parsed.order) || parsed.order.length === 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

function reducer(state, action) {
  const next = baseReducer(state, action);
  return next !== state && EDITS.has(action.type) ? { ...next, rev: state.rev + 1 } : next;
}

function baseReducer(state, action) {
  switch (action.type) {
    // `rev` only ever grows, and `savedRev` records the last edit the server
    // has, so "unsaved" is simply rev !== savedRev, across project switches too.
    case 'hydrate':
      return { ...hydrate(action.project), rev: state.rev, savedRev: state.rev };

    case 'saved':
      return { ...state, savedRev: Math.max(state.savedRev, action.rev) };

    case 'reset':
      return { ...blank, rev: state.rev, savedRev: state.rev };

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
      return { ...state, items: {}, order: [], dismissed: {}, frozen: null };

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
  const [state, dispatch] = useReducer(reducer, blank);
  const { status, user } = useAuth();
  const userId = status === 'signed-in' ? user?.id : null;
  const [saveFailed, setSaveFailed] = useState(false);

  // Load the active project whenever a different user signs in; empty the
  // basket when they sign out, so the next person never sees it.
  useEffect(() => {
    if (!userId) { dispatch({ type: 'reset' }); return undefined; }
    let live = true;
    (async () => {
      try {
        let project = await getActiveProject();
        const legacy = takeLegacyBasket();
        if (legacy && !(project.spec?.order?.length)) {
          const spec = {
            items: legacy.items, order: legacy.order,
            dismissed: legacy.dismissed ?? {}, frozen: legacy.frozen ?? null,
          };
          project = await saveProject(project.id, { name: legacy.project || project.name, spec });
        }
        if (live) { dispatch({ type: 'hydrate', project }); setSaveFailed(false); }
      } catch {
        if (live) setSaveFailed(true);
      }
    })();
    return () => { live = false; };
  }, [userId]);

  // Save edits to the server, debounced. Hydration does not bump `rev`, so a
  // project that was just loaded is never written straight back.
  const pending = useRef(null);
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; });

  const flush = useCallback(async ({ keepalive = false } = {}) => {
    const s = stateRef.current;
    clearTimeout(pending.current);
    pending.current = null;
    if (!s.loaded || !s.projectId || s.rev === s.savedRev) return;
    const rev = s.rev;
    try {
      await saveProject(s.projectId, { name: s.project || 'Untitled specification', spec: specOf(s) }, { keepalive });
      dispatch({ type: 'saved', rev });
      setSaveFailed(false);
    } catch {
      setSaveFailed(true);
    }
  }, []);

  const unsaved = state.loaded && state.rev !== state.savedRev;
  useEffect(() => {
    if (!unsaved) return undefined;
    clearTimeout(pending.current);
    pending.current = setTimeout(() => { flush(); }, SAVE_DELAY_MS);
    return undefined;
  }, [unsaved, state.rev, flush]);

  // A save still waiting when the tab closes goes out with keepalive.
  useEffect(() => {
    const onHide = () => { if (pending.current) flush({ keepalive: true }); };
    window.addEventListener('pagehide', onHide);
    return () => window.removeEventListener('pagehide', onHide);
  }, [flush]);

  const saveState = saveFailed ? 'error' : unsaved ? 'saving' : 'saved';

  /** Make another saved project the basket. Saves the current one first. */
  const switchProject = useCallback(async (id) => {
    await flush();
    await activateProject(id);
    dispatch({ type: 'hydrate', project: await getActiveProject() });
  }, [flush]);

  /** Start an empty project and make it the basket. */
  const newProject = useCallback(async (name) => {
    await flush();
    const project = await apiCreateProject(name || 'Untitled specification');
    dispatch({ type: 'hydrate', project });
    return project;
  }, [flush]);

  /** Reload the active project from the server, e.g. after it was deleted. */
  const reloadActive = useCallback(async () => {
    dispatch({ type: 'hydrate', project: await getActiveProject() });
  }, []);

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
   * Gap warnings. Deliberately rule-based, not inferred, an officer needs to
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
        text: 'No primary product standard selected, the specification has nothing to conform to.',
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
        text: `${superseded.map((s) => s.code).join(', ')} ${superseded.length === 1 ? 'is' : 'are'} superseded, replace before export.`,
      });
    }
    return out;
  }, [list, grouped]);

  const value = useMemo(
    () => ({
      ...state, list, grouped, gaps, saveState,
      count: list.length,
      has: (code) => !!state.items[code],
      add, addMany, remove, move, dismiss, undismiss, freeze, setProject, clear,
      switchProject, newProject, reloadActive, flush,
    }),
    [state, list, grouped, gaps, saveState, add, addMany, remove, move, dismiss, undismiss, freeze,
      setProject, clear, switchProject, newProject, reloadActive, flush]
  );

  return <SpecContext.Provider value={value}>{children}</SpecContext.Provider>;
}

export function useSpec() {
  const ctx = useContext(SpecContext);
  if (!ctx) throw new Error('useSpec must be used inside SpecProvider');
  return ctx;
}

/** Clause text generation, the thing the officer actually pastes. */
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
