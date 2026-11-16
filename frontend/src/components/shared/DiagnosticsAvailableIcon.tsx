import { ChartLine } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

const LABEL = 'Diagnostics available';

/** Informational marker shown beside a case name when the case links diagnostics. */
export const DiagnosticsAvailableIcon = () => (
  <TooltipProvider delayDuration={150}>
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={LABEL}
          className="inline-flex shrink-0 rounded-sm bg-sky-50 p-0.5 text-sky-700"
        >
          <ChartLine className="h-3.5 w-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent className="text-xs">{LABEL}</TooltipContent>
    </Tooltip>
  </TooltipProvider>
);
