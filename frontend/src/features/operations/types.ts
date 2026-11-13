/** Response shapes of the read-only ingestion operations APIs. */

export const JOB_TYPES = ['staging', 'archive', 'diagnostics'] as const;
export type JobType = (typeof JOB_TYPES)[number];

export type ScheduledJobHealth = 'healthy' | 'failed' | 'running' | 'stale';

export interface UploadFailureCase {
  case_path: string;
  status_code: number | null;
  attempts: number;
  message: string;
}

export interface UploadFailures {
  counts: Record<string, number>;
  cases: UploadFailureCase[];
  truncated: boolean;
}

export interface ScheduledJobRun {
  id: string;
  status: 'running' | 'succeeded' | 'failed';
  started_at: string;
  finished_at: string | null;
  failure_reason: 'api_request' | 'filesystem' | 'unexpected' | null;
  failure_message: string | null;
  failure_status_code: number | null;
  upload_failures: UploadFailures | null;
}

export interface ScheduledJobHealthOut {
  id: string;
  machine_name: string;
  scan_mode: string;
  max_silence_minutes: number;
  max_duration_minutes: number;
  health: ScheduledJobHealth;
  last_reported_at: string | null;
  latest_completed_run: ScheduledJobRun | null;
  active_run: ScheduledJobRun | null;
  active_run_count: number;
  latest_upload_run: ScheduledJobRun | null;
}

export type UploadFailureCategory =
  | 'auth'
  | 'bad_upload'
  | 'conflict'
  | 'server'
  | 'unavailable'
  | 'other';

export interface UploadFailureDailyCount {
  day: string;
  machine_name: string;
  category: UploadFailureCategory;
  count: number;
}

export interface ScheduledJobHealthResponse {
  jobs: ScheduledJobHealthOut[];
  upload_failure_daily_counts: UploadFailureDailyCount[];
}

export interface IngestionSummaryRow {
  day: string;
  machine: string;
  case_id: string;
  case_name: string;
  hpc_username: string;
  new_executions: number;
}

export interface IngestionSummaryResponse {
  rows: IngestionSummaryRow[];
  totals: { new_executions: number; distinct_cases: number };
}

export interface RejectedExecution {
  machine_name: string;
  case_identity: string;
  execution_id: string;
  outcome: 'rejected_incomplete' | 'rejected_invalid';
  errors: Record<string, string>[];
}

export interface RejectedExecutionsResponse {
  executions: RejectedExecution[];
  total: number;
}
