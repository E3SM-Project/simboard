import { useQueryClient } from '@tanstack/react-query';
import { Loader2, X } from 'lucide-react';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { comparePath } from '@/features/diagnostics/compareState';
import {
  type BasketEntry,
  entryLabel,
  groupKey,
  MAX_RUNS_PER_GROUP,
  useComparisonBasket,
} from '@/features/diagnostics/comparisonBasket';
import { validateComparison } from '@/features/diagnostics/comparisonValidation';

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
  const client = useQueryClient();
  const navigate = useNavigate();
  const [checking, setChecking] = useState(false);
  const [problem, setProblem] = useState('');
  const [retryable, setRetryable] = useState(false);
  const validating = useRef(false);
  const mounted = useRef(false);
  const [collapsed, setCollapsed] = useState(true);
  const [selectedGroup, setSelectedGroup] = useState('');
  const { pathname, key: locationKey } = useLocation();
  const inWorkspace = pathname === '/diagnostics' || pathname === '/diagnostics/compare';
  const visible = entries.length > 0 && !inWorkspace;
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
  }, [visible]);

  const groups = useMemo(() => {
    const byKey = new Map<string, BasketEntry[]>();
    entries.forEach((e) => byKey.set(groupKey(e), [...(byKey.get(groupKey(e)) ?? []), e]));
    return [...byKey];
  }, [entries]);
  const active = groups.find(([key]) => key === selectedGroup) ?? groups[0];
  const signature = JSON.stringify([locationKey, active]);
  const currentSignature = useRef(signature);
  currentSignature.current = signature;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    setProblem('');
    setRetryable(false);
  }, [signature]);

  const compare = async () => {
    if (validating.current || !active) return;
    const runs = active[1].map((entry) => ({ url: entry.url, label: entryLabel(entry) }));
    const startedSignature = signature;
    validating.current = true;
    setChecking(true);
    setProblem('');
    setRetryable(false);
    try {
      const failure = await validateComparison(client, runs);
      if (!mounted.current || currentSignature.current !== startedSignature) return;
      if (failure) {
        setProblem(failure.problem);
        setRetryable(failure.retryable);
        return;
      }
      navigate(comparePath(runs));
    } catch {
      if (mounted.current && currentSignature.current === startedSignature) {
        setProblem('Could not check run compatibility. Check your connection and try again.');
        setRetryable(true);
      }
    } finally {
      validating.current = false;
      if (mounted.current) setChecking(false);
    }
  };

  if (entries.length === 0 || inWorkspace) return null;

  return (
    <div
      ref={barRef}
      role="region"
      aria-label="Diagnostics comparison"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 shadow-[0_-4px_16px_rgba(15,23,42,0.08)] backdrop-blur"
    >
      <div className="mx-auto flex max-h-[45vh] max-w-[1440px] flex-col gap-3 overflow-y-auto px-4 py-3 md:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-950">Diagnostics</h2>
            <Badge variant="secondary" aria-live="polite">
              {entries.length} selected
            </Badge>
            {groups.length > 1 ? (
              <span className="text-xs text-slate-500">{active[1].length} in this group</span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {groups.length > 1 ? (
              <Select value={active[0]} onValueChange={setSelectedGroup} disabled={checking}>
                <SelectTrigger
                  aria-label="Comparison group"
                  className="h-8 w-[min(260px,65vw)] text-xs"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {groups.map(([key, group]) => (
                    <SelectItem key={key} value={key}>
                      {GROUP_TITLES[key] ?? key} ({group.length})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={!collapsed}
              aria-controls="comparison-tray-selections"
              onClick={() => setCollapsed(!collapsed)}
            >
              {collapsed ? 'Expand' : 'Collapse'}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={checking}
              aria-busy={checking}
              onClick={() => void compare()}
            >
              {checking ? (
                <>
                  <Loader2
                    className="mr-1 h-4 w-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                  <span role="status">Checking compatibility…</span>
                </>
              ) : (
                'Compare'
              )}
            </Button>
          </div>
        </div>
        {problem ? (
          <p role="alert" className="text-sm text-red-600">
            {problem}
          </p>
        ) : null}
        {retryable && !checking ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-fit"
            onClick={() => void compare()}
          >
            Retry comparison
          </Button>
        ) : null}

        {collapsed ? null : (
          <div id="comparison-tray-selections" className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-slate-500">
                Compare runs of the same kind, across cases or time ranges.
              </p>
              <Button variant="ghost" size="sm" disabled={checking} onClick={clear}>
                Clear all
              </Button>
            </div>
            {groups.map(([key, group]) => (
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
                        className="flex max-w-full items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs"
                      >
                        <span className="min-w-0 break-words font-medium text-slate-900">
                          {entry.caseName}
                        </span>
                        <span className="text-slate-500">{entry.period}</span>
                        <button
                          type="button"
                          disabled={checking}
                          onClick={() => remove(entry.url)}
                          className="shrink-0 rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label={`Remove ${entryLabel(entry)}`}
                        >
                          <X className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
