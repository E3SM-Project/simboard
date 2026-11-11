import { ChevronRight, EyeOff, X } from 'lucide-react';
import {
  type DragEvent,
  type MouseEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TableCellText } from '@/components/ui/table-cell-text';
import { norm, renderCellValue } from '@/features/compare/utils';
import { reconcileExecutionOrder } from '@/lib/catalog/executionDiscovery';
import { repositoryBrowserUrl } from '@/lib/catalog/repository';
import { caseDetailsPath, executionDetailsPath } from '@/lib/catalog/urls';
import { type ArtifactKind, getArtifactsByKind } from '@/types/artifact';
import type { ExecutionOut } from '@/types/index';
import { formatDate, formatModelDate, getModelDateDuration } from '@/utils/utils';

interface CompareWorkspaceProps {
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
  selectedExecutions: ExecutionOut[];
  contextNotice?: ReactNode;
  hiddenStorageKey?: string;
}

interface CompareMetricRow {
  label: string;
  values: unknown[];
  renderMode?: 'default' | 'rich' | 'repository';
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

const arraysEqual = <T,>(left: T[], right: T[]) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

export const CompareWorkspace = ({
  contextNotice,
  hiddenStorageKey = 'compare_hidden_cols',
  selectedExecutionIds,
  setSelectedExecutionIds,
  selectedExecutions,
}: CompareWorkspaceProps) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();

  // -------------------- Global State --------------------
  // -------------------- Local State --------------------
  const [orderedIds, setOrderedIds] = useState(selectedExecutionIds);
  const displayIds = reconcileExecutionOrder(orderedIds, selectedExecutionIds);
  const order = displayIds.map((id) => selectedExecutionIds.indexOf(id));
  const setOrder = (update: number[] | ((current: number[]) => number[])) => {
    const nextOrder = typeof update === 'function' ? update(order) : update;
    setOrderedIds(nextOrder.map((index) => selectedExecutionIds[index]));
  };

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
  const [diffsOnlyEnabled, setDiffsOnlyEnabled] = useState(true);

  // -------------------- Derived Data --------------------
  const visibleOrder = order.filter(
    (colIdx) =>
      colIdx < selectedExecutionIds.length &&
      !hidden.includes(selectedExecutionIds[colIdx]) &&
      selectedExecutions.some((execution) => execution.id === selectedExecutionIds[colIdx]),
  );
  const canCompareDifferences = visibleOrder.length > 1;
  const showDifferencesOnly = diffsOnlyEnabled && canCompareDifferences;

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

  const getExecutionById = (id: string) =>
    selectedExecutions.find((execution) => execution.id === id);

  const visibleColumns = visibleOrder.map((colIdx) => {
    const executionId = selectedExecutionIds[colIdx];
    const execution = getExecutionById(executionId);

    return {
      caseHref:
        execution?.machine?.name && execution.hpcUsername
          ? caseDetailsPath({
              machineName: execution.machine.name,
              hpcUsername: execution.hpcUsername,
              caseName: execution.caseName,
            })
          : undefined,
      caseName: execution?.caseName || '—',
      colIdx,
      executionHeader: headers[colIdx],
      executionHref:
        execution?.machine?.name && execution.hpcUsername
          ? executionDetailsPath({
              machineName: execution.machine.name,
              hpcUsername: execution.hpcUsername,
              caseName: execution.caseName,
              executionId: execution.executionId,
            })
          : undefined,
      executionId,
    };
  });

