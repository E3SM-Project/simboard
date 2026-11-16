import { CircleHelp } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { isAbbreviatedCommitHash } from '@/features/catalog/caseUtils';

export const CommitHashHelp = ({ hash }: { hash?: string | null }) => {
  const abbreviated = hash ? isAbbreviatedCommitHash(hash) : false;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={
              abbreviated ? 'About this abbreviated commit hash' : 'About this commit hash'
            }
            className="ml-1 inline-flex shrink-0 align-middle text-muted-foreground hover:text-foreground"
          >
            <CircleHelp className="size-3" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          Git commit the model was built from. Full hashes come from GIT_LOG.
          {abbreviated ? ' This hash is abbreviated because GIT_LOG was unavailable.' : null}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
