import { useState } from 'react';

import { ExecutionStatusBadge } from '@/components/shared/ExecutionStatusBadge';
import { Button, type ButtonProps } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { suppressNextBrowseInteraction } from '@/features/browse/components/ExecutionResults/selectionGuard';
import { useExecution } from '@/lib/catalog/hooks/useExecution';
import { getArtifactsByKind } from '@/types/artifact';
import type { ExecutionListItemOut } from '@/types/index';
import { formatModelDate } from '@/utils/utils';

interface ExecutionBrowseDetailsDialogProps {
  execution: ExecutionListItemOut;
  triggerLabel?: string;
  triggerVariant?: ButtonProps['variant'];
  triggerSize?: ButtonProps['size'];
  triggerClassName?: string;
}

export const ExecutionBrowseDetailsDialog = ({
  execution: listExecution,
  triggerLabel = 'More Details',
  triggerVariant = 'outline',
  triggerSize = 'default',
  triggerClassName,
}: ExecutionBrowseDetailsDialogProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const {
    data: executionDetail,
    error,
    isFetching,
    refetch,
  } = useExecution(listExecution.id, isOpen);
  const handleTriggerInteraction = (event: React.SyntheticEvent) => {
    event.stopPropagation();
  };
  const stopDrawerPropagation = (event: React.SyntheticEvent) => {
    event.stopPropagation();
  };

  if (!executionDetail) {
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
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{listExecution.executionId}</DialogTitle>
            <DialogDescription>
              {error
                ? `Could not load execution details: ${error}`
                : isFetching
                  ? 'Loading execution details…'
                  : 'Execution details are unavailable.'}
            </DialogDescription>
          </DialogHeader>
          {error ? (
            <Button type="button" variant="outline" onClick={() => void refetch()}>
              Retry
            </Button>
          ) : null}
        </DialogContent>
      </Dialog>
    );
  }

  const execution = executionDetail;

  const startStr = execution.simulationStartDate
    ? formatModelDate(execution.simulationStartDate)
    : 'N/A';
  const endStr = execution.simulationEndDate
    ? formatModelDate(execution.simulationEndDate)
    : 'N/A';
  const runStartStr = execution.runStartDate
    ? new Date(execution.runStartDate).toISOString().slice(0, 10)
    : 'N/A';
  const runEndStr = execution.runEndDate
    ? new Date(execution.runEndDate).toISOString().slice(0, 10)
    : 'N/A';
  const createdAtStr = new Date(execution.createdAt).toISOString().slice(0, 10);
  const updatedAtStr = new Date(execution.updatedAt).toISOString().slice(0, 10);
  const diagnosticLinks = execution.groupedLinks.diagnostic ?? [];
  const performanceLinks = execution.groupedLinks.performance ?? [];
  const outputPaths = getArtifactsByKind(
    execution.artifacts,
    execution.groupedArtifacts,
    'output',
  );
  const archivePaths = getArtifactsByKind(
    execution.artifacts,
    execution.groupedArtifacts,
    'archive',
  );
  const runScripts = getArtifactsByKind(
    execution.artifacts,
    execution.groupedArtifacts,
    'run_script',
  );
  const postprocessingScripts = getArtifactsByKind(
    execution.artifacts,
    execution.groupedArtifacts,
    'postprocessing_script',
  );

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
            <DialogTitle className="text-xl text-slate-950">{execution.executionId}</DialogTitle>
            <DialogDescription className="mt-2 text-sm leading-6 text-slate-600">
              Additional browse details for{' '}
              <span className="font-medium">{execution.caseName}</span>.
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
                  <p className="mt-1 text-sm text-slate-700">{execution.caseName}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    Status
                  </p>
                  <div className="mt-1">
                    <ExecutionStatusBadge status={execution.status} />
                  </div>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    Machine
                  </p>
                  <p className="mt-1 text-sm text-slate-700">{execution.machine.name}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    Compiler
                  </p>
                  <p className="mt-1 text-sm text-slate-700">{execution.compiler ?? 'N/A'}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    Grid
                  </p>
                  <p className="mt-1 text-sm text-slate-700">{execution.gridName}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    Case Hash
                  </p>
                  <p className="mt-1 text-sm text-slate-700">{execution.caseHash ?? 'N/A'}</p>
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
                    {execution.createdByUser?.email ?? execution.createdBy ?? 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                    HPC Username
                  </p>
                  <p className="mt-1 text-sm text-slate-700">{execution.hpcUsername ?? 'N/A'}</p>
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

            {(execution.gitRepositoryUrl ||
              execution.gitBranch ||
              execution.gitTag ||
              execution.gitCommitHash) && (
              <section className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Version Control
                </h3>
                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  {execution.gitRepositoryUrl && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Repository
                      </p>
                      <p className="mt-1 break-all text-sm text-slate-700">
                        {execution.gitRepositoryUrl}
                      </p>
                    </div>
                  )}
                  {execution.gitBranch && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Branch
                      </p>
                      <p className="mt-1 break-all font-mono text-xs text-slate-700">
                        {execution.gitBranch}
                      </p>
                    </div>
                  )}
                  {execution.gitTag && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Tag
                      </p>
                      <p className="mt-1 text-sm text-slate-700">{execution.gitTag}</p>
                    </div>
                  )}
                  {execution.gitCommitHash && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Commit
                      </p>
                      <p className="mt-1 break-all font-mono text-xs text-slate-700">
                        {execution.gitCommitHash}
                      </p>
                    </div>
                  )}
                </div>
              </section>
            )}

            {(execution.description ||
              execution.keyFeatures ||
              execution.knownIssues ||
              execution.notesMarkdown) && (
              <section className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Notes And Context
                </h3>
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
                  {execution.description && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Description
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-700">
                        {execution.description}
                      </p>
                    </div>
                  )}
                  {execution.keyFeatures && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Key Features
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-700">
                        {execution.keyFeatures}
                      </p>
                    </div>
                  )}
                  {execution.knownIssues && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Known Issues
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-700">
                        {execution.knownIssues}
                      </p>
                    </div>
                  )}
                  {execution.notesMarkdown && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Notes
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                        {execution.notesMarkdown}
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

            {(outputPaths.length > 0 ||
              runScripts.length > 0 ||
              archivePaths.length > 0 ||
              postprocessingScripts.length > 0) && (
              <section className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Artifact Paths
                </h3>
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
                  {outputPaths.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Output Paths
                      </p>
                      <ul className="mt-2 space-y-2 text-sm text-slate-700">
                        {outputPaths.map((item) => (
                          <li key={item.id} className="break-all">
                            {item.label ?? item.uri}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {runScripts.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Run Scripts
                      </p>
                      <ul className="mt-2 space-y-2 text-sm text-slate-700">
                        {runScripts.map((item) => (
                          <li key={item.id} className="break-all">
                            {item.label ?? item.uri}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {archivePaths.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        Short-Term Archive Paths
                      </p>
                      <ul className="mt-2 space-y-2 text-sm text-slate-700">
                        {archivePaths.map((item) => (
                          <li key={item.id} className="break-all">
                            {item.label ?? item.uri}
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
                        {postprocessingScripts.map((item) => (
                          <li key={item.id} className="break-all">
                            {item.label ?? item.uri}
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