  const metrics = {
    configuration: [
      makeMetricRow('Case Name', 'caseName', ''),
      makeMetricRow('Model Version', 'gitTag', ''),
      makeMetricRow('Compset Long Name', 'compsetLongName', ''),
      makeMetricRow('Grid Alias', 'gridAlias', ''),
      makeMetricRow('Grid Long Name', 'gridLongName', ''),
      makeMetricRow('Initialization Type', 'initializationType', ''),
      makeMetricRow('Compiler', 'compiler', ''),
    ],
    modelSetup: [
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
      makeMetricRow('Git Repository', 'gitRepositorySource', '', 'repository'),
      makeMetricRow('Git Branch', 'gitBranch', ''),
      makeMetricRow('Git Tag', 'gitTag', ''),
      makeMetricRow('Git Commit Hash', 'gitCommitHash', ''),
      makeMetricRow('HPC Username', 'hpcUsername', ''),
    ],
    locations: [
      makeArtifactMetricRow('Output Paths', 'output'),
      makeArtifactMetricRow('Short-Term Archive Paths', 'archive'),
      makeArtifactMetricRow('Run Script Paths', 'run_script'),
      makeArtifactMetricRow('Post-processing Scripts', 'postprocessing_script'),
    ],
  };

  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(Object.keys(metrics).map((section) => [section, true])),
  );

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

  const totalChangedRows = compareSections.reduce((sum, section) => sum + section.diffCount, 0);

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
      setOrderedIds((previous) => reconcileExecutionOrder(previous, selectedExecutionIds));
      previousSelectedExecutionIds.current = selectedExecutionIds;
    }
  }, [selectedExecutionIds, selectedExecutions]);

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
      const execution = getExecutionById(selectedExecutionIds[colIdx]);
      const caseHref =
        execution?.machine?.name && execution.hpcUsername
          ? caseDetailsPath({
              machineName: execution.machine.name,
              hpcUsername: execution.hpcUsername,
              caseName: execution.caseName,
            })
          : undefined;
      const textValue = value === null || value === undefined || value === '' ? '—' : String(value);

      if (caseHref) {
        return (
          <a
            href={caseHref}
            className="text-blue-600 transition hover:underline"
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

    if (row.renderMode === 'repository') {
      const source = typeof value === 'string' ? value : null;
      const href = repositoryBrowserUrl(source);
      const text = <TableCellText value={source || '—'} lines={2} fullValueMode="tooltip" />;

      return href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 hover:underline"
        >
          {text}
        </a>
      ) : (
        text
      );
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
  return (
    <div className="flex min-h-0 flex-col gap-4" data-case-comparison>
      {contextNotice}
      {selectedExecutionIds.length < 2 ? (
        <Alert variant="warning">
          Select at least two executions using Edit executions to compare.
        </Alert>
      ) : null}
      {selectedExecutionIds.length >= 2 && selectedExecutions.length < 2 ? (
        <p className="text-sm text-muted-foreground" role="status">
          Comparison needs details for at least two selected executions.
        </p>
      ) : null}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-muted-foreground">
          <span className="font-medium text-foreground" aria-live="polite">
            {visibleColumns.length} execution{visibleColumns.length === 1 ? '' : 's'} ·{' '}
            {totalChangedRows} differing field{totalChangedRows === 1 ? '' : 's'}
          </span>
          <span className="ml-3 inline-block">Compared against the reference execution</span>
        </p>
        <div
          className="inline-flex rounded-lg border bg-muted-subtle p-1"
          role="group"
          aria-label="Comparison fields"
        >
          <Button
            size="sm"
            variant={showDifferencesOnly ? 'default' : 'ghost'}
            aria-pressed={showDifferencesOnly}
            disabled={!canCompareDifferences}
            onClick={() => setDiffsOnlyEnabled(true)}
          >
            Differences ({totalChangedRows})
          </Button>
          <Button
            size="sm"
            variant={!showDifferencesOnly ? 'default' : 'ghost'}
            aria-pressed={!showDifferencesOnly}
            onClick={() => setDiffsOnlyEnabled(false)}
          >
            All fields
          </Button>
        </div>
      </div>
      {hidden.length > 0 ? (
        <div
          className="flex shrink-0 flex-wrap items-center gap-2 text-sm"
          aria-label="Show hidden executions"
        >
          <span>Hidden executions:</span>
          {hidden.map((id) => (
            <Button key={id} size="sm" variant="outline" onClick={() => handleShow(id)}>
              Show {headers[selectedExecutionIds.indexOf(id)] ?? id}
            </Button>
          ))}
        </div>
      ) : null}
      <div
        className="min-h-0 overflow-auto rounded-lg border border-border"
        tabIndex={0}
        role="region"
        aria-label="Execution comparison"
      >
        <table
          className="w-full table-fixed border-separate border-spacing-0 text-left text-sm"
          style={{ minWidth: 180 + visibleColumns.length * 260 }}
        >
          <colgroup>
            <col style={{ width: 180 }} />
            {visibleColumns.map((column) => (
              <col key={column.executionId} />
            ))}
          </colgroup>
          <thead className="sticky top-0 z-20">
            <tr>
              <th
                scope="col"
                className="sticky left-0 z-30 border-b border-r bg-muted px-3 py-3 font-medium"
              >
                Field
              </th>
              {visibleColumns.map((column, index) => (
                <th
                  key={column.executionId}
                  scope="col"
                  className={`border-b border-r bg-muted px-3 py-3 align-top font-medium ${dragOverIdx === column.colIdx ? 'ring-2 ring-inset ring-blue-400' : ''}`}
                  draggable
                  onDragStart={() => handleDragStart(column.colIdx)}
                  onDragOver={(event) => handleDragOver(event, column.colIdx)}
                  onDragLeave={handleDragLeave}
                  onDrop={() => handleDrop(column.colIdx)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <a
                      href={column.executionHref}
                      onClick={(event) => handleInternalLinkClick(event, column.executionHref)}
                      className="min-w-0 break-all font-mono text-blue-600 hover:underline"
                    >
                      {column.executionHeader}
                    </a>
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        aria-label={`Hide ${column.executionHeader}`}
                        title="Hide execution (keep selected)"
                        className="rounded p-1 hover:bg-card"
                        onClick={() => handleHide(column.colIdx)}
                      >
                        <EyeOff size={14} />
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove ${column.executionHeader}`}
                        title="Remove execution from selection"
                        className="rounded p-1 hover:bg-card"
                        onClick={() => handleRemove(column.colIdx)}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                  {index === 0 ? (
                    <Badge variant="secondary" className="mt-1">
                      Reference
                    </Badge>
                  ) : (
                    <button
                      type="button"
                      className="mt-1 text-xs text-blue-600 hover:underline"
                      aria-label={`Use ${column.executionHeader} as reference`}
                      onClick={() =>
                        setOrder((current) => [
                          column.colIdx,
                          ...current.filter((item) => item !== column.colIdx),
                        ])
                      }
                    >
                      Use as reference
                    </button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          {compareSections.map((section) => {
            const rows = showDifferencesOnly ? section.diffRows : section.rows;
            if (rows.length === 0 || visibleColumns.length === 0) return null;

            return (
              <tbody key={section.key}>
                <tr>
                  <th
                    colSpan={visibleColumns.length + 1}
                    scope="colgroup"
                    className="border-b bg-muted-subtle text-foreground"
                  >
                    <button
                      type="button"
                      className="sticky left-0 inline-flex items-center gap-2 px-3 py-2 text-left"
                      aria-expanded={expandedSections[section.key]}
                      onClick={() => toggleSection(section.key)}
                    >
                      <ChevronRight
                        size={14}
                        className={expandedSections[section.key] ? 'rotate-90' : ''}
                      />
                      {section.label}
                      <span className="text-xs font-normal text-muted-foreground">
                        {section.diffCount} difference{section.diffCount === 1 ? '' : 's'}
                      </span>
                    </button>
                  </th>
                </tr>
                {expandedSections[section.key] &&
                  rows.map((row) => (
                    <tr key={row.label}>
                      <th
                        scope="row"
                        className="sticky left-0 z-10 border-b border-r bg-card px-3 py-2 align-top font-medium"
                      >
                        {row.label}
                      </th>
                      {visibleColumns.map((column) => {
                        const value = row.values[column.colIdx];
                        const changed =
                          row.diffable !== false &&
                          column.colIdx !== visibleOrder[0] &&
                          norm(value) !== norm(row.values[visibleOrder[0]]);

                        return (
                          <td
                            key={column.executionId}
                            data-different={changed || undefined}
                            className={`border-b border-r px-3 py-2 align-top ${changed ? 'bg-amber-50/70' : 'bg-card'}`}
                          >
                            {changed ? (
                              <span className="sr-only">Differs from reference column. </span>
                            ) : null}
                            {renderCompareValue(section.key, row, value, column.colIdx)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
              </tbody>
            );
          })}
        </table>
        {visibleColumns.length === 0 ? (
          <p className="p-4 text-muted-foreground">
            Unhide an execution to restore compare columns.
          </p>
        ) : canCompareDifferences && diffsOnlyEnabled && totalChangedRows === 0 ? (
          <p className="p-4 text-muted-foreground">No differences across visible executions.</p>
        ) : null}
      </div>
    </div>
  );
};
