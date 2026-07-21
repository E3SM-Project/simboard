import { ArrowRight, FolderOpen, GitCompareArrows, Search, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
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
import type { Machine, Site } from '@/types/index';

interface HomePageProps {
  machines: Machine[];
  sites: Site[];
}

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
  const machineSimulationCounts = new Map<Machine['id'], number>(
    Object.entries(overview?.machineCounts ?? {}),
  );
  const featuredMachines = [...machines]
    .sort(
      (left, right) =>
        (machineSimulationCounts.get(right.id) ?? 0) - (machineSimulationCounts.get(left.id) ?? 0),
    )
    .slice(0, 6);
  const siteNamesById = new Map(sites.map((site) => [site.id, site.name]));
  const machinesBySite = new Map(
    sites.map((site) => [
      site.id,
      machines.filter(
        (machine) => machine.siteId === site.id || (!machine.siteId && machine.site === site.name),
      ),
    ]),
  );

  const workflows = [
    {
      title: 'Browse Cases',
      description:
        'Browse grouped simulation work, scan related runs, and open deeper case details.',
      to: '/cases',
      action: 'Open Cases',
      icon: FolderOpen,
    },
    {
      title: 'Explore Runs',
      description:
        'Use the advanced run browser when you need detailed filters, selection, and compare setup.',
      to: '/browse',
      action: 'Open Runs',
      icon: Search,
    },
    {
      title: 'Compare Simulations',
      description: 'Inspect selected runs side by side to review differences in metadata.',
      to: '/compare',
      action: 'Open Compare',
      icon: GitCompareArrows,
    },
    {
      title: 'Upload a Case',
      description: 'Submit new case metadata to share results and preserve provenance.',
      to: '/upload',
      action: 'Open Upload',
      icon: Upload,
    },
  ];

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-500">
        Loading catalog overview…
      </div>
    );
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
              SimBoard is a public-facing interface for browsing, comparing, and sharing cataloged
              E3SM simulations. Start with a broad view of the catalog, then drill into cases and
              runs when you want more detail.
            </p>
          </div>

          <ul className="space-y-2 text-sm leading-6 text-muted-foreground md:text-base">
            <li>
              Browse simulation collections, open case pages, and inspect the runs connected to
              them.
            </li>
            <li>
              Jump into run-level views when you need machine, version, user, or date-specific
              context.
            </li>
            <li>
              Compare simulations side by side and share specific case or run pages with
              collaborators.
            </li>
          </ul>

          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link to="/cases">Browse Cases</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/browse">Open Runs</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/compare">Compare</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/upload">Upload Simulation</Link>
            </Button>
          </div>

          <div className="grid overflow-hidden rounded-xl border border-muted sm:grid-cols-2 xl:grid-cols-5">
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 sm:border-r xl:border-b-0">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Total Cases
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {totalCases}
              </p>
            </div>
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 sm:border-r xl:border-b-0">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Total Simulations
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {overview?.totalSimulations ?? 0}
              </p>
            </div>
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 sm:border-r xl:border-b-0 xl:border-r">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Machines
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {machines.length}
              </p>
            </div>
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 sm:border-r xl:border-b-0 xl:border-r">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Sites
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {sites.length}
              </p>
            </div>
            <div className="flex min-h-28 flex-col gap-4 px-4 py-4">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Latest Submission
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {latestSubmission ? new Date(latestSubmission).toLocaleDateString() : 'N/A'}
              </p>
            </div>
          </div>
        </div>

        <div className="hidden md:flex md:max-w-sm md:flex-col md:items-center md:justify-center md:gap-4 md:self-center">
          <div className="flex w-full items-center justify-center rounded-2xl border border-muted bg-muted/15 px-8 py-10">
            <img
              src="/logos/e3sm-logo.jpg"
              alt="E3SM logo"
              className="max-h-28 w-full object-contain"
            />
          </div>
          <p className="text-center text-sm leading-6 text-muted-foreground">
            SimBoard surfaces curated simulations and catalog activity from the E3SM project.
          </p>
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
        <div className="mb-4 space-y-1">
          <h2 className="text-2xl font-bold">Sites</h2>
          <p className="text-muted-foreground">
            Facilities hosting machines represented in the SimBoard catalog.
          </p>
        </div>
        <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead>Site</TableHead>
                <TableHead>Machines</TableHead>
                <TableHead>Machine Count</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sites.map((site) => {
                const siteMachines = machinesBySite.get(site.id) ?? [];
                return (
                  <TableRow key={site.id}>
                    <TableCell>{site.name}</TableCell>
                    <TableCell>
                      <TableCellText
                        value={siteMachines.map((machine) => machine.name).join(', ') || 'N/A'}
                        lines={2}
                      />
                    </TableCell>
                    <TableCell>{siteMachines.length}</TableCell>
                  </TableRow>
                );
              })}
              {sites.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground">
                    No sites available.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="mx-auto mt-10 w-full max-w-7xl">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="space-y-1">
            <h2 className="text-2xl font-bold">Recent Cases</h2>
            <p className="text-muted-foreground">
              Open recently active case pages and move from grouped simulation context into run
              details.
            </p>
          </div>
          <Button asChild variant="secondary">
            <Link to="/cases">Browse Cases</Link>
          </Button>
        </div>
        <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[32%] min-w-[320px]">Case Name</TableHead>
                <TableHead>HPC Username</TableHead>
                <TableHead>Machines</TableHead>
                <TableHead>Runs</TableHead>
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
                  <TableCell>{caseRecord.simulationCount}</TableCell>
                  <TableCell>{caseRecord.caseGroup ?? '—'}</TableCell>
                  <TableCell>{new Date(caseRecord.lastUpdated).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <Button asChild variant="outline" size="sm" className="h-8 gap-1 px-2">
                      <Link to={`/cases/${caseRecord.id}`}>
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

      <section className="mx-auto mt-10 w-full max-w-7xl">
        <div className="mb-4 space-y-1">
          <h2 className="text-2xl font-bold">Machines</h2>
          <p className="text-muted-foreground">
            Systems used to run simulations represented in the SimBoard catalog.
          </p>
        </div>
        <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Architecture</TableHead>
                <TableHead>GPU Support</TableHead>
                <TableHead>Simulation Count</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {featuredMachines.map((machine) => (
                <TableRow key={machine.id}>
                  <TableCell>{machine.name}</TableCell>
                  <TableCell>
                    {(machine.siteId ? siteNamesById.get(machine.siteId) : undefined) ??
                      machine.site ??
                      'N/A'}
                  </TableCell>
                  <TableCell className="align-top">
                    <TableCellText value={machine.architecture || 'N/A'} lines={2} />
                  </TableCell>
                  <TableCell>{machine.gpu ? 'Yes' : 'No'}</TableCell>
                  <TableCell>{machineSimulationCounts.get(machine.id) ?? 0}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
            <p>Public interface for browsing, comparing, and sharing cataloged E3SM simulations.</p>
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
