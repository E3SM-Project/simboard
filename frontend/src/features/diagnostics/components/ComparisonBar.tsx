import { X } from 'lucide-react';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { comparePath } from '@/features/diagnostics/compareState';
import {
  type BasketEntry,
  entryLabel,
  groupKey,
  MAX_RUNS_PER_GROUP,
  useComparisonBasket,
} from '@/features/diagnostics/comparisonBasket';

const GROUP_TITLES: Record<string, string> = {
  'e3sm_diags:model_vs_obs': 'E3SM Diags · model vs observations',
  'e3sm_diags:model_vs_model': 'E3SM Diags · model vs model',
  mpas_analysis: 'MPAS-Analysis',
};

/**
 * The runs picked for comparison, shown on every page until cleared. Each
 * kind of run is its own comparison, since only like runs share plots.
 */
export const ComparisonBar = () => {
  const { entries, remove, clear } = useComparisonBasket();
  const [collapsed, setCollapsed] = useState(false);
  const barRef = useRef<HTMLDivElement | null>(null);

  // The bar is fixed to the viewport; pad the page so it never hides content.
  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const fit = () => (document.body.style.paddingBottom = `${bar.offsetHeight}px`);
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(bar);
    return () => {
      observer.disconnect();
      document.body.style.paddingBottom = '';
    };
  }, [entries.length]);

  const groups = useMemo(() => {
    const byKey = new Map<string, BasketEntry[]>();
    entries.forEach((e) => byKey.set(groupKey(e), [...(byKey.get(groupKey(e)) ?? []), e]));
    return [...byKey];
  }, [entries]);

  if (entries.length === 0) return null;

  return (
    <div
      ref={barRef}
      role="region"
      aria-label="Diagnostics comparison"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 shadow-[0_-4px_16px_rgba(15,23,42,0.08)] backdrop-blur"
    >
      <div className="mx-auto flex max-h-[45vh] max-w-[1440px] flex-col gap-3 overflow-y-auto px-4 py-3 md:px-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-950">Diagnostics comparison</h2>
            <Badge variant="secondary">{entries.length}</Badge>
          </div>
          <div className="flex gap-1.5">
            <Button variant="ghost" size="sm" onClick={() => setCollapsed(!collapsed)}>
              {collapsed ? 'Show' : 'Hide'}
            </Button>
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear
            </Button>
          </div>
        </div>

        {collapsed
          ? null
          : groups.map(([key, group]) => (
              <div
                key={key}
                className="flex flex-col gap-2 rounded-lg border border-slate-200/80 bg-slate-50/60 p-2.5 lg:flex-row lg:items-center lg:justify-between"
              >
                <div className="min-w-0 space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                    {GROUP_TITLES[key] ?? key}{' '}
                    <span className="font-normal normal-case text-slate-500">
                      {group.length}/{MAX_RUNS_PER_GROUP}
                    </span>
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {group.map((entry) => (
                      <li
                        key={entry.url}
                        className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs"
                      >
                        <span className="font-medium text-slate-900">{entry.caseName}</span>
                        <span className="text-slate-500">{entry.period}</span>
                        <button
                          type="button"
                          onClick={() => remove(entry.url)}
                          className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          aria-label={`Remove ${entryLabel(entry)}`}
                        >
                          <X className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                {group.length < 2 ? (
                  <span className="text-xs text-slate-500">
                    Add a run from another case to compare.
                  </span>
                ) : (
                  <Button asChild size="sm">
                    <Link
                      to={comparePath(group.map((e) => ({ url: e.url, label: entryLabel(e) })))}
                    >
                      Compare
                    </Link>
                  </Button>
                )}
              </div>
            ))}
      </div>
    </div>
  );
};
