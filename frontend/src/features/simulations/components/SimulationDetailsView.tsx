import { useState } from 'react';
import { Link } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { SimulationPathCard } from '@/features/simulations/components/SimulationPathCard';
import { SimulationTypeBadge } from '@/features/simulations/components/SimulationTypeBadge';
import { cn } from '@/lib/utils';
import type { SimulationOut } from '@/types';
import { formatDate, getSimulationDuration } from '@/utils/utils';

// -------------------- Types --------------------
interface SimulationDetailsViewProps {
  simulation: SimulationOut;
  canEdit?: boolean;
}

// -------------------- Small UI helpers --------------------
const FieldRow = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="grid grid-cols-12 items-center gap-2">
    <Label className="col-span-3 md:col-span-2 text-xs text-muted-foreground">{label}</Label>
    <div className="col-span-9 md:col-span-10">{children}</div>
  </div>
);

const ReadonlyInput = ({ value, className }: { value?: string | null; className?: string }) => (
  <Input value={value || '—'} readOnly className={cn('h-8 text-sm', className)} />
);

// -------------------- View Component --------------------
export const SimulationDetailsView = ({
  simulation,
  canEdit = false,
}: SimulationDetailsViewProps) => {
  const [activeTab, setActiveTab] = useState('summary');
  const [notes, setNotes] = useState(simulation.notesMarkdown || '');

  // Temporary local-only comments
  const [newComment, setNewComment] = useState('');
  const [comments, setComments] = useState<
    { id: string; author: string; date: string; text: string }[]
  >([
    {
      id: 'c1',
      author: 'Jane Doe',
      date: '2024-02-15T13:45:00Z',
      text: 'The sea-ice diagnostics will be added later.',
    },
  ]);

  const addComment = () => {
    if (!newComment.trim()) return;
    setComments((prev) => [
      ...prev,
      {
        id: `c${prev.length + 1}`,
        author: 'You',
        date: new Date().toISOString(),
        text: newComment.trim(),
      },
    ]);
    setNewComment('');
  };

  return (
    <div className="mx-auto w-full max-w-[1200px] px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{simulation.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Type:</span>
            <SimulationTypeBadge simulationType={simulation.simulationType} />
            <span>•</span>
            <span>Status:</span>
            <SimulationStatusBadge status={simulation.status} />
            {simulation.gitTag && (
              <>
                <span>•</span>
                <span>Version/Tag:</span>
                <code className="rounded bg-muted px-2 py-0.5 text-xs">{simulation.gitTag}</code>
              </>
            )}
            <span>•</span>
            <Link to="/browse" className="text-blue-600 hover:underline">
              Back to results
            </Link>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link to="/compare">Add to Compare</Link>
          </Button>
          <Button disabled={!canEdit}>Save</Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="outputs">Outputs & Logs</TabsTrigger>
        </TabsList>

        {/* SUMMARY TAB */}
        <TabsContent value="summary" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <FieldRow label="Simulation Name">
                  <ReadonlyInput value={simulation.name} />
                </FieldRow>
                <FieldRow label="Case Name">
                  <ReadonlyInput value={simulation.caseName} />
                </FieldRow>
                <FieldRow label="Model Version">
                  <ReadonlyInput value={simulation.gitTag ?? undefined} />
                </FieldRow>
                <FieldRow label="Compset">
                  <ReadonlyInput value={simulation.compset ?? undefined} />
                </FieldRow>
                <FieldRow label="Grid Name">
                  <ReadonlyInput value={simulation.gridName ?? undefined} />
                </FieldRow>
                <FieldRow label="Grid Resolution">
                  <ReadonlyInput value={simulation.gridResolution ?? undefined} />
                </FieldRow>
                <FieldRow label="Initialization Type">
                  <ReadonlyInput value={simulation.initializationType ?? undefined} />
                </FieldRow>
                <FieldRow label="Compiler">
                  <ReadonlyInput value={simulation.compiler ?? undefined} />
                </FieldRow>
                <FieldRow label="Parent Simulation ID">
                  <ReadonlyInput value={simulation.parentSimulationId ?? undefined} />
                </FieldRow>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Model Setup</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <FieldRow label="Simulation Type">
                  <ReadonlyInput value={simulation.simulationType} />
                </FieldRow>
                <FieldRow label="Status">
                  <ReadonlyInput value={simulation.status} />
                </FieldRow>
                <FieldRow label="Campaign ID">
                  <ReadonlyInput value={simulation.campaignId} />
                </FieldRow>
                <FieldRow label="Experiment Type ID">
                  <ReadonlyInput value={simulation.experimentTypeId} />
                </FieldRow>
                <FieldRow label="Machine">
                  <ReadonlyInput value={simulation.machine.name} />
                </FieldRow>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <FieldRow label="Simulation Start Date">
                  <span className="text-sm">
                    {simulation.simulationStartDate
                      ? formatDate(simulation.simulationStartDate)
                      : '—'}
                  </span>
                </FieldRow>
                <FieldRow label="Simulation End Date">
                  <span className="text-sm">
                    {simulation.simulationEndDate ? formatDate(simulation.simulationEndDate) : '—'}
                  </span>
                </FieldRow>
                <FieldRow label="Total Duration">
                  <span className="text-sm">
                    {simulation.simulationStartDate && simulation.simulationEndDate
                      ? (() => {
                          return getSimulationDuration(
                            simulation.simulationStartDate,
                            simulation.simulationEndDate,
                          );
                        })()
                      : '—'}
                  </span>
                </FieldRow>
                {simulation.runStartDate && (
                  <FieldRow label="Run Start Date">
                    <span className="text-sm">{formatDate(simulation.runStartDate)}</span>
                  </FieldRow>
                )}
                {simulation.runEndDate && (
                  <FieldRow label="Run End Date">
                    <span className="text-sm">{formatDate(simulation.runEndDate)}</span>
                  </FieldRow>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Provenance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">Created:</Label>
                  <span className="text-sm">
                    {simulation.createdAt ? formatDate(simulation.createdAt) : '—'}
                  </span>
                  {simulation.createdBy && (
                    <span className="text-sm">by {simulation.createdBy}</span>
                  )}
                </div>
                {/* Last edited row */}
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">
                    Last edited:
                  </Label>
                  <span className="text-sm">
                    {simulation.updatedAt ? formatDate(simulation.updatedAt) : '—'}
                  </span>
                  {simulation.lastUpdatedBy && (
                    <span className="text-sm">by {simulation.lastUpdatedBy}</span>
                  )}
                </div>
                {/* Simulation UUID row */}
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">
                    Simulation UUID:
                  </Label>
                  <ReadonlyInput
                    value={
                      simulation.id
                        ? `${simulation.id.slice(0, 8)}…${simulation.id.slice(-6)}`
                        : undefined
                    }
                  />
                  {simulation.id && (
                    <Button
                      variant="outline"
                      size="sm"
                      type="button"
                      onClick={() => navigator.clipboard.writeText(simulation.id)}
                      title="Copy full Simulation ID"
                    >
                      Copy
                    </Button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">
                    Git Repository:
                  </Label>
                  {simulation.gitRepositoryUrl ? (
                    <a
                      href={simulation.gitRepositoryUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:underline"
                    >
                      {simulation.gitRepositoryUrl}
                    </a>
                  ) : (
                    <p className="text-sm">—</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">Git Branch:</Label>
                  <p className="text-sm">{simulation.gitBranch ?? '—'}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">Git Tag:</Label>
                  <p className="text-sm">{simulation.gitTag ?? '—'}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">
                    Git Commit Hash:
                  </Label>
                  <p className="text-sm">{simulation.gitCommitHash ?? '—'}</p>
                </div>
              </CardContent>
            </Card>
          </div>
          <Card className="lg:col-span-2">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">External Resources</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <Label className="mb-1 block text-sm">Diagnostics</Label>
                  {simulation.groupedLinks.diagnostic?.length ? (
                    <ul className="list-disc pl-5 text-sm">
                      {simulation.groupedLinks.diagnostic.map((d) => (
                        <li key={d.url} className="flex items-center gap-2">
                          <a
                            className="text-blue-600 hover:underline flex items-center gap-1"
                            href={d.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              width="16"
                              height="16"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              className="inline-block"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M15 7h2a5 5 0 015 5v0a5 5 0 01-5 5h-2m-6 0H7a5 5 0 01-5-5v0a5 5 0 015-5h2m1 5h4"
                              />
                            </svg>
                            {d.label}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="mb-2 text-sm text-muted-foreground">
                      Links to diagnostics will appear here once available.
                    </div>
                  )}
                </div>
                <div>
                  <Label className="mb-1 block text-sm">Performance</Label>
                  {simulation.groupedLinks.performance?.length ? (
                    <ul className="list-disc pl-5 text-sm">
                      {simulation.groupedLinks.performance.map((p) => (
                        <li key={p.url} className="flex items-center gap-2">
                          <a
                            className="text-blue-600 hover:underline flex items-center gap-1"
                            href={p.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              width="16"
                              height="16"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              className="inline-block"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M15 7h2a5 5 0 015 5v0a5 5 0 01-5 5h-2m-6 0H7a5 5 0 01-5-5v0a5 5 0 015-5h2m1 5h4"
                              />
                            </svg>
                            {p.label}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="mb-2 text-sm text-muted-foreground">
                      Links to performance metrics will appear here once available.
                    </div>
                  )}
                </div>
              </div>
              <div>
                {Object.entries(simulation.groupedLinks)
                  .filter(([key]) => key !== 'diagnostic' && key !== 'performance')
                  .map(([key, linkList]) => (
                    <div key={key} className="mb-4">
                      <h4 className="text-sm font-medium capitalize">{key}</h4>
                      <ul className="list-disc pl-5 text-sm">
                        {linkList.map((link) => (
                          <li key={link.url} className="flex items-center gap-2">
                            <a
                              className="text-blue-600 hover:underline flex items-center gap-1"
                              href={link.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="16"
                                height="16"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                className="inline-block"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M15 7h2a5 5 0 015 5v0a5 5 0 01-5 5h-2m-6 0H7a5 5 0 01-5-5v0a5 5 0 015-5h2m1 5h4"
                                />
                              </svg>
                              {link.label}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                placeholder="Add notes..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="min-h-[120px]"
              />
              {!canEdit && (
                <p className="text-xs text-muted-foreground">
                  A user account with write privilege is required to update this simulation page.
                </p>
              )}
              <div>
                <Button disabled={!canEdit}>Save</Button>
              </div>
            </CardContent>
          </Card>
          <div>
            <h3 className="mb-2 text-sm font-semibold tracking-tight">Comments</h3>
            <div className="space-y-4">
              {comments.map((c) => (
                <div
                  key={c.id}
                  className="flex gap-3 py-4 px-2 rounded transition-all"
                  style={{ marginBottom: '16px', marginTop: '16px' }}
                >
                  <Avatar className="h-8 w-8 mt-1">
                    <AvatarFallback>
                      {c.author
                        .split(' ')
                        .map((n) => n[0])
                        .join('')
                        .slice(0, 2)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                      <span className="font-medium text-foreground">{c.author}</span>
                      <span>•</span>
                      <span>{formatDate(c.date)}</span>
                    </div>
                    <p className="text-sm leading-relaxed">{c.text}</p>
                  </div>
                </div>
              ))}
              <Separator />
              <div className="flex items-start gap-2">
                <Textarea
                  placeholder="Add a comment ..."
                  className="min-h-[80px]"
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                />
                <Button onClick={addComment} className="shrink-0">
                  Post
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* OUTPUTS TAB */}
        <TabsContent value="outputs" className="space-y-6">
          <SimulationPathCard
            kind="output"
            title="Output Paths"
            description="These are the primary output files generated by the simulation."
            paths={simulation.groupedArtifacts.output?.map((a) => a.uri) || []}
            emptyText="No output paths available."
          />
          <SimulationPathCard
            kind="archive"
            title="Archive Paths"
            description="These paths contain archived data files from the simulation."
            paths={simulation.groupedArtifacts.archive?.map((a) => a.uri) || []}
            emptyText="No archive artifacts available."
          />
          <SimulationPathCard
            kind="runScript"
            title="Run Script Paths"
            description="Scripts used to run the simulation."
            paths={simulation.groupedArtifacts.runScript?.map((a) => a.uri) || []}
            emptyText="No run script artifacts available."
          />
          <SimulationPathCard
            kind="batchLog"
            title="Batch Log Paths"
            description="Log files generated during the batch processing of the simulation."
            paths={simulation.groupedArtifacts.batchLog?.map((a) => a.uri) || []}
            emptyText="No batch log artifacts available."
          />
        </TabsContent>
      </Tabs>
    </div>
  );
};
