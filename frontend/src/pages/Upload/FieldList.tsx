import { SimulationCreateForm } from '@/types/simulation';

interface FieldDef {
  name: string;
  label: string;
}

interface FieldListProps {
  form: SimulationCreateForm;
  fields: FieldDef[];
  className?: string;
}

export const FieldList = ({ form, fields, className = 'text-sm space-y-1' }: FieldListProps) => {
  return (
    <div className={className}>
      {fields.map((field) => {
        const value = form[field.name as keyof SimulationCreateForm];

        const displayValue = Array.isArray(value) ? value.join(', ') || '—' : (value ?? '—');

        return (
          <div key={field.name}>
            <strong>{field.label}:</strong> {String(displayValue)}
          </div>
        );
      })}
    </div>
  );
};
