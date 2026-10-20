/**
 * Cross-page selection of diagnostics viewers destined for an IICE comparison.
 *
 * IICE compares the same plot across several cases, so the useful workflow is:
 * open case A, pick a viewer, open case B, pick the matching viewer, compare.
 * That spans routes, so the selection lives outside React state: a small
 * localStorage-backed store exposed through `useSyncExternalStore`. Any
 * component can read it and the basket bar can act on it.
 *
 * Entries are keyed by viewer URL, which is unique per case and run.
 */

import { useCallback, useSyncExternalStore } from 'react';

import type { IiceTool } from '@/lib/iice';
import type { DiagnosticsViewerOut } from '@/types';

export const IICE_BASKET_STORAGE_KEY = 'iice_comparison_basket';
export const IICE_BASKET_MAX_ENTRIES = 12;

export interface IiceBasketEntry {
  /** Viewer URL; doubles as the entry id. */
  url: string;
  caseId: string;
  caseName: string;
  tool: IiceTool;
  subsection: string | null;
  comparison: DiagnosticsViewerOut['comparison'];
  startYear: number | null;
  endYear: number | null;
  /** Label that will be sent to IICE; user-editable. */
  label: string;
  /** Reference case for model_vs_model runs; user-editable, seeded from the hint. */
  referenceCase: string;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let cache: IiceBasketEntry[] | null = null;

const isEntry = (value: unknown): value is IiceBasketEntry => {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.url === 'string' &&
    typeof candidate.caseId === 'string' &&
    typeof candidate.caseName === 'string' &&
    (candidate.tool === 'e3sm_diags' || candidate.tool === 'mpas_analysis') &&
    typeof candidate.label === 'string'
  );
};

const read = (): IiceBasketEntry[] => {
  if (cache) {
    return cache;
  }
  try {
    const raw =
      typeof localStorage === 'undefined' ? null : localStorage.getItem(IICE_BASKET_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    cache = Array.isArray(parsed) ? parsed.filter(isEntry) : [];
  } catch {
    cache = [];
  }
  return cache;
};

const write = (entries: IiceBasketEntry[]): void => {
  cache = entries;
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(IICE_BASKET_STORAGE_KEY, JSON.stringify(entries));
    }
  } catch {
    // Storage may be full or disabled; the in-memory copy still works.
  }
  listeners.forEach((listener) => listener());
};

const subscribe = (listener: Listener): (() => void) => {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === IICE_BASKET_STORAGE_KEY) {
      cache = null;
      listener();
    }
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
};

const EMPTY: IiceBasketEntry[] = [];
const getServerSnapshot = () => EMPTY;

/** Build a basket entry from a discovered viewer with sensible defaults. */
export const toBasketEntry = (
  viewer: DiagnosticsViewerOut,
  caseId: string,
  caseName: string,
  label: string,
): IiceBasketEntry => ({
  url: viewer.url,
  caseId,
  caseName,
  tool: viewer.tool,
  subsection: viewer.subsection,
  comparison: viewer.comparison,
  startYear: viewer.startYear,
  endYear: viewer.endYear,
  label,
  referenceCase: viewer.comparison === 'model_vs_model' ? (viewer.referenceHint ?? '') : '',
});

export const useIiceBasket = () => {
  const entries = useSyncExternalStore(subscribe, read, getServerSnapshot);

  const add = useCallback((entry: IiceBasketEntry): boolean => {
    const current = read();
    if (current.some((existing) => existing.url === entry.url)) {
      return true;
    }
    if (current.length >= IICE_BASKET_MAX_ENTRIES) {
      return false;
    }
    write([...current, entry]);
    return true;
  }, []);

  const remove = useCallback((url: string) => {
    write(read().filter((entry) => entry.url !== url));
  }, []);

  const update = useCallback(
    (url: string, patch: Partial<Pick<IiceBasketEntry, 'label' | 'referenceCase'>>) => {
      write(read().map((entry) => (entry.url === url ? { ...entry, ...patch } : entry)));
    },
    [],
  );

  const clear = useCallback(() => write([]), []);

  const has = useCallback((url: string) => entries.some((entry) => entry.url === url), [entries]);

  return { entries, add, remove, update, clear, has };
};
