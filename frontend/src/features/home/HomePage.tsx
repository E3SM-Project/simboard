import { ArrowRight, FolderOpen, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/loading-state';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import { useCatalogOverview } from '@/lib/catalog/hooks/useCatalogOverview';
import { caseDetailsPath } from '@/lib/catalog/urls';
import type { Machine, Site } from '@/types/index';

import { ProductionCasesTable } from './components/ProductionCasesTable';

interface HomePageProps {
  machines: Machine[];
  sites: Site[];
}

interface InfrastructureRow {
  key: string;
  siteName: string;
  machine?: Machine;
}

interface InfrastructureTableProps {
  emptyMessage: string;
  machineCaseCounts: Map<Machine['id'], number>;
  rows: InfrastructureRow[];
}

const CURRENTLY_SUPPORTED_SITE_NAMES = new Set(['NERSC', 'LCRC']);

const InfrastructureTable = ({
  emptyMessage,
  machineCaseCounts,
  rows,
}: InfrastructureTableProps) => (
  <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
    <Table className="table-fixed">
      <TableHeader>
        <TableRow>
          <TableHead>Site</TableHead>
          <TableHead>Machine</TableHead>
          <TableHead>Architecture</TableHead>
          <TableHead>GPU Support</TableHead>
          <TableHead>Case Count</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ key, siteName, machine }) => (
          <TableRow key={key}>
            <TableCell>{siteName}</TableCell>
            <TableCell className="capitalize">{machine?.name ?? 'N/A'}</TableCell>
            <TableCell className="align-top">
              <TableCellText value={machine?.architecture ?? 'N/A'} lines={2} />
            </TableCell>
            <TableCell>{machine ? (machine.gpu ? 'Yes' : 'No') : 'N/A'}</TableCell>
            <TableCell>{machine ? (machineCaseCounts.get(machine.id) ?? 0) : 'N/A'}</TableCell>
          </TableRow>
        ))}
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={5} className="text-center text-muted-foreground">
              {emptyMessage}
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  </div>
);

