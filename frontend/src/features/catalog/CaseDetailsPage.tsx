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

import { updateCase } from '@/api/catalog';
import { useAuth } from '@/auth/hooks/useAuth';
import { MarkdownContent } from '@/components/shared/MarkdownContent';
import { normalizeSelectedExecutionIds } from '@/components/shared/normalizeSelectedExecutionIds';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingState } from '@/components/ui/loading-state';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  type ExecutionDateSort,
  formatCaseDate,
  formatCaseHashLabel,
  formatExecutionDuration,
  getCaseHashConfigurationDifferences,
  getExecutionDateWindow,
  groupExecutionSummaries,
  MISSING_CASE_HASH_LABEL,
  sortCaseExecutions,
  sortCaseHashGroups,
} from '@/features/catalog/caseUtils';
import {
  CaseArtifactsTable,
  type CaseArtifactValue,
} from '@/features/catalog/components/CaseArtifactsTable';
import {
  CaseConfigurationDetails,
  CaseConfigurationSummary,
  CaseHashConfigurationDifferences,
} from '@/features/catalog/components/CaseConfiguration';
import {
  CaseExecutionsTable,
  type ExecutionColumnKey,
  ExecutionColumnsMenu,
} from '@/features/catalog/components/CaseExecutionsTable';
import { EditableExternalLinkList } from '@/features/catalog/components/EditableExternalLinkList';
import { ExecutionPicker } from '@/features/catalog/components/ExecutionPicker';
import { MarkdownEditorField } from '@/features/catalog/components/MarkdownEditorField';
import { MetadataHistory } from '@/features/catalog/components/MetadataHistory';
import { PerformanceSourceDirectories } from '@/features/catalog/components/PerformanceSourceDirectory';
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
} from '@/features/catalog/externalLinkEditing';
import { useMetadataHistory } from '@/features/catalog/hooks/useMetadataHistory';
import { toast } from '@/hooks/use-toast';
import {
  getExecutionDiscoveryContext,
  hasCaseHashContext,
  matchesExecutionSearch,
  toggleCaseExecution,
} from '@/lib/catalog/executionDiscovery';
import { useCaseExecutions } from '@/lib/catalog/hooks/useCaseExecutions';
import { useReadableCase } from '@/lib/catalog/hooks/useReadableCase';
import { invalidateCatalog } from '@/lib/catalog/invalidateCatalog';
import { caseDetailsPath } from '@/lib/catalog/urls';
import type {
  CaseDetailOut,
  CaseEditableField,
  CaseSimulationTypeValue,
  CaseUpdate,
  ExecutionSummaryOut,
  ExternalLinkOut,
} from '@/types';
import { formatModelDate } from '@/utils/utils';

const formatGroupExecutionWindow = (executions: ExecutionSummaryOut[]) => {
  const { startDate, endDate } = getExecutionDateWindow(executions);

  return `${formatModelDate(startDate)} → ${formatModelDate(endDate)}`;
};

const pluralize = (count: number, singular: string, plural = `${singular}s`) =>
  `${count} ${count === 1 ? singular : plural}`;

const areStringArraysEqual = (left: string[], right: string[]) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

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
  renderCompareSection?: (options: { caseId: string; onClose: () => void }) => React.ReactNode;
  selectedCaseExecutionIdsByCase: Record<string, string[]>;
  setSelectedCaseExecutionIdsForCase: (caseId: string, ids: string[]) => void;
}

type ExecutionViewMode = 'grouped' | 'flat';
type EditableFormState = {
  [K in Exclude<CaseEditableField, 'simulationType'>]: string;
} & { simulationType: CaseSimulationTypeValue };
type CaseSaveError = {
  message: string;
  validationDetails: ValidationDetail[];
};

interface CaseDetailsLocationState {
  from?: string;
}

const SCROLLABLE_GROUPS_THRESHOLD = 5;
const SCROLLABLE_FLAT_ROWS_THRESHOLD = 10;
const CASE_HASH_GROUPING_TOOLTIP =
  'Case name is human-readable label. Case hash identifies specific CIME case instance. Multiple hashes under one case name usually mean case was recreated or cloned.';
const CASE_EDIT_FIELDS: ReadonlyArray<CaseEditableField> = [
  'caseGroup',
  'simulationType',
  'description',
  'keyFeatures',
  'knownIssues',
  'notesMarkdown',
];

