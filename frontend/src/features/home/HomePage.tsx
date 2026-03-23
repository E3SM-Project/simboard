import { GitCompareArrows, Search, Upload } from 'lucide-react';
import { useMemo } from 'react';
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
import LatestSimulationsTable from '@/features/home/components/LatestSimulationsTable';
import type { Machine, SimulationOut } from '@/types/index';

interface HomePageProps {
  simulations: SimulationOut[];
  machines: Machine[];
}

export const HomePage = ({ simulations, machines }: HomePageProps) => {
  const latestSimulations = useMemo(
    () =>
      [...simulations]
        .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
        .slice(0, 6),
    [simulations],
  );
  const latestSubmission = latestSimulations[0]?.createdAt;
  const canonicalCount = simulations.filter((simulation) => simulation.isCanonical).length;
  const machineSimulationCounts = new Map<Machine['id'], number>();
  for (const simulation of simulations) {
    machineSimulationCounts.set(
      simulation.machineId,
      (machineSimulationCounts.get(simulation.machineId) ?? 0) + 1,
    );
  }
  const featuredMachines = [...machines]
    .sort(
      (left, right) =>
        (machineSimulationCounts.get(right.id) ?? 0) - (machineSimulationCounts.get(left.id) ?? 0),
    )
    .slice(0, 6);

  const workflows = [
    {
      title: 'Browse Curated Simulations',
      description: 'Filter simulations by case, campaign, context, and execution metadata.',
      to: '/browse',
      action: 'Open Browse',
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
      title: 'Upload a Simulation',
      description: 'Submit new simulation metadata to share results and preserve provenance.',
      to: '/upload',
      action: 'Open Upload',
      icon: Upload,
    },
  ];

  return (
    <main className="min-h-[70vh] bg-white px-4 py-10">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 rounded-2xl border border-muted bg-white p-8 shadow-sm md:flex-row md:items-start md:justify-between md:p-10">
        <div className="max-w-3xl space-y-5">
          <div className="space-y-3">
            <h1 className="text-4xl font-bold tracking-tight text-foreground md:text-5xl">
              Explore E3SM Simulations
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
              SimBoard is a web interface for exploring, comparing, and sharing curated simulations
              from the Department of Energy&apos;s Energy Exascale Earth System Model.
            </p>
          </div>

          <ul className="space-y-2 text-sm leading-6 text-muted-foreground md:text-base">
            <li>
              Browse cataloged runs across cases, campaigns, configurations, and execution metadata.
            </li>
            <li>
              Compare simulations side by side to inspect canonical status, versioning, and context.
            </li>
            <li>Review recent submissions and the machines used to run cataloged E3SM datasets.</li>
          </ul>

          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link to="/browse">Browse Simulations</Link>
            </Button>
            <Button asChild>
              <Link to="/upload">Upload Simulation</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/compare">Compare</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/simulations">All Simulations</Link>
            </Button>
          </div>

          <div className="grid overflow-hidden rounded-xl border border-muted sm:grid-cols-2 xl:grid-cols-4">
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 sm:border-r xl:border-b-0">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Total Simulations
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {simulations.length}
              </p>
            </div>
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 sm:border-b sm:border-r xl:border-b-0">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Canonical
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {canonicalCount}
              </p>
            </div>
            <div className="flex min-h-28 flex-col gap-4 border-b border-muted px-4 py-4 xl:border-b-0 xl:border-r">
              <p className="min-h-[2.75rem] text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Machines
              </p>
              <p className="mt-auto text-xl font-semibold leading-none text-foreground sm:text-2xl">
                {machines.length}
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
        <div className="grid gap-4 md:grid-cols-3">
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
            <h2 className="text-2xl font-bold">Recently Added Simulations</h2>
            <p className="text-muted-foreground">
              Preview recent catalog activity and jump directly into the full simulation index.
            </p>
          </div>
          <Button asChild variant="secondary">
            <Link to="/simulations">View All Simulations</Link>
          </Button>
        </div>
        <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
          <LatestSimulationsTable latestSimulations={latestSimulations} />
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
                <TableHead>GPU</TableHead>
                <TableHead>Simulation Count</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {featuredMachines.map((machine) => (
                <TableRow key={machine.id}>
                  <TableCell>{machine.name}</TableCell>
                  <TableCell>{machine.site || 'N/A'}</TableCell>
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
