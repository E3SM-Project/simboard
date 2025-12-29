import { Copy, ExternalLink } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                   */
/* -------------------------------------------------------------------------- */

export const norm = (v: unknown) => {
  if (Array.isArray(v)) return JSON.stringify(v);
  if (v === null || v === undefined || v === '') return '—';
  return String(v);
};

interface LinkLike {
  url: string;
  label: string;
  isExternal: boolean;
}

/**
 * Normalizes artifacts and links into a consistent [{ url, label, isExternal }] array.
 * Supports artifacts with { uri, label, name } and links with { url, label }.
 */
export const toLinkArray = (value: unknown): LinkLike[] => {
  if (!value) return [];

  const normalize = (item: unknown): LinkLike[] => {
    if (!item) return [];

    // Plain string (URI or URL)
    if (typeof item === 'string') {
      if (item.startsWith('http') || item.startsWith('file:') || item.startsWith('/')) {
        return [
          {
            url: item,
            label: makeLabelFromPath(item),
            isExternal: item.startsWith('http'),
          },
        ];
      }
      return [];
    }

    // Object (artifact or link)
    if (typeof item === 'object') {
      const obj = item as Record<string, string | undefined>;
      const href = obj.url ?? obj.uri;

      if (!href) return [];

      return [
        {
          url: href,
          label: obj.label ?? obj.name ?? makeLabelFromPath(href),
          isExternal: href.startsWith('http'),
        },
      ];
    }

    return [];
  };

  return Array.isArray(value) ? value.flatMap(normalize) : normalize(value);
};

/** Generate short display label from URI/URL if none provided */
const makeLabelFromPath = (uri: string) => {
  if (!uri) return '';

  if (uri.startsWith('http')) {
    try {
      const { hostname, pathname } = new URL(uri);
      const shortPath =
        pathname.length > 30 ? pathname.slice(0, 27).replace(/\/$/, '') + '…' : pathname;

      return `${hostname}${shortPath}`;
    } catch {
      return uri;
    }
  }
  const parts = uri.split('/');
  return parts.at(-1) || uri;
};

/* -------------------------------------------------------------------------- */
/*  Cell Renderer                                                             */
/* -------------------------------------------------------------------------- */

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // optional toast or console.warn
  }
};

/**
 * Renders clickable links (URLs) or plain URIs with tooltips and icons.
 */
export const renderCellValue = (value: unknown): React.ReactNode => {
  const links = toLinkArray(value);

  if (links.length > 0) {
    return (
      <TooltipProvider delayDuration={150}>
        <div className="flex flex-wrap gap-2">
          {links.map((l, i) => (
            <Tooltip key={`${l.url}-${i}`}>
              <TooltipTrigger asChild>
                {l.isExternal ? (
                  // External URLs (Diagnostics / Performance)
                  <a
                    href={l.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-600 underline break-all hover:text-blue-800"
                  >
                    {l.label}
                    <ExternalLink
                      size={14}
                      strokeWidth={1.75}
                      className="opacity-70 inline-block"
                    />
                  </a>
                ) : (
                  // Local URIs (Locations)
                  <span className="inline-flex items-center gap-1 text-gray-700 break-all">
                    <span>{l.url}</span>
                    <button
                      type="button"
                      onClick={() => copyText(l.url)}
                      className="p-1 rounded hover:bg-gray-100"
                      aria-label="Copy path"
                      title="Copy full path/URI"
                    >
                      <Copy size={13} className="text-gray-500" />
                    </button>
                  </span>
                )}
              </TooltipTrigger>
              <TooltipContent side="top" align="start" className="max-w-[40rem] break-all">
                {l.url}
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      </TooltipProvider>
    );
  }

  if (Array.isArray(value)) {
    return value.length ? value.join(', ') : <span className="text-gray-400">—</span>;
  }

  if (value === null || value === undefined || value === '') {
    return <span className="text-gray-400">—</span>;
  }

  return String(value);
};
