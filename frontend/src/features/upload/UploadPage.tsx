import axios from 'axios';
import { AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  ArchiveUploadValidationDetail,
  ArchiveUploadValidationError,
  IngestionUploadSimulationSummary,
  uploadSimulationArchive,
} from '@/features/upload/api/api';
import { toast } from '@/hooks/use-toast';
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
  const [selectedMachineId, setSelectedMachineId] = useState('');
  const [hpcUsername, setHpcUsername] = useState('');
  const [archiveFile, setArchiveFile] = useState<File | null>(null);
  const [archiveFileError, setArchiveFileError] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const [createdSimulations, setCreatedSimulations] = useState<IngestionUploadSimulationSummary[]>(
    [],
  );
  const [validationErrors, setValidationErrors] = useState<ArchiveUploadValidationError[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [fileInputKey, setFileInputKey] = useState(0);
  const validationPanelRef = useRef<HTMLDivElement | null>(null);

  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.id === selectedMachineId) ?? null,
    [machines, selectedMachineId],
  );
  const createdCaseSummary = useMemo(() => {
    if (createdSimulations.length === 0) {
      return null;
    }

    const firstSimulation = createdSimulations[0];
    const allSameCase = createdSimulations.every(
      (simulation) => simulation.case_id === firstSimulation.case_id,
    );

    if (!allSameCase) {
      return null;
    }

    return {
      id: firstSimulation.case_id,
      name: firstSimulation.case_name,
    };
  }, [createdSimulations]);
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
    setCreatedSimulations([]);
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
      setCreatedSimulations([]);
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
    setCreatedSimulations([]);
    setValidationErrors([]);

    try {
      const response = await uploadSimulationArchive({
        file: fileToUpload,
        machineName: selectedMachine.name,
        hpcUsername: hpcUsername.trim() || undefined,
      });

      resetFileSelection();
      setCreatedSimulations(response.simulations);

      setUploadStatus({
        tone: 'success',
        title: 'Archive ingested',
        description:
          response.created_count > 0
            ? `${response.created_count} simulation(s) created and ${response.duplicate_count} duplicate(s) skipped.`
            : `No new simulations were created. ${response.duplicate_count} duplicate(s) were skipped.`,
      });
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;

        if (isArchiveUploadValidationDetail(detail)) {
          setCreatedSimulations([]);
          setValidationErrors(detail.errors);
          setUploadStatus(null);
          return;
        }

        if (typeof detail === 'string') {
          setCreatedSimulations([]);
          setUploadStatus({
            tone: 'error',
            title: 'Upload failed',
            description: detail,
          });
          return;
        }
      }

      setCreatedSimulations([]);
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
    <div className="w-full min-h-[calc(100vh-64px)] bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-bold">Upload a Case or Run</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload either a full E3SM performance case archive or a single execution directory
            packaged as
            <code className="ml-1 rounded bg-gray-100 px-1 py-0.5 text-xs">
              &lt;execution_id&gt;/...
            </code>
            .
          </p>
        </header>

        <div className="space-y-6">
          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3 rounded-md border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="space-y-2">
                <p>
                  Supported archive types:{' '}
                  <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">.tar.gz</code>,{' '}
                  <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">.tgz</code>, and{' '}
                  <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">.zip</code>.
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
                  <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">
                    &lt;execution_id&gt;/...
                  </code>
                  .
                </p>
              </div>
            </div>

            <div className="mt-6 grid gap-5 md:grid-cols-2">
              <div>
                <label className="text-sm font-medium">
                  Machine <span className="text-red-500">*</span>
                </label>
                <select
                  className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3"
                  value={selectedMachineId}
                  onChange={(event) => setSelectedMachineId(event.target.value)}
                >
                  <option value="">Select a machine...</option>
                  {machines.map((machine) => (
                    <option key={machine.id} value={machine.id}>
                      {machine.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium">HPC Username</label>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-gray-300 px-3"
                  value={hpcUsername}
                  onChange={(event) => setHpcUsername(event.target.value)}
                  placeholder="Optional provenance username"
                  type="text"
                />
              </div>
            </div>

            <div className="mt-5">
              <label className="text-sm font-medium">
                Performance Archive <span className="text-red-500">*</span>
              </label>
              <input
                key={fileInputKey}
                accept={FILE_INPUT_ACCEPT}
                className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm file:mr-4 file:rounded-md file:border-0 file:bg-gray-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white"
                onChange={handleArchiveChange}
                type="file"
              />

              <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-600">
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <p className="font-medium text-gray-700">Required root files</p>
                    <p className="mt-1">
                      <code>e3sm_timing..*..*</code>, <code>CaseStatus..*.gz</code>,{' '}
                      <code>GIT_DESCRIBE..*.gz</code>
                    </p>
                  </div>
                  <div>
                    <p className="font-medium text-gray-700">
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
                <div className="mt-3 flex items-start gap-2 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    Selected <span className="font-medium">{archiveFile.name}</span> (
                    {(archiveFile.size / (1024 * 1024)).toFixed(2)} MB)
                  </span>
                </div>
              ) : null}

              {archiveFileError ? (
                <p className="mt-2 text-sm text-red-600">{archiveFileError}</p>
              ) : null}
            </div>

            {validationErrors.length > 0 ? (
              <div
                className="mt-5 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
                ref={validationPanelRef}
                tabIndex={-1}
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <p className="font-medium">
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
                            className="rounded-md border border-red-200 bg-white/70 p-3"
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
              </div>
            ) : null}

            <div className="mt-6 flex justify-end gap-3">
              <button
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700"
                onClick={resetFileSelection}
                type="button"
              >
                Clear file
              </button>
              <button
                className="rounded-md bg-gray-900 px-5 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isUploading}
                onClick={handleUpload}
                type="button"
              >
                {isUploading ? 'Uploading archive...' : 'Upload archive'}
              </button>
            </div>

            {uploadStatus && validationErrors.length === 0 ? (
              <div
                className={`mt-5 rounded-md border p-4 text-sm ${
                  uploadStatus.tone === 'success'
                    ? 'border-green-200 bg-green-50 text-green-800'
                    : uploadStatus.tone === 'error'
                      ? 'border-red-200 bg-red-50 text-red-800'
                      : 'border-blue-200 bg-blue-50 text-blue-900'
                }`}
              >
                <div className="flex items-start gap-2">
                  {uploadStatus.tone === 'success' ? (
                    <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : uploadStatus.tone === 'error' ? (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <Info className="mt-0.5 h-4 w-4 shrink-0" />
                  )}
                  <div>
                    <p className="font-medium">{uploadStatus.title}</p>
                    <p className="mt-1">{uploadStatus.description}</p>
                  </div>
                </div>
              </div>
            ) : null}

            {createdSimulations.length > 0 ? (
              <div className="mt-5 rounded-md border border-gray-200 bg-white text-sm">
                <div className="flex items-center justify-between gap-4 border-b border-gray-200 bg-gray-50/60 px-4 py-3">
                  <div>
                    <p className="font-medium text-gray-900">
                      Created simulations ({createdSimulations.length})
                    </p>
                    {createdCaseSummary ? (
                      <p className="mt-1 text-sm text-gray-700" title={createdCaseSummary.name}>
                        Case: {createdCaseSummary.name}
                      </p>
                    ) : null}
                  </div>
                  {createdCaseSummary ? (
                    <Link
                      className="shrink-0 text-sm font-medium text-blue-700 hover:underline"
                      to={`/cases/${createdCaseSummary.id}`}
                    >
                      View case
                    </Link>
                  ) : null}
                </div>

                <div className="max-h-96 overflow-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50 text-xs text-gray-600">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium">Execution ID</th>
                        <th className="px-4 py-3 text-right font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 bg-white">
                      {createdSimulations.map((simulation) => (
                        <tr className="hover:bg-gray-50" key={simulation.id}>
                          <td className="px-4 py-4">
                            <Link
                              className="block truncate font-medium text-blue-700 hover:underline"
                              title={simulation.execution_id}
                              to={`/simulations/${simulation.id}`}
                            >
                              {simulation.execution_id}
                            </Link>
                          </td>
                          <td className="px-4 py-4 text-right text-sm">
                            <div className="flex justify-end gap-3">
                              <Link
                                className="text-blue-700 hover:underline"
                                to={`/simulations/${simulation.id}`}
                              >
                                Open
                              </Link>
                              {!createdCaseSummary ? (
                                <Link
                                  className="text-blue-700 hover:underline"
                                  to={`/cases/${simulation.case_id}`}
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

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Archive Layout</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              The uploader is intended for packaged E3SM performance archives from systems such as
              Chrysalis and NERSC. You can upload a full case archive or a single execution
              directory at archive root. Files must live either at the execution-directory root or
              under <code>casedocs/</code> in the expected locations.
            </p>

            <div className="mt-4 rounded-md border border-gray-200 bg-gray-50 p-4">
              <h3 className="text-sm font-medium">Example</h3>
              <pre className="mt-2 overflow-x-auto text-xs text-gray-700">
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
              <p className="mt-2 text-xs text-gray-500">
                A full case archive includes the case directory above. A single-run archive can
                start directly at
                <code className="mx-1 rounded bg-gray-100 px-1 py-0.5">1081156.251218-200923/</code>
                .
              </p>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-medium">Required root files</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-700">
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
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-700">
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
