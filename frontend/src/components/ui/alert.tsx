import { cva, type VariantProps } from 'class-variance-authority';
import * as React from 'react';

import { cn } from '@/lib/utils';

const alertVariants = cva('rounded-md border p-3 text-sm', {
  variants: {
    variant: {
      error: 'border-red-200 bg-red-50 text-red-700',
      warning: 'border-amber-200 bg-amber-50 text-amber-900',
      info: 'border-sky-200 bg-sky-50 text-sky-950',
    },
  },
  defaultVariants: {
    variant: 'info',
  },
});

type AlertProps = React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>;

/** Inline notice for errors, warnings, and contextual info. Errors are announced assertively. */
const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ className, variant, ...props }, ref) => (
    <div
      ref={ref}
      role={variant === 'error' ? 'alert' : 'status'}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  ),
);
Alert.displayName = 'Alert';

export { Alert };
