import { useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  ArchiveUploadValidationDetail,
  ArchiveUploadValidationError,
  IngestionUploadExecutionSummary,
  uploadExecutionArchive,
} from '@/features/upload/api/api';
import { toast } from '@/hooks/use-toast';
import { invalidateCatalog } from '@/lib/catalog/invalidateCatalog';
import { caseDetailsPath, executionDetailsPath } from '@/lib/catalog/urls';
import type { Machine } from '@/types';

interface UploadPageProps {
  machines: Machine[];
}

interface UploadStatus {
  tone: 'info' | 'success' | 'error';
  title: string;
  description: string;
}

const MAX_ARCHIVE_SIZE_BYTES = 50 * 1024 * 1024;
const SUPPORTED_ARCHIVE_EXTENSIONS = ['.tar.gz', '.tgz', '.zip'];
const FILE_INPUT_ACCEPT = '.tar.gz,.tgz,.zip,application/gzip,application/zip';
const EXECUTION_ID_PATTERN = /^\d+\.\d+-\d+$/;
const ARCHIVE_LEVEL_VALIDATION_LABEL = 'Archive-level validation';
const UPLOAD_STATUS_ICONS = { success: CheckCircle, error: AlertTriangle, info: Info } as const;

const hasSupportedArchiveExtension = (filename: string): boolean => {
  const normalized = filename.toLowerCase();

  return SUPPORTED_ARCHIVE_EXTENSIONS.some((extension) => normalized.endsWith(extension));
};

const validateArchiveFile = (file: File | null): string | null => {
  if (!file) {
    return 'Select a performance archive to upload.';
  }

  if (!hasSupportedArchiveExtension(file.name)) {
    return 'File must be a .tar.gz, .tgz, or .zip archive.';
  }

  if (file.size > MAX_ARCHIVE_SIZE_BYTES) {
    return 'File must be 50 MB or smaller.';
  }

  return null;
};

const stripArchiveExtension = (filename: string): string => {
  const normalized = filename.toLowerCase();
  const matchingExtension = SUPPORTED_ARCHIVE_EXTENSIONS.find((extension) =>
    normalized.endsWith(extension),
  );

  return matchingExtension ? filename.slice(0, -matchingExtension.length) : filename;
};

const formatExecutionDirLabel = (executionDir: string, archiveFilename?: string | null): string => {
  if (!executionDir) {
    return ARCHIVE_LEVEL_VALIDATION_LABEL;
  }

  const segments = executionDir.replace(/\\/g, '/').replace(/\/+$/, '').split('/').filter(Boolean);

  if (segments.length === 0) {
    return ARCHIVE_LEVEL_VALIDATION_LABEL;
  }

  const archiveRootName = archiveFilename ? stripArchiveExtension(archiveFilename) : null;
  const archiveRootIndex = archiveRootName ? segments.lastIndexOf(archiveRootName) : -1;

  if (archiveRootIndex >= 0) {
    return segments.slice(archiveRootIndex).join('/');
  }

  for (let index = segments.length - 1; index >= 0; index -= 1) {
    if (!EXECUTION_ID_PATTERN.test(segments[index])) {
      continue;
    }

    const previousSegment = segments[index - 1];

    if (previousSegment && !previousSegment.toLowerCase().startsWith('tmp')) {
      return `${previousSegment}/${segments[index]}`;
    }

    return segments[index];
  }

  return segments.length > 1 ? segments.slice(-2).join('/') : segments[0];
};

const formatValidationLocation = (location: string): string => {
  if (location === 'archive root') {
    return 'Execution root';
  }

  if (location === 'casedocs/') {
    return 'casedocs/';
  }

  return location;
};

const formatValidationIssueTitle = (error: ArchiveUploadValidationError): string => {
  switch (error.code) {
    case 'missing_required_file':
      return `Missing required file: ${error.file_spec}`;
    case 'multiple_matching_files':
      return `Multiple files matched: ${error.file_spec}`;
    case 'missing_required_value':
      return `Missing required value in: ${error.file_spec}`;
    case 'file_not_found':
      return 'Referenced metadata file was not found';
    default:
      return error.file_spec ? `Validation error: ${error.file_spec}` : 'Validation error';
  }
};

const shouldShowValidationMessage = (error: ArchiveUploadValidationError): boolean =>
  error.code === 'missing_required_value' || error.code === 'file_not_found';

