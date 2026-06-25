import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  type EditableLinkRow,
  EXTERNAL_LINK_KIND_OPTIONS,
  type ResourceRowFieldErrors,
} from '@/features/simulations/externalLinkEditing';
import { cn } from '@/lib/utils';
import type { ExternalLinkKind } from '@/types';

interface EditableExternalLinkListProps {
  title: string;
  description?: string;
  items: EditableLinkRow[];
  valueLabel?: string;
  valuePlaceholder: string;
  addLabel: string;
  onAdd: () => void;
  onKindChange: (index: number, kind: ExternalLinkKind) => void;
  onLabelChange: (index: number, value: string) => void;
  onValueChange: (index: number, value: string) => void;
  onRemove: (index: number) => void;
  rowErrors?: ResourceRowFieldErrors[];
}

export const EditableExternalLinkList = ({
  title,
  description,
  items,
  valueLabel = 'URL',
  valuePlaceholder,
  addLabel,
  onAdd,
  onKindChange,
  onLabelChange,
  onValueChange,
  onRemove,
  rowErrors,
}: EditableExternalLinkListProps) => (
  <div className="space-y-3">
    <div className="flex items-start justify-between gap-3">
      <div>
        <Label className="text-sm font-medium">{title}</Label>
        {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      <Button type="button" variant="outline" size="sm" onClick={onAdd}>
        <Plus className="mr-1 h-4 w-4" />
        {addLabel}
      </Button>
    </div>

    {items.length === 0 ? (
      <div className="rounded-md border border-dashed px-3 py-4 text-sm text-muted-foreground">
        No entries yet.
      </div>
    ) : (
      <div className="space-y-3">
        {items.map((item, index) => (
          <div key={`${item.kind}-${index}`} className="rounded-md border p-3">
            <div className="grid gap-3 md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1.4fr)_auto] md:items-start">
              <div className="space-y-1">
                <Label className="mb-1 block text-xs text-muted-foreground">Kind</Label>
                <Select
                  value={item.kind}
                  onValueChange={(value: ExternalLinkKind) => onKindChange(index, value)}
                >
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder="Select kind" />
                  </SelectTrigger>
                  <SelectContent>
                    {EXTERNAL_LINK_KIND_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {rowErrors?.[index]?.kind ? (
                  <p className="min-h-4 text-xs leading-4 text-red-600">{rowErrors[index].kind}</p>
                ) : (
                  <div className="min-h-4" aria-hidden="true" />
                )}
              </div>
              <div className="space-y-1">
                <Label className="mb-1 block text-xs text-muted-foreground">Label</Label>
                <Input
                  value={item.label}
                  onChange={(event) => onLabelChange(index, event.target.value)}
                  placeholder="Optional label"
                  className={cn(
                    'h-9 text-sm',
                    rowErrors?.[index]?.label ? 'border-red-300 focus-visible:ring-red-200' : '',
                  )}
                />
                {rowErrors?.[index]?.label ? (
                  <p className="min-h-4 text-xs leading-4 text-red-600">{rowErrors[index].label}</p>
                ) : (
                  <div className="min-h-4" aria-hidden="true" />
                )}
              </div>
              <div className="space-y-1">
                <Label className="mb-1 block text-xs text-muted-foreground">{valueLabel}</Label>
                <Input
                  value={item.value}
                  onChange={(event) => onValueChange(index, event.target.value)}
                  placeholder={valuePlaceholder}
                  className={cn(
                    'h-9 text-sm',
                    rowErrors?.[index]?.value ? 'border-red-300 focus-visible:ring-red-200' : '',
                  )}
                />
                {rowErrors?.[index]?.value ? (
                  <p className="min-h-4 text-xs leading-4 text-red-600">{rowErrors[index].value}</p>
                ) : (
                  <div className="min-h-4" aria-hidden="true" />
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => onRemove(index)}
                aria-label={`Remove ${title} item ${index + 1}`}
                className="mt-6 self-start"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);
