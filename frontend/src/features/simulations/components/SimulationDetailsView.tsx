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
import { updateSimulation } from '@/features/simulations/api/api';
import { SimulationPathCard } from '@/features/simulations/components/SimulationPathCard';
import { SimulationTypeBadge } from '@/features/simulations/components/SimulationTypeBadge';
import { canEditSimulationField, SIMULATION_FIELDS } from '@/features/simulations/simulationFields';
import { cn } from '@/lib/utils';
import type { Machine, SimulationOut, SimulationUpdate } from '@/types';
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

const ReadonlyValue = ({ value }: { value?: string | null }) => (
  <span className="text-sm text-foreground">{value || '—'}</span>
);

// -------------------- View Component --------------------
export const SimulationDetailsView = ({
  simulation,
  canEdit = false,
}: SimulationDetailsViewProps) => {
  const [activeTab, setActiveTab] = useState('summary');
  const [editMode, setEditMode] = useState(false);
  const [form, setForm] = useState<SimulationOut>({ ...simulation });
  const [notes, setNotes] = useState(simulation.notesMarkdown || '');
  const [newComment, setNewComment] = useState('');
  const [comments, setComments] = useState([
    {
      id: 'c1',
      author: 'Jane Doe',
      date: '2024-02-15T13:45:00Z',
      text: 'The sea-ice diagnostics will be added later.',
    },
  ]);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Todo: When implementing real permissions, adjust this context accordingly.
  // Example:   isAdmin: currentUser.role === 'admin',
  const ctx = { isOwner: canEdit, isAdmin: canEdit };

  const canEditField = (name: keyof typeof SIMULATION_FIELDS) =>
    editMode && canEditSimulationField(SIMULATION_FIELDS[name], ctx);

  const handleChange = <K extends keyof SimulationOut>(field: K, value: SimulationOut[K]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

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

  const handleSave = async () => {
    setSaving(true);
    setErrorMsg(null);

    const payload: SimulationUpdate = {};

    (Object.keys(SIMULATION_FIELDS) as (keyof typeof SIMULATION_FIELDS)[]).forEach((key) => {
      if (!canEditSimulationField(SIMULATION_FIELDS[key], ctx)) return;
      if (form[key] !== simulation[key]) {
        (payload as any)[key] = form[key];
      }
    });

    if (notes !== simulation.notesMarkdown) {
      payload.notesMarkdown = notes;
    }

    try {
      await updateSimulation(simulation.id, payload);
      window.location.reload();
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to update simulation');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1200px] px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {canEditField('name') ? (
              <Input value={form.name} onChange={(e) => handleChange('name', e.target.value)} />
            ) : (
              simulation.name
            )}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Type:</span>
            <SimulationTypeBadge simulationType={simulation.simulationType} />
            <span>•</span>
            <span>Status:</span>
            <SimulationStatusBadge status={simulation.status} />
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

          {editMode ? (
            <>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setEditMode(false);
                  setForm({ ...simulation });
                  setNotes(simulation.notesMarkdown || '');
                }}
                disabled={saving}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button onClick={() => setEditMode(true)} disabled={!canEdit}>
              Edit
            </Button>
          )}
        </div>
      </div>

      {errorMsg && <div className="text-red-600 text-sm">{errorMsg}</div>}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full justify-start">
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="outputs">Outputs & Logs</TabsTrigger>
        </TabsList>

        {/* ================= SUMMARY TAB ================= */}
        <TabsContent value="summary" className="space-y-6">
          {/* Configuration + Model Setup */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Configuration */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(
                  [
                    'caseName',
                    'compset',
                    'compsetAlias',
                    'gridName',
                    'gridResolution',
                    'initializationType',
                    'compiler',
                    'parentSimulationId',
                  ] as const
                ).map((f) => (
                  <FieldRow key={f} label={SIMULATION_FIELDS[f].label}>
                    {canEditField(f) ? (
                      <Input
                        value={(form as any)[f] ?? ''}
                        onChange={(e) => handleChange(f as any, e.target.value)}
                      />
                    ) : (
                      <ReadonlyValue value={(simulation as any)[f]} />
                    )}
                  </FieldRow>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Model Setup</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Simulation Type */}
                <FieldRow label={SIMULATION_FIELDS.simulationType.label}>
                  {editMode && canEditSimulationField(SIMULATION_FIELDS.simulationType, ctx) ? (
                    <select
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={form.simulationType}
                      onChange={(e) => handleChange('simulationType', e.target.value)}
                    >
                      {SIMULATION_FIELDS.simulationType.options!.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <ReadonlyValue value={simulation.simulationType} />
                  )}
                </FieldRow>

                <FieldRow label={SIMULATION_FIELDS.status.label}>
                  {editMode && canEditSimulationField(SIMULATION_FIELDS.status, ctx) ? (
                    <select
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={form.status}
                      onChange={(e) => handleChange('status', e.target.value)}
                    >
                      {SIMULATION_FIELDS.status.options!.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <ReadonlyValue value={simulation.status} />
                  )}
                </FieldRow>

                <FieldRow label={SIMULATION_FIELDS.campaignId.label}>
                  {editMode && canEditSimulationField(SIMULATION_FIELDS.campaignId, ctx) ? (
                    <Input
                      value={form.campaignId ?? ''}
                      onChange={(e) => handleChange('campaignId', e.target.value || null)}
                    />
                  ) : (
                    <ReadonlyValue value={simulation.campaignId} />
                  )}
                </FieldRow>

                <FieldRow label={SIMULATION_FIELDS.experimentTypeId.label}>
                  {editMode && canEditSimulationField(SIMULATION_FIELDS.experimentTypeId, ctx) ? (
                    <Input
                      value={form.experimentTypeId ?? ''}
                      onChange={(e) => handleChange('experimentTypeId', e.target.value || null)}
                    />
                  ) : (
                    <ReadonlyValue value={simulation.experimentTypeId} />
                  )}
                </FieldRow>

                <FieldRow label={SIMULATION_FIELDS.machineId.label}>
                  <ReadonlyValue value={simulation.machineId} />
                </FieldRow>
              </CardContent>
            </Card>
          </div>

          {/* Timeline + Provenance (side-by-side) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Timeline */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <FieldRow label={SIMULATION_FIELDS.simulationStartDate.label}>
                  <span className="text-sm">{formatDate(simulation.simulationStartDate)}</span>
                </FieldRow>

                <FieldRow label={SIMULATION_FIELDS.simulationEndDate.label}>
                  {canEditField('simulationEndDate') ? (
                    <Input
                      type="datetime-local"
                      value={
                        form.simulationEndDate
                          ? new Date(form.simulationEndDate).toISOString().slice(0, 19)
                          : ''
                      }
                      onChange={(e) =>
                        handleChange(
                          'simulationEndDate',
                          e.target.value ? new Date(e.target.value + 'Z').toISOString() : null,
                        )
                      }
                    />
                  ) : (
                    <span className="text-sm">
                      {simulation.simulationEndDate
                        ? formatDate(simulation.simulationEndDate)
                        : '—'}
                    </span>
                  )}
                </FieldRow>

                <FieldRow label="Total Duration">
                  <span className="text-sm">
                    {simulation.simulationEndDate
                      ? getSimulationDuration(
                          simulation.simulationStartDate,
                          simulation.simulationEndDate,
                        )
                      : '—'}
                  </span>
                </FieldRow>

                {simulation.runStartDate && (
                  <FieldRow label={SIMULATION_FIELDS.runStartDate.label}>
                    <span className="text-sm">{formatDate(simulation.runStartDate)}</span>
                  </FieldRow>
                )}

                {simulation.runEndDate && (
                  <FieldRow label={SIMULATION_FIELDS.runEndDate.label}>
                    <span className="text-sm">{formatDate(simulation.runEndDate)}</span>
                  </FieldRow>
                )}
              </CardContent>
            </Card>

            {/* Provenance */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Provenance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">Created:</Label>
                  <span className="text-sm">{formatDate(simulation.createdAt)}</span>
                  {simulation.createdBy && (
                    <span className="text-sm">by {simulation.createdBy}</span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">
                    Last edited:
                  </Label>
                  <span className="text-sm">{formatDate(simulation.updatedAt)}</span>
                  {simulation.lastUpdatedBy && (
                    <span className="text-sm">by {simulation.lastUpdatedBy}</span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground min-w-[100px]">
                    Simulation UUID:
                  </Label>
                  <ReadonlyValue
                    value={
                      simulation.id
                        ? `${simulation.id.slice(0, 8)}…${simulation.id.slice(-6)}`
                        : undefined
                    }
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigator.clipboard.writeText(simulation.id)}
                  >
                    Copy
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* External Resources */}
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

              {/* Other link groups */}
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

          {/* Notes */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="min-h-[120px]"
                disabled={!canEdit}
              />
            </CardContent>
          </Card>

          {/* Comments (placeholder) */}
          <div>
            <h3 className="mb-2 text-sm font-semibold tracking-tight">Comments</h3>
            <div className="space-y-4">
              {comments.map((c) => (
                <div key={c.id} className="flex gap-3 py-4 px-2 rounded">
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
                    <p className="text-sm">{c.text}</p>
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
                <Button onClick={addComment}>Post</Button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* ================= OUTPUTS TAB ================= */}
        <TabsContent value="outputs" className="space-y-6">
          <SimulationPathCard
            kind="output"
            title="Output Paths"
            description="Primary output files generated by the simulation."
            paths={simulation.groupedArtifacts.output?.map((a) => a.uri) || []}
            emptyText="No output paths available."
          />
          <SimulationPathCard
            kind="archive"
            title="Archive Paths"
            description="Archived simulation data."
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
            description="Log files generated during batch processing."
            paths={simulation.groupedArtifacts.batchLog?.map((a) => a.uri) || []}
            emptyText="No batch log artifacts available."
          />
        </TabsContent>
      </Tabs>
    </div>
  );
};
