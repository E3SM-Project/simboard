import {
  BadgeCheck,
  Clock,
  FlaskConical,
  GitBranch,
  Lightbulb,
  Rocket,
  Server,
  Tag,
} from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import type { SimulationOut } from '@/types/index';

interface SimulationResultCard {
  simulation: SimulationOut;
  selected: boolean;
  isSelectionDisabled: boolean;
  handleSelect: (sim: SimulationOut) => void;
}

export const SimulationResultCard = ({
  simulation,
  selected,
  isSelectionDisabled,
  handleSelect,
}: SimulationResultCard) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  // -------------------- Derived Data --------------------
  const startStr = simulation.simulationStartDate
    ? new Date(simulation.simulationStartDate).toISOString().slice(0, 10)
    : 'N/A';
  const endStr = simulation.simulationEndDate
    ? new Date(simulation.simulationEndDate).toISOString().slice(0, 10)
    : 'N/A';
  const runStartStr = simulation.runStartDate
    ? new Date(simulation.runStartDate).toISOString().slice(0, 10)
    : 'N/A';
  const runEndStr = simulation.runEndDate
    ? new Date(simulation.runEndDate).toISOString().slice(0, 10)
    : 'N/A';
  const createdAtStr = new Date(simulation.createdAt).toISOString().slice(0, 10);
  const updatedAtStr = new Date(simulation.updatedAt).toISOString().slice(0, 10);
  const diagnosticLinks = simulation.groupedLinks.diagnostic ?? [];
  const performanceLinks = simulation.groupedLinks.performance ?? [];
  const runScripts = simulation.groupedArtifacts.runScript ?? [];
  const archivePaths = simulation.groupedArtifacts.archive ?? [];
  const postprocessingScripts =
    simulation.groupedArtifacts.postProcessingScript ??
    simulation.groupedArtifacts.postprocessingScript ??
    [];

  return (
    <Card
      className={`flex h-full w-full flex-col rounded-2xl border bg-white p-0 shadow-sm transition-shadow ${
        selected
          ? 'border-slate-300 ring-1 ring-slate-200'
          : 'border-slate-200 hover:shadow-md'
      } ${isSelectionDisabled ? 'cursor-default' : 'cursor-pointer'}`}
      onClick={() => {
        if (!isSelectionDisabled || selected) {
          handleSelect(simulation);
        }
      }}
    >
      <div className="flex flex-col items-start gap-4 p-5 sm:flex-row">
        <Checkbox
          checked={selected}
          onCheckedChange={() => handleSelect(simulation)}
          aria-label="Select for comparison"
          className="mt-1"
          disabled={isSelectionDisabled && !selected}
          onClick={(event) => event.stopPropagation()}
          style={{ width: 24, height: 24 }}
        />
        <div className="w-full max-w-2xl min-w-0 flex-1">
          <CardHeader className="mb-4 flex flex-col items-start gap-2.5 p-0">
            <div className="min-w-0">
              <span className="block break-words text-base font-semibold tracking-tight text-slate-950">
                {simulation.executionId}
              </span>
              <div className="mt-1 break-words text-sm leading-6 text-slate-500">
                <span className="font-medium text-slate-600">Case:</span> {simulation.caseName}
              </div>
            </div>
            <div className="flex w-full flex-wrap items-center gap-2 text-xs uppercase tracking-[0.12em] text-slate-400">
              <span>Status</span>
              <SimulationStatusBadge status={simulation.status} />
            </div>
          </CardHeader>

          <CardContent
            className="p-0"
            style={{
              minHeight: '340px', // adjust as needed for consistent bottom alignment
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* One metadata item per line with bold labels */}
            <dl className="mb-2 space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <dt className="flex items-center gap-2 whitespace-nowrap font-semibold text-slate-700">
                  <Rocket className="w-4 h-4" /> Campaign:
                </dt>
                <dd className="break-words font-normal text-slate-600">{simulation.campaign}</dd>
              </div>

              <div className="flex items-start gap-2">
                <dt className="flex items-center gap-2 whitespace-nowrap font-semibold text-slate-700">
                  <Lightbulb className="w-4 h-4" /> Experiment:
                </dt>
                <dd className="break-words font-normal text-slate-600">
                  {simulation.experimentType}
                </dd>
              </div>

              <div className="flex items-start gap-2">
                <dt className="flex items-center gap-2 whitespace-nowrap font-semibold text-slate-700">
                  <Clock className="w-4 h-4" /> Model Run Dates:
                </dt>
                <dd className="break-words font-normal text-slate-600">
                  {startStr} {'\u2192'} {endStr}
                </dd>
              </div>
            </dl>

            <div className="my-2 w-full border-t border-slate-200" />

            <div className="mb-4 mt-2 space-y-2 text-xs text-slate-700">
              <div className="flex items-start gap-2">
                <FlaskConical className="mt-0.5 h-3 w-3 shrink-0 text-slate-700" />
                <span className="font-semibold">Grid:</span>
                <span className="min-w-0 break-words font-normal text-slate-500">
                  {simulation.gridName}
                </span>
              </div>
              <div className="flex items-start gap-2">
                <Server className="mt-0.5 h-3 w-3 shrink-0 text-slate-700" />
                <span className="font-semibold">Machine:</span>
                <span className="min-w-0 break-words font-normal text-slate-500">
                  {simulation.machine.name}
                </span>
              </div>
            </div>

            <div className="mb-4 mt-2 flex flex-wrap items-center gap-2">
              <Badge
                variant="secondary"
                className="flex items-center gap-1 border border-slate-200 bg-slate-50 px-2 py-1 text-sm text-slate-700"
              >
                <Tag className="w-4 h-4" />
                Tag:
                <span className="text-xs px-1 py-1 ml-1">{simulation.gitTag}</span>
              </Badge>
              <Badge
                variant="secondary"
                className="flex items-center gap-1 border border-slate-200 bg-slate-50 px-2 py-1 text-sm text-slate-700"
              >
                Canonical: {simulation.isCanonical ? 'Yes' : 'No'}
                {!simulation.isCanonical && simulation.changeCount > 0 && (
                  <span className="ml-1 text-xs text-muted-foreground">
                    (Changes: {simulation.changeCount})
                  </span>
                )}
              </Badge>
              <Badge
                className={`text-xs px-2 py-1 ${
                  simulation.simulationType === 'production'
                    ? 'bg-green-600 text-white'
                    : simulation.simulationType === 'master'
                      ? 'bg-blue-600 text-white'
                      : 'bg-yellow-400 text-black'
                }`}
                style={{
                  backgroundColor:
                    simulation.simulationType === 'production'
                      ? '#16a34a'
                      : simulation.simulationType === 'master'
                        ? '#2563eb'
                        : '#facc15',
                  color:
                    simulation.simulationType === 'production' ||
                    simulation.simulationType === 'master'
                      ? '#fff'
                      : '#000',
                }}
              >
                {simulation.simulationType === 'production' ? (
                  <>
                    <BadgeCheck className="w-4 h-4 mr-1" /> Production Run
                  </>
                ) : simulation.simulationType === 'master' ? (
                  <>
                    <GitBranch className="w-4 h-4 mr-1" /> Master Run
                  </>
                ) : (
                  <>
                    <FlaskConical className="w-4 h-4 mr-1" /> Experimental Run
                  </>
                )}
              </Badge>
            </div>

            <div style={{ height: '6px' }} />

            <Dialog open={isDetailsOpen} onOpenChange={setIsDetailsOpen}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  className="mb-4 w-full justify-between rounded-xl border-slate-200 bg-slate-50/70 px-4 py-6 text-left text-base text-slate-900 hover:bg-slate-100"
                  onClick={(event) => event.stopPropagation()}
                >
                  More Details
                </Button>
              </DialogTrigger>
              <DialogContent
                className="left-auto right-0 top-0 h-[100dvh] w-full max-w-[min(92vw,42rem)] translate-x-0 translate-y-0 gap-0 overflow-hidden rounded-none border-l border-slate-200 p-0 data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-2xl sm:rounded-none"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex h-full min-h-0 flex-col">
                  <DialogHeader className="border-b border-slate-200 px-6 py-5 text-left">
                    <DialogTitle className="text-xl text-slate-950">
                      {simulation.executionId}
                    </DialogTitle>
                    <DialogDescription className="mt-2 text-sm leading-6 text-slate-600">
                      Additional browse details for <span className="font-medium">{simulation.caseName}</span>.
                    </DialogDescription>
                  </DialogHeader>

                  <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
                    <section className="space-y-3">
                      <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                        Overview
                      </h3>
                      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/60 p-4 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Case
                          </p>
                          <p className="mt-1 text-sm text-slate-700">{simulation.caseName}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Status
                          </p>
                          <div className="mt-1">
                            <SimulationStatusBadge status={simulation.status} />
                          </div>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Machine
                          </p>
                          <p className="mt-1 text-sm text-slate-700">{simulation.machine.name}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Compiler
                          </p>
                          <p className="mt-1 text-sm text-slate-700">{simulation.compiler ?? 'N/A'}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Grid
                          </p>
                          <p className="mt-1 text-sm text-slate-700">{simulation.gridName}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Canonical
                          </p>
                          <p className="mt-1 text-sm text-slate-700">
                            {simulation.isCanonical ? 'Yes' : 'No'}
                            {!simulation.isCanonical && simulation.changeCount > 0
                              ? ` (${simulation.changeCount} changes)`
                              : ''}
                          </p>
                        </div>
                      </div>
                    </section>

                    <section className="space-y-3">
                      <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                        Runtime And Provenance
                      </h3>
                      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Model Run Dates
                          </p>
                          <p className="mt-1 text-sm text-slate-700">
                            {startStr} to {endStr}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Runtime Window
                          </p>
                          <p className="mt-1 text-sm text-slate-700">
                            {runStartStr} to {runEndStr}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Created By
                          </p>
                          <p className="mt-1 text-sm text-slate-700">
                            {simulation.createdByUser?.email ?? simulation.createdBy ?? 'N/A'}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            HPC Username
                          </p>
                          <p className="mt-1 text-sm text-slate-700">{simulation.hpcUsername ?? 'N/A'}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                            Catalog Dates
                          </p>
                          <p className="mt-1 text-sm text-slate-700">
                            Created {createdAtStr}, updated {updatedAtStr}
                          </p>
                        </div>
                      </div>
                    </section>

                    {(simulation.gitRepositoryUrl ||
                      simulation.gitBranch ||
                      simulation.gitTag ||
                      simulation.gitCommitHash) && (
                      <section className="space-y-3">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                          Version Control
                        </h3>
                        <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                          {simulation.gitRepositoryUrl && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Repository
                              </p>
                              <p className="mt-1 break-all text-sm text-slate-700">
                                {simulation.gitRepositoryUrl}
                              </p>
                            </div>
                          )}
                          {simulation.gitBranch && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Branch
                              </p>
                              <p className="mt-1 break-all font-mono text-xs text-slate-700">
                                {simulation.gitBranch}
                              </p>
                            </div>
                          )}
                          {simulation.gitTag && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Tag
                              </p>
                              <p className="mt-1 text-sm text-slate-700">{simulation.gitTag}</p>
                            </div>
                          )}
                          {simulation.gitCommitHash && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Commit
                              </p>
                              <p className="mt-1 break-all font-mono text-xs text-slate-700">
                                {simulation.gitCommitHash}
                              </p>
                            </div>
                          )}
                        </div>
                      </section>
                    )}

                    {(simulation.description ||
                      simulation.keyFeatures ||
                      simulation.knownIssues ||
                      simulation.notesMarkdown) && (
                      <section className="space-y-3">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                          Notes And Context
                        </h3>
                        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
                          {simulation.description && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Description
                              </p>
                              <p className="mt-1 text-sm leading-6 text-slate-700">
                                {simulation.description}
                              </p>
                            </div>
                          )}
                          {simulation.keyFeatures && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Key Features
                              </p>
                              <p className="mt-1 text-sm leading-6 text-slate-700">
                                {simulation.keyFeatures}
                              </p>
                            </div>
                          )}
                          {simulation.knownIssues && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Known Issues
                              </p>
                              <p className="mt-1 text-sm leading-6 text-slate-700">
                                {simulation.knownIssues}
                              </p>
                            </div>
                          )}
                          {simulation.notesMarkdown && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Notes
                              </p>
                              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                                {simulation.notesMarkdown}
                              </p>
                            </div>
                          )}
                        </div>
                      </section>
                    )}

                    {(diagnosticLinks.length > 0 || performanceLinks.length > 0) && (
                      <section className="space-y-3">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                          External Links
                        </h3>
                        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
                          {diagnosticLinks.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Diagnostics
                              </p>
                              <ul className="mt-2 space-y-2">
                                {diagnosticLinks.map((link) => (
                                  <li key={link.id}>
                                    <a
                                      href={link.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-sm text-blue-700 underline"
                                    >
                                      {link.label}
                                    </a>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {performanceLinks.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Performance
                              </p>
                              <ul className="mt-2 space-y-2">
                                {performanceLinks.map((link) => (
                                  <li key={link.id}>
                                    <a
                                      href={link.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-sm text-blue-700 underline"
                                    >
                                      {link.label}
                                    </a>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </section>
                    )}

                    {(runScripts.length > 0 || archivePaths.length > 0 || postprocessingScripts.length > 0) && (
                      <section className="space-y-3">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                          Artifact Paths
                        </h3>
                        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
                          {runScripts.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Run Scripts
                              </p>
                              <ul className="mt-2 space-y-2 text-sm text-slate-700">
                                {runScripts.map((item, index) => (
                                  <li key={index} className="break-all">
                                    {typeof item === 'string' ? item : (item.label ?? item.uri)}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {archivePaths.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Archive Paths
                              </p>
                              <ul className="mt-2 space-y-2 text-sm text-slate-700">
                                {archivePaths.map((item, index) => (
                                  <li key={index} className="break-all">
                                    {typeof item === 'string' ? item : (item.label ?? item.uri)}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {postprocessingScripts.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                                Postprocessing Scripts
                              </p>
                              <ul className="mt-2 space-y-2 text-sm text-slate-700">
                                {postprocessingScripts.map((item, index) => (
                                  <li key={index} className="break-all">
                                    {typeof item === 'string' ? item : (item.label ?? item.uri)}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </section>
                    )}
                  </div>
                </div>
              </DialogContent>
            </Dialog>

            <div className="flex flex-col sm:flex-row items-center gap-4 mt-4 justify-end">
              <Button
                variant="outline"
                size="sm"
                className="w-full sm:w-40"
                onClick={(event) => {
                  event.stopPropagation();
                  navigate(`/simulations/${simulation.id}`);
                }}
              >
                View All Details
              </Button>
            </div>
          </CardContent>
        </div>
      </div>
    </Card>
  );
};
