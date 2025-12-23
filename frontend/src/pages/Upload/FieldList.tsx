import type { ExternalLinkIn } from '@/types/link';
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
export const FieldList = ({ form, fields, className = 'text-sm space-y-2' }: FieldListProps) => {
  return (
    <div className={className}>
      {fields.map((field) => {
        const value = form[field.name as keyof SimulationCreateForm];
        const isEmpty =
          value === undefined ||
          value === null ||
          (Array.isArray(value) ? value.length === 0 : value === '') ||
          (typeof value === 'object' && value !== null && Object.keys(value).length === 0);

        let displayValue: string | JSX.Element;
        // @ts-expect-error: type may exist on some fields
        if (field.type === 'links' && Array.isArray(value) && value.length > 0) {
          displayValue = (
            <ul className="list-disc ml-6">
              {value
                .filter((link: ExternalLinkIn) => link.label && link.url)
                .map((link: ExternalLinkIn, idx: number) => (
                  <li key={idx}>
                    <span className="font-medium">{link.label}:</span>{' '}
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 underline"
                    >
                      {link.url}
                    </a>
                  </li>
                ))}
            </ul>
          );
          // If no valid links, show em dash
          if (
            value.filter((link: { label: string; url: string }) => link.label && link.url)
              .length === 0
          ) {
            displayValue = '—';
          }
        } else if (Array.isArray(value)) {
          displayValue = value.join(', ') || '—';
        } else if (typeof value === 'object' && value !== null) {
          displayValue = JSON.stringify(value, null, 2);
        } else {
          displayValue = value ?? '—';
        }

        let bgColor = 'bg-gray-100';
        // @ts-expect-error: required may exist on some fields
        if (field.required) {
          bgColor = isEmpty ? 'bg-yellow-100' : 'bg-green-100';
        }

        return (
          <div key={field.name} className={`rounded px-3 py-2 ${bgColor} flex items-center`}>
            <span className="font-semibold flex-shrink-0 min-w-[180px]">
              {field.label}
              {/* @ts-expect-error: required may exist on some fields */}
              {field.required && <span className="ml-1 text-red-500">*</span>}:
            </span>
            <span className="ml-4 whitespace-pre-wrap">{displayValue}</span>
          </div>
        );
      })}
    </div>
  );
};
