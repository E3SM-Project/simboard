import { Check, Copy, ExternalLink, X } from 'lucide-react';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useToast } from '@/hooks/use-toast';
import { buildIiceLink, type IiceTool } from '@/lib/iice';
import { IICE_BASKET_MAX_PER_TOOL, type IiceBasketEntry, useIiceBasket } from '@/lib/iiceBasket';

const TOOL_LABELS: Record<IiceTool, string> = {
  e3sm_diags: 'E3SM Diags',
  mpas_analysis: 'MPAS-Analysis',
};

/**
 * IICE drives a whole comparison from one template, so model-vs-observations
 * and model-vs-model runs cannot share a link. Group by tool and mode, and
 * build a link per group.
 */
type GroupKey = `${IiceTool}:${'obs' | 'model'}`;

const groupKeyFor = (entry: IiceBasketEntry): GroupKey =>
  `${entry.tool}:${entry.comparison === 'model_vs_model' ? 'model' : 'obs'}`;

const groupLabel = (key: GroupKey): string => {
  const [tool, mode] = key.split(':') as [IiceTool, 'obs' | 'model'];
  if (tool === 'mpas_analysis') {
    return TOOL_LABELS[tool];
  }
  return `${TOOL_LABELS[tool]} · ${mode === 'model' ? 'model vs model' : 'model vs observations'}`;
};

const period = (entry: IiceBasketEntry): string =>
  entry.startYear != null && entry.endYear != null
    ? `${String(entry.startYear).padStart(4, '0')}-${String(entry.endYear).padStart(4, '0')}`
    : '';

/**
 * Persistent bar showing the diagnostics viewers staged for IICE and the
 * comparison links built from them.
 *
 * IICE compares one tool at a time, so entries are grouped by tool and each
 * group gets its own link. Rendering nothing when the basket is empty keeps
 * the bar out of the way for everyone not using it.
 */
export const IiceComparisonBar = () => {
  const { entries, remove, update, clear } = useIiceBasket();
  const { toast } = useToast();
  const [collapsed, setCollapsed] = useState(false);
  const barRef = useRef<HTMLDivElement | null>(null);
  const visible = entries.length > 0;

  // The bar is fixed to the viewport, so it would cover whatever sits at the
  // bottom of the page. Reserve its height as body padding while shown so the
  // page content, including the diagnostics card, ends above it.
  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!visible || !bar) {
      document.body.style.paddingBottom = '';
      return;
    }
    const apply = () => {
      document.body.style.paddingBottom = `${bar.getBoundingClientRect().height}px`;
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(bar);
    return () => {
      observer.disconnect();
      document.body.style.paddingBottom = '';
    };
  }, [visible, collapsed, entries.length]);

  const groups = useMemo(() => {
    const byGroup = new Map<GroupKey, IiceBasketEntry[]>();
    entries.forEach((entry) => {
      const key = groupKeyFor(entry);
      const list = byGroup.get(key) ?? [];
      list.push(entry);
      byGroup.set(key, list);
    });
    return [...byGroup.entries()];
  }, [entries]);

  if (!visible) {
    return null;
  }

  const copyLink = async (link: string) => {
    try {
      await navigator.clipboard.writeText(link);
      toast({ title: 'IICE link copied' });
    } catch {
      toast({ title: 'Could not copy link', variant: 'destructive' });
    }
  };

  return (
    <div
      ref={barRef}
      role="region"
      aria-label="IICE comparison"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 shadow-[0_-4px_16px_rgba(15,23,42,0.08)] backdrop-blur"
    >
      <div className="mx-auto flex max-w-[1440px] flex-col gap-3 px-4 py-3 md:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-950">IICE comparison</h2>
            <Badge variant="secondary">{entries.length}</Badge>
            <span className="hidden text-xs text-slate-500 sm:inline">
              Add matching viewers from other cases, then open them side by side.
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Button variant="ghost" size="sm" onClick={() => setCollapsed((value) => !value)}>
              {collapsed ? 'Show' : 'Hide'}
            </Button>
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear
            </Button>
          </div>
        </div>

        {collapsed ? null : (
          <div className="flex flex-col gap-3">
            {groups.map(([key, groupEntries]) => (
              <ToolGroup
                key={key}
                groupKey={key}
                entries={groupEntries}
                onRemove={remove}
                onUpdate={update}
                onCopy={copyLink}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

interface ToolGroupProps {
  groupKey: GroupKey;
  entries: IiceBasketEntry[];
  onRemove: (url: string) => void;
  onUpdate: (url: string, patch: Partial<Pick<IiceBasketEntry, 'label' | 'referenceCase'>>) => void;
  onCopy: (link: string) => void;
}

const ToolGroup = ({ groupKey, entries, onRemove, onUpdate, onCopy }: ToolGroupProps) => {
  const tool = groupKey.split(':')[0] as IiceTool;
  const missingReference = entries.filter(
    (entry) => entry.comparison === 'model_vs_model' && entry.referenceCase.trim() === '',
  );

  const link = buildIiceLink({
    tool,
    entries: entries.map((entry) => ({
      url: entry.url,
      label: entry.label,
      referenceCase: entry.referenceCase.trim() || undefined,
    })),
  });

  const disabledReason =
    entries.length < 2
      ? 'Add a viewer from another case to compare.'
      : missingReference.length > 0
        ? 'Enter the reference case for model-vs-model runs.'
        : null;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200/80 bg-slate-50/60 p-2.5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {groupLabel(groupKey)}{' '}
          <span className="font-normal normal-case text-slate-500">
            {entries.length}/{IICE_BASKET_MAX_PER_TOOL}
          </span>
        </p>
        <ul className="flex flex-wrap gap-1.5">
          {entries.map((entry) => (
            <li
              key={entry.url}
              className="flex max-w-full flex-wrap items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs"
            >
              <span className="font-medium text-slate-900">{entry.caseName}</span>
              {period(entry) ? <span className="text-slate-500">{period(entry)}</span> : null}
              {entry.subsection ? (
                <span className="hidden text-slate-400 md:inline" title={entry.subsection}>
                  {entry.subsection}
                </span>
              ) : null}
              {entry.comparison === 'model_vs_model' ? (
                <label className="flex items-center gap-1 text-slate-500">
                  <span className="whitespace-nowrap">vs ref case:</span>
                  <Input
                    value={entry.referenceCase}
                    onChange={(event) => onUpdate(entry.url, { referenceCase: event.target.value })}
                    placeholder="e.g. v3.LR.piControl"
                    aria-label={`Reference case for ${entry.caseName} ${period(entry)}`}
                    className="h-6 w-44 px-1.5 text-xs"
                  />
                </label>
              ) : null}
              <button
                type="button"
                onClick={() => onRemove(entry.url)}
                className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label={`Remove ${entry.caseName} ${period(entry)} from comparison`}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                {link && !disabledReason ? (
                  <Button asChild size="sm">
                    <a href={link} target="_blank" rel="noreferrer">
                      Compare in IICE
                      <ExternalLink className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
                    </a>
                  </Button>
                ) : (
                  <Button size="sm" disabled>
                    Compare in IICE
                  </Button>
                )}
              </span>
            </TooltipTrigger>
            {disabledReason ? (
              <TooltipContent className="text-xs">{disabledReason}</TooltipContent>
            ) : null}
          </Tooltip>
        </TooltipProvider>
        {link ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onCopy(link)}
            aria-label="Copy IICE link"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        ) : null}
        {disabledReason === null ? (
          <Check className="h-4 w-4 text-emerald-600" aria-label="Ready to compare" />
        ) : null}
      </div>
    </div>
  );
};
