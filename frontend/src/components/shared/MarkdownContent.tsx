import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownContentProps {
  content?: string | null;
  className?: string;
  placeholder?: string;
}

type MarkdownSegment =
  | { type: 'markdown'; content: string }
  | { type: 'headerless-table'; rows: string[][] };

const NO_HEADER_TABLE_MARKER = '<!-- simboard-table:no-header -->';

const isExternalHref = (href: string): boolean => /^https?:\/\//i.test(href);

const joinClasses = (...classNames: Array<string | undefined | null | false>): string =>
  classNames.filter(Boolean).join(' ');

const parseTableRow = (line: string): string[] => {
  const trimmedLine = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  const cells: string[] = [];
  let currentCell = '';

  for (let index = 0; index < trimmedLine.length; index += 1) {
    const character = trimmedLine[index];
    const nextCharacter = trimmedLine[index + 1];

    if (character === '\\' && nextCharacter === '|') {
      currentCell += '|';
      index += 1;
      continue;
    }

    if (character === '|') {
      cells.push(currentCell.trim());
      currentCell = '';
      continue;
    }

    currentCell += character;
  }

  cells.push(currentCell.trim());

  return cells;
};

const splitMarkdownSegments = (content: string): MarkdownSegment[] => {
  const lines = content.split('\n');
  const segments: MarkdownSegment[] = [];
  let currentMarkdownLines: string[] = [];
  let lineIndex = 0;

  const flushMarkdownLines = () => {
    if (currentMarkdownLines.length === 0) {
      return;
    }

    segments.push({ type: 'markdown', content: currentMarkdownLines.join('\n') });
    currentMarkdownLines = [];
  };

  while (lineIndex < lines.length) {
    if (lines[lineIndex]?.trim() !== NO_HEADER_TABLE_MARKER) {
      currentMarkdownLines.push(lines[lineIndex] ?? '');
      lineIndex += 1;
      continue;
    }

    const tableLines: string[] = [];
    let tableLineIndex = lineIndex + 1;

    while (tableLineIndex < lines.length && lines[tableLineIndex]?.trim().startsWith('|')) {
      tableLines.push(lines[tableLineIndex] ?? '');
      tableLineIndex += 1;
    }

    if (tableLines.length < 2) {
      currentMarkdownLines.push(lines[lineIndex] ?? '');
      lineIndex += 1;
      continue;
    }

    flushMarkdownLines();

    segments.push({
      type: 'headerless-table',
      rows: [parseTableRow(tableLines[0]), ...tableLines.slice(2).map(parseTableRow)],
    });
    lineIndex = tableLineIndex;
  }

  flushMarkdownLines();

  return segments;
};

const markdownComponents: Components = {
  h1: ({ className, ...props }) => (
    <h1
      className={joinClasses('mt-1 text-xl font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={joinClasses('mt-1 text-lg font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={joinClasses('mt-1 text-base font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      className={joinClasses('mt-1 text-sm font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  p: ({ className, ...props }) => (
    <p className={joinClasses('leading-6 [&:not(:first-child)]:mt-3', className)} {...props} />
  ),
  a: ({ className, href, ...props }) => {
    const isExternal = href ? isExternalHref(href) : false;
    return (
      <a
        className={joinClasses('font-medium text-blue-600 underline underline-offset-4', className)}
        href={href}
        rel={isExternal ? 'noreferrer noopener' : undefined}
        target={isExternal ? '_blank' : undefined}
        {...props}
      />
    );
  },
  ul: ({ className, ...props }) => (
    <ul
      className={joinClasses('ml-5 list-disc space-y-1 [&:not(:first-child)]:mt-3', className)}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={joinClasses('ml-5 list-decimal space-y-1 [&:not(:first-child)]:mt-3', className)}
      {...props}
    />
  ),
  li: ({ className, ...props }) => <li className={joinClasses('pl-1', className)} {...props} />,
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={joinClasses(
        'mt-3 border-l-2 border-border/80 pl-4 italic text-muted-foreground',
        className,
      )}
      {...props}
    />
  ),
  code: ({ className, ...props }) => (
    <code
      className={joinClasses('rounded bg-muted px-1.5 py-0.5 font-mono text-[0.875em]', className)}
      {...props}
    />
  ),
  pre: ({ className, ...props }) => (
    <pre
      className={joinClasses(
        'mt-3 overflow-x-auto rounded-md bg-slate-950 px-3 py-2 font-mono text-sm text-slate-50',
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={joinClasses('my-4 border-border', className)} {...props} />
  ),
  table: ({ className, ...props }) => (
    <div className="my-4 overflow-x-auto">
      <table
        className={joinClasses('w-full border-collapse text-left text-sm', className)}
        {...props}
      />
    </div>
  ),
  thead: ({ className, ...props }) => (
    <thead className={joinClasses('border-b border-border', className)} {...props} />
  ),
  tbody: ({ className, ...props }) => (
    <tbody className={joinClasses('[&_tr:last-child]:border-0', className)} {...props} />
  ),
  tr: ({ className, ...props }) => (
    <tr className={joinClasses('border-b border-border/70', className)} {...props} />
  ),
  th: ({ className, ...props }) => (
    <th className={joinClasses('px-3 py-2 font-semibold', className)} {...props} />
  ),
  td: ({ className, ...props }) => (
    <td className={joinClasses('px-3 py-2 align-top', className)} {...props} />
  ),
};

export const MarkdownContent = ({
  content,
  className,
  placeholder = '—',
}: MarkdownContentProps) => {
  if (!content?.trim()) {
    return (
      <div
        className={joinClasses(
          'simboard-markdown-content rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground',
          className,
        )}
      >
        {placeholder}
      </div>
    );
  }

  const segments = splitMarkdownSegments(content);

  return (
    <div
      className={joinClasses(
        'simboard-markdown-content rounded-md border bg-muted/30 px-3 py-2 text-sm text-foreground',
        className,
      )}
    >
      {segments.map((segment, index) =>
        segment.type === 'markdown' ? (
          <ReactMarkdown
            key={`markdown-${index}`}
            remarkPlugins={[remarkGfm]}
            skipHtml
            components={markdownComponents}
          >
            {segment.content}
          </ReactMarkdown>
        ) : (
          <div key={`headerless-table-${index}`} className="my-4 overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <tbody className="[&_tr:last-child]:border-0">
                {segment.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-b border-border/70">
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex} className="px-3 py-2 align-top">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          skipHtml
                          components={markdownComponents}
                        >
                          {cell.replace(/<br \/>/g, '\n')}
                        </ReactMarkdown>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      )}
    </div>
  );
};
