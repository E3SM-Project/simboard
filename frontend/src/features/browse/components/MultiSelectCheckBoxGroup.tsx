import { Checkbox } from '@/components/ui/checkbox';

export type Option = string | { value: string; label: string };

interface MultiSelectCheckboxGroupProps {
  label: string;
  options: Option[];
  selected: string[]; // always IDs under the hood
  onChange: (next: string[]) => void;
  renderOptionLabel?: (option: Option) => React.ReactNode;
}

const MultiSelectCheckboxGroup = ({
  label,
  options,
  selected,
  onChange,
  renderOptionLabel,
}: MultiSelectCheckboxGroupProps) => {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </label>
      <div className="space-y-1.5">
        {options.map((opt) => {
          const value = typeof opt === 'string' ? opt : opt.value;
          const display = renderOptionLabel
            ? renderOptionLabel(opt)
            : typeof opt === 'string'
              ? opt
              : opt.label;
          const isChecked = selected?.includes(value);
          return (
            <div key={value} className="flex items-center gap-2">
              <Checkbox
                id={`${label}-${value}`}
                checked={isChecked}
                onCheckedChange={(checked) => {
                  let next: string[] = selected ?? [];
                  if (checked === true) next = Array.from(new Set([...next, value]));
                  else if (checked === false) next = next.filter((s) => s !== value);
                  onChange(next);
                }}
              />
              <label htmlFor={`${label}-${value}`} className="text-sm text-slate-700">
                {display}
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
};
export default MultiSelectCheckboxGroup;
