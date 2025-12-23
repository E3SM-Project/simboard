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
}) => {
  // Simple URL validation function
  const isValidUrl = (url: string) => {
    try {
      new URL(url);

      return true;
    } catch {
      return false;
    }
  };

  const [showTooltipIndex, setShowTooltipIndex] = React.useState<number | null>(null);

  return (
    <div>
      <div className="font-medium mb-2">
        {title} <span className="text-xs text-muted-foreground">{optionalText}</span>
      </div>
      {links.map((lnk, i) => {
        const invalidUrl = lnk.url && !isValidUrl(lnk.url);
        return (
          <div key={i} className="flex gap-2 mb-2 items-center">
            <input
              className="w-1/3 h-10 rounded-md border px-3"
              placeholder="Label"
              value={lnk.label}
              onChange={(e) => onChange(i, 'label', e.target.value)}
            />
            <div className="relative w-2/3">
              <input
                className={`w-full h-10 rounded-md border px-3 ${
                  invalidUrl ? 'border-red-500' : ''
                }`}
                placeholder="URL"
                value={lnk.url}
                onChange={(e) => onChange(i, 'url', e.target.value)}
                onFocus={() => {
                  if (invalidUrl) setShowTooltipIndex(i);
                }}
                onBlur={() => {
                  setShowTooltipIndex(null);
                }}
              />
              {invalidUrl && showTooltipIndex === i && (
                <div className="absolute left-0 top-full mt-1 text-xs bg-red-100 text-red-700 px-2 py-1 rounded shadow z-10">
                  Invalid URL
                </div>
              )}
            </div>
          </div>
        );
      })}
      <button type="button" className="text-sm text-blue-600 underline" onClick={onAdd}>
        + Add Link
      </button>
    </div>
  );
};
