import type { RenderableField } from '@/features/upload/types/field';
import { SimulationCreateForm } from '@/types/simulation';

interface ReviewFieldListProps {
  form: SimulationCreateForm;
  fields: RenderableField[];
  className?: string;
}
export const ReviewFieldList = ({
  form,
  fields,
  className = 'text-sm space-y-2',
}: ReviewFieldListProps) => {
  const fieldIsEmpty = (value: unknown): boolean => {
    if (value == null) return true;
    if (Array.isArray(value)) return value.length === 0;
    if (typeof value === 'object') return Object.keys(value).length === 0;
    return value === '';
  };

  return (
    <div className={className}>
      {fields.map((field) => {
        const value = form[field.name as keyof SimulationCreateForm];
        const isEmpty = fieldIsEmpty(value);

        let bgColor = 'bg-gray-100';
        if (field.required) {
          bgColor = isEmpty ? 'bg-yellow-100' : 'bg-green-100';
        }

        let displayValue: React.ReactNode = '—';

        if (!isEmpty && field.renderValue) {
          displayValue = field.renderValue(String(value));
        } else if (Array.isArray(value)) {
          displayValue = value.length ? value.join(', ') : '—';
        } else if (typeof value === 'object' && value !== null) {
          displayValue = JSON.stringify(value, null, 2);
        } else if (!isEmpty) {
          displayValue = value;
        }

        return (
          <div key={field.name} className={`rounded px-3 py-2 ${bgColor} flex items-center`}>
            <span className="font-semibold flex-shrink-0 min-w-[180px]">
              {field.label}
              {field.required && <span className="ml-1 text-red-500">*</span>}:
            </span>
            <span className="ml-4 whitespace-pre-wrap">{displayValue}</span>
          </div>
        );
      })}
    </div>
  );
};
