import React from 'react';

interface Link {
  label: string;
  url: string;
}

interface LinkFieldProps {
  title: string;
  links: Link[];
  onChange: (index: number, field: 'label' | 'url', value: string) => void;
  onAdd: () => void;
  optionalText?: string;
}

export const LinkField: React.FC<LinkFieldProps> = ({
  title,
  links,
  onChange,
  onAdd,
  optionalText = '(optional)',
}) => (
  <div>
    <div className="font-medium mb-2">
      {title} <span className="text-xs text-muted-foreground">{optionalText}</span>
    </div>
    {links.map((lnk, i) => (
      <div key={i} className="flex gap-2 mb-2">
        <input
          className="w-1/3 h-10 rounded-md border px-3"
          placeholder="Label"
          value={lnk.label}
          onChange={(e) => onChange(i, 'label', e.target.value)}
        />
        <input
          className="w-2/3 h-10 rounded-md border px-3"
          placeholder="URL"
          value={lnk.url}
          onChange={(e) => onChange(i, 'url', e.target.value)}
        />
      </div>
    ))}
    <button type="button" className="text-sm text-blue-600 underline" onClick={onAdd}>
      + Add Link
    </button>
  </div>
);
