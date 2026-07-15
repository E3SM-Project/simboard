import { useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ExternalLink,
  Info,
  Search,
  Share2,
} from 'lucide-react';
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';

import { useAuth } from '@/auth/hooks/useAuth';
import { MarkdownContent } from '@/components/shared/MarkdownContent';
import { normalizeSelectedSimulationIds } from '@/components/shared/normalizeSelectedSimulationIds';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { updateCase } from '@/features/simulations/api/api';
import {
  formatCaseDate,
  formatCaseHashLabel,
  formatSimulationDateRange,
  getDefaultExpandedGroupKeys,
  getSimulationSummaryDateWindow,
  groupSimulationSummaries,
  matchesSimulationGroupFilter,
  MISSING_CASE_HASH_LABEL,
  type SimulationSummaryGroupFilter,
} from '@/features/simulations/caseUtils';
import { EditableExternalLinkList } from '@/features/simulations/components/EditableExternalLinkList';
import { MarkdownEditorField } from '@/features/simulations/components/MarkdownEditorField';
import {
  areResourceListsEqual,
  createEmptyRowErrors,
  type EditableLinkRow,
  getClientLinkRowErrors,
  hasAnyResourceRowErrors,
  mapLinkSaveValidationErrors,
  normalizeLinkRows,
  type ResourceRowFieldErrors,
  toEditableLinkRows,
  type ValidationDetail,
} from '@/features/simulations/externalLinkEditing';
import { useCase } from '@/features/simulations/hooks/useCase';
import { useCaseSimulations } from '@/features/simulations/hooks/useCaseSimulations';
import { invalidateCatalog } from '@/features/simulations/invalidateCatalog';
import { toast } from '@/hooks/use-toast';
import type {
  CaseDetailOut,
  CaseEditableField,
  CaseUpdate,
  ExternalLinkOut,
  SimulationListItemOut,
  SimulationSummaryOut,
} from '@/types';

const DetailField = ({
  label,
  value,
  mono = false,
  title,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  title?: string;
}) => (
  <div className="min-w-0 space-y-1" title={title}>
    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
      {label}
    </div>
    <div
      className={`truncate font-semibold text-slate-950 ${mono ? 'font-mono text-xs' : 'text-sm'}`}
    >
      {value}
    </div>
  </div>
);

const summarizeValues = (values: string[]) => {
  if (values.length === 0) return '—';
  if (values.length === 1) return values[0];

  return `${values[0]} +${values.length - 1}`;
};

const summarizeDistinctValues = (values: Array<string | null | undefined>) => {
  const uniqueValues = [...new Set(values.filter((value): value is string => Boolean(value)))];

  if (uniqueValues.length === 0) return '—';
  if (uniqueValues.length === 1) return uniqueValues[0];

  return `${uniqueValues[0]} +${uniqueValues.length - 1}`;
};

const formatRunDateRange = (startDate?: string | null, endDate?: string | null) => {
  if (!startDate && !endDate) return '—';

  return `${startDate?.slice(0, 10) ?? '—'} → ${endDate?.slice(0, 10) ?? '—'}`;
};

const formatGroupSimulationWindow = (simulations: SimulationSummaryOut[]) => {
  const { startDate, endDate } = getSimulationSummaryDateWindow(simulations);

  return `${formatCaseDate(startDate)} → ${formatCaseDate(endDate)}`;
};

const pluralize = (count: number, singular: string, plural = `${singular}s`) =>
  `${count} ${count === 1 ? singular : plural}`;

const RESOURCE_GROUP_LABELS: Record<ExternalLinkOut['kind'], string> = {
  diagnostic: 'Diagnostics',
  performance: 'Performance',
  docs: 'Documentation',
  other: 'Other resources',
};

const RESOURCE_KIND_DESCRIPTIONS: Record<ExternalLinkOut['kind'], string> = {
  diagnostic: 'zppy diagnostic output',
  performance: 'performance output',
  docs: 'linked documentation',
  other: 'linked resource',
};

interface CaseDetailsPageProps {
  renderCompareSection?: (options: { onClose: () => void }) => React.ReactNode;
  selectedCaseSimulationIdsByCase: Record<string, string[]>;
  setSelectedCaseSimulationIdsForCase: (caseId: string, ids: string[]) => void;
}

interface GroupSimulation {
  summary: SimulationSummaryOut;
  details?: SimulationListItemOut;
}

type SimulationViewMode = 'grouped' | 'flat';
type EditableFormState = Record<CaseEditableField, string>;
type CaseSaveError = {
  message: string;
  validationDetails: ValidationDetail[];
};

interface CaseDetailsLocationState {
  from?: string;
}

const MAX_SELECTION = 5;
const SCROLLABLE_GROUPS_THRESHOLD = 5;
const SCROLLABLE_FLAT_ROWS_THRESHOLD = 10;
const CASE_HASH_GROUPING_TOOLTIP =
  'Case name is human-readable label. Case hash identifies specific CIME case instance. Multiple hashes under one case name usually mean case was recreated or cloned.';
const GROUP_FILTER_OPTIONS: Array<{ value: SimulationSummaryGroupFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'multiRun', label: 'Multi-run' },
  { value: 'missing', label: 'Missing hash' },
];

const getGroupRunDateWindow = (simulations: GroupSimulation[]) => {
  const datedRuns = simulations.filter(
    ({ details }) => details?.runStartDate != null || details?.runEndDate != null,
  );

  if (datedRuns.length === 0) {
    return '—';
  }

  let earliestStart: string | null = null;
  let latestEnd: string | null = null;

  for (const { details } of datedRuns) {
    const runStartDate = details?.runStartDate ?? details?.runEndDate ?? null;
    const runEndDate = details?.runEndDate ?? details?.runStartDate ?? null;

    if (runStartDate && (earliestStart == null || runStartDate < earliestStart)) {
      earliestStart = runStartDate;
    }

    if (runEndDate && (latestEnd == null || runEndDate > latestEnd)) {
      latestEnd = runEndDate;
    }
  }

  return formatRunDateRange(earliestStart, latestEnd);
};

const countDistinctValues = (values: string[]) => new Set(values).size;

