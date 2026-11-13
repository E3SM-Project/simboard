import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useAuth } from '@/auth/hooks/useAuth';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { FailedUploadsSection } from '@/features/operations/components/FailedUploadsSection';
import { JobHealthSection } from '@/features/operations/components/JobHealthSection';
import { RecentIngestionsSection } from '@/features/operations/components/RecentIngestionsSection';
import { RejectedExecutionsSection } from '@/features/operations/components/RejectedExecutionsSection';
import {
  useIngestionSummary,
  useJobHealth,
  useRejectedExecutions,
} from '@/features/operations/hooks/useOperations';
import {
  formatUtc,
  parseOperationsFilters,
  RANGE_DAYS,
  utcDateWindow,
} from '@/features/operations/operationsUtils';
import { JOB_TYPES } from '@/features/operations/types';
import type { Site } from '@/types';

const ALL = 'all';
const PAGE_CLASS = 'mx-auto w-full max-w-7xl px-4 py-8';

interface OperationsDashboardPageProps {
  sites: Site[];
}

/** Admin-only page; data requests start only after the role check passes. */
export const OperationsDashboardPage = ({ sites }: OperationsDashboardPageProps) => {
  const { user } = useAuth();

  if (user?.role !== 'admin') {
    return (
      <main className={PAGE_CLASS}>
        <Alert variant="warning" role="group" className="rounded-xl p-6">
          <h1 className="font-semibold">Administrators only</h1>
          <p>The operations dashboard is available to SimBoard administrators.</p>
        </Alert>
      </main>
    );
  }

  return <OperationsDashboard sites={sites} />;
};

const OperationsDashboard = ({ sites }: OperationsDashboardPageProps) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const siteNames = useMemo(() => sites.map((site) => site.name).sort(), [sites]);
  const { jobType, siteName, rangeDays } = parseOperationsFilters(searchParams, siteNames);
  // Recompute each render so the window advances past UTC midnight; query keys
  // change only when its dates do.
  const dateWindow = utcDateWindow(rangeDays);

  const jobsQuery = useJobHealth(siteName);
  const summaryQuery = useIngestionSummary(siteName, dateWindow.startDate, dateWindow.endDate);
  const rejectedQuery = useRejectedExecutions(siteName);

  const setFilter = (key: string, value: string, defaultValue = ALL) => {
    const next = new URLSearchParams(searchParams);
    if (value === defaultValue) next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  };
  const resetFilters = () => setSearchParams({}, { replace: true });
  const resetJobFilters = jobType || siteName ? resetFilters : undefined;
  const resetSiteFilter = siteName ? resetFilters : undefined;
  const filtersActive = Boolean(jobType || siteName) || rangeDays !== RANGE_DAYS[0];

  const queries = [jobsQuery, summaryQuery, rejectedQuery];
  const isRefreshing = queries.some((query) => query.isFetching);
  // Report the oldest load so the page never looks fresher than any section.
  const loadedAt = queries.map((query) => query.dataUpdatedAt).filter((time) => time > 0);
  const updatedAt = loadedAt.length
    ? formatUtc(new Date(Math.min(...loadedAt)).toISOString())
    : null;
  const refreshAll = () => void Promise.all(queries.map((query) => query.refetch()));

  return (
    <main className={`${PAGE_CLASS} space-y-4`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Operations Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Job health, failed uploads, ingestions, and rejected executions for this environment.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3 lg:w-[36rem]">
          <div className="space-y-1">
            <Label htmlFor="operations-job-type">Job type</Label>
            <Select value={jobType ?? ALL} onValueChange={(value) => setFilter('job_type', value)}>
              <SelectTrigger id="operations-job-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All job types</SelectItem>
                {JOB_TYPES.map((value) => (
                  <SelectItem key={value} value={value} className="capitalize">
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="operations-site">Site</Label>
            <Select value={siteName ?? ALL} onValueChange={(value) => setFilter('site', value)}>
              <SelectTrigger id="operations-site">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All sites</SelectItem>
                {siteNames.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="operations-range">Date range</Label>
            <Select
              value={String(rangeDays)}
              onValueChange={(value) => setFilter('range', value, String(RANGE_DAYS[0]))}
            >
              <SelectTrigger id="operations-range">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RANGE_DAYS.map((days) => (
                  <SelectItem key={days} value={String(days)}>
                    Last {days} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="text-xs text-muted-foreground">
          Times are UTC. Job type applies to job health and failed upload cases; date range applies
          to recent ingestions and daily failure counts.
        </p>
        <div className="flex items-center gap-3">
          {updatedAt ? (
            <span className="text-xs text-muted-foreground">Updated {updatedAt} UTC</span>
          ) : null}
          {filtersActive ? (
            <Button type="button" variant="link" size="sm" className="px-0" onClick={resetFilters}>
              Reset filters
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isRefreshing}
            onClick={refreshAll}
          >
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </div>

      <JobHealthSection query={jobsQuery} jobType={jobType} onResetFilters={resetJobFilters} />
      <FailedUploadsSection
        query={jobsQuery}
        jobType={jobType}
        dateWindow={dateWindow}
        rangeDays={rangeDays}
        onResetFilters={resetJobFilters}
      />
      <RecentIngestionsSection
        query={summaryQuery}
        rangeDays={rangeDays}
        onResetFilters={resetSiteFilter}
      />
      <RejectedExecutionsSection query={rejectedQuery} onResetFilters={resetSiteFilter} />
    </main>
  );
};
