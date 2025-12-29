import { JSX } from 'react';

import { ArtifactIn } from '@/types';
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

        let displayValue: string | JSX.Element = '—';

        // 1. Structural rendering.
        // @ts-expect-error: discriminated union to be fixed later
        if (field.type === 'links' && Array.isArray(value)) {
          const validLinks = value.filter((link: ExternalLinkIn) => link.label && link.url);

          displayValue =
            validLinks.length === 0 ? (
              '—'
            ) : (
              <ul className="list-disc ml-6">
                {validLinks.map((link, idx) => (
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

          // 2. Field-provided renderValue (scalar customization)
        } else if (!isEmpty && field.renderValue) {
          displayValue = field.renderValue(value);

          // 3. Generic fallbacks
        } else if (Array.isArray(value)) {
          displayValue = value.length ? value.join(', ') : '—';
        } else if (typeof value === 'object' && value !== null) {
          displayValue = JSON.stringify(value, null, 2);
        } else if (!isEmpty) {
          displayValue = value;
        }

        let bgColor = 'bg-gray-100';

        // FIXME: Fix the type check here.
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
