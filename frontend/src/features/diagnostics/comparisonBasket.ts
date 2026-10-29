/**
 * Runs picked for comparison, kept across pages and tabs.
 *
 * The workflow spans routes (pick a run on one case, then the matching run on
 * another), so the selection lives in localStorage behind
 * ``useSyncExternalStore`` rather than in React state.
 */

import { useCallback, useSyncExternalStore } from 'react';

import {
  type BasketEntry,
  groupKey,
  MAX_RUNS_PER_GROUP,
} from '@/features/diagnostics/compareState';

export {
  type BasketEntry,
  entryLabel,
  groupKey,
  MAX_RUNS_PER_GROUP,
  toEntry,
} from '@/features/diagnostics/compareState';

const STORAGE_KEY = 'simboard.diagnostics-comparison';

const isEntry = (value: unknown): value is BasketEntry => {
  const v = value as Partial<BasketEntry> | null;
  return (
    typeof v?.url === 'string' &&
    typeof v.caseId === 'string' &&
    typeof v.caseName === 'string' &&
    (v.tool === 'e3sm_diags' || v.tool === 'mpas_analysis')
  );
};

let cache: BasketEntry[] | null = null;
const listeners = new Set<() => void>();

const read = (): BasketEntry[] => {
  if (cache) return cache;
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    cache = Array.isArray(parsed) ? parsed.filter(isEntry) : [];
  } catch {
    cache = [];
  }
  return cache;
};

const write = (entries: BasketEntry[]) => {
  cache = entries;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Storage full or disabled: the in-memory copy still works.
  }
  listeners.forEach((listener) => listener());
};

const subscribe = (listener: () => void) => {
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      cache = null;
      listener();
    }
  };
  listeners.add(listener);
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
};

export const useComparisonBasket = () => {
  const entries = useSyncExternalStore(subscribe, read, () => []);

  const countIn = useCallback(
    (entry: Pick<BasketEntry, 'tool' | 'comparison'>) =>
      entries.filter((e) => groupKey(e) === groupKey(entry)).length,
    [entries],
  );

  /** Add an entry; false when its group is already full. */
  const add = useCallback((entry: BasketEntry): boolean => {
    const current = read();
    if (current.some((e) => e.url === entry.url)) return true;
    if (current.filter((e) => groupKey(e) === groupKey(entry)).length >= MAX_RUNS_PER_GROUP) {
      return false;
    }
    write([...current, entry]);
    return true;
  }, []);

  const remove = useCallback((url: string) => write(read().filter((e) => e.url !== url)), []);
  const clear = useCallback(() => write([]), []);
  const has = useCallback((url: string) => entries.some((e) => e.url === url), [entries]);

  return { entries, add, remove, clear, has, countIn };
};
