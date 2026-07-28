import { useQueries } from '@tanstack/react-query';
import { ChevronRight, EyeOff, GripVertical, X } from 'lucide-react';
import {
  type DragEvent,
  Fragment,
  type MouseEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { getExecutionById } from '@/api/catalog';
import { normalizeSelectedExecutionIds } from '@/components/shared/normalizeSelectedExecutionIds';
import { Badge } from '@/components/ui/badge';
import { TableCellText } from '@/components/ui/table-cell-text';
import CompareToolbar from '@/features/compare/components/CompareToolbar';
import { norm, renderCellValue } from '@/features/compare/utils';
import { catalogQueryKeys } from '@/lib/catalog/queryKeys';
import { type ArtifactKind, getArtifactsByKind } from '@/types/artifact';
import type { ExecutionOut } from '@/types/index';
import { formatDate, formatModelDate, getModelDateDuration } from '@/utils/utils';

interface ComparePageProps {
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
}

interface CompareLocationState {
  selectedExecutionIds?: string[];
  selectedExecutions?: ExecutionOut[];
}

interface CompareWorkspaceProps {
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
  selectedExecutions: ExecutionOut[];
  backLabel?: string;
  contextNotice?: ReactNode;
  description?: string;
  embedded?: boolean;
  emptyStateActionHref?: string;
  emptyStateActionLabel?: string;
  emptyStateMessage?: string;
  hiddenStorageKey?: string;
  labelColumnWidth?: number;
  onBack?: () => void;
  showHeader?: boolean;
  toolbarDescription?: string;
  title?: string;
}

interface CompareMetricRow {
  label: string;
  values: unknown[];
  renderMode?: 'default' | 'rich';
  diffable?: boolean;
}

interface CompareSection {
  key: string;
  label: string;
  rows: CompareMetricRow[];
  diffRows: CompareMetricRow[];
  diffCount: number;
  hasDiffs: boolean;
}

interface CompareSummaryCard {
  key: string;
  label: string;
  values: string[];
  uniqueValueCount: number;
}

const arraysEqual = <T,>(left: T[], right: T[]) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

export const CompareWorkspace = ({
  backLabel = 'Back to Browse',
  contextNotice,
  description = 'Compare selected executions side by side across cases. Drag columns to reorder, hide or remove executions, and expand sections for detailed metrics.',
  embedded = false,
  emptyStateActionHref = '/browse',
  emptyStateActionLabel = 'Go to Browse Page',
  emptyStateMessage = 'No executions selected for comparison.',
  hiddenStorageKey = 'compare_hidden_cols',
  labelColumnWidth,
  onBack,
  showHeader = true,
  selectedExecutionIds,
  setSelectedExecutionIds,
  selectedExecutions,
  toolbarDescription,
  title = 'Cross-Case Compare',
}: CompareWorkspaceProps) => {
  const LABEL_COLUMN_WIDTH = labelColumnWidth ?? 260;
  const VALUE_COLUMN_WIDTH = 320;

  // -------------------- Router --------------------
  const navigate = useNavigate();

  // -------------------- Global State --------------------
  // -------------------- Local State --------------------
  const [order, setOrder] = useState(selectedExecutionIds.map((_, i) => i));

  const executionHeaders = selectedExecutionIds.map((id) => {
    const execution = selectedExecutions.find((item) => item.id === id);
    return execution?.executionId || id;
  });
  const [headers, setHeaders] = useState(executionHeaders);

  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [hidden, setHidden] = useState<string[]>(() => {
    const stored = localStorage.getItem(hiddenStorageKey);
    try {
      const parsed = stored ? JSON.parse(stored) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  const dragCol = useRef<number | null>(null);
  const previousSelectedExecutionIds = useRef(selectedExecutionIds);
  const [diffsEnabled, setDiffsEnabled] = useState(false);
  const [diffsOnlyEnabled, setDiffsOnlyEnabled] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const previousExpandedSections = useRef<Record<string, boolean> | null>(null);

  // -------------------- Derived Data --------------------
  const visibleOrder = order.filter((colIdx) => !hidden.includes(selectedExecutionIds[colIdx]));
  const canCompareDifferences = visibleOrder.length > 1;

  const getExecutionProp = <K extends keyof ExecutionOut>(
    id: string,
    prop: K,
    fallback: ExecutionOut[K] | '',
  ): ExecutionOut[K] => {
    const execution = selectedExecutions.find((s) => s.id === id);
    return (execution?.[prop] ?? fallback) as ExecutionOut[K];
  };

  const makeMetricRow = <T extends keyof ExecutionOut>(
    label: string,
    prop: T,
    fallback: ExecutionOut[T] | '' = '',
    renderMode: CompareMetricRow['renderMode'] = 'default',
    diffable = true,
  ): CompareMetricRow => {
    const values = selectedExecutionIds.map((id) => {
      const execution = selectedExecutions.find((s) => s.id === id);
      if (!execution) return fallback;
      return (execution[prop] ?? fallback) as ExecutionOut[T];
    });

    return { label, values, renderMode, diffable };
  };

  const makeArtifactMetricRow = (
    label: string,
    kind: ArtifactKind,
    fallback: unknown[] = [],
    diffable = true,
  ): CompareMetricRow => {
    const values = selectedExecutionIds.map((id) => {
      const execution = selectedExecutions.find((s) => s.id === id);
      if (!execution) return fallback;

      return getArtifactsByKind(execution.artifacts, execution.groupedArtifacts, kind);
    });

    return { label, values, diffable };
  };

  const rowHasDiffs = (row: CompareMetricRow): boolean => {
    if (row.diffable === false) {
      return false;
    }

    if (visibleOrder.length <= 1) return false;

    const first = norm(row.values[visibleOrder[0]]);

    for (let i = 1; i < visibleOrder.length; i++) {
      if (norm(row.values[visibleOrder[i]]) !== first) return true;
    }

    return false;
  };

  const formatSectionLabel = (sectionKey: string) =>
    sectionKey.replace(/([A-Z])/g, ' $1').replace(/^./, (str) => str.toUpperCase());

  const formatCompareDate = (date: string | null | undefined) => formatModelDate(date);

  const formatDateRange = (start: string | null | undefined, end: string | null | undefined) => {
    const startLabel = formatCompareDate(start);
    const endLabel = formatCompareDate(end);

    if (startLabel === '—' && endLabel === '—') {
      return '—';
    }

    return `${startLabel} -> ${endLabel}`;
  };

  const getExecutionById = (id: string) =>
    selectedExecutions.find((execution) => execution.id === id);

  const buildVersionSummary = (execution: ExecutionOut | undefined) => {
    if (!execution) return '—';

    const parts = [
      execution.gitBranch || null,
      execution.gitTag || null,
      execution.gitCommitHash ? execution.gitCommitHash.slice(0, 7) : null,
    ].filter(Boolean);

    return parts.length > 0 ? parts.join(' • ') : '—';
  };

  const buildConfigurationSummary = (execution: ExecutionOut | undefined) => {
    if (!execution) return '—';

    const configBits = [
      execution.compset || null,
      execution.gridName || null,
      execution.gridResolution || null,
    ]
      .filter(Boolean)
      .join(' • ');

    return configBits || '—';
  };

  const visibleColumns = visibleOrder.map((colIdx) => {
    const executionId = selectedExecutionIds[colIdx];
    const execution = getExecutionById(executionId);

    return {
      caseHref: execution?.caseId ? `/cases/${execution.caseId}` : undefined,
      caseName: execution?.caseName || '—',
      colIdx,
      executionHeader: headers[colIdx],
      executionHref: `/executions/${executionId}`,
      executionId,
    };
  });

  const metrics = {
    configuration: [
      makeMetricRow('Case Name', 'caseName', ''),
      makeMetricRow('Model Version', 'gitTag', ''),
      makeMetricRow('Compset', 'compset', ''),
      makeMetricRow('Grid Name', 'gridName', ''),
      makeMetricRow('Grid Resolution', 'gridResolution', ''),
      makeMetricRow('Initialization Type', 'initializationType', ''),
      makeMetricRow('Compiler', 'compiler', ''),
    ],
    modelSetup: [
      makeMetricRow('Simulation Type', 'simulationType', ''),
      makeMetricRow('Status', 'status', ''),
      makeMetricRow('Campaign ID', 'campaign', ''),
      makeMetricRow('Experiment Type ID', 'experimentType', ''),
      {
        label: 'Machine Name',
        values: selectedExecutionIds.map((id) => {
          const execution = selectedExecutions.find((s) => s.id === id);
          return execution?.machine?.name ?? '';
        }),
      },
      makeMetricRow('Branch', 'gitBranch', ''),
    ],
    timeline: [
      {
        label: 'Model Start',
        values: selectedExecutionIds.map((id) => {
          const date = getExecutionProp(id, 'simulationStartDate', '');
          return formatModelDate(date as string);
        }),
      },
      {
        label: 'Model End',
        values: selectedExecutionIds.map((id) => {
          const date = getExecutionProp(id, 'simulationEndDate', '');
          return formatModelDate(date as string);
        }),
      },
      {
        label: 'Duration',
        values: selectedExecutionIds.map((id) => {
          const start = getExecutionProp(id, 'simulationStartDate', '');
          const end = getExecutionProp(id, 'simulationEndDate', '');
          if (start && end) {
            try {
              return getModelDateDuration(start as string, end as string);
            } catch {
              return '—';
            }
          }
          return '—';
        }),
      },
      {
        label: 'Calendar Start',
        values: selectedExecutionIds.map((id) => {
          const date = getExecutionProp(id, 'runStartDate', '');
          return date ? formatDate(date as string) : '—';
        }),
      },
      {
        label: 'Calendar End Date',
        values: selectedExecutionIds.map((id) => {
          const date = getExecutionProp(id, 'runEndDate', '');
          return date ? formatDate(date as string) : '—';
        }),
      },
    ],
    provenance: [
      makeMetricRow('Git Repository', 'gitRepositoryUrl', '', 'rich'),
      makeMetricRow('Git Branch', 'gitBranch', ''),
      makeMetricRow('Git Tag', 'gitTag', ''),
      makeMetricRow('Git Commit Hash', 'gitCommitHash', ''),
      makeMetricRow('HPC Username', 'hpcUsername', ''),
    ],
    locations: [
      makeArtifactMetricRow('Output Paths', 'output'),
      makeArtifactMetricRow('Archive Paths', 'archive'),
      makeArtifactMetricRow('Run Script Paths', 'run_script'),
      makeArtifactMetricRow('Post-processing Scripts', 'postprocessing_script'),
    ],
  };

  const defaultExpanded = ['configuration', 'modelSetup', 'timeline'];
  const allSectionKeys = Object.keys(metrics);
  const initialExpandedSections: Record<string, boolean> = {};

  allSectionKeys.forEach((section) => {
    initialExpandedSections[section] = defaultExpanded.includes(section);
  });
  const [expandedSections, setExpandedSections] =
    useState<Record<string, boolean>>(initialExpandedSections);

  const compareSections: CompareSection[] = Object.entries(metrics).map(([sectionKey, rows]) => {
    const diffRows = rows.filter((row) => rowHasDiffs(row));

    return {
      key: sectionKey,
      label: formatSectionLabel(sectionKey),
      rows,
      diffRows,
      diffCount: diffRows.length,
      hasDiffs: diffRows.length > 0,
    };
  });

  const changedSectionCount = compareSections.filter((section) => section.hasDiffs).length;
  const totalChangedRows = compareSections.reduce((sum, section) => sum + section.diffCount, 0);

  const summaryCards: CompareSummaryCard[] = [
    {
      key: 'status',
      label: 'Status',
      values: selectedExecutionIds.map((id) => getExecutionById(id)?.status || '—'),
    },
    {
      key: 'machine',
      label: 'Machine',
      values: selectedExecutionIds.map((id) => getExecutionById(id)?.machine?.name || '—'),
    },
    {
      key: 'provenance',
      label: 'Branch / Tag / Commit',
      values: selectedExecutionIds.map((id) => buildVersionSummary(getExecutionById(id))),
    },
    {
      key: 'configuration',
      label: 'Compset / Grid',
      values: selectedExecutionIds.map((id) => buildConfigurationSummary(getExecutionById(id))),
    },
    {
      key: 'dateRange',
      label: 'Model Date Range',
      values: selectedExecutionIds.map((id) => {
        const execution = getExecutionById(id);

        return formatDateRange(execution?.simulationStartDate, execution?.simulationEndDate);
      }),
    },
  ]
    .filter((card) => rowHasDiffs({ label: card.label, values: card.values }))
    .map((card) => ({
      ...card,
      uniqueValueCount: visibleOrder
        .map((colIdx) => card.values[colIdx] || '—')
        .filter((value, index, values) => values.indexOf(value) === index).length,
    }));

  // -------------------- Effects --------------------
  useEffect(() => {
    setHidden((prev) => {
      const nextHidden = prev.filter((id) => selectedExecutionIds.includes(id));
      return arraysEqual(prev, nextHidden) ? prev : nextHidden;
    });
  }, [selectedExecutionIds]);

  useEffect(() => {
    localStorage.setItem(hiddenStorageKey, JSON.stringify(hidden));
  }, [hidden, hiddenStorageKey]);

  useEffect(() => {
    const nextHeaders = selectedExecutionIds.map(
      (id) => selectedExecutions.find((s) => s.id === id)?.executionId || id,
    );

    setHeaders((prev) => (arraysEqual(prev, nextHeaders) ? prev : nextHeaders));

    if (!arraysEqual(previousSelectedExecutionIds.current, selectedExecutionIds)) {
      setOrder(selectedExecutionIds.map((_, i) => i));
      previousSelectedExecutionIds.current = selectedExecutionIds;
    }
  }, [selectedExecutionIds, selectedExecutions]);

  useEffect(() => {
    if (canCompareDifferences || !diffsOnlyEnabled) {
      return;
    }

    setDiffsOnlyEnabled(false);

    if (previousExpandedSections.current) {
      setExpandedSections(previousExpandedSections.current);
      previousExpandedSections.current = null;
    }
  }, [canCompareDifferences, diffsOnlyEnabled]);

  useEffect(() => {
    if (summaryExpanded && summaryCards.length === 0) {
      setSummaryExpanded(false);
    }
  }, [summaryCards.length, summaryExpanded]);

  // -------------------- Handlers --------------------
  const handleShow = (hiddenId: string) => {
    setHidden((prev) => prev.filter((id) => id !== hiddenId));
  };

  const handleHide = (colIdx: number) => {
    const executionId = selectedExecutionIds[colIdx];
    if (!hidden.includes(executionId)) {
      setHidden((prev) => [...prev, executionId]);
    }
  };

  const handleRemove = (colIdx: number) => {
    const executionId = selectedExecutionIds[colIdx];
    setSelectedExecutionIds(selectedExecutionIds.filter((id) => id !== executionId));
  };

  const handleDragStart = (colIdx: number) => {
    dragCol.current = colIdx;
  };

  const handleDragOver = (e: DragEvent, colIdx: number) => {
    e.preventDefault();
    setDragOverIdx(colIdx);
  };

  const handleDragLeave = () => {
    setDragOverIdx(null);
  };

  const handleDrop = (colIdx: number) => {
    if (dragCol.current === null || dragCol.current === colIdx) {
      setDragOverIdx(null);
      dragCol.current = null;
      return;
    }
    const newOrder = [...order];
    const fromIdx = newOrder.indexOf(dragCol.current);
    const toIdx = newOrder.indexOf(colIdx);
    newOrder.splice(toIdx, 0, newOrder.splice(fromIdx, 1)[0]);
    setOrder(newOrder);
    setDragOverIdx(null);
    dragCol.current = null;
  };

  const toggleSection = (sectionKey: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionKey]: !prev[sectionKey],
    }));
  };

  const handleDiffOnlyToggle = (checked: boolean) => {
    setDiffsOnlyEnabled(checked);

    if (checked) {
      previousExpandedSections.current = expandedSections;
      setExpandedSections(
        compareSections.reduce<Record<string, boolean>>((nextState, section) => {
          nextState[section.key] = section.hasDiffs;
          return nextState;
        }, {}),
      );
      return;
    }

    if (previousExpandedSections.current) {
      setExpandedSections(previousExpandedSections.current);
      previousExpandedSections.current = null;
    }
  };

  const handleInternalLinkClick = (
    event: MouseEvent<HTMLAnchorElement>,
    href: string | undefined,
  ) => {
    if (!href) {
      event.preventDefault();
      return;
    }

    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }

    event.preventDefault();
    navigate(href);
  };

  const renderCompareValue = (
    sectionKey: string,
    row: CompareMetricRow,
    value: unknown,
    colIdx: number,
  ) => {
    if (sectionKey === 'configuration' && row.label === 'Case Name') {
      const caseId = getExecutionProp(selectedExecutionIds[colIdx], 'caseId', '');
      const caseHref = caseId ? `/cases/${caseId}` : undefined;
      const textValue = value === null || value === undefined || value === '' ? '—' : String(value);

      if (caseHref) {
        return (
          <a
            href={caseHref}
            className="text-blue-700 transition hover:underline"
            title={`Go to case details for ${textValue}`}
            onClick={(event) => {
              handleInternalLinkClick(event, caseHref);
            }}
          >
            <TableCellText value={textValue} lines={2} fullValueMode="tooltip" />
          </a>
        );
      }

      return <TableCellText value={textValue} lines={2} fullValueMode="tooltip" />;
    }

    if (
      row.renderMode === 'rich' ||
      sectionKey === 'locations' ||
      sectionKey === 'diagnostics' ||
      sectionKey === 'performance'
    ) {
      return <div className="max-w-full min-w-0 break-words">{renderCellValue(value)}</div>;
    }

    const lines =
      sectionKey === 'notes' || sectionKey === 'keyFeatures' || sectionKey === 'knownIssues'
        ? 3
        : 2;
    const textValue = value === null || value === undefined || value === '' ? '—' : String(value);

    return <TableCellText value={textValue} lines={lines} fullValueMode="tooltip" />;
  };

  const visibleValueWidth = Math.max(visibleColumns.length, 1) * VALUE_COLUMN_WIDTH;
  const tableMinWidth = LABEL_COLUMN_WIDTH + visibleValueWidth;

  // -------------------- Render --------------------
  if (selectedExecutionIds.length === 0) {
    return (
      <div className="max-w-screen-2xl mx-auto p-8 text-center text-gray-600">
        <p className="text-lg mb-4">{emptyStateMessage}</p>
        <a
          href={emptyStateActionHref}
          className="inline-block px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
        >
          {emptyStateActionLabel}
        </a>
      </div>
    );
  }

  return (
    <div className={embedded ? 'w-full' : 'w-full bg-white'}>
      <div className={embedded ? 'w-full' : 'mx-auto max-w-[1800px] px-4 py-8 sm:px-6'}>
        {showHeader ? (
          <header className="mb-6">
            <h1 className="mb-2 text-3xl font-bold">{title}</h1>
            <p className="text-gray-600">{description}</p>
          </header>
        ) : null}

        {contextNotice}

        <CompareToolbar
          backLabel={backLabel}
          canCompareDifferences={canCompareDifferences}
          changedSectionCount={changedSectionCount}
          diffsEnabled={diffsEnabled}
          diffsOnlyEnabled={diffsOnlyEnabled}
          onDiffOnlyToggle={handleDiffOnlyToggle}
          onDiffToggle={setDiffsEnabled}
          onSummaryToggle={() => setSummaryExpanded((prev) => !prev)}
          executionCount={selectedExecutionIds.length}
          onBackToBrowse={onBack}
          summaryExpanded={summaryExpanded}
          summaryHighlightCount={summaryCards.length}
          toolbarDescription={
            toolbarDescription ??
            (embedded
              ? undefined
              : 'Sticky controls keep cross-case compare actions, summary, and diff filters visible while reviewing execution metadata.')
          }
          totalChangedRows={totalChangedRows}
        />

        {summaryExpanded && (
          <section className="mt-4 rounded-2xl border border-blue-200 bg-blue-50/60 p-4 shadow-sm">
            <div id="compare-change-summary">
              <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-800">
                    Change Summary
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    Compact diff summary for the highest-signal fields across selected executions.
                  </p>
                </div>
                <Badge
                  variant="outline"
                  className="self-start border-blue-200 bg-white text-slate-700"
                >
                  {summaryCards.length} highlight{summaryCards.length === 1 ? '' : 's'}
                </Badge>
              </div>

              {visibleOrder.length === 0 ? (
                <p className="mt-4 text-sm text-slate-600">
                  All selected executions are hidden. Unhide one or more executions to review
                  changes.
                </p>
              ) : summaryCards.length === 0 ? (
                <p className="mt-4 text-sm text-slate-600">
                  No high-signal differences across visible executions.
                </p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <div
                    className="min-w-max rounded-lg border border-white/80 bg-white/90 shadow-sm"
                    style={{ minWidth: 280 + visibleOrder.length * 220 }}
                  >
                    <div className="flex border-b bg-blue-50/70 text-xs font-semibold uppercase tracking-wide text-slate-600">
                      <div className="shrink-0 px-4 py-3" style={{ width: 280 }}>
                        Field
                      </div>
                      {visibleColumns.map((column) => (
                        <div
                          key={`summary-header-${column.executionId}`}
                          className="shrink-0 border-l px-4 py-3"
                          style={{ width: 220 }}
                        >
                          <TableCellText
                            value={column.executionHeader}
                            lines={1}
                            mono
                            className="text-[11px] text-slate-600"
                            fullValueMode="tooltip"
                          />
                        </div>
                      ))}
                    </div>

                    {summaryCards.map((card) => (
                      <div key={card.key} className="flex border-t first:border-t-0">
                        <div
                          className="shrink-0 px-4 py-3 text-sm font-semibold text-slate-800"
                          style={{ width: 280 }}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span>{card.label}</span>
                            <span className="text-xs font-medium text-slate-500">
                              {card.uniqueValueCount} distinct
                            </span>
                          </div>
                        </div>

                        {visibleColumns.map((column) => (
                          <div
                            key={`${card.key}-${column.executionId}`}
                            className="shrink-0 border-l px-4 py-3"
                            style={{ width: 220 }}
                          >
                            <TableCellText
                              value={card.values[column.colIdx]}
                              lines={3}
                              className="text-sm text-slate-900"
                              fullValueMode="tooltip"
                            />
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Show Hidden Executions  */}
        <section
          aria-label="Show hidden executions"
          className={`mb-2 mt-4 flex min-h-[2.75rem] flex-wrap items-center gap-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-3 py-2${
            hidden.length === 0 ? ' invisible' : ''
          }`}
          style={{ minHeight: '2.75rem' }}
        >
          {hidden.length > 0 && (
            <>
              <span className="text-sm font-medium text-slate-600">Hidden executions:</span>
              {hidden.map((hiddenId) => {
                const idx = selectedExecutionIds.indexOf(hiddenId);
                const headerName = headers[idx] ?? hiddenId;

                return (
                  <button
                    key={hiddenId}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:bg-blue-50"
                    onClick={() => handleShow(hiddenId)}
                    type="button"
                  >
                    {headerName} <span className="ml-1 text-blue-600 font-bold">+</span>
                  </button>
                );
              })}
              <button
                className="ml-1 rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white transition hover:bg-slate-700"
                onClick={() => setHidden([])}
                type="button"
              >
                Unhide All
              </button>
            </>
          )}
        </section>

        {/* Table */}
        <div className="max-h-[calc(100vh-12rem)] overflow-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="min-w-max" style={{ minWidth: tableMinWidth }}>
            <div className="sticky top-0 z-20 flex border-b border-slate-200 bg-slate-100">
              <div
                className="sticky left-0 z-30 shrink-0 border-r border-slate-200 bg-slate-100 px-4 py-3 text-xs font-semibold uppercase text-slate-600 shadow-sm"
                style={{ width: LABEL_COLUMN_WIDTH }}
              >
                <div className="flex h-full items-center justify-between gap-3">
                  <span>Field</span>
                  <Badge
                    variant="outline"
                    className="border-slate-300 bg-white text-[11px] text-slate-700"
                  >
                    {visibleColumns.length} visible
                  </Badge>
                </div>
              </div>

              {visibleColumns.map((column) => {
                const isDropTarget =
                  dragOverIdx === column.colIdx &&
                  dragCol.current !== null &&
                  dragCol.current !== column.colIdx;

                return (
                  <div
                    key={column.executionId}
                    className={`group relative shrink-0 border-r border-slate-200 bg-slate-100 px-4 py-3 transition ${
                      isDropTarget ? 'ring-2 ring-blue-400 ring-inset' : ''
                    }`}
                    draggable
                    onDragStart={() => handleDragStart(column.colIdx)}
                    onDragOver={(event) => handleDragOver(event, column.colIdx)}
                    onDragLeave={handleDragLeave}
                    onDrop={() => handleDrop(column.colIdx)}
                    style={{
                      opacity: dragCol.current === column.colIdx ? 0.55 : 1,
                      width: VALUE_COLUMN_WIDTH,
                    }}
                  >
                    <div className="flex items-start gap-3">
                      <GripVertical
                        className="mt-0.5 h-4 w-4 shrink-0 cursor-grab text-slate-400"
                        aria-hidden="true"
                      />
                      <div className="min-w-0 flex-1">
                        <a
                          href={column.executionHref}
                          className="block max-w-full font-mono text-sm font-semibold text-blue-700 transition hover:underline"
                          title={`Go to details for ${column.executionHeader}`}
                          onClick={(event) => {
                            handleInternalLinkClick(event, column.executionHref);
                          }}
                        >
                          <TableCellText
                            value={column.executionHeader}
                            lines={1}
                            fullValueMode="tooltip"
                          />
                        </a>
                        {column.caseHref ? (
                          <a
                            href={column.caseHref}
                            className="mt-1 block text-xs text-slate-600 transition hover:text-blue-700 hover:underline"
                            title={`Go to case details for ${column.caseName}`}
                            onClick={(event) => {
                              handleInternalLinkClick(event, column.caseHref);
                            }}
                          >
                            <TableCellText
                              value={column.caseName}
                              lines={1}
                              fullValueMode="tooltip"
                            />
                          </a>
                        ) : (
                          <TableCellText
                            value={column.caseName}
                            lines={1}
                            className="mt-1 text-xs text-slate-600"
                            fullValueMode="tooltip"
                          />
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                        <button
                          type="button"
                          aria-label={`Hide ${column.executionHeader}`}
                          className="rounded-full border border-slate-200 bg-white p-1.5 text-slate-500 transition hover:border-amber-300 hover:bg-amber-50 hover:text-amber-700"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleHide(column.colIdx);
                          }}
                          title="Hide"
                        >
                          <EyeOff className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          aria-label={`Remove ${column.executionHeader}`}
                          className="rounded-full border border-slate-200 bg-white p-1.5 text-slate-500 transition hover:border-red-300 hover:bg-red-50 hover:text-red-700"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleRemove(column.colIdx);
                          }}
                          title="Remove"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}

              {visibleColumns.length === 0 && (
                <div
                  className="shrink-0 border-r border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-500"
                  style={{ width: visibleValueWidth }}
                >
                  Unhide an execution to restore compare columns.
                </div>
              )}
            </div>

            {compareSections.map((section) => {
              const rowsToRender = diffsOnlyEnabled ? section.diffRows : section.rows;
              const sectionSupportsDiffBadges = section.rows.some((row) => row.diffable !== false);

              return (
                <Fragment key={section.key}>
                  <button
                    className={`flex w-full border-b border-slate-200 text-left transition focus:outline-none ${
                      expandedSections[section.key]
                        ? 'bg-slate-100 text-slate-900'
                        : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
                    }`}
                    onClick={() => toggleSection(section.key)}
                    aria-expanded={expandedSections[section.key]}
                    aria-controls={`section-${section.key}`}
                    type="button"
                    style={{ minWidth: tableMinWidth }}
                  >
                    <span
                      className={`sticky left-0 z-10 flex shrink-0 items-start gap-3 border-r border-slate-200 px-4 py-3 shadow-sm ${
                        expandedSections[section.key] ? 'bg-slate-100' : 'bg-slate-50'
                      }`}
                      style={{ width: LABEL_COLUMN_WIDTH }}
                    >
                      <span
                        className="mt-1 transition-transform duration-200"
                        style={{
                          display: 'inline-block',
                          transform: expandedSections[section.key]
                            ? 'rotate(90deg)'
                            : 'rotate(0deg)',
                        }}
                      >
                        <ChevronRight size={16} strokeWidth={2} color="#4B5563" />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">
                          {section.label}
                        </span>
                        <span className="mt-1.5 flex flex-wrap items-center gap-2">
                          <Badge
                            variant="outline"
                            className="border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold uppercase tracking-normal text-slate-600"
                          >
                            {section.rows.length} row{section.rows.length === 1 ? '' : 's'} total
                          </Badge>
                          {section.hasDiffs ? (
                            <Badge
                              variant="outline"
                              className="border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-normal text-amber-800"
                            >
                              {section.diffCount} diff
                            </Badge>
                          ) : sectionSupportsDiffBadges ? (
                            <Badge
                              variant="outline"
                              className="border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold uppercase tracking-normal text-slate-500"
                            >
                              No changes
                            </Badge>
                          ) : null}
                        </span>
                      </span>
                    </span>
                    <span className="shrink-0 px-4 py-3" style={{ width: visibleValueWidth }} />
                  </button>

                  {expandedSections[section.key] && (
                    <div id={`section-${section.key}`}>
                      {rowsToRender.length === 0 ? (
                        <div className="flex border-b border-slate-200 bg-slate-50">
                          <div
                            className="sticky left-0 z-10 shrink-0 border-r border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-500 shadow-sm"
                            style={{ width: LABEL_COLUMN_WIDTH }}
                          >
                            No changed rows
                          </div>
                          <div
                            className="px-4 py-3 text-sm text-slate-500"
                            style={{ width: visibleValueWidth }}
                          >
                            No changed rows in this section for the currently visible executions.
                          </div>
                        </div>
                      ) : (
                        rowsToRender.map((row) => {
                          const rowIsDifferent = rowHasDiffs(row);
                          const isDiff = rowIsDifferent && (diffsEnabled || diffsOnlyEnabled);

                          return (
                            <div
                              key={row.label}
                              className={`flex border-b border-slate-200 ${
                                isDiff ? 'bg-amber-50' : 'bg-white'
                              }`}
                            >
                              <div
                                className={`sticky left-0 z-10 shrink-0 border-r border-slate-200 bg-white px-4 py-3 text-sm font-medium shadow-sm ${
                                  isDiff ? 'border-l-2 border-amber-300' : ''
                                }`}
                                style={{ width: LABEL_COLUMN_WIDTH }}
                              >
                                {row.label}
                              </div>

                              {visibleColumns.map((column) => {
                                const value = row.values[column.colIdx];

                                return (
                                  <div
                                    key={column.executionId}
                                    className="shrink-0 border-r border-slate-100 px-4 py-3 text-sm align-top last:border-r-0"
                                    style={{ width: VALUE_COLUMN_WIDTH }}
                                  >
                                    {renderCompareValue(section.key, row, value, column.colIdx)}
                                  </div>
                                );
                              })}
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export const ComparePage = ({
  selectedCaseExecutionIdsByCase,
  selectedExecutionIds,
  setSelectedExecutionIds,
}: ComparePageProps) => {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = location.state as CompareLocationState | null;
  const routedSelectedExecutionIds = normalizeSelectedExecutionIds(
    locationState?.selectedExecutionIds,
  );
  const routedSelectedExecutions = Array.isArray(locationState?.selectedExecutions)
    ? locationState.selectedExecutions
    : [];
  const shouldUseRoutedSelection =
    selectedExecutionIds.length < 2 && routedSelectedExecutionIds.length >= 2;
  const caseSelectionFallbackCandidates = Object.values(selectedCaseExecutionIdsByCase)
    .map((ids) => normalizeSelectedExecutionIds(ids))
    .filter((ids) => ids.length >= 2);
  const caseSelectionFallbackIds =
    caseSelectionFallbackCandidates.length === 1 ? caseSelectionFallbackCandidates[0] : [];
  const shouldUseCaseSelectionFallback =
    !shouldUseRoutedSelection &&
    selectedExecutionIds.length < 2 &&
    caseSelectionFallbackIds.length >= 2;
  const effectiveSelectedExecutionIds = shouldUseRoutedSelection
    ? routedSelectedExecutionIds
    : shouldUseCaseSelectionFallback
      ? caseSelectionFallbackIds
      : selectedExecutionIds;
  const detailQueries = useQueries({
    queries: effectiveSelectedExecutionIds.map((executionId) => ({
      queryKey: catalogQueryKeys.executions.detail(executionId),
      queryFn: () => getExecutionById(executionId),
      initialData: routedSelectedExecutions.find((execution) => execution.id === executionId),
    })),
  });
  const effectiveSelectedExecutions = detailQueries
    .map((query) => query.data)
    .filter((execution): execution is ExecutionOut => execution != null);

  useEffect(() => {
    if (!shouldUseRoutedSelection && !shouldUseCaseSelectionFallback) {
      return;
    }

    setSelectedExecutionIds(effectiveSelectedExecutionIds);
  }, [
    effectiveSelectedExecutionIds,
    setSelectedExecutionIds,
    shouldUseCaseSelectionFallback,
    shouldUseRoutedSelection,
  ]);

  return (
    <CompareWorkspace
      key="global-compare"
      selectedExecutionIds={effectiveSelectedExecutionIds}
      setSelectedExecutionIds={setSelectedExecutionIds}
      selectedExecutions={effectiveSelectedExecutions}
      onBack={() => navigate('/browse')}
    />
  );
};