const CASE_EDIT_FIELDS: ReadonlyArray<CaseEditableField> = [
  'description',
  'keyFeatures',
  'knownIssues',
  'notesMarkdown',
];

const toEditableFormState = (caseRecord: CaseDetailOut): EditableFormState => ({
  description: caseRecord.description ?? '',
  keyFeatures: caseRecord.keyFeatures ?? '',
  knownIssues: caseRecord.knownIssues ?? '',
  notesMarkdown: caseRecord.notesMarkdown ?? '',
});

const normalizeEditableValue = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed || null;
};

const buildUpdatePayload = (
  caseRecord: CaseDetailOut,
  formState: EditableFormState,
  linkRows: EditableLinkRow[],
): CaseUpdate => {
  const payload: CaseUpdate = {};

  for (const field of CASE_EDIT_FIELDS) {
    const nextValue = normalizeEditableValue(formState[field]);
    const currentValue = caseRecord[field] ?? null;

    if (nextValue !== currentValue) {
      payload[field] = nextValue;
    }
  }

  const nextLinks = normalizeLinkRows(linkRows);
  const currentLinks = normalizeLinkRows(toEditableLinkRows(caseRecord.links, 'case'));
  if (!areResourceListsEqual(nextLinks, currentLinks)) {
    payload.links = nextLinks;
  }

  return payload;
};

const getUpdateError = (error: unknown): CaseSaveError => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (typeof detail === 'string') {
      return {
        message: detail,
        validationDetails: [],
      };
    }

    if (Array.isArray(detail)) {
      const validationDetails = detail
        .map((item) => {
          const message = typeof item?.msg === 'string' ? item.msg : null;
          const loc = Array.isArray(item?.loc)
            ? item.loc.filter(
                (part: unknown): part is string | number =>
                  typeof part === 'string' || typeof part === 'number',
              )
            : [];

          if (!message) return null;
          return {
            loc,
            msg: message,
          };
        })
        .filter((item): item is CaseSaveError['validationDetails'][number] => Boolean(item));

      if (validationDetails.length > 0) {
        return {
          message: 'One or more fields need attention before this case can be saved.',
          validationDetails,
        };
      }
    }
  }

  return {
    message: error instanceof Error ? error.message : 'Failed to update case.',
    validationDetails: [],
  };
};

const renderResourceLink = (link: ExternalLinkOut) => (
  <a
    key={link.id}
    href={link.url}
    target="_blank"
    rel="noreferrer"
    className="group flex w-full items-start justify-between gap-3 rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2.5 text-left transition-colors hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2"
    aria-label={`${link.label || link.url} (${RESOURCE_KIND_DESCRIPTIONS[link.kind]})`}
  >
    <div className="min-w-0 space-y-1">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <p className="break-all text-sm font-medium leading-5 text-slate-900">
          {link.label || link.url}
        </p>
        <Badge
          variant="outline"
          className="h-5 rounded-full border-slate-200 px-2 text-[11px] font-medium text-slate-600"
        >
          {RESOURCE_GROUP_LABELS[link.kind]}
        </Badge>
      </div>
      <p className="text-xs text-slate-500">{RESOURCE_KIND_DESCRIPTIONS[link.kind]}</p>
    </div>
    <div className="flex shrink-0 items-center gap-1 pt-0.5 text-slate-400 transition-colors group-hover:text-slate-600 group-focus-visible:text-slate-600">
      <ExternalLink className="h-3.5 w-3.5" />
      <span className="sr-only">Opens in a new tab</span>
    </div>
  </a>
);

const mergeRowFieldErrors = (
  primary: ResourceRowFieldErrors,
  secondary: ResourceRowFieldErrors,
): ResourceRowFieldErrors => ({
  ...primary,
  ...secondary,
});

