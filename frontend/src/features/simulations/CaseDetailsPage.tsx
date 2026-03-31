import { ArrowLeft, Pin, Share2 } from 'lucide-react';
import { useMemo } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import {
  formatCaseDate,
  formatSimulationDateRange,
  getReferenceSimulation,
  sortSimulationSummaries,
} from '@/features/simulations/caseUtils';
import { useCase } from '@/features/simulations/hooks/useCase';
import { toast } from '@/hooks/use-toast';
import type { SimulationOut } from '@/types';

const MetadataRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="flex items-start justify-between gap-4 border-b border-border/60 py-3 last:border-b-0">
    <span className="text-sm text-muted-foreground">{label}</span>
    <div className="text-right text-sm font-medium">{value}</div>
  </div>
);

interface CaseDetailsPageProps {
  simulations: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
}

const MAX_SELECTION = 5;

export const CaseDetailsPage = ({
  simulations: allSimulations,
  selectedSimulationIds,
  setSelectedSimulationIds,
}: CaseDetailsPageProps) => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: caseRecord, loading, error } = useCase(id ?? '');
  const currentPath = `${location.pathname}${location.search}`;
  const state = location.state as { from?: string } | null;
  const backHref = typeof state?.from === 'string' ? state.from : '/cases';
  const simulationDetailsById = useMemo(
    () => new Map(allSimulations.map((simulation) => [simulation.id, simulation])),
    [allSimulations],
  );

  const handleShareCase = async () => {
    if (!id) return;

    const shareUrl = new URL(`/cases/${id}`, window.location.origin).toString();
    const canUseWebShare = typeof navigator.share === 'function';

    try {
      if (canUseWebShare) {
        await navigator.share({
          title: caseRecord?.name ?? 'SimBoard Case',
          text: caseRecord?.name ?? 'SimBoard Case',
          url: shareUrl,
        });
      } else {
        await navigator.clipboard.writeText(shareUrl);
      }

      toast({
        title: 'Case link ready',
        description: canUseWebShare ? 'Share dialog opened.' : 'Case URL copied to clipboard.',
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }

      toast({
        title: 'Unable to share case',
        description: 'Try copying the page URL directly from your browser.',
        variant: 'destructive',
      });
    }
  };

  if (!id) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Invalid case ID</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Loading case details…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (!caseRecord) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center text-gray-500">Case not found</div>
      </div>
    );
  }

  const referenceSimulation = getReferenceSimulation(caseRecord);
  const simulations = sortSimulationSummaries(caseRecord.simulations).map((simulation) => ({
    summary: simulation,
    details: simulationDetailsById.get(simulation.id),
  }));
  const summarizeValues = (values: string[]) => {
    if (values.length === 0) return '—';
    if (values.length === 1) return values[0];

    return `${values[0]} +${values.length - 1}`;
  };
  const machineSummary = summarizeValues(caseRecord.machineNames);
  const hpcUsernameSummary = summarizeValues(caseRecord.hpcUsernames);
  const isCompareButtonDisabled = selectedSimulationIds.length < 2;

  const toggleSimulationSelection = (simulationId: string) => {
    if (selectedSimulationIds.includes(simulationId)) {
      setSelectedSimulationIds(selectedSimulationIds.filter((id) => id !== simulationId));
      return;
    }

    if (selectedSimulationIds.length >= MAX_SELECTION) {
      return;
    }

    setSelectedSimulationIds([...selectedSimulationIds, simulationId]);
  };

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-6 px-6 py-8">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <Button variant="outline" size="sm" asChild className="mb-3">
            <Link to={backHref}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">{caseRecord.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Case detail</span>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start">
          {caseRecord.caseGroup && <Badge variant="outline">{caseRecord.caseGroup}</Badge>}
          <Button variant="outline" size="sm" type="button" onClick={handleShareCase}>
            <Share2 className="h-4 w-4" />
            Share Case
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Case Metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <MetadataRow label="Total Simulations" value={caseRecord.simulations.length} />
            <MetadataRow label="Machines" value={machineSummary} />
            <MetadataRow label="HPC Usernames" value={hpcUsernameSummary} />
            <MetadataRow label="Case Group" value={caseRecord.caseGroup ?? '—'} />
            <MetadataRow label="Created" value={formatCaseDate(caseRecord.createdAt)} />
            <MetadataRow label="Last Updated" value={formatCaseDate(caseRecord.updatedAt)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Reference Simulation</CardTitle>
          </CardHeader>
          <CardContent>
            {referenceSimulation ? (
              <>
                <p className="mb-4 text-sm leading-6 text-muted-foreground">
                  This is the first successful run for the case and serves as the reference used to
                  compare configuration changes across the other simulations.
                </p>
                <MetadataRow
                  label="Execution ID"
                  value={
                    <Link
                      to={`/simulations/${referenceSimulation.id}`}
                      state={{ from: currentPath }}
                      className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                    >
                      {referenceSimulation.executionId}
                      <span
                        className="inline-flex items-center"
                        title="Reference simulation"
                        aria-label="Reference simulation"
                      >
                        <Pin className="h-3.5 w-3.5 text-amber-600" />
                      </span>
                    </Link>
                  }
                />
                <MetadataRow
                  label="Status"
                  value={<SimulationStatusBadge status={referenceSimulation.status} />}
                />
                <MetadataRow
                  label="Simulation Dates"
                  value={formatSimulationDateRange(referenceSimulation)}
                />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                No reference simulation is set for this case.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-xl font-semibold">Simulations</h2>
          <p className="text-sm text-muted-foreground">
            Execution-level summaries for this case. Reference runs are pinned first.
          </p>
        </div>

        <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/70 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button
              type="button"
              onClick={() => navigate('/compare')}
              disabled={isCompareButtonDisabled}
            >
              Compare Selected
            </Button>
            <div className="text-sm text-slate-600">
              Selected <span className="font-semibold text-slate-950">{selectedSimulationIds.length}</span>{' '}
              / {MAX_SELECTION}
            </div>
          </div>

          {selectedSimulationIds.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-slate-600 hover:text-slate-900"
              onClick={() => setSelectedSimulationIds([])}
            >
              Deselect all
            </Button>
          )}
        </div>

        <div className="overflow-hidden rounded-md border bg-background">
          <div className="max-h-[32rem] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">Select</TableHead>
                  <TableHead>Execution ID</TableHead>
                  <TableHead>Changes</TableHead>
                  <TableHead>Initialization</TableHead>
                  <TableHead>Git Tag</TableHead>
                  <TableHead>Simulation Dates</TableHead>
                  <TableHead>Run Dates</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {simulations.map(({ summary, details }) => (
                  <TableRow key={summary.id}>
                    <TableCell className="align-top">
                      <Checkbox
                        checked={selectedSimulationIds.includes(summary.id)}
                        disabled={
                          !selectedSimulationIds.includes(summary.id) &&
                          selectedSimulationIds.length >= MAX_SELECTION
                        }
                        onCheckedChange={() => toggleSimulationSelection(summary.id)}
                        aria-label={`Select ${summary.executionId} for compare`}
                      />
                    </TableCell>
                    <TableCell className="align-top">
                      <Link
                        to={`/simulations/${summary.id}`}
                        state={{ from: currentPath }}
                        className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                      >
                        {summary.executionId}
                        {summary.isReference && (
                          <span
                            className="inline-flex items-center"
                            title="Reference simulation"
                            aria-label="Reference simulation"
                          >
                            <Pin className="h-3.5 w-3.5 text-amber-600" />
                          </span>
                        )}
                      </Link>
                    </TableCell>
                    <TableCell className="align-top">
                      {summary.isReference ? (
                        <span className="text-sm font-medium text-slate-700">Reference</span>
                      ) : (
                        summary.changeCount
                      )}
                    </TableCell>
                    <TableCell className="align-top">
                      <TableCellText value={details?.initializationType ?? '—'} lines={1} />
                    </TableCell>
                    <TableCell className="align-top">
                      <TableCellText value={details?.gitTag ?? '—'} lines={1} />
                    </TableCell>
                    <TableCell className="align-top">
                      {formatSimulationDateRange(summary)}
                    </TableCell>
                    <TableCell className="align-top">
                      {details?.runStartDate || details?.runEndDate ? (
                        <span
                          title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}
                        >
                          {`${details?.runStartDate?.slice(0, 10) ?? '—'} → ${details?.runEndDate?.slice(0, 10) ?? '—'}`}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </section>
    </div>
  );
};