const isArchiveUploadValidationDetail = (
  detail: unknown,
): detail is ArchiveUploadValidationDetail => {
  if (!detail || typeof detail !== 'object') {
    return false;
  }

  const candidate = detail as Partial<ArchiveUploadValidationDetail>;

  return (
    typeof candidate.message === 'string' &&
    Array.isArray(candidate.errors) &&
    candidate.errors.every(
      (error) =>
        error &&
        typeof error === 'object' &&
        typeof (error as Partial<ArchiveUploadValidationError>).message === 'string',
    )
  );
};

export const UploadPage = ({ machines }: UploadPageProps) => {
  const queryClient = useQueryClient();
  const [selectedMachineId, setSelectedMachineId] = useState('');
  const [hpcUsername, setHpcUsername] = useState('');
  const [archiveFile, setArchiveFile] = useState<File | null>(null);
  const [archiveFileError, setArchiveFileError] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const [createdExecutions, setCreatedExecutions] = useState<IngestionUploadExecutionSummary[]>([]);
  const [validationErrors, setValidationErrors] = useState<ArchiveUploadValidationError[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [fileInputKey, setFileInputKey] = useState(0);
  const validationPanelRef = useRef<HTMLDivElement | null>(null);

  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.id === selectedMachineId) ?? null,
    [machines, selectedMachineId],
  );
  const createdCaseSummary = useMemo(() => {
    if (createdExecutions.length === 0) {
      return null;
    }

    const firstExecution = createdExecutions[0];
    const allSameCase = createdExecutions.every(
      (execution) => execution.case_id === firstExecution.case_id,
    );

    if (!allSameCase) {
      return null;
    }

    return {
      id: firstExecution.case_id,
      name: firstExecution.case_name,
      machineName: firstExecution.machine_name,
      hpcUsername: firstExecution.hpc_username,
    };
  }, [createdExecutions]);
  const validationErrorGroups = useMemo(() => {
    const groups = new Map<string, ArchiveUploadValidationError[]>();

    for (const error of validationErrors) {
      const executionDir = error.execution_dir || 'Archive-level validation';
      const group = groups.get(executionDir);

      if (group) {
        group.push(error);
        continue;
      }

      groups.set(executionDir, [error]);
    }

    return Array.from(groups, ([executionDir, errors]) => ({
      executionDir,
      displayExecutionDir: formatExecutionDirLabel(executionDir, archiveFile?.name),
      errors,
    }));
  }, [archiveFile?.name, validationErrors]);
  const validationExecutionCount = validationErrorGroups.length;
  const validationIssueCount = validationErrors.length;

  useEffect(() => {
    if (validationErrors.length === 0) {
      return;
    }

    validationPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    validationPanelRef.current?.focus({ preventScroll: true });
  }, [validationErrors.length]);

  const handleArchiveChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    const nextError = validateArchiveFile(nextFile);

    setArchiveFile(nextFile);
    setArchiveFileError(nextError);
    setUploadStatus(null);
    setCreatedExecutions([]);
    setValidationErrors([]);
  };

  const resetFileSelection = () => {
    setArchiveFile(null);
    setArchiveFileError(null);
    setFileInputKey((current) => current + 1);
  };

  const handleUpload = async () => {
    const fileToUpload = archiveFile;
    const nextFileError = validateArchiveFile(fileToUpload);
    if (nextFileError || !fileToUpload) {
      setArchiveFileError(nextFileError);
      return;
    }

    if (!selectedMachine) {
      setCreatedExecutions([]);
      setUploadStatus({
        tone: 'error',
        title: 'Machine required',
        description: 'Select the machine that produced this performance archive before uploading.',
      });
      return;
    }

    setIsUploading(true);
    setUploadStatus({
      tone: 'info',
      title: 'Uploading and validating archive',
      description:
        'The archive is being uploaded, extracted, and checked against the required file specs.',
    });
    setCreatedExecutions([]);
    setValidationErrors([]);

    try {
      const response = await uploadExecutionArchive({
        file: fileToUpload,
        machineName: selectedMachine.name,
        hpcUsername: hpcUsername.trim() || undefined,
      });

      resetFileSelection();
      setCreatedExecutions(response.executions);
      await invalidateCatalog(queryClient);

      setUploadStatus({
        tone: 'success',
        title: 'Archive ingested',
        description:
          response.created_count > 0
            ? `${response.created_count} execution(s) created and ${response.duplicate_count} duplicate(s) skipped.`
            : `No new executions were created. ${response.duplicate_count} duplicate(s) were skipped.`,
      });
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;

        if (isArchiveUploadValidationDetail(detail)) {
          setCreatedExecutions([]);
          setValidationErrors(detail.errors);
          setUploadStatus(null);
          return;
        }

        if (typeof detail === 'string') {
          setCreatedExecutions([]);
          setUploadStatus({
            tone: 'error',
            title: 'Upload failed',
            description: detail,
          });
          return;
        }
      }

      setCreatedExecutions([]);
      setUploadStatus({
        tone: 'error',
        title: 'Upload failed',
        description: 'We could not ingest the archive. Please review the archive and try again.',
      });
      toast({
        title: 'Upload failed',
        description: 'An unexpected server or network error occurred while uploading the archive.',
        variant: 'destructive',
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="w-full min-h-[calc(100vh-64px)] bg-muted-subtle">
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Upload a Case</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Cases are normally ingested automatically from supported HPC environments. Use this form
            to manually upload a compressed E3SM performance case archive when it is not yet
            available in the catalog.
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            A case archive contains one or more execution directories. A single execution directory
            may also be uploaded when packaged as
            <code className="ml-1 rounded bg-muted px-1 py-0.5 text-xs">
              &lt;execution_id&gt;/...
            </code>
            .
          </p>
        </header>

        <div className="space-y-6">
          <section className="rounded-xl border bg-card p-6 shadow-sm">
            <Alert variant="info" className="flex items-start gap-3 p-4">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="space-y-2">
                <p>
                  <span className="font-medium">Automatic HPC ingestion:</span> current performance
                  archives are scanned regularly, and historical archives are scanned daily.
                  Schedules and date coverage vary by site. Targeted E3SM v3 historical data is
                  ingested from Chrysalis archives.
                </p>
                <p>
                  <a
                    className="font-medium underline underline-offset-2"
                    href="https://simboard.readthedocs.io/en/latest/user/ingestion-coverage/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    View ingestion coverage and schedules
                  </a>
                  .
                </p>
                <p>
                  Supported archive types:{' '}
                  <code className="rounded bg-sky-100 px-1 py-0.5 text-xs">.tar.gz</code>,{' '}
                  <code className="rounded bg-sky-100 px-1 py-0.5 text-xs">.tgz</code>, and{' '}
                  <code className="rounded bg-sky-100 px-1 py-0.5 text-xs">.zip</code>.
                </p>
                <p>
                  Maximum upload size: <span className="font-medium">50 MB</span>. The backend
                  validates archive layout against the required E3SM performance-file specs before
                  ingestion.
                </p>
                <p>
                  Browser uploads use strict validation. If any execution directory is incomplete or
                  invalid, the entire archive is rejected and no executions are ingested.
                </p>
                <p>
                  You can upload either a case archive containing one or more execution directories,
                  or a single execution packaged directly as{' '}
                  <code className="rounded bg-sky-100 px-1 py-0.5 text-xs">
                    &lt;execution_id&gt;/...
                  </code>
                  .
                </p>
              </div>
            </Alert>

            <div className="mt-6 grid gap-5 md:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="upload-machine">
                  Machine <RequiredMark />
                </Label>
                <Select value={selectedMachineId} onValueChange={setSelectedMachineId}>
                  <SelectTrigger id="upload-machine" aria-required="true">
                    <SelectValue placeholder="Select a machine…" />
                  </SelectTrigger>
                  <SelectContent>
                    {machines.map((machine) => (
                      <SelectItem key={machine.id} value={machine.id}>
                        {machine.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="upload-hpc-username">HPC Username</Label>
                <Input
                  id="upload-hpc-username"
                  value={hpcUsername}
                  onChange={(event) => setHpcUsername(event.target.value)}
                  placeholder="Optional provenance username"
                  type="text"
                />
              </div>
            </div>

            <div className="mt-5 space-y-1">
              <Label htmlFor="upload-archive">
                Performance Archive <RequiredMark />
              </Label>
              <Input
                key={fileInputKey}
                id="upload-archive"
                accept={FILE_INPUT_ACCEPT}
                aria-required="true"
                aria-invalid={archiveFileError ? true : undefined}
                aria-describedby={archiveFileError ? 'upload-archive-error' : undefined}
                className="cursor-pointer"
                onChange={handleArchiveChange}
                type="file"
              />

              <div className="mt-3 rounded-md border border-border bg-muted-subtle p-3 text-xs text-muted-foreground">
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <p className="font-medium text-foreground">Required root files</p>
                    <p className="mt-1">
                      <code>e3sm_timing..*..*</code>, <code>CaseStatus..*.gz</code>,{' '}
                      <code>GIT_DESCRIBE..*.gz</code>
                    </p>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">
                      Required <code>casedocs/</code> files
                    </p>
                    <p className="mt-1">
                      <code>README.case..*.gz</code>, <code>env_case.xml..*.gz</code>,{' '}
                      <code>env_build.xml..*.gz</code>, <code>env_run.xml..*</code>
                    </p>
                  </div>
                </div>
              </div>

              {archiveFile ? (
                <Alert variant="success" className="mt-3 flex items-start gap-2">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    Selected <span className="font-medium">{archiveFile.name}</span> (
                    {(archiveFile.size / (1024 * 1024)).toFixed(2)} MB)
                  </span>
                </Alert>
              ) : null}

              {archiveFileError ? (
                <p id="upload-archive-error" className="mt-2 text-sm text-destructive">
                  {archiveFileError}
                </p>
              ) : null}
            </div>

            {validationErrors.length > 0 ? (
              <Alert
                variant="error"
                role="group"
                aria-labelledby="upload-validation-heading"
                className="mt-5 p-4 text-red-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                ref={validationPanelRef}
                tabIndex={-1}
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <p id="upload-validation-heading" className="font-medium">
                      {validationExecutionCount} execution
                      {validationExecutionCount === 1 ? '' : 's'} failed validation. No executions
                      were ingested.
                    </p>
                    <p className="mt-1 text-red-700">
                      Review the {validationIssueCount} reported issue
                      {validationIssueCount === 1 ? '' : 's'} below, fix the metadata gaps, and
                      upload the archive again.
                    </p>
                    <div className="mt-3 space-y-3">
                      {validationErrorGroups.map(
                        ({ executionDir, displayExecutionDir, errors }) => (
                          <div
                            key={executionDir}
                            className="rounded-md border border-red-200 bg-card/70 p-3"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="font-medium text-red-900">{displayExecutionDir}</p>
                              <span className="shrink-0 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                                {errors.length} issue{errors.length === 1 ? '' : 's'}
                              </span>
                            </div>
                            <ul className="mt-2 space-y-2">
                              {errors.map((error) => (
                                <li
                                  key={`${executionDir}-${error.file_spec}-${error.location}-${error.code}`}
                                  className="rounded-md border border-red-100 bg-red-50/70 px-3 py-2"
                                >
                                  <p className="font-medium text-red-900">
                                    {formatValidationIssueTitle(error)}
                                  </p>
                                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-red-700">
                                    {error.location ? (
                                      <span className="rounded bg-red-100 px-2 py-0.5">
                                        Location: {formatValidationLocation(error.location)}
                                      </span>
                                    ) : null}
                                    {shouldShowValidationMessage(error) ? (
                                      <span>{error.message}</span>
                                    ) : null}
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                </div>
              </Alert>
            ) : null}

            <div className="mt-6 flex justify-end gap-3">
              <Button type="button" variant="outline" onClick={resetFileSelection}>
                Clear file
              </Button>
              <Button type="button" disabled={isUploading} onClick={handleUpload}>
                {isUploading ? 'Uploading archive…' : 'Upload archive'}
              </Button>
            </div>

            {uploadStatus && validationErrors.length === 0 ? (
              <UploadStatusAlert status={uploadStatus} />
            ) : null}

            {createdExecutions.length > 0 ? (
              <div className="mt-5 rounded-md border border-border bg-card text-sm">
                <div className="flex items-center justify-between gap-4 border-b border-border bg-muted-subtle/60 px-4 py-3">
                  <div>
                    <p className="font-medium text-foreground">
                      Created executions ({createdExecutions.length})
                    </p>
                    {createdCaseSummary ? (
                      <p className="mt-1 text-sm text-foreground" title={createdCaseSummary.name}>
                        Case: {createdCaseSummary.name}
                      </p>
                    ) : null}
                  </div>
                  {createdCaseSummary ? (
                    <Link
                      className="shrink-0 text-sm font-medium text-blue-600 hover:underline"
                      to={caseDetailsPath({
                        machineName: createdCaseSummary.machineName,
                        hpcUsername: createdCaseSummary.hpcUsername,
                        caseName: createdCaseSummary.name,
                      })}
                    >
                      View case
                    </Link>
                  ) : null}
                </div>

                <div className="max-h-96 overflow-auto">
                  <table className="min-w-full divide-y divide-border">
                    <thead className="bg-muted-subtle text-xs text-muted-foreground">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium">Execution ID</th>
                        <th className="px-4 py-3 text-right font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border bg-card">
                      {createdExecutions.map((execution) => (
                        <tr className="hover:bg-muted-subtle" key={execution.id}>
                          <td className="px-4 py-4">
                            <Link
                              className="block truncate font-medium text-blue-600 hover:underline"
                              title={execution.execution_id}
                              to={executionDetailsPath({
                                machineName: execution.machine_name,
                                hpcUsername: execution.hpc_username,
                                caseName: execution.case_name,
                                executionId: execution.execution_id,
                              })}
                            >
                              {execution.execution_id}
                            </Link>
                          </td>
                          <td className="px-4 py-4 text-right text-sm">
                            <div className="flex justify-end gap-3">
                              <Link
                                className="text-blue-600 hover:underline"
                                to={executionDetailsPath({
                                  machineName: execution.machine_name,
                                  hpcUsername: execution.hpc_username,
                                  caseName: execution.case_name,
                                  executionId: execution.execution_id,
                                })}
                              >
                                Open
                              </Link>
                              {!createdCaseSummary ? (
                                <Link
                                  className="text-blue-600 hover:underline"
                                  to={caseDetailsPath({
                                    machineName: execution.machine_name,
                                    hpcUsername: execution.hpc_username,
                                    caseName: execution.case_name,
                                  })}
                                >
                                  View case
                                </Link>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </section>

          <section className="rounded-xl border bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Archive Layout</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              The uploader is intended for packaged E3SM performance archives from systems such as
              Chrysalis and NERSC. You can upload a full case archive or a single execution
              directory at archive root. Files must live either at the execution-directory root or
              under <code>casedocs/</code> in the expected locations.
            </p>

            <div className="mt-4 rounded-md border border-border bg-muted-subtle p-4">
              <h3 className="text-sm font-medium">Example</h3>
              <pre className="mt-2 overflow-x-auto text-xs text-foreground">
                {`qa/
└── performance_archive/
    └── v3.LR.historical_0121/
        └── 1081156.251218-200923/
            ├── e3sm_timing.001.001
            ├── CaseStatus.001.gz
            ├── GIT_DESCRIBE.001.gz
            ├── GIT_CONFIG.001.gz
            ├── GIT_STATUS.001.gz
            └── CaseDocs/
                ├── README.case.001.gz
                ├── env_case.xml.001.gz
                ├── env_build.xml.001.gz
                └── env_run.xml.001.gz`}
              </pre>
              <p className="mt-2 text-xs text-muted-foreground">
                A full case archive includes the case directory above. A single-execution archive
                can start directly at
                <code className="mx-1 rounded bg-muted px-1 py-0.5">1081156.251218-200923/</code>.
              </p>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-medium">Required root files</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-foreground">
                  <li>
                    <code>e3sm_timing..*..*</code>
                  </li>
                  <li>
                    <code>CaseStatus..*.gz</code>
                  </li>
                  <li>
                    <code>GIT_DESCRIBE..*.gz</code>
                  </li>
                </ul>
              </div>

              <div>
                <h3 className="text-sm font-medium">Required casedocs files</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-foreground">
                  <li>
                    <code>README.case..*.gz</code>
                  </li>
                  <li>
                    <code>env_case.xml..*.gz</code>
                  </li>
                  <li>
                    <code>env_build.xml..*.gz</code>
                  </li>
                  <li>
                    <code>env_run.xml..*</code>
                  </li>
                </ul>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

const RequiredMark = () => (
  <>
    <span className="text-destructive" aria-hidden="true">
      *
    </span>
    <span className="sr-only">(required)</span>
  </>
);

const UploadStatusAlert = ({ status }: { status: UploadStatus }) => {
  const Icon = UPLOAD_STATUS_ICONS[status.tone];

  return (
    <Alert variant={status.tone} className="mt-5 flex items-start gap-2 p-4">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-medium">{status.title}</p>
        <p className="mt-1">{status.description}</p>
      </div>
    </Alert>
  );
};
