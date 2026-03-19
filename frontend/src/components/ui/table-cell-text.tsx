import { useEffect, useRef, useState } from 'react';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type FullValueMode = 'title' | 'tooltip';

interface TableCellTextProps {
  value: string | number | null | undefined;
  className?: string;
  lines?: 1 | 2 | 3;
  mono?: boolean;
  placeholder?: string;
  fullValueMode?: FullValueMode;
}

const clampClassNames: Record<NonNullable<TableCellTextProps['lines']>, string> = {
  1: 'truncate whitespace-nowrap',
  2: 'line-clamp-2 break-words whitespace-normal',
  3: 'line-clamp-3 break-words whitespace-normal',
};

export const TableCellText = ({
  value,
  className,
  lines = 1,
  mono = false,
  placeholder = '—',
  fullValueMode = 'title',
}: TableCellTextProps) => {
  const contentRef = useRef<HTMLSpanElement>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const text = value === null || value === undefined || value === '' ? placeholder : String(value);

  useEffect(() => {
    const element = contentRef.current;

    if (!element) {
      return;
    }

    const updateOverflow = () => {
      const nextIsOverflowing =
        element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight + 1;
      setIsOverflowing(nextIsOverflowing);
    };

    updateOverflow();

    const resizeObserver = new ResizeObserver(updateOverflow);
    resizeObserver.observe(element);

    return () => {
      resizeObserver.disconnect();
    };
  }, [text, lines, mono, className]);

  const content = (
    <span
      ref={contentRef}
      className={cn(
        'block min-w-0 max-w-full',
        mono && 'font-mono text-xs',
        clampClassNames[lines],
        className,
      )}
      title={fullValueMode === 'title' ? text : undefined}
    >
      {text}
    </span>
  );

  if (fullValueMode === 'title') {
    return content;
  }

  if (!isOverflowing) {
    return content;
  }

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>{content}</TooltipTrigger>
        <TooltipContent className="max-w-[36rem] break-all text-xs">{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
