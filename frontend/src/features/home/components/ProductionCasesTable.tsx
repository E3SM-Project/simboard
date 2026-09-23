import { ArrowRight } from 'lucide-react';
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
import { useCases } from '@/lib/catalog/hooks/useCases';
import { caseDetailsPath } from '@/lib/catalog/urls';

export const ProductionCasesTable = () => {
  const {
    data: cases,
    error,
    isFetching,
    loading,
    refetch,
  } = useCases({
    page: 1,
    pageSize: 6,
    simulationType: 'production',
    sortBy: 'latest_run_activity',
    sortOrder: 'desc',
  });

  if (loading) {
    return <LoadingState label="Loading production cases" />;
  }

  if (error && cases.length === 0) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
        <p>Could not load production cases.</p>
        <Button
          className="mt-3"
          size="sm"
          type="button"
          variant="outline"
          onClick={() => void refetch()}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-muted bg-white p-4 shadow-sm md:p-6">
      {error ? (
        <div className="mb-3 flex items-center justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <span>Could not refresh production cases. Showing previously loaded data.</span>
          <Button size="sm" type="button" variant="outline" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      ) : null}
      {isFetching ? (
        <LoadingState
          className="mb-3 min-h-0 border-0 bg-transparent p-0"
          kind="inline"
          label="Refreshing production cases"
        />
      ) : null}
      <div className="overflow-x-auto">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[32%] min-w-[320px]">Case Name</TableHead>
              <TableHead>HPC Username</TableHead>
              <TableHead>Machine</TableHead>
              <TableHead>Executions</TableHead>
              <TableHead>Case Group</TableHead>
              <TableHead>Last Updated</TableHead>
              <TableHead>Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No production cases are currently available.
                </TableCell>
              </TableRow>
            ) : (
              cases.map((caseRecord) => (
                <TableRow key={caseRecord.id}>
                  <TableCell className="align-top">
                    <TableCellText value={caseRecord.name} lines={1} />
                  </TableCell>
                  <TableCell className="align-top">
                    <TableCellText value={caseRecord.hpcUsername} lines={1} />
                  </TableCell>
                  <TableCell className="align-top">
                    <TableCellText value={caseRecord.machineName} lines={1} />
                  </TableCell>
                  <TableCell>{caseRecord.executionCount}</TableCell>
                  <TableCell>{caseRecord.caseGroup ?? '—'}</TableCell>
                  <TableCell>{new Date(caseRecord.updatedAt).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <Button asChild className="h-8 gap-1 px-2" size="sm" variant="outline">
                      <Link
                        to={caseDetailsPath({
                          machineName: caseRecord.machineName,
                          hpcUsername: caseRecord.hpcUsername,
                          caseName: caseRecord.name,
                        })}
                      >
                        Open <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};