export const HomePage = ({ machines, sites }: HomePageProps) => {
  const { data: overview, error, isLoading, refetch } = useCatalogOverview();
  const totalCases = overview?.totalCases ?? 0;
  const latestSubmission = overview?.latestSubmission;
  const recentCases = (overview?.recentCases ?? []).map((caseRecord) => ({
    ...caseRecord,
    machineSummary: caseRecord.machineName,
    hpcUsernameSummary: caseRecord.hpcUsername,
    lastUpdated: caseRecord.updatedAt,
  }));
  const machineCaseCounts = new Map<Machine['id'], number>(
    Object.entries(overview?.machineCounts ?? {}),
  );
  const siteIdByName = new Map(sites.map((site) => [site.name, site.id]));
  const machinesBySite = new Map<Site['id'], Machine[]>();
  machines.forEach((machine) => {
    const siteId = machine.siteId ?? (machine.site ? siteIdByName.get(machine.site) : undefined);
    if (!siteId) return;

    const siteMachines = machinesBySite.get(siteId) ?? [];
    siteMachines.push(machine);
    machinesBySite.set(siteId, siteMachines);
  });
  const siteMachineRows = sites.flatMap((site): InfrastructureRow[] => {
    const siteMachines = [...(machinesBySite.get(site.id) ?? [])].sort((left, right) =>
      left.name.localeCompare(right.name),
    );

    if (siteMachines.length === 0) {
      return [{ key: `site-${site.id}`, siteName: site.name, machine: undefined }];
    }

    return siteMachines.map((machine) => ({
      key: machine.id,
      siteName: site.name,
      machine,
    }));
  });
  const matchedMachineIds = new Set(
    siteMachineRows.flatMap((row) => (row.machine ? [row.machine.id] : [])),
  );
  const unmatchedMachineRows = machines
    .filter((machine) => !matchedMachineIds.has(machine.id))
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((machine) => ({
      key: machine.id,
      siteName: machine.site ?? 'N/A',
      machine,
    }));
  const infrastructureRows = [...siteMachineRows, ...unmatchedMachineRows];
  const currentlySupportedInfrastructureRows = infrastructureRows.filter(({ siteName }) =>
    CURRENTLY_SUPPORTED_SITE_NAMES.has(siteName),
  );
  const upcomingInfrastructureRows = infrastructureRows.filter(
    ({ siteName }) => !CURRENTLY_SUPPORTED_SITE_NAMES.has(siteName),
  );

  const workflows = [
    {
      title: 'Browse Cases',
      description:
        'Browse grouped execution work, scan related executions, and open deeper case details.',
      to: '/cases',
      action: 'Open Cases',
      icon: FolderOpen,
    },
    {
      title: 'Upload a Case',
      description:
        'Manually upload a compressed case archive when it is not available through automated HPC ingestion.',
      to: '/upload',
      action: 'Open Upload',
      icon: Upload,
    },
  ];

  if (isLoading) {
    return <LoadingState kind="page" label="Loading catalog overview" />;
  }

  if (error && !overview) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6">
        <div className="space-y-3 text-center">
          <p className="text-red-600">Could not load catalog overview.</p>
          <Button type="button" variant="outline" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-[70vh] bg-white px-4 py-10">
      {error ? (
        <div className="mx-auto mb-4 flex w-full max-w-7xl items-center justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <span>Could not refresh catalog overview. Showing previously loaded data.</span>
          <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      ) : null}

      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 rounded-2xl border border-muted bg-white p-8 shadow-sm md:flex-row md:items-start md:justify-between md:p-10">
        <div className="max-w-3xl space-y-5">
          <div className="space-y-3">
            <h1 className="text-4xl font-bold tracking-tight text-foreground md:text-5xl">
              Explore E3SM Simulations
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
              Discover and explore cataloged E3SM simulations.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link to="/cases">Browse Cases</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/upload">Upload Case</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/about">About SimBoard</Link>
            </Button>
          </div>

          <div className="border-t border-muted pt-5">
            <p className="text-sm font-medium text-foreground">Catalog at a glance</p>
            <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3">
              <div>
                <dt className="text-sm text-muted-foreground">Cases</dt>
                <dd className="mt-1 text-2xl font-semibold tracking-tight text-foreground">
                  {totalCases}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Executions</dt>
                <dd className="mt-1 text-2xl font-semibold tracking-tight text-foreground">
                  {overview?.totalExecutions ?? 0}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Compute systems</dt>
                <dd className="mt-1 text-2xl font-semibold tracking-tight text-foreground">
                  {machines.length}{' '}
                  <span className="text-base font-normal text-muted-foreground">
                    across {sites.length} {sites.length === 1 ? 'site' : 'sites'}
                  </span>
                </dd>
              </div>
            </dl>
            <p className="mt-5 text-sm text-muted-foreground">
              Last submission:{' '}
              <span className="font-medium text-foreground">
                {latestSubmission ? new Date(latestSubmission).toLocaleDateString() : 'N/A'}
              </span>
            </p>
          </div>
        </div>

        <div className="hidden md:flex md:max-w-sm md:flex-col md:items-center md:justify-center md:self-center">
          <div className="flex w-full items-center justify-center rounded-2xl border border-muted bg-muted/15 px-8 py-10">
            <img
              src="/logos/e3sm-logo.jpg"
              alt="E3SM logo"
              className="max-h-48 w-full object-contain"
            />
          </div>
        </div>
      </section>

      <section className="mx-auto mt-10 w-full max-w-7xl space-y-4">
        <div className="space-y-1">
          <h2 className="text-2xl font-bold">Common Workflows</h2>
          <p className="text-muted-foreground">
            Jump from the catalog overview into the primary SimBoard tasks.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {workflows.map((workflow) => {
            const Icon = workflow.icon;
            return (
              <div
                key={workflow.title}
                className="flex h-full flex-col gap-4 rounded-xl border border-muted bg-white p-5 shadow-sm"
              >
                <div className="flex items-center gap-2 text-foreground">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-lg font-semibold">{workflow.title}</h3>
                </div>
                <p className="text-sm leading-6 text-muted-foreground">{workflow.description}</p>
                <Button asChild variant="secondary" className="mt-auto self-start">
                  <Link to={workflow.to}>{workflow.action}</Link>
                </Button>
              </div>
            );
          })}
        </div>
      </section>

      <section className="mx-auto mt-10 w-full max-w-7xl">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="space-y-1">
            <h2 className="text-2xl font-bold">Production Cases</h2>
            <p className="text-muted-foreground">
              Production-classified simulations across all machines.
            </p>
          </div>
          <Button asChild variant="secondary">
            <Link to="/cases?simulationType=production">Browse Production Cases</Link>
          </Button>
        </div>
        <ProductionCasesTable />
      </section>

      <section className="mx-auto mt-10 w-full max-w-7xl">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="space-y-1">
            <h2 className="text-2xl font-bold">Recent Cases</h2>
            <p className="text-muted-foreground">
              Open recently active case pages and move from grouped execution context into execution
              details.
            </p>
          </div>
          <Button asChild variant="secondary">
            <Link to="/cases">Browse Recent Cases</Link>
          </Button>
        </div>
        <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[32%] min-w-[320px]">Case Name</TableHead>
                <TableHead>HPC Username</TableHead>
                <TableHead>Machines</TableHead>
                <TableHead>Executions</TableHead>
                <TableHead>Case Group</TableHead>
                <TableHead>Last Updated</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentCases.map((caseRecord) => (
                <TableRow key={caseRecord.id}>
                  <TableCell className="align-top">
                    <TableCellText value={caseRecord.name} lines={1} />
                  </TableCell>
                  <TableCell className="align-top">
                    <TableCellText value={caseRecord.hpcUsernameSummary} lines={1} />
                  </TableCell>
                  <TableCell className="align-top">
                    <TableCellText value={caseRecord.machineSummary} lines={1} />
                  </TableCell>
                  <TableCell>{caseRecord.executionCount}</TableCell>
                  <TableCell>{caseRecord.caseGroup ?? '—'}</TableCell>
                  <TableCell>{new Date(caseRecord.lastUpdated).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <Button asChild variant="outline" size="sm" className="h-8 gap-1 px-2">
                      <Link
                        to={caseDetailsPath({
                          machineName: caseRecord.machineName,
                          hpcUsername: caseRecord.hpcUsername,
                          caseName: caseRecord.name,
                        })}
                      >
                        Open
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
      <section className="mx-auto mt-10 w-full max-w-7xl space-y-8">
        <div className="space-y-1">
          <h2 className="text-2xl font-bold">Sites and Machines</h2>
          <p className="text-muted-foreground">
            Computing facilities and systems represented in the SimBoard catalog.
          </p>
        </div>
        <div className="space-y-4">
          <div className="space-y-1">
            <h3 className="text-lg font-semibold">Currently Supported</h3>
            <p className="text-sm text-muted-foreground">
              NERSC and LCRC sites and machines with active SimBoard support.
            </p>
          </div>
          <InfrastructureTable
            emptyMessage="No currently supported sites or machines are available."
            machineCaseCounts={machineCaseCounts}
            rows={currentlySupportedInfrastructureRows}
          />
        </div>
        <div className="space-y-4">
          <div className="space-y-1">
            <h3 className="text-lg font-semibold">Upcoming Support</h3>
            <p className="text-sm text-muted-foreground">
              Additional sites and machines planned for future SimBoard support.
            </p>
          </div>
          <InfrastructureTable
            emptyMessage="No upcoming sites or machines are listed."
            machineCaseCounts={machineCaseCounts}
            rows={upcomingInfrastructureRows}
          />
        </div>
      </section>
      <footer className="mx-auto mt-12 w-full max-w-7xl border-t border-muted pt-6">
        <div className="flex flex-col gap-6 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <img
              src="/logos/simboard-logo-full.png"
              alt="SimBoard logo"
              className="h-10 w-auto object-contain"
              loading="lazy"
            />
            <p>Public interface for browsing, comparing, and sharing cataloged E3SM executions.</p>
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <a
              href="https://www.e3sm.org/"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-opacity hover:opacity-80"
              aria-label="Visit the E3SM website"
            >
              <img
                src="/logos/e3sm-logo.jpg"
                alt="E3SM logo"
                className="h-10 w-auto object-contain"
                loading="lazy"
              />
            </a>
            <a
              href="https://www.energy.gov/"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-opacity hover:opacity-80"
              aria-label="Visit the U.S. Department of Energy website"
            >
              <img
                src="/logos/doe-logo.png"
                alt="U.S. Department of Energy logo"
                className="h-12 w-auto object-contain"
                loading="lazy"
              />
            </a>
          </div>
        </div>
      </footer>
    </main>
  );
};
