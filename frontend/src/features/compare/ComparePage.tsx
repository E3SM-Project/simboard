import { ChevronRight } from 'lucide-react';
import { Fragment, type MouseEvent, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { TableCellText } from '@/components/ui/table-cell-text';
import { AIFloatingButton } from '@/features/compare/components/AIFloatingButton';
import CompareToolbar from '@/features/compare/components/CompareToolbar';
import { norm, renderCellValue } from '@/features/compare/utils';
import { type ArtifactKind, getArtifactsByKind } from '@/types/artifact';
import type { SimulationOut } from '@/types/index';
import { formatDate, getSimulationDuration } from '@/utils/utils';

interface ComparePageProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  selectedSimulations: SimulationOut[];
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

export const ComparePage = ({
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: ComparePageProps) => {
  const LABEL_COLUMN_WIDTH = 260;
  const VALUE_COLUMN_WIDTH = 320;

  // -------------------- Router --------------------
  const navigate = useNavigate();
  const handleButtonClick = () => navigate('/Browse');

  // -------------------- Global State --------------------
  const HIDDEN_KEY = 'compare_hidden_cols';

  // -------------------- Local State --------------------
  const [order, setOrder] = useState(selectedSimulationIds.map((_, i) => i));

  const simHeaders = selectedSimulationIds.map((id) => {
    const sim = selectedSimulations.find((s) => s.id === id);
    return sim?.executionId || id;
  });
  const [headers, setHeaders] = useState(simHeaders);

  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [hidden, setHidden] = useState<string[]>(() => {
    const stored = localStorage.getItem(HIDDEN_KEY);
    try {
      const parsed = stored ? JSON.parse(stored) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  const dragCol = useRef<number | null>(null);
  const [diffsEnabled, setDiffsEnabled] = useState(false);
  const [diffsOnlyEnabled, setDiffsOnlyEnabled] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const previousExpandedSections = useRef<Record<string, boolean> | null>(null);

  // -------------------- Derived Data --------------------
  const visibleOrder = order.filter((colIdx) => !hidden.includes(selectedSimulationIds[colIdx]));
  const canCompareDifferences = visibleOrder.length > 1;

  const getSimProp = <K extends keyof SimulationOut>(
    id: string,
    prop: K,
    fallback: SimulationOut[K] | '',
  ): SimulationOut[K] => {
    const sim = selectedSimulations.find((s) => s.id === id);
    return (sim?.[prop] ?? fallback) as SimulationOut[K];
  };

  const makeMetricRow = <T extends keyof SimulationOut>(
    label: string,
    prop: T,
    fallback: SimulationOut[T] | '' = '',
    renderMode: CompareMetricRow['renderMode'] = 'default',
    diffable = true,
  ): CompareMetricRow => {
    const values = selectedSimulationIds.map((id) => {
      const sim = selectedSimulations.find((s) => s.id === id);
      if (!sim) return fallback;
      return (sim[prop] ?? fallback) as SimulationOut[T];
    });

    return { label, values, renderMode, diffable };
  };

  const makeArtifactMetricRow = (
    label: string,
    kind: ArtifactKind,
    fallback: unknown[] = [],
    diffable = true,
  ): CompareMetricRow => {
    const values = selectedSimulationIds.map((id) => {
      const sim = selectedSimulations.find((s) => s.id === id);
      if (!sim) return fallback;

      return getArtifactsByKind(sim.artifacts, sim.groupedArtifacts, kind);
    });

    return { label, values, diffable };
  };

  const makeGroupedLinkMetricRow = (
    label: string,
    kind: string,
    fallback: unknown[] = [],
    diffable = true,
  ): CompareMetricRow => {
    const values = selectedSimulationIds.map((id) => {
      const sim = selectedSimulations.find((s) => s.id === id);
      if (!sim) return fallback;

      return sim.groupedLinks[kind] ?? fallback;
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

  const formatCompareDate = (date: string | null | undefined) => (date ? formatDate(date) : '—');

  const formatDateRange = (start: string | null | undefined, end: string | null | undefined) => {
    const startLabel = formatCompareDate(start);
    const endLabel = formatCompareDate(end);

    if (startLabel === '—' && endLabel === '—') {
      return '—';
    }

    return `${startLabel} -> ${endLabel}`;
  };

  const getSimulationById = (id: string) => selectedSimulations.find((sim) => sim.id === id);

  const buildVersionSummary = (simulation: SimulationOut | undefined) => {
    if (!simulation) return '—';

    const parts = [
      simulation.gitBranch || null,
      simulation.gitTag || null,
      simulation.gitCommitHash ? simulation.gitCommitHash.slice(0, 7) : null,
    ].filter(Boolean);

    return parts.length > 0 ? parts.join(' • ') : '—';
  };

  const buildConfigurationSummary = (simulation: SimulationOut | undefined) => {
    if (!simulation) return '—';

    const configBits = [
      simulation.compset || null,
      simulation.gridName || null,
      simulation.gridResolution || null,
    ]
      .filter(Boolean)
      .join(' • ');

    return configBits || '—';
  };

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
        values: selectedSimulationIds.map((id) => {
          const sim = selectedSimulations.find((s) => s.id === id);
          return sim?.machine?.name ?? '';
        }),
      },
      makeMetricRow('Branch', 'gitBranch', ''),
    ],
    timeline: [
      {
        label: 'Model Start',
        values: selectedSimulationIds.map((id) => {
          const date = getSimProp(id, 'simulationStartDate', '');
          return date ? formatDate(date as string) : '—';
        }),
      },
      {
        label: 'Model End',
        values: selectedSimulationIds.map((id) => {
          const date = getSimProp(id, 'simulationEndDate', '');
          return date ? formatDate(date as string) : '—';
        }),
      },
      {
        label: 'Duration',
        values: selectedSimulationIds.map((id) => {
          const start = getSimProp(id, 'simulationStartDate', '');
          const end = getSimProp(id, 'simulationEndDate', '');
          if (start && end) {
            try {
              return getSimulationDuration(start as string, end as string);
            } catch {
              return '—';
            }
          }
          return '—';
        }),
      },
      {
        label: 'Calendar Start',
        values: selectedSimulationIds.map((id) => {
          const date = getSimProp(id, 'runStartDate', '');
          return date ? formatDate(date as string) : '—';
        }),
      },
      {
        label: 'Calendar End Date',
        values: selectedSimulationIds.map((id) => {
          const date = getSimProp(id, 'runEndDate', '');
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
    keyFeatures: [makeMetricRow('Key Features', 'keyFeatures', '', 'default', false)],
    knownIssues: [makeMetricRow('Known Issues', 'knownIssues', '', 'default', false)],
    locations: [
      makeArtifactMetricRow('Output Paths', 'output'),
      makeArtifactMetricRow('Archive Paths', 'archive'),
      makeArtifactMetricRow('Run Script Paths', 'run_script'),
      makeArtifactMetricRow('Post-processing Scripts', 'postprocessing_script'),
    ],
    diagnostics: [makeGroupedLinkMetricRow('Diagnostic Links', 'diagnostic', [], false)],
    performance: [makeGroupedLinkMetricRow('PACE Links', 'performance', [], false)],
    notes: [makeMetricRow('Notes', 'notesMarkdown', '', 'default', false)],
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
      values: selectedSimulationIds.map((id) => getSimulationById(id)?.status || '—'),
    },
    {
      key: 'machine',
      label: 'Machine',
      values: selectedSimulationIds.map((id) => getSimulationById(id)?.machine?.name || '—'),
    },
    {
      key: 'provenance',
      label: 'Branch / Tag / Commit',
      values: selectedSimulationIds.map((id) => buildVersionSummary(getSimulationById(id))),
    },
    {
      key: 'configuration',
      label: 'Compset / Grid',
      values: selectedSimulationIds.map((id) => buildConfigurationSummary(getSimulationById(id))),
    },
    {
      key: 'dateRange',
      label: 'Model Date Range',
      values: selectedSimulationIds.map((id) => {
        const simulation = getSimulationById(id);

        return formatDateRange(simulation?.simulationStartDate, simulation?.simulationEndDate);
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
    setHidden((prev) => prev.filter((id) => selectedSimulationIds.includes(id)));
  }, [selectedSimulationIds]);

  useEffect(() => {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify(hidden));
  }, [hidden]);

  useEffect(() => {
    setHeaders(
      selectedSimulationIds.map(
        (id) => selectedSimulations.find((s) => s.id === id)?.executionId || id,
      ),
    );
    setOrder(selectedSimulationIds.map((_, i) => i));
  }, [selectedSimulationIds, selectedSimulations]);

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

  // -------------------- Handlers --------------------
  const handleShow = (hiddenId: string) => {
    setHidden((prev) => prev.filter((id) => id !== hiddenId));
  };

  const handleHide = (colIdx: number) => {
    const simId = selectedSimulationIds[colIdx];
    if (!hidden.includes(simId)) {
      setHidden((prev) => [...prev, simId]);
    }
  };

  const handleRemove = (colIdx: number) => {
    const simId = selectedSimulationIds[colIdx];
    setSelectedSimulationIds(selectedSimulationIds.filter((id) => id !== simId));
  };

  const handleDragStart = (colIdx: number) => {
    dragCol.current = colIdx;
  };

  const handleDragOver = (e: React.DragEvent, colIdx: number) => {
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
      const caseId = getSimProp(selectedSimulationIds[colIdx], 'caseId', '');
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

  // -------------------- Render --------------------
  if (selectedSimulationIds.length === 0) {
    return (
      <div className="max-w-screen-2xl mx-auto p-8 text-center text-gray-600">
        <p className="text-lg mb-4">No simulations selected for comparison.</p>
        <a
          href="/browse"
          className="inline-block px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
        >
          Go to Browse Page
        </a>
      </div>
    );
  }

  return (
    <div className="w-full bg-white">
      <div className="mx-auto max-w-[1800px] px-4 py-8 sm:px-6">
        <header className="mb-6">
          <h1 className="text-3xl font-bold mb-2">Compare Simulations</h1>
          <p className="text-gray-600">
            Compare multiple simulations side by side. Drag columns to reorder, hide or remove
            simulations, and expand sections for detailed metrics.
          </p>
        </header>

        <CompareToolbar
          simulationCount={selectedSimulationIds.length}
          onBackToBrowse={handleButtonClick}
        />

        <section className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-700">
                Diff-First Compare
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Surface changed rows and sections first, then fall back to full metadata review.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={diffsOnlyEnabled}
                  disabled={!canCompareDifferences}
                  onChange={(e) => handleDiffOnlyToggle(e.target.checked)}
                />
                <span className="select-none">Differences only</span>
              </label>
              <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={diffsEnabled}
                  disabled={!canCompareDifferences}
                  onChange={(e) => setDiffsEnabled(e.target.checked)}
                />
                <span className="select-none">Highlight differences</span>
              </label>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="border-slate-300 bg-white text-slate-700">
              {changedSectionCount} changed section{changedSectionCount === 1 ? '' : 's'}
            </Badge>
            <Badge variant="outline" className="border-slate-300 bg-white text-slate-700">
              {totalChangedRows} changed row{totalChangedRows === 1 ? '' : 's'}
            </Badge>
            {summaryCards.length > 0 && (
              <button
                type="button"
                onClick={() => setSummaryExpanded((prev) => !prev)}
                aria-expanded={summaryExpanded}
                aria-controls="compare-change-summary"
                className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                <span
                  className="transition-transform duration-200"
                  style={{ transform: summaryExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                >
                  <ChevronRight size={14} strokeWidth={2} color="currentColor" />
                </span>
                {summaryExpanded ? 'Hide summary' : `Show ${summaryCards.length} highlights`}
              </button>
            )}
            {diffsOnlyEnabled && (
              <Badge className="border-0 bg-slate-900 text-white shadow-none">Diff-only mode</Badge>
            )}
            {!canCompareDifferences && (
              <span className="text-xs text-slate-500">
                Unhide or add another simulation to compare differences.
              </span>
            )}
          </div>
        </section>

        {summaryExpanded && (
          <section className="mt-4 rounded-xl border border-blue-200 bg-blue-50/60 p-3">
            <div id="compare-change-summary">
              <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-800">
                    Change Summary
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    Compact diff summary for the highest-signal fields across selected simulations.
                  </p>
                </div>
                <Badge variant="outline" className="self-start border-blue-200 bg-white text-slate-700">
                  {summaryCards.length} highlight{summaryCards.length === 1 ? '' : 's'}
                </Badge>
              </div>

              {visibleOrder.length === 0 ? (
                <p className="mt-4 text-sm text-slate-600">
                  All selected simulations are hidden. Unhide one or more simulations to review
                  changes.
                </p>
              ) : summaryCards.length === 0 ? (
                <p className="mt-4 text-sm text-slate-600">
                  No high-signal differences across visible simulations.
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
                      {visibleOrder.map((colIdx) => (
                        <div
                          key={`summary-header-${selectedSimulationIds[colIdx]}`}
                          className="shrink-0 border-l px-4 py-3"
                          style={{ width: 220 }}
                        >
                          <TableCellText
                            value={headers[colIdx]}
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

                        {visibleOrder.map((colIdx) => (
                          <div
                            key={`${card.key}-${selectedSimulationIds[colIdx]}`}
                            className="shrink-0 border-l px-4 py-3"
                            style={{ width: 220 }}
                          >
                            <TableCellText
                              value={card.values[colIdx]}
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

        {/* Show Hidden Simulations  */}
        <section
          aria-label="Show hidden simulations"
          className={`mb-2 mt-4 flex min-h-[2.25rem] items-center gap-2${hidden.length === 0 ? ' invisible' : ''}`}
          style={{ height: '2.25rem' }}
        >
          {hidden.length > 0 && (
            <>
              <span className="text-sm text-gray-600">Hidden:</span>
              {hidden.map((hiddenId) => {
                const idx = selectedSimulationIds.indexOf(hiddenId);
                const headerName = headers[idx] ?? hiddenId;

                return (
                  <button
                    key={hiddenId}
                    className="px-2 py-1 text-xs bg-gray-200 rounded hover:bg-blue-200 transition"
                    onClick={() => handleShow(hiddenId)}
                    type="button"
                  >
                    {headerName} <span className="ml-1 text-blue-600 font-bold">+</span>
                  </button>
                );
              })}
              <button
                className="ml-2 px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 transition"
                onClick={() => setHidden([])}
                type="button"
              >
                Unhide All
              </button>
            </>
          )}
        </section>

        {/* Table */}
        <div className="overflow-x-auto">
          <div
            className="min-w-max"
            style={{ minWidth: LABEL_COLUMN_WIDTH + visibleOrder.length * VALUE_COLUMN_WIDTH }}
          >
            {/* Column headers */}
            <div className="flex border-b bg-gray-100 font-semibold text-sm">
              <div
                className="sticky left-0 z-10 shrink-0 border-r bg-white px-4 py-2 shadow-sm"
                style={{ width: LABEL_COLUMN_WIDTH }}
              ></div>
              {order
                .filter((colIdx) => !hidden.includes(selectedSimulationIds[colIdx]))
                .map((colIdx) => (
                  <div
                    key={colIdx}
                    className="relative shrink-0 cursor-default border-r px-4 py-3 group"
                    draggable
                    onDragStart={() => handleDragStart(colIdx)}
                    onDragOver={(e) => handleDragOver(e, colIdx)}
                    onDragLeave={() => handleDragLeave()}
                    onDrop={() => handleDrop(colIdx)}
                    style={{
                      opacity: dragCol.current === colIdx ? 0.5 : 1,
                      zIndex: dragOverIdx === colIdx ? 20 : undefined,
                      width: VALUE_COLUMN_WIDTH,
                    }}
                  >
                    <div className="flex items-start gap-2">
                      {/* Drag handle */}
                      <span
                        className="cursor-grab text-gray-400 hover:text-blue-600"
                        title="Drag to reorder"
                        style={{ display: 'inline-flex', alignItems: 'center' }}
                        tabIndex={-1}
                        aria-label="Drag handle"
                      >
                        <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                          <circle cx="5" cy="6" r="1.5" fill="currentColor" />
                          <circle cx="5" cy="10" r="1.5" fill="currentColor" />
                          <circle cx="5" cy="14" r="1.5" fill="currentColor" />
                          <circle cx="10" cy="6" r="1.5" fill="currentColor" />
                          <circle cx="10" cy="10" r="1.5" fill="currentColor" />
                          <circle cx="10" cy="14" r="1.5" fill="currentColor" />
                        </svg>
                      </span>
                      {/* Sim name clickable */}
                      <div className="min-w-0 pr-12 text-left">
                        {(() => {
                          const simulationHref = `/simulations/${selectedSimulationIds[colIdx]}`;
                          const caseId = getSimProp(selectedSimulationIds[colIdx], 'caseId', '');
                          const caseHref = caseId ? `/cases/${caseId}` : undefined;
                          const caseName = String(
                            getSimProp(selectedSimulationIds[colIdx], 'caseName', ''),
                          );

                          return (
                            <>
                              <a
                                href={simulationHref}
                                className="block max-w-full truncate font-mono text-sm font-semibold text-blue-700 transition hover:underline"
                                tabIndex={0}
                                title={`Go to details for ${headers[colIdx]}`}
                                onClick={(event) => {
                                  handleInternalLinkClick(event, simulationHref);
                                }}
                              >
                                {headers[colIdx]}
                              </a>
                              {caseHref ? (
                                <a
                                  href={caseHref}
                                  className="mt-1 block text-xs text-muted-foreground transition hover:text-blue-700 hover:underline"
                                  title={`Go to case details for ${caseName}`}
                                  onClick={(event) => {
                                    handleInternalLinkClick(event, caseHref);
                                  }}
                                >
                                  <TableCellText
                                    value={caseName}
                                    lines={2}
                                    className="mt-1 text-xs"
                                    fullValueMode="tooltip"
                                  />
                                </a>
                              ) : (
                                <TableCellText
                                  value={caseName}
                                  lines={2}
                                  className="mt-1 text-xs text-muted-foreground"
                                  fullValueMode="tooltip"
                                />
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </div>
                    <button
                      type="button"
                      aria-label={`Hide ${headers[colIdx]}`}
                      className="absolute top-1 right-8 text-gray-400 hover:text-yellow-600 bg-white rounded-full w-6 h-6 flex items-center justify-center border border-gray-200 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleHide(colIdx);
                      }}
                      tabIndex={0}
                      title="Hide"
                    >
                      &minus;
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove ${headers[colIdx]}`}
                      className="absolute top-1 right-2 text-gray-400 hover:text-red-600 bg-white rounded-full w-6 h-6 flex items-center justify-center border border-gray-200 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemove(colIdx);
                      }}
                      tabIndex={0}
                      title="Remove"
                    >
                      ×
                    </button>
                    {dragOverIdx === colIdx &&
                      dragCol.current !== null &&
                      dragCol.current !== colIdx && (
                        <div
                          className="absolute inset-0 pointer-events-none"
                          style={{
                            border: '2px dashed #2563eb',
                            borderRadius: 6,
                            boxSizing: 'border-box',
                          }}
                        />
                      )}
                  </div>
                ))}
            </div>

            {/* Sections + rows */}
            {compareSections.map((section) => {
              const rowsToRender = diffsOnlyEnabled ? section.diffRows : section.rows;

              return (
                <Fragment key={section.key}>
                  <div
                    className={`flex border-t items-center transition-all ${
                      expandedSections[section.key]
                        ? 'border-l-2 border-blue-500 bg-gray-100'
                        : 'bg-gray-50'
                    }`}
                    style={{
                      ...(expandedSections[section.key]
                        ? { borderLeftWidth: '3px', borderTopWidth: '2px' }
                        : {}),
                    }}
                  >
                    <button
                      className={`sticky left-0 z-10 shrink-0 flex items-center justify-between gap-2 border-r bg-white px-4 py-3 text-left text-base font-semibold shadow-sm focus:outline-none ${
                        expandedSections[section.key] ? 'text-gray-900' : 'text-gray-600'
                      }`}
                      style={{ width: LABEL_COLUMN_WIDTH }}
                      onClick={() => toggleSection(section.key)}
                      aria-expanded={expandedSections[section.key]}
                      aria-controls={`section-${section.key}`}
                      type="button"
                    >
                      <span className="flex min-w-0 items-center">
                        <span
                          className="mr-2 transition-transform duration-200"
                          style={{
                            display: 'inline-block',
                            transform: expandedSections[section.key]
                              ? 'rotate(90deg)'
                              : 'rotate(0deg)',
                          }}
                        >
                          <ChevronRight size={16} strokeWidth={2} color="#4B5563" />
                        </span>
                        <span className="truncate">{section.label}</span>
                      </span>
                      {section.diffCount > 0 && (
                        <Badge
                          variant="outline"
                          className="shrink-0 border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-normal text-blue-700"
                        >
                          {section.diffCount} diff
                        </Badge>
                      )}
                    </button>
                  </div>

                  {expandedSections[section.key] && (
                    <div id={`section-${section.key}`}>
                      {rowsToRender.length === 0 ? (
                        <div className="flex border-t bg-gray-50/80">
                          <div
                            className="sticky left-0 z-10 shrink-0 border-r bg-white px-4 py-3 text-sm font-medium text-gray-500 shadow-sm"
                            style={{ width: LABEL_COLUMN_WIDTH }}
                          >
                            No changed rows
                          </div>
                          <div
                            className="px-4 py-3 text-sm text-gray-500"
                            style={{ width: Math.max(visibleOrder.length, 1) * VALUE_COLUMN_WIDTH }}
                          >
                            No changed rows in this section for the currently visible simulations.
                          </div>
                        </div>
                      ) : (
                        rowsToRender.map((row) => {
                          const rowIsDifferent = rowHasDiffs(row);
                          const isDiff = rowIsDifferent && (diffsEnabled || diffsOnlyEnabled);

                          return (
                            <div
                              key={row.label}
                              className={`flex border-t ${isDiff ? 'bg-blue-50/70' : ''}`}
                            >
                              {/* metric/label cell */}
                              <div
                                className={`sticky left-0 z-10 shrink-0 border-r bg-white px-4 py-2 text-sm font-medium shadow-sm ${
                                  isDiff ? 'border-l-2 border-blue-300' : ''
                                }`}
                                style={{ width: LABEL_COLUMN_WIDTH }}
                              >
                                {row.label}
                              </div>

                              {/* values */}
                              {visibleOrder.map((colIdx) => {
                                const value = row.values[colIdx];

                                return (
                                  <div
                                    key={colIdx}
                                    className="shrink-0 px-4 py-2 text-sm align-top"
                                    style={{ width: VALUE_COLUMN_WIDTH }}
                                  >
                                    {renderCompareValue(section.key, row, value, colIdx)}
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

            {/* Comparison AI Floating Widget */}
            <AIFloatingButton
              selectedSimulations={selectedSimulations.filter((sim) =>
                selectedSimulationIds.includes(sim.id),
              )}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
