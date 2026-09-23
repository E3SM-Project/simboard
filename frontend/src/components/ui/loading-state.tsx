import { cn } from '@/lib/utils';

import { Spinner } from './spinner';

type LoadingStateKind = 'page' | 'section' | 'inline';

interface LoadingStateProps {
  className?: string;
  kind?: LoadingStateKind;
  label?: string;
}

export const LoadingState = ({
  className,
  kind = 'section',
  label = 'Loading',
}: LoadingStateProps) => (
  <div
    className={cn(
      'flex items-center justify-center gap-2 text-sm text-muted-foreground',
      kind === 'page' && 'min-h-[60vh]',
      kind === 'section' && 'min-h-32 rounded-xl border border-dashed border-muted bg-muted/10 p-6',
      kind === 'inline' && 'min-h-0',
      className,
    )}
    role="status"
    aria-live="polite"
  >
    <Spinner aria-hidden="true" className={kind === 'inline' ? 'size-4' : 'size-5'} />
    <span>{label}</span>
  </div>
);
