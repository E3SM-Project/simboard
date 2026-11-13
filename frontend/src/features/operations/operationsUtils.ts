import {
  JOB_TYPES,
  type JobType,
  type RejectedExecution,
  type ScheduledJobHealthOut,
  type UploadFailureCase,
  type UploadFailureCategory,
  type UploadFailureDailyCount,
} from '@/features/operations/types';

export const RANGE_DAYS = [7, 14, 30, 90] as const;
export type RangeDays = (typeof RANGE_DAYS)[number];
const DEFAULT_RANGE_DAYS: RangeDays = 7;

export interface OperationsFilters {
  jobType?: JobType;
  siteName?: string;
  rangeDays: RangeDays;
}

/** Read filters from URL params, ignoring unknown values. */
export const parseOperationsFilters = (
  params: URLSearchParams,
  siteNames: string[],
): OperationsFilters => {
  const jobType = params.get('job_type');
  const siteName = params.get('site');
  const rangeDays = Number(params.get('range'));

  return {
    jobType: JOB_TYPES.find((value) => value === jobType),
    // Accept the site before the site list loads so the first request is filtered.
    siteName:
      siteName && (siteNames.length === 0 || siteNames.includes(siteName)) ? siteName : undefined,
    rangeDays: RANGE_DAYS.find((value) => value === rangeDays) ?? DEFAULT_RANGE_DAYS,
  };
};

/** Return the UTC date window [startDate, endDate) covering the last N days, including today. */
export const utcDateWindow = (rangeDays: number, now = new Date()) => {
  const end = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
  const toDate = (time: number) => new Date(time).toISOString().slice(0, 10);

  return { startDate: toDate(end - rangeDays * 86_400_000), endDate: toDate(end) };
};

export const formatUtc = (value: string | null | undefined) =>
  value ? new Date(value).toISOString().slice(0, 16).replace('T', ' ') : null;

export const JOB_STATUSES = ['healthy', 'running', 'failed', 'stale', 'never_reported'] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

/** Separate jobs that never reported from jobs that stopped reporting. */
export const getJobStatus = (job: ScheduledJobHealthOut): JobStatus =>
  job.health === 'stale' && job.last_reported_at === null ? 'never_reported' : job.health;

const FAILURE_REASON_LABELS: Record<string, string> = {
  api_request: 'API request failed',
  filesystem: 'Filesystem error',
  unexpected: 'Unexpected error',
};

const formatMinutes = (minutes: number) =>
  minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`;

/** Explain a job's status, mirroring how the API derives health. */
export const getJobDetails = (job: ScheduledJobHealthOut, now = new Date()): string | null => {
  const status = getJobStatus(job);
  const failure = describeFailure(job.latest_completed_run);
  if (status === 'never_reported') return 'No report received';
  if (status === 'stale') {
    const silentMinutes = (now.getTime() - Date.parse(job.last_reported_at ?? '')) / 60_000;
    // Stale without exceeding the silence limit means the newest run overran.
    const reason =
      silentMinutes > job.max_silence_minutes
        ? `No report for over ${formatMinutes(job.max_silence_minutes)}`
        : `Run exceeded ${formatMinutes(job.max_duration_minutes)} without finishing`;

    return failure ? `${reason}; last run: ${failure}` : reason;
  }
  if (status === 'running' && job.active_run) {
    const extra = job.active_run_count > 1 ? ` (${job.active_run_count} active runs)` : '';

    return `Started ${formatUtc(job.active_run.started_at)} UTC${extra}`;
  }

  return status === 'failed' ? failure : null;
};

const describeFailure = (run: ScheduledJobHealthOut['latest_completed_run']) => {
  if (!run?.failure_reason) return null;

  const httpStatus = run.failure_status_code ? ` (HTTP ${run.failure_status_code})` : '';
  const message = run.failure_message ? `: ${run.failure_message}` : '';

  return `${FAILURE_REASON_LABELS[run.failure_reason]}${httpStatus}${message}`;
};

export const filterJobs = (jobs: ScheduledJobHealthOut[], jobType?: JobType) =>
  jobType ? jobs.filter((job) => job.scan_mode === jobType) : jobs;

export interface FailedUploadRow extends UploadFailureCase {
  jobId: string;
  machineName: string;
}

/** Flatten the cases still failing in each job's latest upload run. */
export const getFailedUploads = (jobs: ScheduledJobHealthOut[]) => {
  const rows: FailedUploadRow[] = [];
  const truncatedJobs: { jobId: string; shown: number; total: number }[] = [];
  let total = 0;

  for (const job of jobs) {
    const failures = job.latest_upload_run?.upload_failures;
    if (!failures) continue;

    const jobTotal = Object.values(failures.counts).reduce((sum, count) => sum + count, 0);
    total += jobTotal;
    rows.push(
      ...failures.cases.map((failure) => ({
        ...failure,
        jobId: job.id,
        machineName: job.machine_name,
      })),
    );
    if (failures.truncated) {
      truncatedJobs.push({ jobId: job.id, shown: failures.cases.length, total: jobTotal });
    }
  }

  return { rows, truncatedJobs, total };
};

export const UPLOAD_FAILURE_CATEGORY_LABELS: Record<UploadFailureCategory, string> = {
  auth: 'Auth',
  bad_upload: 'Bad upload',
  conflict: 'Conflict',
  server: 'Server',
  unavailable: 'Unavailable',
  other: 'Other',
};

export interface DailyFailureRow {
  day: string;
  machineName: string;
  counts: Partial<Record<UploadFailureCategory, number>>;
  total: number;
}

/** Pivot daily counts in the window to one row per day and machine, newest first. */
export const getDailyFailureRows = (
  counts: UploadFailureDailyCount[],
  dateWindow: { startDate: string; endDate: string },
) => {
  const rowsByKey = new Map<string, DailyFailureRow>();
  const present = new Set<UploadFailureCategory>();

  for (const { day, machine_name, category, count } of counts) {
    if (day < dateWindow.startDate || day >= dateWindow.endDate) continue;

    const key = `${day}|${machine_name}`;
    const row = rowsByKey.get(key) ?? { day, machineName: machine_name, counts: {}, total: 0 };
    row.counts[category] = (row.counts[category] ?? 0) + count;
    row.total += count;
    rowsByKey.set(key, row);
    present.add(category);
  }

  const categories = (
    Object.keys(UPLOAD_FAILURE_CATEGORY_LABELS) as UploadFailureCategory[]
  ).filter((category) => present.has(category));
  const rows = [...rowsByKey.values()].sort(
    (left, right) =>
      right.day.localeCompare(left.day) || left.machineName.localeCompare(right.machineName),
  );

  return { rows, categories };
};

export const formatRejectionErrors = (errors: RejectedExecution['errors']) =>
  errors
    .map(({ field, message }) => (field && message ? `${field}: ${message}` : (message ?? field)))
    .filter(Boolean)
    .join('; ');
