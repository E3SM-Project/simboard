import { Link, useParams } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  formatCaseDate,
  formatSimulationDateRange,
  getCanonicalSimulation,
  sortSimulationSummaries,
} from '@/features/simulations/caseUtils';
import { useCase } from '@/features/simulations/hooks/useCase';

const MetadataRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="flex items-start justify-between gap-4 border-b border-border/60 py-3 last:border-b-0">
    <span className="text-sm text-muted-foreground">{label}</span>
    <div className="text-right text-sm font-medium">{value}</div>
  </div>
);

export const CaseDetailsPage = () => {
  const { id } = useParams<{ id: string }>();
  const { data: caseRecord, loading, error } = useCase(id ?? '');

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

  const canonicalSimulation = getCanonicalSimulation(caseRecord);
  const simulations = sortSimulationSummaries(caseRecord.simulations);

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-6 px-6 py-8">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-bold">{caseRecord.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Case detail</span>
            <span>•</span>
            <Link to="/cases" className="text-blue-600 hover:underline">
              Back to cases
            </Link>
          </div>
        </div>
        {caseRecord.caseGroup && <Badge variant="outline">{caseRecord.caseGroup}</Badge>}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Case Metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <MetadataRow label="Case Group" value={caseRecord.caseGroup ?? '—'} />
            <MetadataRow label="Total Simulations" value={caseRecord.simulations.length} />
            <MetadataRow label="Created" value={formatCaseDate(caseRecord.createdAt)} />
            <MetadataRow label="Last Updated" value={formatCaseDate(caseRecord.updatedAt)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Canonical Simulation</CardTitle>
          </CardHeader>
          <CardContent>
            {canonicalSimulation ? (
              <>
                <MetadataRow
                  label="Execution ID"
                  value={
                    <Link
                      to={`/simulations/${canonicalSimulation.id}`}
                      className="font-mono text-xs text-blue-600 hover:underline"
                    >
                      {canonicalSimulation.executionId}
                    </Link>
                  }
                />
                <MetadataRow
                  label="Status"
                  value={<SimulationStatusBadge status={canonicalSimulation.status} />}
                />
                <MetadataRow label="Change Count" value={canonicalSimulation.changeCount} />
                <MetadataRow
                  label="Simulation Dates"
                  value={formatSimulationDateRange(canonicalSimulation)}
                />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                No canonical simulation is set for this case.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-xl font-semibold">Simulations</h2>
          <p className="text-sm text-muted-foreground">
            Execution-level summaries for this case. Canonical runs are pinned first.
          </p>
        </div>

        <div className="overflow-hidden rounded-md border bg-background">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Execution ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Canonical</TableHead>
                  <TableHead>Change Count</TableHead>
                  <TableHead>Simulation Dates</TableHead>
                  <TableHead>View Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {simulations.map((simulation) => (
                  <TableRow key={simulation.id}>
                    <TableCell className="align-top">
                      <Link
                        to={`/simulations/${simulation.id}`}
                        className="font-mono text-xs text-blue-600 hover:underline"
                      >
                        {simulation.executionId}
                      </Link>
                    </TableCell>
                    <TableCell className="align-top">
                      <SimulationStatusBadge status={simulation.status} />
                    </TableCell>
                    <TableCell className="align-top">
                      {simulation.isCanonical ? (
                        <Badge
                          variant="outline"
                          className="border-green-200 bg-green-50 text-green-700"
                        >
                          Canonical
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="align-top">{simulation.changeCount}</TableCell>
                    <TableCell className="align-top">
                      {formatSimulationDateRange(simulation)}
                    </TableCell>
                    <TableCell className="align-top">
                      <Link
                        to={`/simulations/${simulation.id}`}
                        className="text-blue-600 hover:underline"
                      >
                        View simulation
                      </Link>
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
