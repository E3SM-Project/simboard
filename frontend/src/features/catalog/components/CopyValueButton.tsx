import { Copy } from 'lucide-react';

import { Button } from '@/components/ui/button';

export const CopyValueButton = ({ label, value }: { label: string; value: string }) => (
  <Button
    variant="ghost"
    size="icon"
    className="ml-1 h-5 w-5 align-middle text-muted-foreground"
    aria-label={`Copy ${label}`}
    title={`Copy ${label}`}
    onClick={() => void navigator.clipboard?.writeText(value).catch(() => undefined)}
  >
    <Copy className="h-3 w-3" />
  </Button>
);
