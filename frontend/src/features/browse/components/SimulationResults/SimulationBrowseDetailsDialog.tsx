import { useState } from 'react';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Button, type ButtonProps } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  suppressNextBrowseInteraction,
} from '@/features/browse/components/SimulationResults/selectionGuard';
import type { SimulationOut } from '@/types/index';

interface SimulationBrowseDetailsDialogProps {
  simulation: SimulationOut;
  triggerLabel?: string;
  triggerVariant?: ButtonProps['variant'];
  triggerSize?: ButtonProps['size'];
  triggerClassName?: string;
}

export const SimulationBrowseDetailsDialog = ({
  simulation,
  triggerLabel = 'More Details',
  triggerVariant = 'outline',
  triggerSize = 'default',
  triggerClassName,
}: SimulationBrowseDetailsDialogProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const handleTriggerInteraction = (event: React.SyntheticEvent) => {
    event.stopPropagation();
  };
  const stopDrawerPropagation = (event: React.SyntheticEvent) => {
    event.stopPropagation();
  };

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
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button
          variant={triggerVariant}
          size={triggerSize}
          className={triggerClassName}
          data-prevent-selection="true"
          onPointerDown={handleTriggerInteraction}
          onMouseDown={handleTriggerInteraction}
          onClick={handleTriggerInteraction}
        >
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent
        className="left-auto right-0 top-0 h-[100dvh] w-full max-w-[min(92vw,42rem)] translate-x-0 translate-y-0 gap-0 overflow-hidden rounded-none border-l border-slate-200 p-0 data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-2xl sm:rounded-none"
        onPointerDownOutside={() => {
          suppressNextBrowseInteraction();
        }}
        onPointerDownCapture={stopDrawerPropagation}
        onClickCapture={stopDrawerPropagation}
      >
        <div className="flex h-full min-h-0 flex-col">
          <DialogHeader className="border-b border-slate-200 px-6 py-5 text-left">
            <DialogTitle className="text-xl text-slate-950">{simulation.executionId}</DialogTitle>
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
                    Reference
                  </p>
                  <p className="mt-1 text-sm text-slate-700">
                    {simulation.isReference ? 'Yes' : 'No'}
                    {!simulation.isReference && simulation.changeCount > 0
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

            {(runScripts.length > 0 ||
              archivePaths.length > 0 ||
              postprocessingScripts.length > 0) && (
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
  );
};
