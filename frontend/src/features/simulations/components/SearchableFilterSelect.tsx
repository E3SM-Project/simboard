import { Check, ChevronsUpDown } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

interface SearchableFilterOption {
  value: string;
  label: string;
}

interface SearchableFilterSelectProps {
  label: string;
  value: string;
  placeholder: string;
  options: SearchableFilterOption[];
  onValueChange: (value: string) => void;
}

const MAX_VISIBLE_OPTIONS = 100;

export const SearchableFilterSelect = ({
  label,
  value,
  placeholder,
  options,
  onValueChange,
}: SearchableFilterSelectProps) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const selectedLabel = useMemo(
    () => options.find((option) => option.value === value)?.label,
    [options, value],
  );
  const { matchingOptions, matchingOptionCount } = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase();
    const matches = normalizedSearch
      ? options.filter((option) => option.label.toLocaleLowerCase().includes(normalizedSearch))
      : options;

    return {
      matchingOptions: matches.slice(0, MAX_VISIBLE_OPTIONS),
      matchingOptionCount: matches.length,
    };
  }, [options, search]);

  const handleSelect = (nextValue: string) => {
    onValueChange(nextValue);
    setOpen(false);
    setSearch('');
  };

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) setSearch('');
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          className="h-10 w-full justify-between rounded-xl border-slate-200 bg-white font-normal shadow-none"
        >
          <span className={cn('truncate', !selectedLabel && 'text-muted-foreground')}>
            {selectedLabel ?? placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      {open && (
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Search options..."
              value={search}
              onValueChange={setSearch}
            />
            <CommandList>
              <CommandEmpty>No options found.</CommandEmpty>
              <CommandGroup>
                {!search && (
                  <CommandItem value="__all__" onSelect={() => handleSelect('')}>
                    <Check className={cn('h-4 w-4', value ? 'opacity-0' : 'opacity-100')} />
                    {placeholder}
                  </CommandItem>
                )}
                {matchingOptions.map((option) => (
                  <CommandItem
                    key={option.value}
                    value={option.value}
                    onSelect={() => handleSelect(option.value)}
                  >
                    <Check
                      className={cn(
                        'h-4 w-4',
                        value === option.value ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    {option.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
            {matchingOptionCount > MAX_VISIBLE_OPTIONS && (
              <p className="border-t px-3 py-2 text-xs text-muted-foreground">
                Showing first {MAX_VISIBLE_OPTIONS} results. Search to narrow.
              </p>
            )}
          </Command>
        </PopoverContent>
      )}
    </Popover>
  );
};