const toEditableFormState = (caseRecord: CaseDetailOut): EditableFormState => ({
  caseGroup: caseRecord.caseGroup ?? '',
  simulationType: caseRecord.simulationType,
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
    if (field === 'simulationType') {
      if (formState.simulationType !== caseRecord.simulationType) {
        payload.simulationType = formState.simulationType;
      }
      continue;
    }

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
    className="group inline-flex max-w-full items-center gap-2 rounded-md px-2 py-1 text-left transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2"
    aria-label={`${link.label || link.url} (${RESOURCE_KIND_DESCRIPTIONS[link.kind]})`}
  >
    <div className="min-w-0">
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
    </div>
    <div className="flex shrink-0 items-center gap-1 text-slate-400 transition-colors group-hover:text-slate-600 group-focus-visible:text-slate-600">
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
  selectedCaseExecutionIdsByCase,
  setSelectedCaseExecutionIdsForCase,
}: CaseDetailsPageProps) => {
  const queryClient = useQueryClient();
  const {
    caseName,
    hpcUsername,
    machine: machineName,
  } = useParams<{
    caseName: string;
    hpcUsername: string;
    machine: string;
  }>();
  const readableIdentity =
    machineName && hpcUsername && caseName ? { machineName, hpcUsername, caseName } : null;
  const { data: fetchedCaseRecord, loading, error } = useReadableCase(readableIdentity);
  const caseId = fetchedCaseRecord?.id;
  const [dateSort, setDateSort] = useState<ExecutionDateSort>({
    key: 'simulation',
    direction: 'asc',
  });
  const {
    data: allExecutions,
    error: executionsError,
    fetchNextPage,
    hasNextPage,
    isLoading: executionsLoading,
    isFetchingNextPage,
    refetch: refetchExecutions,
    total: executionTotal,
  } = useCaseExecutions(caseId, {
    sortBy: dateSort.key === 'run' ? 'run_activity' : 'simulation_start_date',
    sortOrder: dateSort.direction,
  });
  const location = useLocation();
  const compareButtonRef = useRef<HTMLButtonElement | null>(null);
  const compareTitleRef = useRef<HTMLHeadingElement | null>(null);
  const executionsSectionRef = useRef<HTMLElement | null>(null);
  const { user, isAuthenticated, loading: authLoading, loginWithGithub } = useAuth();
  const [viewMode, setViewMode] = useState<ExecutionViewMode>('flat');
  const [visibleExecutionColumns, setVisibleExecutionColumns] = useState<ExecutionColumnKey[]>([
    'initializationType',
    'machineName',
  ]);
  const [executionQuery, setExecutionQuery] = useState('');
  const [artifactExecutionIds, setArtifactExecutionIds] = useState<string[] | null>(null);
  const [expandedGroupKeys, setExpandedGroupKeys] = useState<string[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const history = useMetadataHistory('case', caseId ?? '', isHistoryOpen);
  const [caseRecord, setCaseRecord] = useState<CaseDetailOut | null>(null);
  const [formState, setFormState] = useState<EditableFormState | null>(null);
  const [linkRows, setLinkRows] = useState<EditableLinkRow[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<CaseSaveError | null>(null);
  const [editReason, setEditReason] = useState('');
  const [serverLinkRowErrors, setServerLinkRowErrors] = useState<ResourceRowFieldErrors[]>([]);
  const [saveSummaryMessage, setSaveSummaryMessage] = useState<string | null>(null);
  const [isCompareVisible, setIsCompareVisible] = useState(false);
  const currentPath = `${location.pathname}${location.search}`;
  const state = location.state as CaseDetailsLocationState | null;
  const backHref = typeof state?.from === 'string' ? state.from : '/cases';
  const executionDetailsById = useMemo(
    () => new Map(allExecutions.map((execution) => [execution.id, execution])),
    [allExecutions],
  );
  const rawExecutionGroups = useMemo(
    () => groupExecutionSummaries(caseRecord?.executions ?? []),
    [caseRecord?.executions],
  );
  const hasMultipleCaseHashes = rawExecutionGroups.filter((group) => !group.isFallback).length > 1;
  const executionGroups = useMemo(
    () =>
      rawExecutionGroups.map((group) => ({
        ...group,
        executions: group.executions.map((execution) => ({
          summary: execution,
          details: executionDetailsById.get(execution.id),
        })),
      })),
    [rawExecutionGroups, executionDetailsById],
  );
  const executionCandidates = useMemo(
    () => executionGroups.flatMap((group) => group.executions),
    [executionGroups],
  );
  const executionDiscovery = useMemo(
    () => getExecutionDiscoveryContext(executionCandidates),
    [executionCandidates],
  );
  const showCaseHashContext = hasCaseHashContext(caseRecord?.executions ?? []);
  const sortedExecutionGroups = useMemo(
    () => sortCaseHashGroups(executionGroups),
    [executionGroups],
  );
  const artifactFilteredExecutionGroups = useMemo(() => {
    if (artifactExecutionIds == null) {
      return sortedExecutionGroups;
    }

    const matchingExecutionIds = new Set(artifactExecutionIds);
    return sortedExecutionGroups
      .map((group) => ({
        ...group,
        executions: group.executions.filter(({ summary }) =>
          matchingExecutionIds.has(summary.executionId),
        ),
      }))
      .filter((group) => group.executions.length > 0);
  }, [artifactExecutionIds, sortedExecutionGroups]);
  const filteredExecutionGroups = useMemo(
    () =>
      artifactFilteredExecutionGroups
        .map((group) => ({
          ...group,
          executions: sortCaseExecutions(
            group.executions.filter(
              (candidate) =>
                matchesExecutionSearch(candidate, executionDiscovery, executionQuery) ||
                formatExecutionDuration(candidate.summary)
                  .toLowerCase()
                  .includes(executionQuery.trim().toLowerCase()),
            ),
            dateSort,
          ),
        }))
        .filter((group) => group.executions.length > 0),
    [artifactFilteredExecutionGroups, dateSort, executionDiscovery, executionQuery],
  );
  const filteredFlatExecutions = useMemo(
    () =>
      sortCaseExecutions(
        filteredExecutionGroups.flatMap((group) => group.executions),
        dateSort,
      ),
    [filteredExecutionGroups, dateSort],
  );
  const baselineGroup = filteredExecutionGroups[0];
  const configurationDifferences = useMemo(
    () =>
      getCaseHashConfigurationDifferences(
        caseRecord?.configurationGroups ?? [],
        baselineGroup?.caseHash,
      ),
    [caseRecord?.configurationGroups, baselineGroup?.caseHash],
  );
  const visibleExecutionIds = useMemo(
    () => new Set(filteredFlatExecutions.map(({ summary }) => summary.id)),
    [filteredFlatExecutions],
  );
  const caseExecutionIdSet = useMemo(
    () => new Set(caseRecord?.executions.map((execution) => execution.id) ?? []),
    [caseRecord?.executions],
  );
  const rawCaseSelectedExecutionIds = caseId
    ? normalizeSelectedExecutionIds(selectedCaseExecutionIdsByCase[caseId] ?? [])
    : [];
  const caseSelectedExecutionIds = rawCaseSelectedExecutionIds.filter((executionId) =>
    caseExecutionIdSet.has(executionId),
  );
  const caseSelectedExecutionCount = caseSelectedExecutionIds.length;
  const shouldRenderCompare = isCompareVisible;
  const selectedCurrentCaseExecutionIds = caseSelectedExecutionIds;
  const hiddenSelectedCount = selectedCurrentCaseExecutionIds.filter(
    (executionId) => !visibleExecutionIds.has(executionId),
  ).length;
  const useScrollableGroupsPanel =
    viewMode === 'grouped'
      ? filteredExecutionGroups.length > SCROLLABLE_GROUPS_THRESHOLD
      : filteredFlatExecutions.length > SCROLLABLE_FLAT_ROWS_THRESHOLD;

  useEffect(() => {
    if (loading) {
      setCaseRecord(null);
      setFormState(null);
      setLinkRows([]);
      setIsEditing(false);
      setSaveError(null);
      return;
    }

    if (fetchedCaseRecord) {
      setCaseRecord(fetchedCaseRecord);
      setFormState(toEditableFormState(fetchedCaseRecord));
      setLinkRows(toEditableLinkRows(fetchedCaseRecord.links, 'case'));
      setEditReason('');
      setIsEditing(false);
      setSaveError(null);
      return;
    }

    if (!loading && !error) {
      setCaseRecord(null);
      setFormState(null);
      setLinkRows([]);
      setEditReason('');
      setIsEditing(false);
      setSaveError(null);
    }
  }, [error, fetchedCaseRecord, loading]);

  useEffect(() => {
    if (!caseRecord) {
      return;
    }

    if (!authLoading && user?.can_edit_managed_content !== true) {
      setFormState(toEditableFormState(caseRecord));
      setLinkRows(toEditableLinkRows(caseRecord.links, 'case'));
      setEditReason('');
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
    const visibleGroupKeys = new Set(filteredExecutionGroups.map((group) => group.key));
    setExpandedGroupKeys((currentKeys) => {
      const nextKeys = currentKeys.filter((key) => visibleGroupKeys.has(key));
      return areStringArraysEqual(currentKeys, nextKeys) ? currentKeys : nextKeys;
    });
  }, [filteredExecutionGroups]);

  const handleShareCase = async () => {
    if (!readableIdentity) return;

    const shareUrl = new URL(caseDetailsPath(readableIdentity), window.location.origin).toString();
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

  const updateField = (field: Exclude<CaseEditableField, 'simulationType'>, value: string) => {
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
    setEditReason('');
    setIsEditing(false);
  };

  const handleSave = async () => {
    if (!caseId || !caseRecord || !formState) return;

    if (hasAnyResourceRowErrors(getClientLinkRowErrors(linkRows))) {
      return;
    }

    const payload = buildUpdatePayload(caseRecord, formState, linkRows);
    if (Object.keys(payload).length === 0) {
      setSaveError(null);
      setIsEditing(false);
      return;
    }
    const normalizedReason = editReason.trim();
    if (normalizedReason) {
      payload.editReason = normalizedReason;
    }

    setIsSaving(true);
    setSaveError(null);

    try {
      const updatedCaseRecord = await updateCase(caseId, payload);
      setCaseRecord(updatedCaseRecord);
      setFormState(toEditableFormState(updatedCaseRecord));
      setLinkRows(toEditableLinkRows(updatedCaseRecord.links, 'case'));
      setEditReason('');
      setIsEditing(false);
      await invalidateCatalog(queryClient);
      await history.reset();
    } catch (saveErr) {
      setSaveError(getUpdateError(saveErr));
    } finally {
      setIsSaving(false);
    }
  };

  if (!readableIdentity) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Invalid case identity</div>
      </div>
    );
  }

  if (
    loading ||
    (executionsLoading && allExecutions.length === 0) ||
    (caseRecord != null && caseRecord.id !== caseId)
  ) {
    return <LoadingState kind="page" label="Loading case details" />;
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (executionsError && allExecutions.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6">
        <div className="space-y-3 text-center">
          <p className="text-red-600">Could not load case executions: {executionsError}</p>
          <Button type="button" variant="outline" onClick={() => void refetchExecutions()}>
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
  const resourceLinks = caseRecord.links;
  const resourceCount = isEditing ? linkRows.length : caseRecord.links.length;
  const diagnosticsTierLabel = caseRecord.diagnosticsTiers.join(' and ');
  const hasAmbiguousDiagnosticsTiers = caseRecord.diagnosticsTiers.length > 1;
  const hasDiagnosticsMismatch =
    caseRecord.simulationType != null &&
    caseRecord.diagnosticsTiers.length === 1 &&
    caseRecord.diagnosticsTiers[0] !== caseRecord.simulationType;
  const artifactValuesByKey = caseRecord.artifacts.reduce((groups, artifact) => {
    const key = JSON.stringify([artifact.kind, artifact.uri]);
    const value = groups.get(key);
    if (value) {
      if (!value.executionIds.includes(artifact.executionId)) {
        value.executionIds.push(artifact.executionId);
      }
      if (value.label == null && artifact.label != null) {
        value.label = artifact.label;
      }
      return groups;
    }

    groups.set(key, {
      id: artifact.id,
      kind: artifact.kind,
      uri: artifact.uri,
      label: artifact.label ?? null,
      executionIds: [artifact.executionId],
    });
    return groups;
  }, new Map<string, CaseArtifactValue>());
  const artifactValues = Array.from(artifactValuesByKey.values());
  const isCompareButtonDisabled = caseSelectedExecutionCount < 2;
  const filteredExecutionCount = filteredFlatExecutions.length;
  const activeExecutionCount =
    viewMode === 'grouped' ? filteredExecutionGroups.length : filteredExecutionCount;
  const totalExecutionCount = viewMode === 'grouped' ? executionGroups.length : executionTotal;
  const showingFallbackOnlyGroup =
    viewMode === 'grouped' &&
    filteredExecutionGroups.length === 1 &&
    filteredExecutionGroups[0]?.isFallback === true;
  const statusSummary =
    viewMode === 'grouped'
      ? showingFallbackOnlyGroup
        ? `1 fallback group containing ${pluralize(filteredExecutionCount, 'execution')}`
        : `Showing ${activeExecutionCount} of ${totalExecutionCount} groups containing ${pluralize(
            filteredExecutionCount,
            'execution',
          )}`
      : !showCaseHashContext
        ? `Showing ${activeExecutionCount} of ${totalExecutionCount} executions`
        : `Showing ${activeExecutionCount} of ${totalExecutionCount} executions from ${pluralize(
            filteredExecutionGroups.filter((group) => !group.isFallback).length,
            'Case Hash group',
          )}`;

  const toggleExecutionSelection = (executionId: string) => {
    if (caseId) {
      setSelectedCaseExecutionIdsForCase(
        caseId,
        toggleCaseExecution(caseSelectedExecutionIds, executionId),
      );
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

  const resetGroupFilters = () => {
    setExecutionQuery('');
  };

  const toggleDateSort = (key: ExecutionDateSort['key']) => {
    setDateSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }));
  };
  const executionTableProps = {
    discovery: executionDiscovery,
    visibleColumns: visibleExecutionColumns,
    selectedIds: caseSelectedExecutionIds,
    onToggleSelection: toggleExecutionSelection,
    sort: dateSort,
    onSort: toggleDateSort,
    identity: readableIdentity,
    from: currentPath,
  };

  const clearArtifactExecutionFilter = () => {
    setArtifactExecutionIds(null);
  };

  const filterExecutionsForArtifact = (executionIds: string[]) => {
    setArtifactExecutionIds([...new Set(executionIds)]);
    setViewMode('flat');
    requestAnimationFrame(() => {
      executionsSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
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
          <p className="mt-1 text-xs text-muted-foreground">
            Page updated: {formatCaseDate(caseRecord.updatedAt)}
          </p>
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
        <Card className="border-slate-200 bg-slate-50/40 shadow-sm" data-case-metadata>
          <CardContent className="space-y-4 p-4">
            <h2 className="text-lg font-semibold text-slate-950">Case Metadata</h2>

            {formState ? (
              <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="min-w-0 space-y-1">
                  <Label
                    htmlFor={isEditing ? 'case-group' : undefined}
                    className="block text-[13px] font-semibold leading-4 text-muted-foreground"
                  >
                    Case Group
                  </Label>
                  {isEditing ? (
                    <>
                      <Input
                        id="case-group"
                        className="max-w-sm"
                        value={formState.caseGroup}
                        onChange={(event) => updateField('caseGroup', event.target.value)}
                        aria-describedby="case-group-help"
                        placeholder="No case group"
                      />
                      <p id="case-group-help" className="text-xs text-muted-foreground">
                        Changing Case Group applies to all executions in this case. Clearing it
                        allows future ingestion to populate it again.
                      </p>
                    </>
                  ) : (
                    <p className="text-sm font-normal leading-5 text-foreground [overflow-wrap:anywhere]">
                      {caseRecord.caseGroup ?? 'Unset'}
                    </p>
                  )}
                </div>
                <div className="min-w-0 space-y-1">
                  <Label className="block text-[13px] font-semibold leading-4 text-muted-foreground">
                    Case Classification
                  </Label>
                  {isEditing ? (
                    <Select
                      value={formState.simulationType ?? 'unset'}
                      onValueChange={(value) => {
                        setSaveError(null);
                        setFormState((current) =>
                          current
                            ? {
                                ...current,
                                simulationType:
                                  value === 'unset' ? null : (value as CaseSimulationTypeValue),
                              }
                            : current,
                        );
                      }}
                    >
                      <SelectTrigger aria-label="Case classification" className="max-w-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="unset">Unset</SelectItem>
                        <SelectItem value="development">Development</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-sm font-normal capitalize leading-5 text-foreground">
                      {caseRecord.simulationType ?? 'Unset'}
                    </p>
                  )}
                  {hasAmbiguousDiagnosticsTiers ? (
                    <Alert variant="warning">
                      Diagnostics provenance has evidence from both {diagnosticsTierLabel} tiers;
                      SimBoard cannot determine one observed tier.
                    </Alert>
                  ) : hasDiagnosticsMismatch ? (
                    <Alert variant="warning">
                      Case classification is {caseRecord.simulationType}, but diagnostics provenance
                      is {diagnosticsTierLabel}.
                    </Alert>
                  ) : null}
                </div>
              </div>
            ) : null}

            <CaseConfigurationSummary record={caseRecord} identity={readableIdentity} />

            {readableIdentity ? (
              <CaseConfigurationDetails record={caseRecord} identity={readableIdentity} />
            ) : null}

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
                    description="Add, relabel, or remove links shared across executions in this case."
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
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    {resourceLinks.map(renderResourceLink)}
                  </div>
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
                <h2 className="text-lg font-semibold text-slate-950">Case Notes</h2>
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
                      <MarkdownContent
                        content={caseRecord.description}
                        className={
                          caseRecord.description?.trim()
                            ? undefined
                            : 'w-fit border-0 bg-transparent p-0'
                        }
                      />
                    </>
                  )}
                </div>

                <div className="grid items-start gap-5 md:grid-cols-2">
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
                        <MarkdownContent
                          content={caseRecord.keyFeatures}
                          className={
                            caseRecord.keyFeatures?.trim()
                              ? undefined
                              : 'w-fit border-0 bg-transparent p-0'
                          }
                        />
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
                        <MarkdownContent
                          content={caseRecord.knownIssues}
                          className={
                            caseRecord.knownIssues?.trim()
                              ? undefined
                              : 'w-fit border-0 bg-transparent p-0'
                          }
                        />
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
                        className={
                          caseRecord.notesMarkdown?.trim()
                            ? undefined
                            : 'w-fit border-0 bg-transparent p-0'
                        }
                      />
                    </>
                  )}
                </div>

                {isEditing ? (
                  <div>
                    <Label htmlFor="case-edit-reason" className="mb-1 block text-xs">
                      Edit reason (optional)
                    </Label>
                    <Textarea
                      id="case-edit-reason"
                      value={editReason}
                      onChange={(event) => setEditReason(event.target.value)}
                      placeholder="Why are these metadata changes needed?"
                      className="min-h-20"
                    />
                  </div>
                ) : null}

                {isEditing && summaryErrorMessage ? (
                  <Alert variant="error">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <p className="font-medium">Save blocked</p>
                        <p className="mt-1">{summaryErrorMessage}</p>
                      </div>
                    </div>
                  </Alert>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section
        ref={executionsSectionRef}
        tabIndex={-1}
        aria-label="Case executions"
        className="space-y-4"
      >
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Executions</h2>
              <p className="max-w-3xl text-sm text-muted-foreground" data-execution-instructions>
                Select 2–5 executions to compare simulation configurations and results.
                {hasMultipleCaseHashes
                  ? ' Multiple case hashes detected. Group by Case Hash to inspect configuration differences.'
                  : ''}
              </p>
            </div>
          </div>

          <div className="space-y-3 px-5 py-4" data-execution-toolbar>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                {showCaseHashContext ? (
                  <>
                    <div
                      className="inline-flex rounded-lg border bg-slate-50 p-1"
                      role="group"
                      aria-label="Execution view"
                    >
                      <Button
                        size="sm"
                        variant={viewMode === 'flat' ? 'default' : 'ghost'}
                        aria-pressed={viewMode === 'flat'}
                        onClick={() => setViewMode('flat')}
                      >
                        All executions
                      </Button>
                      <Button
                        size="sm"
                        variant={viewMode === 'grouped' ? 'default' : 'ghost'}
                        aria-pressed={viewMode === 'grouped'}
                        onClick={() => setViewMode('grouped')}
                      >
                        Group by Case Hash
                      </Button>
                    </div>
                  </>
                ) : null}
              </div>
              <div className="ml-auto flex w-full items-center justify-end gap-2 sm:w-auto">
                <ExecutionColumnsMenu
                  visibleColumns={visibleExecutionColumns}
                  onToggle={(key) =>
                    setVisibleExecutionColumns((columns) =>
                      columns.includes(key)
                        ? columns.filter((column) => column !== key)
                        : [...columns, key],
                    )
                  }
                />
                <div className="relative w-full sm:w-64">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <Input
                    value={executionQuery}
                    onChange={(event) => setExecutionQuery(event.target.value)}
                    placeholder="Search execution ID"
                    className="pl-9"
                    aria-label="Search executions"
                  />
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>{statusSummary}</span>
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                {caseSelectedExecutionCount > 0 ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2 text-xs text-slate-500"
                    onClick={() => caseId && setSelectedCaseExecutionIdsForCase(caseId, [])}
                  >
                    Clear selection
                  </Button>
                ) : null}
                <span className="text-xs text-slate-500" aria-live="polite">
                  {caseSelectedExecutionCount} selected
                </span>
                <Button
                  ref={compareButtonRef}
                  size="sm"
                  onClick={() => setIsCompareVisible(true)}
                  disabled={isCompareButtonDisabled}
                >
                  Compare ({caseSelectedExecutionCount})
                </Button>
              </div>
            </div>

            {hiddenSelectedCount > 0 ? (
              <div className="mt-3 text-xs text-slate-500">
                {hiddenSelectedCount} selected{' '}
                {hiddenSelectedCount === 1 ? 'execution is' : 'executions are'} in filtered-out
                groups.
              </div>
            ) : null}

            {artifactExecutionIds != null ? (
              <Alert
                variant="info"
                className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg px-3 py-2"
              >
                <p>
                  Showing {pluralize(filteredExecutionCount, 'execution')} linked to the selected
                  artifact.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="border-sky-200 bg-white text-sky-950 hover:bg-sky-100"
                  onClick={clearArtifactExecutionFilter}
                >
                  Clear artifact filter
                </Button>
              </Alert>
            ) : null}
          </div>

          <div className="border-t border-slate-200 px-5 py-4">
            <div className={useScrollableGroupsPanel ? 'lg:max-h-[70vh] lg:overflow-y-auto' : ''}>
              <div className="space-y-4">
                {(viewMode === 'grouped'
                  ? filteredExecutionGroups.length
                  : filteredFlatExecutions.length) === 0 ? (
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
                  <CaseExecutionsTable
                    executions={filteredFlatExecutions}
                    {...executionTableProps}
                  />
                ) : (
                  <div className="overflow-hidden rounded-xl border border-slate-200 bg-background">
                    <div className="max-h-[42rem] overflow-auto">
                      <Table className="min-w-[640px] table-fixed">
                        <colgroup>
                          <col style={{ width: '38%' }} />
                          <col style={{ width: '14%' }} />
                          <col style={{ width: '30%' }} />
                          <col style={{ width: '18%' }} />
                        </colgroup>
                        <TableHeader className="sticky top-0 z-10 bg-slate-50">
                          <TableRow className="hover:bg-slate-50">
                            <TableHead className="bg-slate-50">
                              <div className="flex items-center gap-1.5">
                                <span>Case Hash group</span>
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
                            <TableHead className="w-24 bg-slate-50">Executions</TableHead>
                            <TableHead className="bg-slate-50">Simulation period range</TableHead>
                            <TableHead className="bg-slate-50">Actions</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredExecutionGroups.map((group) => {
                            const isOpen = expandedGroupKeys.includes(group.key);
                            const groupPanelId = `case-hash-group-panel-${group.key}`;
                            const fullGroup =
                              executionGroups.find((candidate) => candidate.key === group.key) ??
                              group;
                            const groupSimulationWindow = formatGroupExecutionWindow(
                              fullGroup.executions.map(({ summary }) => summary),
                            );

                            return (
                              <Fragment key={group.key}>
                                <TableRow
                                  className="bg-white hover:bg-slate-50/80"
                                  data-case-hash-baseline={
                                    group.key === baselineGroup?.key ? 'true' : undefined
                                  }
                                >
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
                                          isOpen ? '' : '-rotate-90'
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
                                          {group.key === baselineGroup?.key ? (
                                            <Badge
                                              variant="secondary"
                                              className="text-xs font-normal"
                                              title="Comparison baseline for displayed groups, not an original or authoritative configuration."
                                            >
                                              Baseline
                                            </Badge>
                                          ) : null}
                                        </div>
                                      </div>
                                    </button>
                                    <div className="ml-7">
                                      <CaseHashConfigurationDifferences
                                        differences={
                                          configurationDifferences.get(group.caseHash) ?? []
                                        }
                                      />
                                    </div>
                                  </TableCell>
                                  <TableCell className="align-top">
                                    {fullGroup.executions.length}
                                  </TableCell>
                                  <TableCell className="whitespace-nowrap align-top">
                                    {groupSimulationWindow}
                                  </TableCell>
                                  <TableCell className="align-top">
                                    <button
                                      type="button"
                                      className="whitespace-nowrap rounded-sm font-medium text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                      onClick={() => toggleGroupExpansion(group.key, !isOpen)}
                                      aria-expanded={isOpen}
                                      aria-controls={groupPanelId}
                                    >
                                      {isOpen ? 'Hide executions' : 'View executions'}
                                    </button>
                                  </TableCell>
                                </TableRow>
                                {isOpen ? (
                                  <TableRow className="bg-slate-50/50 hover:bg-slate-50/50">
                                    <TableCell colSpan={4} className="p-0">
                                      <div
                                        id={groupPanelId}
                                        className="border-t border-slate-200 px-4 py-3"
                                      >
                                        <CaseExecutionsTable
                                          executions={group.executions}
                                          {...executionTableProps}
                                        />
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

          {executionsError ? (
            <Alert
              variant="error"
              className="flex items-center justify-between gap-3 rounded-none border-x-0 border-b-0 px-5 py-4"
            >
              <span>Could not load more execution metadata: {executionsError}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void refetchExecutions()}
              >
                Retry
              </Button>
            </Alert>
          ) : null}

          {hasNextPage ? (
            <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-5 py-4">
              <p className="text-sm text-slate-600">
                Loaded metadata for {allExecutions.length} of {executionTotal} executions. ID and
                simulation-date search and grouping include all case executions. Run-date and
                metadata search use loaded metadata only.
                {['run', 'initialization', 'machine'].includes(dateSort.key)
                  ? ' Metadata sort order is partial until remaining metadata loads.'
                  : ''}
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

          <div className="border-t border-slate-200 px-5 py-5">
            <CaseArtifactsTable
              artifacts={artifactValues}
              totalArtifactCount={caseRecord.artifacts.length}
              onFilterExecutionIds={filterExecutionsForArtifact}
            />
          </div>
        </div>
      </section>

      <Dialog open={shouldRenderCompare} onOpenChange={setIsCompareVisible}>
        {renderCompareSection ? (
          <DialogContent
            className="flex max-h-[90dvh] w-[94vw] max-w-[1600px] flex-col gap-0 overflow-hidden rounded-xl p-0 data-[state=closed]:!animate-none data-[state=open]:!animate-none"
            overlayClassName="bg-black/40"
            onInteractOutside={(event) => event.preventDefault()}
            onOpenAutoFocus={(event) => {
              event.preventDefault();
              compareTitleRef.current?.focus();
            }}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              const target = compareButtonRef.current?.disabled
                ? executionsSectionRef.current
                : compareButtonRef.current;
              target?.focus({ preventScroll: true });
            }}
          >
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-5 py-4 pr-12">
              <div className="min-w-0">
                <DialogTitle ref={compareTitleRef} tabIndex={-1} className="focus:outline-none">
                  Compare case executions
                </DialogTitle>
                <DialogDescription className="mt-1 truncate" title={caseRecord.name}>
                  {caseRecord.name}
                </DialogDescription>
              </div>
              <ExecutionPicker
                executions={executionCandidates}
                selectedIds={caseSelectedExecutionIds}
                onSelectionChange={(ids) => setSelectedCaseExecutionIdsForCase(caseRecord.id, ids)}
                loadMore={hasNextPage ? () => void fetchNextPage() : undefined}
                loadingMore={isFetchingNextPage}
              />
            </div>
            <div className="flex min-h-0 flex-col p-4 sm:p-5">
              {renderCompareSection({
                caseId: caseRecord.id,
                onClose: () => setIsCompareVisible(false),
              })}
            </div>
          </DialogContent>
        ) : null}
      </Dialog>

      {!authLoading && user?.is_superuser === true ? (
        <details className="rounded-xl border border-slate-200 p-5">
          <summary className="cursor-pointer text-sm font-semibold">Developer Details</summary>
          <div className="mt-4">
            <PerformanceSourceDirectories directories={caseRecord.sourceDirectories} />
          </div>
        </details>
      ) : null}

      <section>
        <MetadataHistory
          entries={history.data}
          total={history.total}
          loading={history.loading}
          loadingMore={history.isFetchingNextPage}
          loaded={history.loaded}
          error={history.error}
          canLoadMore={history.hasNextPage}
          onLoadMore={() => void history.fetchNextPage()}
          onOpenChange={setIsHistoryOpen}
        />
      </section>
    </div>
  );
};
