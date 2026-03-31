import axios from 'axios';
import { AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { ChangeEvent, useMemo, useState } from 'react';

import {
  ArchiveUploadValidationDetail,
  ArchiveUploadValidationError,
  uploadSimulationArchive,
} from '@/features/upload/api/api';
import { toast } from '@/hooks/use-toast';
import type { Machine } from '@/types';

interface UploadPageProps {
  machines: Machine[];
}

const MAX_ARCHIVE_SIZE_BYTES = 50 * 1024 * 1024;
const SUPPORTED_ARCHIVE_EXTENSIONS = ['.tar.gz', '.tgz', '.zip'];
const FILE_INPUT_ACCEPT = '.tar.gz,.tgz,.zip,application/gzip,application/zip';

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

const isArchiveUploadValidationDetail = (detail: unknown): detail is ArchiveUploadValidationDetail => {
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
  const [validationErrors, setValidationErrors] = useState<ArchiveUploadValidationError[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [fileInputKey, setFileInputKey] = useState(0);

  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.id === selectedMachineId) ?? null,
    [machines, selectedMachineId],
  );

  const handleArchiveChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    const nextError = validateArchiveFile(nextFile);

    setArchiveFile(nextFile);
    setArchiveFileError(nextError);
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
      toast({
        title: 'Machine required',
        description: 'Select the machine that produced this performance archive.',
        variant: 'destructive',
      });
      return;
    }

    setIsUploading(true);
    setValidationErrors([]);

    try {
      const response = await uploadSimulationArchive({
        file: fileToUpload,
        machineName: selectedMachine.name,
        hpcUsername: hpcUsername.trim() || undefined,
      });

      resetFileSelection();

      toast({
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
          setValidationErrors(detail.errors);
          toast({
            title: 'Archive validation failed',
            description: detail.message,
            variant: 'destructive',
          });
          return;
        }

        if (typeof detail === 'string') {
          toast({
            title: 'Upload failed',
            description: detail,
            variant: 'destructive',
          });
          return;
        }
      }

      toast({
        title: 'Upload failed',
        description: 'We could not ingest the archive. Please review the archive and try again.',
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
          <h1 className="text-2xl font-bold">Upload an E3SM Performance Archive</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Submit a packaged performance archive instead of entering simulation metadata manually.
          </p>
        </header>

        <div className="space-y-6">
          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3 rounded-md border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="space-y-2">
                <p>
                  Supported archive types: <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">.tar.gz</code>,{' '}
                  <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">.tgz</code>, and{' '}
                  <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">.zip</code>.
                </p>
                <p>
                  Maximum upload size: <span className="font-medium">50 MB</span>. The backend validates archive layout
                  against the required E3SM performance-file specs before ingestion.
                </p>
                <p>
                  You can upload either a case archive containing one or more execution directories, or a single
                  execution packaged directly as <code className="rounded bg-blue-100 px-1 py-0.5 text-xs">&lt;execution_id&gt;/...</code>.
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

              <p className="mt-2 text-xs text-gray-500">
                Required root files: <code>e3sm_timing..*..*</code>, <code>CaseStatus..*.gz</code>,{' '}
                <code>GIT_DESCRIBE..*.gz</code>. Required <code>casedocs/</code> files: <code>README.case..*.gz</code>,{' '}
                <code>env_case.xml..*.gz</code>, <code>env_build.xml..*.gz</code>, and <code>env_run.xml..*</code>.
              </p>

              {archiveFile ? (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    Selected <span className="font-medium">{archiveFile.name}</span> ({(archiveFile.size / (1024 * 1024)).toFixed(2)} MB)
                  </span>
                </div>
              ) : null}

              {archiveFileError ? <p className="mt-2 text-sm text-red-600">{archiveFileError}</p> : null}
            </div>

            {validationErrors.length > 0 ? (
              <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <p className="font-medium">Archive validation failed.</p>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {validationErrors.map((error) => (
                        <li key={`${error.execution_dir}-${error.file_spec}-${error.location}`}>{error.message}</li>
                      ))}
                    </ul>
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
          </section>

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Archive Layout</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              The uploader is intended for packaged E3SM performance archives from systems such as Chrysalis and NERSC.
              You can upload a full case archive or a single execution directory at archive root. Files must live either
              at the execution-directory root or under <code>casedocs/</code> in the expected locations.
            </p>

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