export const CaseDetailsPage = ({
  renderCompareSection,
  selectedCaseSimulationIdsByCase,
  setSelectedCaseSimulationIdsForCase,
}: CaseDetailsPageProps) => {
  const queryClient = useQueryClient();
  const { id } = useParams<{ id: string }>();
  const {
    data: allSimulations,
    error: simulationsError,
    fetchNextPage,
    hasNextPage,
    isLoading: simulationsLoading,
    isFetchingNextPage,
    refetch: refetchSimulations,
    total: simulationTotal,
  } = useCaseSimulations(id);
  const location = useLocation();
  const compareSectionRef = useRef<HTMLDivElement | null>(null);
  const { user, isAuthenticated, loading: authLoading, loginWithGithub } = useAuth();
  const [viewMode, setViewMode] = useState<SimulationViewMode>('flat');
  const [groupFilterMode, setGroupFilterMode] = useState<SimulationSummaryGroupFilter>('all');
  const [caseHashQuery, setCaseHashQuery] = useState('');
  const [expandedGroupKeys, setExpandedGroupKeys] = useState<string[]>([]);
  const { data: fetchedCaseRecord, loading, error } = useCase(id ?? '');
  const [caseRecord, setCaseRecord] = useState<CaseDetailOut | null>(null);
  const [formState, setFormState] = useState<EditableFormState | null>(null);
  const [linkRows, setLinkRows] = useState<EditableLinkRow[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<CaseSaveError | null>(null);
  const [serverLinkRowErrors, setServerLinkRowErrors] = useState<ResourceRowFieldErrors[]>([]);
  const [saveSummaryMessage, setSaveSummaryMessage] = useState<string | null>(null);
  const [isCompareVisible, setIsCompareVisible] = useState(false);
  const currentPath = `${location.pathname}${location.search}`;
  const state = location.state as CaseDetailsLocationState | null;
  const backHref = typeof state?.from === 'string' ? state.from : '/cases';
  const simulationDetailsById = useMemo(
    () => new Map(allSimulations.map((simulation) => [simulation.id, simulation])),
    [allSimulations],
  );
  const rawSimulationGroups = useMemo(
    () => groupSimulationSummaries(caseRecord?.simulations ?? []),
    [caseRecord?.simulations],
  );
  const simulationGroups = useMemo(
    () =>
      rawSimulationGroups.map((group) => ({
        ...group,
        simulations: group.simulations.map((simulation) => ({
          summary: simulation,
          details: simulationDetailsById.get(simulation.id),
        })),
      })),
    [rawSimulationGroups, simulationDetailsById],
  );
  const sortedSimulationGroups = useMemo(() => {
    const getLatestRunTime = (simulations: GroupSimulation[]) => {
      const timestamps = simulations
        .map(
          ({ details, summary }) =>
            details?.runEndDate ??
            details?.runStartDate ??
            summary.simulationEndDate ??
            summary.simulationStartDate,
        )
        .map((value) => new Date(value).getTime())
        .filter((value) => !Number.isNaN(value));

      return timestamps.length > 0 ? Math.max(...timestamps) : 0;
    };

    return [...simulationGroups].sort((left, right) => {
      if (left.isFallback !== right.isFallback) {
        return left.isFallback ? 1 : -1;
      }

      const leftIsMultiRun = left.simulations.length > 1;
      const rightIsMultiRun = right.simulations.length > 1;
      if (leftIsMultiRun !== rightIsMultiRun) {
        return leftIsMultiRun ? -1 : 1;
      }

      const runDateDifference =
        getLatestRunTime(right.simulations) - getLatestRunTime(left.simulations);
      if (runDateDifference !== 0) {
        return runDateDifference;
      }

      return left.label.localeCompare(right.label);
    });
  }, [simulationGroups]);
  const caseHashGroupCount = rawSimulationGroups.filter((group) => !group.isFallback).length;
  const missingCaseHashCount =
    rawSimulationGroups.find((group) => group.isFallback)?.simulations.length ?? 0;
  const allRunsMissingCaseHash =
    caseRecord != null &&
    caseRecord.simulations.length > 0 &&
    caseHashGroupCount === 0 &&
    missingCaseHashCount > 0;
  const normalizedCaseHashQuery = caseHashQuery.trim().toLowerCase();
  const filteredSimulationGroups = useMemo(
    () =>
      sortedSimulationGroups.filter((group) => {
        if (!matchesSimulationGroupFilter(group, groupFilterMode)) {
          return false;
        }

        if (normalizedCaseHashQuery.length === 0) {
          return true;
        }

        if (group.isFallback) {
          return MISSING_CASE_HASH_LABEL.toLowerCase().includes(normalizedCaseHashQuery);
        }

        return (group.caseHash ?? '').toLowerCase().startsWith(normalizedCaseHashQuery);
      }),
    [groupFilterMode, normalizedCaseHashQuery, sortedSimulationGroups],
  );
  const filteredFlatSimulations = useMemo(
    () => filteredSimulationGroups.flatMap((group) => group.simulations),
    [filteredSimulationGroups],
  );
  const visibleSimulationIds = useMemo(
    () => new Set(filteredFlatSimulations.map(({ summary }) => summary.id)),
    [filteredFlatSimulations],
  );
  const caseSimulationIdSet = useMemo(
    () => new Set(caseRecord?.simulations.map((simulation) => simulation.id) ?? []),
    [caseRecord?.simulations],
  );
  const rawCaseSelectedSimulationIds = id
    ? normalizeSelectedSimulationIds(selectedCaseSimulationIdsByCase[id] ?? [])
    : [];
  const caseSelectedSimulationIds = rawCaseSelectedSimulationIds.filter((simulationId) =>
    caseSimulationIdSet.has(simulationId),
  );
  const caseSelectedSimulationCount = caseSelectedSimulationIds.length;
  const canShowCompare = caseSelectedSimulationCount >= 2;
  const shouldRenderCompare = canShowCompare && isCompareVisible;
  const selectedCurrentCaseSimulationIds = caseSelectedSimulationIds;
  const hiddenSelectedCount = selectedCurrentCaseSimulationIds.filter(
    (simulationId) => !visibleSimulationIds.has(simulationId),
  ).length;
  const hasActiveGroupFilters = groupFilterMode !== 'all' || normalizedCaseHashQuery.length > 0;
  const showGroupActions = filteredSimulationGroups.length > 1;
  const useScrollableGroupsPanel =
    viewMode === 'grouped'
      ? filteredSimulationGroups.length > SCROLLABLE_GROUPS_THRESHOLD
      : filteredFlatSimulations.length > SCROLLABLE_FLAT_ROWS_THRESHOLD;

  useEffect(() => {
    if (loading || (fetchedCaseRecord && fetchedCaseRecord.id !== id)) {
      setCaseRecord(null);
      setFormState(null);
      setLinkRows([]);
      setIsEditing(false);
      setSaveError(null);
      return;
    }

    if (fetchedCaseRecord && fetchedCaseRecord.id === id) {
      setCaseRecord(fetchedCaseRecord);
      setFormState(toEditableFormState(fetchedCaseRecord));
      setLinkRows(toEditableLinkRows(fetchedCaseRecord.links, 'case'));
      setIsEditing(false);
      setSaveError(null);
      return;
    }

    if (!loading && !error) {
      setCaseRecord(null);
      setFormState(null);
      setLinkRows([]);
      setIsEditing(false);
      setSaveError(null);
    }
  }, [error, fetchedCaseRecord, id, loading]);

  useEffect(() => {
    if (!caseRecord) {
      return;
    }

    if (!authLoading && user?.can_edit_managed_content !== true) {
      setFormState(toEditableFormState(caseRecord));
      setLinkRows(toEditableLinkRows(caseRecord.links, 'case'));
      setIsEditing(false);
    }
  }, [authLoading, caseRecord, user?.can_edit_managed_content]);

  useEffect(() => {
    if (!saveError) {
      setServerLinkRowErrors(createEmptyRowErrors(linkRows.length));
      setSaveSummaryMessage(null);
      return;
    }

    const mappedErrors = mapLinkSaveValidationErrors(saveError.validationDetails, linkRows.length);
    setServerLinkRowErrors(mappedErrors.rowErrors);

    if (mappedErrors.unmappedMessages.length > 0) {
      setSaveSummaryMessage(mappedErrors.unmappedMessages.join(' '));
      return;
    }

    if (mappedErrors.hasMappedLinkValueError) {
      setSaveSummaryMessage('One or more links need a full URL including https://.');
      return;
    }

    if (hasAnyResourceRowErrors(mappedErrors.rowErrors)) {
      setSaveSummaryMessage('Fix highlighted resource rows before saving.');
      return;
    }

    setSaveSummaryMessage(saveError.message);
  }, [linkRows.length, saveError]);

  useEffect(() => {
    setExpandedGroupKeys(getDefaultExpandedGroupKeys(sortedSimulationGroups));
  }, [sortedSimulationGroups]);

  useEffect(() => {
    const visibleGroupKeys = new Set(filteredSimulationGroups.map((group) => group.key));
    setExpandedGroupKeys((currentKeys) => currentKeys.filter((key) => visibleGroupKeys.has(key)));
  }, [filteredSimulationGroups]);

  useEffect(() => {
    if (!shouldRenderCompare) {
      return;
    }

    compareSectionRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    });
  }, [shouldRenderCompare]);

  useEffect(() => {
    if (!canShowCompare && isCompareVisible) {
      setIsCompareVisible(false);
    }
  }, [canShowCompare, isCompareVisible]);

  const handleShareCase = async () => {
    if (!id) return;

    const shareUrl = new URL(`/cases/${id}`, window.location.origin).toString();
    const canUseWebShare = typeof navigator.share === 'function';

    try {
      if (canUseWebShare) {
        await navigator.share({
          title: caseRecord?.name ?? 'SimBoard Case',
          text: caseRecord?.name ?? 'SimBoard Case',
          url: shareUrl,
        });
      } else {
        await navigator.clipboard.writeText(shareUrl);
      }

      toast({
        title: 'Case link ready',
        description: canUseWebShare ? 'Share dialog opened.' : 'Case URL copied to clipboard.',
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }

      toast({
        title: 'Unable to share case',
        description: 'Try copying the page URL directly from your browser.',
        variant: 'destructive',
      });
    }
  };

  const canEdit = !authLoading && user?.can_edit_managed_content === true;
  const editAccessMessage = isAuthenticated
    ? 'Read-only. Editing requires SimBoard admin access or verified E3SM GitHub organization membership.'
    : 'Log in with GitHub to edit case metadata.';

  const updateField = (field: CaseEditableField, value: string) => {
    setSaveError(null);
    setFormState((current) => (current ? { ...current, [field]: value } : current));
  };

  const addLinkRow = () => {
    setSaveError(null);
    setLinkRows((current) => [...current, { kind: 'diagnostic', label: '', value: '' }]);
  };

  const updateLinkRow = (index: number, updates: Partial<EditableLinkRow>) => {
    setSaveError(null);
    setLinkRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...updates } : row)),
    );
  };

  const removeLinkRow = (index: number) => {
    setSaveError(null);
    setLinkRows((current) => current.filter((_, rowIndex) => rowIndex !== index));
  };

  const handleCancelEdit = () => {
    if (!caseRecord) return;
    setSaveError(null);
    setFormState(toEditableFormState(caseRecord));
    setLinkRows(toEditableLinkRows(caseRecord.links, 'case'));
    setIsEditing(false);
  };

  const handleSave = async () => {
    if (!id || !caseRecord || !formState) return;

    if (hasAnyResourceRowErrors(getClientLinkRowErrors(linkRows))) {
      return;
    }

    const payload = buildUpdatePayload(caseRecord, formState, linkRows);
    if (Object.keys(payload).length === 0) {
      setSaveError(null);
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    setSaveError(null);

    try {
      const updatedCaseRecord = await updateCase(id, payload);
      setCaseRecord(updatedCaseRecord);
      setFormState(toEditableFormState(updatedCaseRecord));
      setLinkRows(toEditableLinkRows(updatedCaseRecord.links, 'case'));
      setIsEditing(false);
      await invalidateCatalog(queryClient);
    } catch (saveErr) {
      setSaveError(getUpdateError(saveErr));
    } finally {
      setIsSaving(false);
    }
  };

  if (!id) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Invalid case ID</div>
      </div>
    );
  }

  if (loading || simulationsLoading || (caseRecord != null && caseRecord.id !== id)) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Loading case details…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (simulationsError && allSimulations.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6">
        <div className="space-y-3 text-center">
          <p className="text-red-600">Could not load case simulations: {simulationsError}</p>
          <Button type="button" variant="outline" onClick={() => void refetchSimulations()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (!caseRecord) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Case not found</div>
      </div>
    );
  }
  const clientLinkRowErrors = getClientLinkRowErrors(linkRows);
  const combinedLinkRowErrors = linkRows.map((_, index) =>
    mergeRowFieldErrors(clientLinkRowErrors[index] ?? {}, serverLinkRowErrors[index] ?? {}),
  );
  const hasClientLinkErrors = hasAnyResourceRowErrors(clientLinkRowErrors);
  const summaryErrorMessage = saveSummaryMessage
    ? saveSummaryMessage
    : hasClientLinkErrors
      ? 'Fix highlighted resource rows before saving.'
      : null;
  const hasUnsavedChanges =
    formState != null &&
    Object.keys(buildUpdatePayload(caseRecord, formState, linkRows)).length > 0;
  const machineSummary = summarizeValues(caseRecord.machineNames);
  const hpcUsernameSummary = summarizeValues(caseRecord.hpcUsernames);
  const resourceLinks = caseRecord.links;
  const resourceCount = isEditing ? linkRows.length : caseRecord.links.length;
  const isCompareButtonDisabled = caseSelectedSimulationCount < 2;
  const filteredExecutionCount = filteredFlatSimulations.length;
  const activeSimulationCount =
    viewMode === 'grouped' ? filteredSimulationGroups.length : filteredExecutionCount;
  const totalSimulationCount =
    viewMode === 'grouped' ? simulationGroups.length : simulationTotal;
  const summaryHeadline =
    caseRecord.simulations.length === 0
      ? '0 runs'
      : allRunsMissingCaseHash
        ? `${caseRecord.simulations.length} runs, all without Case Hash`
        : `${caseRecord.simulations.length} runs in ${caseHashGroupCount} Case Hash ${
            caseHashGroupCount === 1 ? 'group' : 'groups'
          }`;
  const simulationsIntro = allRunsMissingCaseHash
    ? 'Every execution in this case is missing a Case Hash, so grouped view shows one fallback group.'
    : 'Grouped view clusters executions by Case Hash. Different hashes under one case name usually mean the case was recreated or cloned, and missing-hash executions stay in a fallback group.';
  const showingFallbackOnlyGroup =
    viewMode === 'grouped' &&
    filteredSimulationGroups.length === 1 &&
    filteredSimulationGroups[0]?.isFallback === true;
  const statusSummary =
    viewMode === 'grouped'
      ? showingFallbackOnlyGroup
        ? `1 fallback group containing ${pluralize(filteredExecutionCount, 'execution')}`
        : `Showing ${activeSimulationCount} of ${totalSimulationCount} groups containing ${pluralize(
            filteredExecutionCount,
            'execution',
          )}`
      : `Showing ${activeSimulationCount} of ${totalSimulationCount} executions from ${pluralize(
          filteredSimulationGroups.filter((group) => !group.isFallback).length,
          'Case Hash group',
        )}`;

  const toggleSimulationSelection = (simulationId: string) => {
    if (caseSelectedSimulationIds.includes(simulationId)) {
      if (id) {
        setSelectedCaseSimulationIdsForCase(
          id,
          caseSelectedSimulationIds.filter((selectedId) => selectedId !== simulationId),
        );
      }
      return;
    }

    if (caseSelectedSimulationCount >= MAX_SELECTION) {
      return;
    }

    if (id) {
      setSelectedCaseSimulationIdsForCase(id, [...caseSelectedSimulationIds, simulationId]);
    }
  };

  const toggleGroupExpansion = (groupKey: string, open: boolean) => {
    setExpandedGroupKeys((currentKeys) => {
      if (open) {
        return currentKeys.includes(groupKey) ? currentKeys : [...currentKeys, groupKey];
      }

      return currentKeys.filter((key) => key !== groupKey);
    });
  };

  const handleExpandAllGroups = () => {
    setExpandedGroupKeys(filteredSimulationGroups.map((group) => group.key));
  };

  const handleCollapseAllGroups = () => {
    setExpandedGroupKeys([]);
  };

  const resetGroupFilters = () => {
    setGroupFilterMode('all');
    setCaseHashQuery('');
  };

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-6 px-6 py-8">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <Button variant="outline" size="sm" asChild className="mb-3">
            <Link to={backHref}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">{caseRecord.name}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start">
          {canEdit && isEditing ? (
            <>
              <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={isSaving}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={isSaving || !hasUnsavedChanges || hasClientLinkErrors}
              >
                {isSaving ? 'Saving…' : 'Save Changes'}
              </Button>
            </>
          ) : canEdit ? (
            <Button size="sm" type="button" onClick={() => setIsEditing(true)}>
              Edit
            </Button>
          ) : !isAuthenticated ? (
            <Button variant="outline" size="sm" onClick={loginWithGithub}>
              Log In to Edit
            </Button>
          ) : (
            <TooltipProvider delayDuration={150}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0}>
                    <Button size="sm" disabled>
                      Edit
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>{editAccessMessage}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          <Button variant="outline" size="sm" type="button" onClick={handleShareCase}>
            <Share2 className="h-4 w-4" />
            Share Case
          </Button>
        </div>
      </div>

      <div>
        <Card className="border-slate-200 bg-slate-50/40 shadow-sm">
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                  Case summary
                </p>
                <h2 className="text-lg font-semibold text-slate-950">{summaryHeadline}</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {caseRecord.caseGroup ? (
                  <Badge variant="outline">{caseRecord.caseGroup}</Badge>
                ) : null}
              </div>
            </div>

            <div className="flex flex-wrap gap-3 border-t border-slate-200 pt-3">
              <div className="min-w-[7rem] rounded-lg border border-slate-200 bg-white/80 px-3 py-2">
                <DetailField label="Runs" value={caseRecord.simulations.length} />
              </div>
              <div className="min-w-[9rem] rounded-lg border border-slate-200 bg-white/80 px-3 py-2">
                <DetailField label="Case Hash groups" value={caseHashGroupCount} />
              </div>
              <div
                className="min-w-[10rem] flex-1 rounded-lg border border-slate-200 bg-white/80 px-3 py-2"
                title={
                  caseRecord.machineNames.length > 1
                    ? caseRecord.machineNames.join(', ')
                    : undefined
                }
              >
                <DetailField label="Machines" value={machineSummary} />
              </div>
              <div
                className="min-w-[10rem] flex-1 rounded-lg border border-slate-200 bg-white/80 px-3 py-2"
                title={
                  caseRecord.hpcUsernames.length > 1
                    ? caseRecord.hpcUsernames.join(', ')
                    : undefined
                }
              >
                <DetailField label="HPC users" value={hpcUsernameSummary} />
              </div>
              <div className="min-w-[9rem] rounded-lg border border-slate-200 bg-white/80 px-3 py-2">
                <DetailField label="Last updated" value={formatCaseDate(caseRecord.updatedAt)} />
              </div>
            </div>

            <div className="border-t border-slate-200 pt-3">
              <div className="space-y-3">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <h2 className="text-sm font-semibold text-slate-950">Resources</h2>
                  {resourceCount > 0 ? (
                    <p className="text-sm text-slate-500">({resourceCount})</p>
                  ) : null}
                </div>

                {isEditing ? (
                  <EditableExternalLinkList
                    title="Case-level external links"
                    description="Add, relabel, or remove links shared across runs in this case."
                    items={linkRows}
                    valuePlaceholder="https://example.com/resource"
                    addLabel="Add link"
                    onAdd={addLinkRow}
                    onKindChange={(index, kind) => updateLinkRow(index, { kind })}
                    onLabelChange={(index, value) => updateLinkRow(index, { label: value })}
                    onValueChange={(index, value) => updateLinkRow(index, { value })}
                    onRemove={removeLinkRow}
                    rowErrors={combinedLinkRowErrors}
                  />
                ) : resourceLinks.length > 0 ? (
                  <div className="space-y-2">{resourceLinks.map(renderResourceLink)}</div>
                ) : (
                  <p className="text-sm text-slate-500">No linked resources yet.</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <section>
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="space-y-5 p-5">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-950">Case Metadata</h2>
                <p className="text-sm text-muted-foreground">
                  Shared notes for this case identity. Applies across runs in this case.
                </p>
              </div>
              <div className="flex flex-col items-start gap-2 sm:items-end">
                {!canEdit ? (
                  <p className="text-xs text-muted-foreground">{editAccessMessage}</p>
                ) : null}
              </div>
            </div>

            {formState ? (
              <div className="space-y-5">
                <div>
                  {isEditing ? (
                    <MarkdownEditorField
                      label="Description"
                      value={formState.description}
                      onChange={(value) => updateField('description', value)}
                      placeholder="Add shared case description..."
                    />
                  ) : (
                    <>
                      <Label className="mb-1 block text-xs text-muted-foreground">
                        Description
                      </Label>
                      <MarkdownContent content={caseRecord.description} />
                    </>
                  )}
                </div>

                <div className="grid gap-5 xl:grid-cols-2">
                  <div>
                    {isEditing ? (
                      <MarkdownEditorField
                        label="Key Features"
                        value={formState.keyFeatures}
                        onChange={(value) => updateField('keyFeatures', value)}
                        placeholder="Add shared key features..."
                      />
                    ) : (
                      <>
                        <Label className="mb-1 block text-xs text-muted-foreground">
                          Key Features
                        </Label>
                        <MarkdownContent content={caseRecord.keyFeatures} />
                      </>
                    )}
                  </div>
                  <div>
                    {isEditing ? (
                      <MarkdownEditorField
                        label="Known Issues"
                        value={formState.knownIssues}
                        onChange={(value) => updateField('knownIssues', value)}
                        placeholder="Add shared known issues..."
                      />
                    ) : (
                      <>
                        <Label className="mb-1 block text-xs text-muted-foreground">
                          Known Issues
                        </Label>
                        <MarkdownContent content={caseRecord.knownIssues} />
                      </>
                    )}
                  </div>
                </div>

                <div>
                  {isEditing ? (
                    <MarkdownEditorField
                      label="Notes"
                      value={formState.notesMarkdown}
                      onChange={(value) => updateField('notesMarkdown', value)}
                      placeholder="Add shared case notes..."
                      minHeightClassName="min-h-[160px]"
                    />
                  ) : (
                    <>
                      <Label className="mb-1 block text-xs text-muted-foreground">Notes</Label>
                      <MarkdownContent
                        content={caseRecord.notesMarkdown}
                        className="min-h-[160px]"
                      />
                    </>
                  )}
                </div>

                {isEditing && summaryErrorMessage ? (
                  <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <p className="font-medium">Save blocked</p>
                        <p className="mt-1 text-red-700">{summaryErrorMessage}</p>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section className="space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Simulations</h2>
              <p className="max-w-3xl text-sm text-muted-foreground">{simulationsIntro}</p>
            </div>
          </div>

          <div className="space-y-4 px-5 py-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(22rem,1fr)]">
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      View
                    </div>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:max-w-md">
                      <Button
                        type="button"
                        size="sm"
                        variant={viewMode === 'flat' ? 'default' : 'outline'}
                        onClick={() => setViewMode('flat')}
                        className="justify-center whitespace-nowrap"
                      >
                        All executions
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant={viewMode === 'grouped' ? 'default' : 'outline'}
                        onClick={() => setViewMode('grouped')}
                        className="justify-center whitespace-nowrap"
                      >
                        Grouped by Case Hash
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      Filters
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {GROUP_FILTER_OPTIONS.map((option) => (
                        <Button
                          key={option.value}
                          type="button"
                          size="sm"
                          variant={groupFilterMode === option.value ? 'default' : 'outline'}
                          onClick={() => setGroupFilterMode(option.value)}
                        >
                          {option.label}
                        </Button>
                      ))}
                      {hasActiveGroupFilters ? (
                        <Button type="button" variant="ghost" size="sm" onClick={resetGroupFilters}>
                          Reset filters
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      Search
                    </div>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <Input
                        value={caseHashQuery}
                        onChange={(event) => setCaseHashQuery(event.target.value)}
                        placeholder="Filter Case Hash prefix"
                        className="bg-white pl-9"
                        aria-label="Filter Case Hash prefix"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
                      Actions
                    </div>
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600">
                          Selected case runs{' '}
                          <span className="font-semibold text-slate-950">
                            {caseSelectedSimulationCount}
                          </span>{' '}
                          / {MAX_SELECTION}
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => {
                            if (shouldRenderCompare) {
                              compareSectionRef.current?.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start',
                              });
                              return;
                            }

                            setIsCompareVisible(true);
                          }}
                          disabled={isCompareButtonDisabled}
                        >
                          {shouldRenderCompare ? 'Jump to Compare' : 'Compare Case Runs'}
                        </Button>
                        {shouldRenderCompare ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => setIsCompareVisible(false)}
                          >
                            Hide Compare
                          </Button>
                        ) : null}
                        {caseSelectedSimulationCount > 0 ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-slate-600 hover:text-slate-900"
                            onClick={() => {
                              if (id) {
                                setSelectedCaseSimulationIdsForCase(id, []);
                              }
                            }}
                          >
                            Deselect all
                          </Button>
                        ) : null}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <div
                          aria-hidden={viewMode !== 'grouped' || !showGroupActions}
                          className={`inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white p-1 ${
                            viewMode === 'grouped' && showGroupActions
                              ? ''
                              : 'invisible pointer-events-none'
                          }`}
                        >
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={viewMode !== 'grouped' || !showGroupActions}
                            className="h-7 whitespace-nowrap px-2 text-slate-600 hover:text-slate-900"
                            onClick={handleExpandAllGroups}
                          >
                            Expand all
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={viewMode !== 'grouped' || !showGroupActions}
                            className="h-7 whitespace-nowrap px-2 text-slate-600 hover:text-slate-900"
                            onClick={handleCollapseAllGroups}
                          >
                            Collapse all
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {hiddenSelectedCount > 0 ? (
                <div className="mt-3 text-xs text-slate-500">
                  {hiddenSelectedCount} selected {hiddenSelectedCount === 1 ? 'run is' : 'runs are'}{' '}
                  in filtered-out groups.
                </div>
              ) : null}
            </div>

            <div className="border-t border-slate-200 pt-3 text-sm text-slate-600">
              {statusSummary}
            </div>
          </div>

          <div className="border-t border-slate-200 px-5 py-4">
            <div
              className={
                useScrollableGroupsPanel
                  ? 'rounded-xl bg-slate-50/30 p-3 lg:max-h-[70vh] lg:overflow-y-auto'
                  : ''
              }
            >
              <div className="space-y-4">
                {(viewMode === 'grouped'
                  ? filteredSimulationGroups.length
                  : filteredFlatSimulations.length) === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/40 px-6 py-10 text-center">
                    <p className="text-sm font-medium text-slate-900">
                      {viewMode === 'grouped'
                        ? 'No Case Hash groups match these filters.'
                        : 'No executions match these filters.'}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Try a different filter or reset current filters.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-4"
                      onClick={resetGroupFilters}
                    >
                      Reset filters
                    </Button>
                  </div>
                ) : viewMode === 'flat' ? (
                  <div className="overflow-hidden rounded-xl border border-slate-200 bg-background">
                    <div className="max-h-[28rem] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-12">Select</TableHead>
                            <TableHead>Execution ID</TableHead>
                            <TableHead>Case Hash</TableHead>
                            <TableHead>Initialization</TableHead>
                            <TableHead>Simulation dates</TableHead>
                            <TableHead>Run dates</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredFlatSimulations.map(({ summary, details }) => (
                            <TableRow key={summary.id}>
                              <TableCell className="align-top">
                                <Checkbox
                                  checked={caseSelectedSimulationIds.includes(summary.id)}
                                  disabled={
                                    !caseSelectedSimulationIds.includes(summary.id) &&
                                    caseSelectedSimulationCount >= MAX_SELECTION
                                  }
                                  onCheckedChange={() => toggleSimulationSelection(summary.id)}
                                  aria-label={`Select ${summary.executionId} for compare`}
                                />
                              </TableCell>
                              <TableCell className="align-top">
                                <Link
                                  to={`/simulations/${summary.id}`}
                                  state={{ from: currentPath }}
                                  className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                                >
                                  {summary.executionId}
                                </Link>
                              </TableCell>
                              <TableCell className="align-top">
                                <span
                                  className="font-mono text-xs text-slate-700"
                                  title={summary.caseHash ?? MISSING_CASE_HASH_LABEL}
                                >
                                  {summary.caseHash
                                    ? formatCaseHashLabel(summary.caseHash)
                                    : MISSING_CASE_HASH_LABEL}
                                </span>
                              </TableCell>
                              <TableCell className="align-top">
                                <TableCellText
                                  value={details?.initializationType ?? '—'}
                                  lines={1}
                                />
                              </TableCell>
                              <TableCell className="align-top">
                                {formatSimulationDateRange(summary)}
                              </TableCell>
                              <TableCell className="align-top">
                                {details?.runStartDate || details?.runEndDate ? (
                                  <span
                                    title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}
                                  >
                                    {formatRunDateRange(details?.runStartDate, details?.runEndDate)}
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                ) : (
                  <div className="overflow-hidden rounded-xl border border-slate-200 bg-background">
                    <div className="max-h-[42rem] overflow-auto">
                      <Table className="min-w-[980px]">
                        <TableHeader className="sticky top-0 z-10 bg-slate-50">
                          <TableRow className="hover:bg-slate-50">
                            <TableHead className="w-[22rem] bg-slate-50">
                              <div className="flex items-center gap-1.5">
                                <span>Case Hash</span>
                                <TooltipProvider delayDuration={150}>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <button
                                        type="button"
                                        className="text-slate-400 transition-colors hover:text-slate-600"
                                        aria-label="Explain case hash grouping"
                                      >
                                        <Info className="h-3.5 w-3.5" />
                                      </button>
                                    </TooltipTrigger>
                                    <TooltipContent className="max-w-xs text-xs leading-5">
                                      {CASE_HASH_GROUPING_TOOLTIP}
                                    </TooltipContent>
                                  </Tooltip>
                                </TooltipProvider>
                              </div>
                            </TableHead>
                            <TableHead className="w-24 bg-slate-50">Runs</TableHead>
                            <TableHead className="bg-slate-50">Simulation window</TableHead>
                            <TableHead className="bg-slate-50">Initialization</TableHead>
                            <TableHead className="bg-slate-50">Run dates</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredSimulationGroups.map((group) => {
                            const isOpen = expandedGroupKeys.includes(group.key);
                            const groupPanelId = `case-hash-group-panel-${group.key}`;
                            const groupSimulationWindow = formatGroupSimulationWindow(
                              group.simulations.map(({ summary }) => summary),
                            );
                            const groupRunWindow = getGroupRunDateWindow(group.simulations);
                            const groupInitializationSummary = summarizeDistinctValues(
                              group.simulations.map(({ details }) => details?.initializationType),
                            );
                            const showInitializationColumn =
                              countDistinctValues(
                                group.simulations.map(
                                  ({ details }) => details?.initializationType ?? '—',
                                ),
                              ) > 1;
                            const showSimulationDatesColumn =
                              countDistinctValues(
                                group.simulations.map(({ summary }) =>
                                  formatSimulationDateRange(summary),
                                ),
                              ) > 1;
                            const showRunDatesColumn =
                              countDistinctValues(
                                group.simulations.map(({ details }) =>
                                  formatRunDateRange(details?.runStartDate, details?.runEndDate),
                                ),
                              ) > 1;

                            return (
                              <Fragment key={group.key}>
                                <TableRow className="bg-white hover:bg-slate-50/80">
                                  <TableCell className="align-top">
                                    <button
                                      type="button"
                                      className="flex w-full items-start gap-3 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                      onClick={() => toggleGroupExpansion(group.key, !isOpen)}
                                      aria-expanded={isOpen}
                                      aria-controls={groupPanelId}
                                    >
                                      <ChevronDown
                                        className={`mt-0.5 h-4 w-4 shrink-0 text-slate-500 transition-transform ${
                                          isOpen ? 'rotate-180' : ''
                                        }`}
                                      />
                                      <div className="min-w-0 space-y-1">
                                        <div className="flex flex-wrap items-center gap-2">
                                          <span
                                            className="truncate font-mono text-xs font-semibold text-slate-950 sm:text-sm"
                                            title={group.caseHash ?? MISSING_CASE_HASH_LABEL}
                                          >
                                            {group.isFallback
                                              ? MISSING_CASE_HASH_LABEL
                                              : formatCaseHashLabel(group.caseHash, 22)}
                                          </span>
                                          {group.isFallback ? (
                                            <Badge variant="secondary">Fallback</Badge>
                                          ) : null}
                                        </div>
                                        {group.isFallback ? (
                                          <p className="text-xs text-slate-500">
                                            Older ingests without Case Hash stay in fallback group.
                                          </p>
                                        ) : null}
                                      </div>
                                    </button>
                                  </TableCell>
                                  <TableCell className="align-top">
                                    <Badge variant="outline">
                                      {pluralize(group.simulations.length, 'run')}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="align-top text-sm text-slate-700">
                                    {groupSimulationWindow}
                                  </TableCell>
                                  <TableCell className="align-top text-sm text-slate-700">
                                    <TableCellText value={groupInitializationSummary} lines={1} />
                                  </TableCell>
                                  <TableCell className="align-top text-sm text-slate-700">
                                    {groupRunWindow}
                                  </TableCell>
                                </TableRow>
                                {isOpen ? (
                                  <TableRow className="bg-slate-50/50 hover:bg-slate-50/50">
                                    <TableCell colSpan={6} className="p-0">
                                      <div
                                        id={groupPanelId}
                                        className="border-t border-slate-200 px-4 py-3"
                                      >
                                        <div className="mb-3 flex items-center justify-between gap-3">
                                          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                                            Executions in group
                                          </p>
                                          <p className="text-xs text-slate-500">
                                            {group.simulations.length} visible
                                          </p>
                                        </div>
                                        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                                          <div className="max-h-[20rem] overflow-auto">
                                            <Table>
                                              <TableHeader className="sticky top-0 z-10 bg-white">
                                                <TableRow className="hover:bg-white">
                                                  <TableHead className="w-12 bg-white">
                                                    Select
                                                  </TableHead>
                                                  <TableHead className="bg-white">
                                                    Execution ID
                                                  </TableHead>
                                                  {showInitializationColumn ? (
                                                    <TableHead className="bg-white">
                                                      Initialization
                                                    </TableHead>
                                                  ) : null}
                                                  {showSimulationDatesColumn ? (
                                                    <TableHead className="bg-white">
                                                      Simulation dates
                                                    </TableHead>
                                                  ) : null}
                                                  {showRunDatesColumn ? (
                                                    <TableHead className="bg-white">
                                                      Run dates
                                                    </TableHead>
                                                  ) : null}
                                                </TableRow>
                                              </TableHeader>
                                              <TableBody>
                                                {group.simulations.map(({ summary, details }) => (
                                                  <TableRow key={summary.id}>
                                                    <TableCell className="align-top">
                                                      <Checkbox
                                                        checked={caseSelectedSimulationIds.includes(
                                                          summary.id,
                                                        )}
                                                        disabled={
                                                          !caseSelectedSimulationIds.includes(
                                                            summary.id,
                                                          ) &&
                                                          caseSelectedSimulationCount >=
                                                            MAX_SELECTION
                                                        }
                                                        onCheckedChange={() =>
                                                          toggleSimulationSelection(summary.id)
                                                        }
                                                        aria-label={`Select ${summary.executionId} for compare`}
                                                      />
                                                    </TableCell>
                                                    <TableCell className="align-top">
                                                      <Link
                                                        to={`/simulations/${summary.id}`}
                                                        state={{ from: currentPath }}
                                                        className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                                                      >
                                                        {summary.executionId}
                                                      </Link>
                                                    </TableCell>
                                                    {showInitializationColumn ? (
                                                      <TableCell className="align-top">
                                                        <TableCellText
                                                          value={details?.initializationType ?? '—'}
                                                          lines={1}
                                                        />
                                                      </TableCell>
                                                    ) : null}
                                                    {showSimulationDatesColumn ? (
                                                      <TableCell className="align-top">
                                                        {formatSimulationDateRange(summary)}
                                                      </TableCell>
                                                    ) : null}
                                                    {showRunDatesColumn ? (
                                                      <TableCell className="align-top">
                                                        {details?.runStartDate ||
                                                        details?.runEndDate ? (
                                                          <span
                                                            title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}
                                                          >
                                                            {formatRunDateRange(
                                                              details?.runStartDate,
                                                              details?.runEndDate,
                                                            )}
                                                          </span>
                                                        ) : (
                                                          <span className="text-muted-foreground">
                                                            —
                                                          </span>
                                                        )}
                                                      </TableCell>
                                                    ) : null}
                                                  </TableRow>
                                                ))}
                                              </TableBody>
                                            </Table>
                                          </div>
                                        </div>
                                      </div>
                                    </TableCell>
                                  </TableRow>
                                ) : null}
                              </Fragment>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {simulationsError ? (
            <div className="flex items-center justify-between gap-3 border-t border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
              <span>Could not load more simulation metadata: {simulationsError}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void refetchSimulations()}
              >
                Retry
              </Button>
            </div>
          ) : null}

          {hasNextPage ? (
            <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-5 py-4">
              <p className="text-sm text-slate-600">
                Loaded metadata for {allSimulations.length} of {simulationTotal} runs. Search and
                grouping include all case runs.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isFetchingNextPage}
                onClick={() => void fetchNextPage()}
              >
                {isFetchingNextPage ? 'Loading more…' : 'Load more metadata'}
              </Button>
            </div>
          ) : null}

          {shouldRenderCompare && renderCompareSection ? (
            <div
              ref={compareSectionRef}
              className="scroll-mt-24 border-t border-slate-200 bg-slate-50/30 px-5 py-5"
            >
              <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-1">
                  <h3 className="text-lg font-semibold text-slate-950">
                    Selected Executions Comparison
                  </h3>
                  <p className="max-w-3xl text-sm text-slate-600">
                    Review selected executions side by side within this case. Adjust the selection
                    above to update this comparison.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsCompareVisible(false)}
                >
                  Hide Compare
                </Button>
              </div>

              {renderCompareSection({
                onClose: () => setIsCompareVisible(false),
              })}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
};
