import { Sparkles } from 'lucide-react';
import { useState } from 'react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
import type { SimulationSummaryResponseOut } from '@/types';

interface SimulationSummaryPanelProps {
  summary?: SimulationSummaryResponseOut | null;
  summaryLoading?: boolean;
  summaryError?: string | null;
  summaryRequested?: boolean;
  summaryElapsedMs?: number;
  summaryLastDurationMs?: number | null;
  onGenerateSummary?: () => void | Promise<void>;
  canGenerateSummary?: boolean;
  isCheckingAuth?: boolean;
  onLoginForSummary?: () => void;
}

const formatSummaryRuntime = (durationMs: number) => {
  const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${totalSeconds}s`;
  }

  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
};

const getSummaryActionLabel = ({
  summary,
  summaryLoading = false,
  canGenerateSummary = false,
  isCheckingAuth = false,
}: Pick<
  SimulationSummaryPanelProps,
  'summary' | 'summaryLoading' | 'canGenerateSummary' | 'isCheckingAuth'
>) => {
  if (isCheckingAuth) return 'Checking login...';
  if (summaryLoading) return 'Generating...';
  if (!canGenerateSummary) return 'Log In To Generate AI Summary';
  if (summary) return 'Regenerate AI Summary';
  return 'Generate AI Summary';
};

const getSummaryStatusLabel = ({
  summary,
  summaryLoading = false,
  summaryError = null,
  isCheckingAuth = false,
}: Pick<
  SimulationSummaryPanelProps,
  'summary' | 'summaryLoading' | 'summaryError' | 'isCheckingAuth'
>) => {
  if (isCheckingAuth) return 'Checking login';
  if (summaryLoading) return 'Generating';
  if (summaryError) return 'Error';
  if (summary) return 'Ready';
  return 'Not generated';
};

const getSummaryStatusClasses = (status: string) => {
  switch (status) {
    case 'Ready':
      return 'bg-emerald-100 text-emerald-900';
    case 'Generating':
    case 'Checking login':
      return 'bg-blue-100 text-blue-900';
    case 'Error':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-slate-100 text-slate-700';
  }
};

const SummaryTextBlock = ({ value, className }: { value: string; className?: string }) => (
  <div
    className={cn(
      'min-h-[140px] whitespace-pre-wrap rounded-md border bg-white px-4 py-3 text-sm leading-6 break-words',
      className,
    )}
  >
    {value.trim()}
  </div>
);

const SummaryList = ({ items }: { items: string[] }) => (
  <ul className="space-y-2 rounded-md border bg-white px-4 py-3 text-sm">
    {items.map((item) => (
      <li key={item} className="list-none leading-6">
        {item}
      </li>
    ))}
  </ul>
);

const SummaryCitations = ({ summary }: { summary: SimulationSummaryResponseOut }) => (
  <div className="rounded-md border bg-white">
    <div className="divide-y">
      {summary.citations.map((citation) => (
        <div
          key={`${citation.sourceType}-${citation.path}`}
          className="flex flex-col gap-1 px-4 py-3 text-sm md:flex-row md:items-start md:justify-between"
        >
          <div className="font-medium text-foreground">{citation.label}</div>
          <code className="text-xs text-muted-foreground">{citation.path}</code>
        </div>
      ))}
    </div>
  </div>
);

const SummarySectionAccordion = ({
  summary,
  defaultValue = ['caveats'],
}: {
  summary: SimulationSummaryResponseOut;
  defaultValue?: string[];
}) => {
  const sections = [
    {
      value: 'caveats',
      label: `Caveats (${summary.caveats.length})`,
      visible: summary.caveats.length > 0,
      content: <SummaryList items={summary.caveats} />,
    },
    {
      value: 'limitations',
      label: `Limitations (${summary.limitations.length})`,
      visible: summary.limitations.length > 0,
      content: <SummaryList items={summary.limitations} />,
    },
    {
      value: 'citations',
      label: `Citations (${summary.citations.length})`,
      visible: summary.citations.length > 0,
      content: <SummaryCitations summary={summary} />,
    },
    {
      value: 'followups',
      label: `Suggested Follow-up Questions (${summary.suggestedFollowups.length})`,
      visible: summary.suggestedFollowups.length > 0,
      content: <SummaryList items={summary.suggestedFollowups} />,
    },
  ].filter((section) => section.visible);

  if (sections.length === 0) {
    return null;
  }

  return (
    <Accordion type="multiple" defaultValue={defaultValue} className="rounded-md border bg-white px-4">
      {sections.map((section) => (
        <AccordionItem
          key={section.value}
          value={section.value}
          className="border-slate-200 last:border-b-0"
        >
          <AccordionTrigger className="py-3 text-sm font-medium text-foreground hover:no-underline">
            {section.label}
          </AccordionTrigger>
          <AccordionContent className="pb-3">{section.content}</AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
};

const SummaryActionButton = ({
  summary,
  summaryLoading = false,
  onGenerateSummary,
  canGenerateSummary = false,
  isCheckingAuth = false,
  onLoginForSummary,
  className,
}: Pick<
  SimulationSummaryPanelProps,
  | 'summary'
  | 'summaryLoading'
  | 'onGenerateSummary'
  | 'canGenerateSummary'
  | 'isCheckingAuth'
  | 'onLoginForSummary'
> & {
  className?: string;
}) => (
  <Button
    type="button"
    variant="outline"
    onClick={() => {
      if (!canGenerateSummary) {
        onLoginForSummary?.();
        return;
      }

      void onGenerateSummary?.();
    }}
    disabled={summaryLoading || isCheckingAuth || (!canGenerateSummary && !onLoginForSummary)}
    className={cn('border-blue-200 bg-white text-blue-900 hover:bg-blue-50', className)}
  >
    {isCheckingAuth ? (
      'Checking login...'
    ) : summaryLoading ? (
      <>
        <Spinner className="mr-2 size-4" />
        Generating...
      </>
    ) : (
      getSummaryActionLabel({ summary, summaryLoading, canGenerateSummary, isCheckingAuth })
    )}
  </Button>
);

const SummaryPanelBody = ({
  summary,
  summaryLoading = false,
  summaryError = null,
  summaryRequested = false,
  summaryElapsedMs = 0,
  summaryLastDurationMs = null,
  canGenerateSummary = false,
  isCheckingAuth = false,
  scrollable = false,
  className,
}: Pick<
  SimulationSummaryPanelProps,
  | 'summary'
  | 'summaryLoading'
  | 'summaryError'
  | 'summaryRequested'
  | 'summaryElapsedMs'
  | 'summaryLastDurationMs'
  | 'canGenerateSummary'
  | 'isCheckingAuth'
> & {
  scrollable?: boolean;
  className?: string;
}) => {
  const summaryGenerationMode = summary?.generationMode ?? 'deterministic';
  const summaryGenerationProvider =
    summaryGenerationMode === 'llm' ? summary?.generationProvider ?? null : null;
  const summaryGenerationModel =
    summaryGenerationMode === 'llm' ? summary?.generationModel ?? null : null;

  return (
    <div
      className={cn(
        'space-y-4',
        scrollable && 'max-h-[calc(100vh-15rem)] overflow-y-auto pr-1',
        className,
      )}
    >
      {!summaryRequested && !summary && !summaryError && (
        <div className="flex min-h-[220px] items-center rounded-md border border-dashed border-blue-200 bg-white/80 px-4 py-5 text-sm text-muted-foreground">
          {canGenerateSummary
            ? 'Generate a read-only summary grounded only in metadata already stored in SimBoard. It will not change this simulation record.'
            : 'Log in with GitHub to generate a read-only, metadata-based AI summary for this simulation.'}
        </div>
      )}

      {summaryError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <div>{summaryError}</div>
          {summaryLastDurationMs !== null && (
            <div className="mt-1 text-xs text-red-600/80">
              Latest attempt ran for {formatSummaryRuntime(summaryLastDurationMs)}.
            </div>
          )}
        </div>
      )}

      {summaryLoading && !summary && (
        <div className="flex min-h-[220px] items-center rounded-md border bg-white/80 px-4 py-5">
          <div className="space-y-1 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <Spinner className="size-4" />
              Generating summary from SimBoard metadata...
            </div>
            <div className="pl-6 text-xs text-slate-500">
              {formatSummaryRuntime(summaryElapsedMs)} elapsed. This can fall back to a
              metadata-based summary if AI generation stalls or fails.
            </div>
          </div>
        </div>
      )}

      {summary && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 rounded-md border bg-white px-4 py-3">
            <Badge
              variant="secondary"
              className={
                summaryGenerationMode === 'llm'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-700'
              }
            >
              {summaryGenerationMode === 'llm' ? 'LLM Summary' : 'Deterministic Summary'}
            </Badge>
            {summaryGenerationProvider && (
              <span className="text-sm text-muted-foreground">
                Provider: {summaryGenerationProvider}
                {summaryGenerationModel ? ` · ${summaryGenerationModel}` : ''}
              </span>
            )}
            {summaryLastDurationMs !== null && (
              <span className="text-sm text-muted-foreground">
                Runtime: {formatSummaryRuntime(summaryLastDurationMs)}
              </span>
            )}
          </div>

          {summaryGenerationMode !== 'llm' && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              AI generation did not complete for this attempt. Showing metadata-based summary
              instead.
            </div>
          )}

          <div>
            <Label className="mb-2 block text-xs text-muted-foreground">Summary</Label>
            <SummaryTextBlock value={summary.answer} />
          </div>

          <SummarySectionAccordion
            summary={summary}
            defaultValue={summary.caveats.length > 0 ? ['caveats'] : []}
          />
        </div>
      )}

      {!summary && !summaryLoading && !summaryError && summaryRequested && (
        <div className="flex min-h-[220px] items-center rounded-md border bg-white/80 px-4 py-5 text-sm text-muted-foreground">
          No summary is available yet.
        </div>
      )}

      {isCheckingAuth && !summaryLoading && !summary && !summaryError && !summaryRequested && (
        <div className="text-xs text-muted-foreground">
          Verifying whether summary generation is available for this session.
        </div>
      )}
    </div>
  );
};

export const SimulationSummaryRail = ({
  summary,
  summaryLoading = false,
  summaryError = null,
  summaryRequested = false,
  summaryElapsedMs = 0,
  summaryLastDurationMs = null,
  onGenerateSummary,
  canGenerateSummary = false,
  isCheckingAuth = false,
  onLoginForSummary,
}: SimulationSummaryPanelProps) => (
  <Card className="overflow-hidden border-blue-200/80 bg-gradient-to-br from-blue-50/70 via-white to-slate-50 shadow-sm">
    <CardHeader className="space-y-3 border-b border-blue-100/80 pb-4">
      <div className="space-y-1">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-blue-600" />
          AI Summary
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Read-only summary generated from metadata already recorded in SimBoard.
        </p>
      </div>
      <SummaryActionButton
        summary={summary}
        summaryLoading={summaryLoading}
        onGenerateSummary={onGenerateSummary}
        canGenerateSummary={canGenerateSummary}
        isCheckingAuth={isCheckingAuth}
        onLoginForSummary={onLoginForSummary}
        className="w-full"
      />
    </CardHeader>
    <CardContent className="min-h-[440px] p-4">
      <SummaryPanelBody
        summary={summary}
        summaryLoading={summaryLoading}
        summaryError={summaryError}
        summaryRequested={summaryRequested}
        summaryElapsedMs={summaryElapsedMs}
        summaryLastDurationMs={summaryLastDurationMs}
        canGenerateSummary={canGenerateSummary}
        isCheckingAuth={isCheckingAuth}
        scrollable
      />
    </CardContent>
  </Card>
);

export const SimulationSummaryLauncher = ({
  summary,
  summaryLoading = false,
  summaryError = null,
  summaryRequested = false,
  summaryElapsedMs = 0,
  summaryLastDurationMs = null,
  onGenerateSummary,
  canGenerateSummary = false,
  isCheckingAuth = false,
  onLoginForSummary,
}: SimulationSummaryPanelProps) => {
  const [open, setOpen] = useState(false);
  const status = getSummaryStatusLabel({ summary, summaryLoading, summaryError, isCheckingAuth });

  return (
    <>
      <Card className="border-blue-200/80 bg-gradient-to-br from-blue-50/70 via-white to-slate-50 shadow-sm">
        <CardHeader className="space-y-3 pb-4">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4 text-blue-600" />
                AI Summary
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Open the AI summary drawer without moving the simulation metadata.
              </p>
            </div>
            <Badge className={cn('shrink-0', getSummaryStatusClasses(status))}>{status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-3 pt-0">
          <p className="text-sm text-muted-foreground">
            {summary
              ? summaryLastDurationMs !== null
                ? `Summary ready. Latest attempt took ${formatSummaryRuntime(summaryLastDurationMs)}.`
                : 'Summary is ready to review.'
              : summaryError
                ? summaryLastDurationMs !== null
                  ? `Latest summary attempt failed after ${formatSummaryRuntime(summaryLastDurationMs)}.`
                  : 'Review the latest summary error.'
                : summaryLoading
                  ? `Summary generation is in progress. ${formatSummaryRuntime(summaryElapsedMs)} elapsed.`
                  : canGenerateSummary
                    ? 'Generate a metadata-based summary when you need a quick overview.'
                    : 'Log in to generate a metadata-based summary for this run.'}
          </p>
          <Button
            type="button"
            variant="outline"
            className="shrink-0 border-blue-200 bg-white text-blue-900 hover:bg-blue-50"
            onClick={() => setOpen(true)}
          >
            Open AI Summary
          </Button>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="left-auto right-0 top-0 h-[100dvh] w-full max-w-[min(92vw,42rem)] translate-x-0 translate-y-0 gap-0 overflow-hidden rounded-none border-l border-slate-200 p-0 data-[state=closed]:slide-out-to-right data-[state=closed]:slide-out-to-top-0 data-[state=closed]:zoom-out-100 data-[state=open]:slide-in-from-right data-[state=open]:slide-in-from-top-0 data-[state=open]:zoom-in-100 sm:max-w-[28rem] sm:rounded-none">
          <div className="flex h-full min-h-0 flex-col">
            <DialogHeader className="gap-3 border-b border-blue-100/80 px-6 py-5 text-left">
              <div className="pr-10">
                <DialogTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="h-4 w-4 text-blue-600" />
                  AI Summary
                </DialogTitle>
                <DialogDescription className="mt-1">
                  Read-only summary generated from metadata already recorded in SimBoard.
                </DialogDescription>
              </div>
              <SummaryActionButton
                summary={summary}
                summaryLoading={summaryLoading}
                onGenerateSummary={onGenerateSummary}
                canGenerateSummary={canGenerateSummary}
                isCheckingAuth={isCheckingAuth}
                onLoginForSummary={onLoginForSummary}
                className="w-full justify-center"
              />
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              <SummaryPanelBody
                summary={summary}
                summaryLoading={summaryLoading}
                summaryError={summaryError}
                summaryRequested={summaryRequested}
                summaryElapsedMs={summaryElapsedMs}
                summaryLastDurationMs={summaryLastDurationMs}
                canGenerateSummary={canGenerateSummary}
                isCheckingAuth={isCheckingAuth}
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};
