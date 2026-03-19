import {
  BadgeCheck,
  ChevronDown,
  Clock,
  FlaskConical,
  GitBranch,
  Lightbulb,
  Rocket,
  Server,
  Tag,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import type { SimulationOut } from '@/types/index';

interface SimulationResultCard {
  simulation: SimulationOut;
  selected: boolean;
  handleSelect: (sim: SimulationOut) => void;
}

export const SimulationResultCard = ({
  simulation,
  selected,
  handleSelect,
}: SimulationResultCard) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();

  // -------------------- Derived Data --------------------
  const startStr = simulation.simulationStartDate
    ? new Date(simulation.simulationStartDate).toISOString().slice(0, 10)
    : 'N/A';
  const endStr = simulation.simulationEndDate
    ? new Date(simulation.simulationEndDate).toISOString().slice(0, 10)
    : 'N/A';

  return (
    <Card className="flex h-full w-full flex-col rounded-2xl border border-slate-200 bg-white p-0 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex flex-col items-start gap-4 p-5 sm:flex-row">
        <Checkbox
          checked={selected}
          onCheckedChange={() => handleSelect(simulation)}
          aria-label="Select for comparison"
          className="mt-1"
          style={{ width: 24, height: 24 }}
        />
        <div className="flex-1 w-full min-w-0 max-w-2xl">
          <CardHeader className="mb-4 flex flex-col items-start gap-3 p-0">
            <div className="min-w-0">
              <span className="block break-words text-lg font-semibold tracking-tight text-slate-950">
                {simulation.executionId}
              </span>
              <div className="mt-1 break-words text-sm text-slate-500">
                <span className="font-medium text-slate-600">Case:</span> {simulation.caseName}
              </div>
            </div>
            <div className="flex w-full flex-wrap items-center gap-2 text-sm">
              <span className="font-medium text-slate-600">Status</span>
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

            {/* Grid & Machine grouping with divider and lighter value color */}
            <div className="mb-4 mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-700">
              <div className="flex items-center gap-1">
                <FlaskConical className="h-3 w-3 text-slate-700" />
                <span className="font-semibold">Grid:</span>
                <span className="ml-1 font-normal text-slate-500">{simulation.gridName}</span>
              </div>
              <span className="mx-2 h-4 w-px bg-slate-300" />
              <div className="flex items-center gap-1">
                <Server className="h-3 w-3 text-slate-700" />
                <span className="font-semibold">Machine:</span>
                <span className="ml-1 font-normal text-slate-500">{simulation.machine.name}</span>
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

            <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50/70">
              <details className="w-full group">
                <summary className="flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 transition hover:bg-slate-100 group-open:border-b group-open:border-slate-200">
                  More Details
                  <ChevronDown className="w-4 h-4 ml-2" />
                </summary>
                <div className="space-y-2 px-3 py-3 text-sm text-slate-700">
                  {/* FIXME: Fix this field.  */}
                  {/* Key Features */}
                  {simulation.keyFeatures && (
                    <div>
                      <span className="font-semibold">Key Features:</span>
                      <span className="ml-1 text-gray-600">{simulation.keyFeatures}</span>
                    </div>
                  )}

                  {/* Notes */}
                  {simulation.notesMarkdown && (
                    <div>
                      <span className="font-semibold">Notes:</span>
                      <span className="ml-1 text-gray-600">{simulation.notesMarkdown}</span>
                    </div>
                  )}

                  {/* Known Issues */}
                  {simulation.knownIssues && (
                    <div>
                      <span className="font-semibold">Known Issues:</span>
                      <span className="ml-1 text-gray-600">{simulation.knownIssues}</span>
                    </div>
                  )}

                  {/* Diagnostic Links */}
                  {simulation.groupedLinks.diagnostic &&
                    simulation.groupedLinks.diagnostic.length > 0 && (
                      <div>
                        <span className="font-semibold">Diagnostics:</span>
                        <ul className="list-disc ml-6">
                          {simulation.groupedLinks.diagnostic.map((d, i) => (
                            <li key={i}>
                              <a
                                href={d.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-700 underline"
                              >
                                {d.label}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  {/* PACE Links */}
                  {simulation.groupedLinks.performance &&
                    simulation.groupedLinks.performance.length > 0 && (
                      <div>
                        <span className="font-semibold">PACE Links:</span>
                        <ul className="list-disc ml-6">
                          {simulation.groupedLinks.performance.map((p, i) => (
                            <li key={i}>
                              <a
                                href={p.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-700 underline"
                              >
                                {p.label}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  {/* Git Info */}
                  {(simulation.gitBranch || simulation.gitCommitHash) && (
                    <div>
                      <span className="font-semibold">Git:</span>
                      <span className="ml-1 text-gray-600">
                        {simulation.gitBranch && (
                          <>
                            Branch: <span className="font-mono">{simulation.gitBranch}</span>
                          </>
                        )}
                        {simulation.gitCommitHash && (
                          <>
                            {simulation.gitBranch ? ' | ' : ''}
                            Hash:{' '}
                            <span className="font-mono">
                              {simulation.gitCommitHash.slice(0, 8)}
                            </span>
                          </>
                        )}
                      </span>
                    </div>
                  )}
                  {/* FIXME: Fix this field */}
                  {/* Run Script Paths */}
                  {simulation.groupedArtifacts.runScript &&
                    simulation.groupedArtifacts.runScript.length > 0 && (
                      <div>
                        <span className="font-semibold">Run Scripts:</span>
                        <ul className="list-disc ml-6 text-gray-600">
                          {simulation.groupedArtifacts.runScript.map((p, i) => (
                            <li key={i} className="break-all">
                              {typeof p === 'string' ? p : JSON.stringify(p)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  {/* Archive Paths */}
                  {simulation.groupedArtifacts.archive &&
                    simulation.groupedArtifacts.archive.length > 0 && (
                      <div>
                        <span className="font-semibold">Archive Paths:</span>
                        <ul className="list-disc ml-6 text-gray-600">
                          {simulation.groupedArtifacts.archive.map((p, i) => (
                            <li key={i} className="break-all">
                              {typeof p === 'string' ? p : JSON.stringify(p)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  {/* Postprocessing Scripts */}
                  {simulation.groupedArtifacts.postProcessingScript &&
                    simulation.groupedArtifacts.postProcessingScript.length > 0 && (
                      <div>
                        <span className="font-semibold">Postprocessing Scripts:</span>
                        <ul className="list-disc ml-6 text-gray-600">
                          {simulation.groupedArtifacts.postprocessingScript.map((p, i) => (
                            <li key={i} className="break-all">
                              {typeof p === 'string' ? p : JSON.stringify(p)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                </div>
              </details>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-4 mt-4 justify-end">
              <Button
                variant="outline"
                size="sm"
                className="w-full sm:w-40"
                onClick={() => navigate(`/simulations/${simulation.id}`)}
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
