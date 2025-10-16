import { ChevronRight } from 'lucide-react';
import { Fragment, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { AIFloatingButton } from '@/pages/Compare/AIFloatingButton';
import CompareToolbar from '@/pages/Compare/CompareToolbar';
import { norm, renderCellValue } from '@/pages/Compare/utils';
import type { SimulationOut } from '@/types/index';
import { formatDate, getSimulationDuration } from '@/utils/utils';

interface CompareProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  selectedSimulations: SimulationOut[];
}

const Compare = ({
  selectedSimulationIds,
  setSelectedSimulationIds,
  selectedSimulations,
}: CompareProps) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();
  const handleButtonClick = () => navigate('/Browse');

  // -------------------- Global State --------------------
  const HIDDEN_KEY = 'compare_hidden_cols';

  // -------------------- Local State --------------------
  const [order, setOrder] = useState(selectedSimulationIds.map((_, i) => i));

  const simHeaders = selectedSimulationIds.map((id) => {
    const sim = selectedSimulations.find((s) => s.id === id);
    return sim?.name || id;
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

  // -------------------- Derived Data --------------------
  const visibleOrder = order.filter((colIdx) => !hidden.includes(selectedSimulationIds[colIdx]));

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
  ) => {
    const values = selectedSimulationIds.map((id) => {
      const sim = selectedSimulations.find((s) => s.id === id);
      if (!sim) return fallback;
      return (sim[prop] ?? fallback) as SimulationOut[T];
    });

    return { label, values };
  };

  const makeGroupedMetricRow = (label: string, kind: string, fallback: unknown[] = []) => {
    const values = selectedSimulationIds.map((id) => {
      const sim = selectedSimulations.find((s) => s.id === id);
      if (!sim) return fallback;

      return sim.groupedArtifacts[kind] ?? sim.groupedLinks[kind] ?? fallback;
    });

    return { label, values };
  };

  const rowHasDiffs = (vals: unknown[]): boolean => {
    if (visibleOrder.length <= 1) return false;

    const first = norm(vals[visibleOrder[0]]);

    for (let i = 1; i < visibleOrder.length; i++) {
      if (norm(vals[visibleOrder[i]]) !== first) return true;
    }

    return false;
  };

  const metrics = {
    configuration: [
      makeMetricRow('Simulation Name', 'name', ''),
      makeMetricRow('Case Name', 'caseName', ''),
      makeMetricRow('Model Version', 'gitTag', ''),
      makeMetricRow('Compset', 'compset', ''),
      makeMetricRow('Grid Name', 'gridName', ''),
      makeMetricRow('Grid Resolution', 'gridResolution', ''),
      makeMetricRow('Initialization Type', 'initializationType', ''),
      makeMetricRow('Compiler', 'compiler', ''),
      makeMetricRow('Parent Simulation ID', 'parentSimulationId', ''),
    ],
    modelSetup: [
      makeMetricRow('Simulation Type', 'simulationType', ''),
      makeMetricRow('Status', 'status', ''),
      makeMetricRow('Campaign ID', 'campaignId', ''),
      makeMetricRow('Experiment Type ID', 'experimentTypeId', ''),
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
    keyFeatures: [makeMetricRow('Key Features', 'keyFeatures', '')],
    knownIssues: [makeMetricRow('Known Issues', 'knownIssues', '')],
    locations: [
      makeGroupedMetricRow('Output Paths', 'output'),
      makeGroupedMetricRow('Archive Paths', 'archive'),
      makeGroupedMetricRow('Run Script Paths', 'runScript'),
      makeGroupedMetricRow('Batch Logs', 'batchLog'),
    ],
    diagnostics: [makeGroupedMetricRow('Diagnostic Links', 'diagnostic')],
    performance: [makeGroupedMetricRow('PACE Links', 'performance')],
    notes: [makeMetricRow('Notes', 'notesMarkdown', '')],
    versionControl: [
      makeMetricRow('Repository URL', 'gitRepositoryUrl', ''),
      makeMetricRow('Branch', 'gitBranch', ''),
      makeMetricRow('Version/Tag', 'gitTag', ''),
      makeMetricRow('Commit Hash', 'gitCommitHash', ''),
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

  // -------------------- Effects --------------------
  useEffect(() => {
    setHidden((prev) => prev.filter((id) => selectedSimulationIds.includes(id)));
  }, [selectedSimulationIds]);

  useEffect(() => {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify(hidden));
  }, [hidden]);

  useEffect(() => {
    setHeaders(
      selectedSimulationIds.map((id) => selectedSimulations.find((s) => s.id === id)?.name || id),
    );
    setOrder(selectedSimulationIds.map((_, i) => i));
  }, [selectedSimulationIds, selectedSimulations]);

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
      <div className="mx-auto max-w-[1440px] px-6 py-8">
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

        {/* Highlight Differences */}
        <div className="mt-3 mb-2 flex items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={diffsEnabled}
              onChange={(e) => setDiffsEnabled(e.target.checked)}
            />
            <span className="select-none">Highlight differences</span>
          </label>
          {diffsEnabled && (
            <span className="text-xs text-gray-500">
              Rows that differ across visible simulations are highlighted.
            </span>
          )}
        </div>

        {/* Show Hidden Simulations  */}
        <section
          aria-label="Show hidden simulations"
          className={`mb-2 flex gap-2 items-center min-h-[2.25rem]${hidden.length === 0 ? ' invisible' : ''}`}
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
          <div className="min-w-[72rem]">
            {/* Column headers */}
            <div className="flex border-b bg-gray-100 font-semibold text-sm">
              <div className="sticky-col shrink-0 w-64 px-4 py-2 border-r z-10 bg-white"></div>
              {order
                .filter((colIdx) => !hidden.includes(selectedSimulationIds[colIdx]))
                .map((colIdx) => (
                  <div
                    key={colIdx}
                    className="flex-1 min-w-[12rem] px-4 py-2 text-center cursor-default relative group"
                    draggable
                    onDragStart={() => handleDragStart(colIdx)}
                    onDragOver={(e) => handleDragOver(e, colIdx)}
                    onDragLeave={() => handleDragLeave()}
                    onDrop={() => handleDrop(colIdx)}
                    style={{
                      opacity: dragCol.current === colIdx ? 0.5 : 1,
                      zIndex: dragOverIdx === colIdx ? 20 : undefined,
                    }}
                  >
                    <div className="flex items-center justify-center gap-2">
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
                      <a
                        href={`/simulations/${selectedSimulationIds[colIdx]}`}
                        className="text-lg font-semibold text-blue-700 hover:underline transition"
                        tabIndex={0}
                        title={`Go to details for ${headers[colIdx]}`}
                        onClick={(e) => {
                          e.preventDefault();
                          navigate(`/simulations/${selectedSimulationIds[colIdx]}`);
                        }}
                      >
                        {headers[colIdx]}
                      </a>
                    </div>
                    <button
                      type="button"
                      aria-label={`Hide ${headers[colIdx]}`}
                      className="absolute top-1 right-8 text-gray-400 hover:text-yellow-600 bg-white rounded-full w-6 h-6 flex items-center justify-center border border-gray-200 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleHide(order.findIndex((v) => v === colIdx));
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
                        handleRemove(order.findIndex((v) => v === colIdx));
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
            {Object.entries(metrics).map(([sectionKey, rows]) => (
              <Fragment key={sectionKey}>
                <div
                  className={`flex border-t items-center transition-all ${
                    expandedSections[sectionKey]
                      ? 'border-l-2 border-blue-500 bg-gray-100'
                      : 'bg-gray-50'
                  }`}
                  style={{
                    ...(expandedSections[sectionKey]
                      ? { borderLeftWidth: '3px', borderTopWidth: '2px' }
                      : {}),
                  }}
                >
                  <button
                    className={`sticky-col w-64 px-4 py-3 font-semibold border-r text-lg uppercase tracking-wide bg-white z-10 flex items-center focus:outline-none ${
                      expandedSections[sectionKey] ? 'text-gray-900' : 'text-gray-600'
                    }`}
                    onClick={() => toggleSection(sectionKey)}
                    aria-expanded={expandedSections[sectionKey]}
                    aria-controls={`section-${sectionKey}`}
                    type="button"
                  >
                    <span
                      className="mr-2 transition-transform duration-200"
                      style={{
                        display: 'inline-block',
                        transform: expandedSections[sectionKey] ? 'rotate(90deg)' : 'rotate(0deg)',
                      }}
                    >
                      <ChevronRight size={16} strokeWidth={2} color="#4B5563" />
                    </span>
                    {sectionKey
                      .replace(/([A-Z])/g, ' $1')
                      .replace(/^./, (str) => str.toUpperCase())}
                  </button>
                </div>

                {expandedSections[sectionKey] && (
                  <div id={`section-${sectionKey}`}>
                    {rows.map((row, rowIdx) => {
                      const isDiff = diffsEnabled && rowHasDiffs(row.values);
                      return (
                        <div
                          key={rowIdx}
                          className={`flex border-t ${isDiff ? 'bg-amber-50' : ''}`}
                        >
                          {/* metric/label cell */}
                          <div
                            className={`sticky-col w-64 px-4 py-2 font-medium text-sm border-r bg-white z-10 ${
                              isDiff ? 'border-l-2 border-amber-400' : ''
                            }`}
                          >
                            {row.label}
                          </div>

                          {/* values */}
                          {visibleOrder.map((colIdx) => {
                            const value = row.values[colIdx];
                            return (
                              <div
                                key={colIdx}
                                className="flex-1 min-w-[12rem] px-4 py-2 text-sm break-words"
                              >
                                {renderCellValue(value)}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                )}
              </Fragment>
            ))}

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

export default Compare;
