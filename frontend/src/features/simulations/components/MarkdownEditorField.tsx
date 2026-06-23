import {
  Bold,
  CircleHelp,
  Code,
  Heading2,
  Heading3,
  Italic,
  Link2,
  List,
  ListOrdered,
  ListTodo,
  Minus,
  Quote,
  SquareCode,
  Table2,
} from 'lucide-react';
import { type LucideIcon } from 'lucide-react';
import { useRef, useState } from 'react';

import { MarkdownContent } from '@/components/shared/MarkdownContent';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type EditorSelection = {
  start: number;
  end: number;
};

type EditorResult = {
  nextValue: string;
  selectionStart: number;
  selectionEnd: number;
};

interface MarkdownEditorFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  minHeightClassName?: string;
}

const MARKDOWN_PREVIEW_EMPTY_STATE = 'Nothing to preview yet.';

const HELP_EXAMPLES = [
  { label: 'H2', example: '## Section title' },
  { label: 'H3', example: '### Subsection title' },
  { label: 'Bullet list', example: '- First item\n- Second item' },
  { label: 'Numbered list', example: '1. First step\n2. Second step' },
  { label: 'Task list', example: '- [ ] Pending task\n- [x] Done task' },
  { label: 'Link', example: '[Example](https://example.com)' },
  { label: 'Code block', example: '```\ncode here\n```' },
  { label: 'Horizontal rule', example: '---' },
  { label: 'Table', example: '| Column | Value |\n| --- | --- |\n| Item | Data |' },
] as const;

const getSelection = (element: HTMLTextAreaElement): EditorSelection => ({
  start: element.selectionStart,
  end: element.selectionEnd,
});

const getLineRange = (value: string, selection: EditorSelection): EditorSelection => {
  const lineStart = value.lastIndexOf('\n', Math.max(selection.start - 1, 0)) + 1;
  const lineEndIndex = value.indexOf('\n', selection.end);
  const lineEnd = lineEndIndex === -1 ? value.length : lineEndIndex;

  return { start: lineStart, end: lineEnd };
};

const replaceSelection = (
  value: string,
  selection: EditorSelection,
  insertedText: string,
  selectionStart: number,
  selectionEnd: number = selectionStart,
): EditorResult => ({
  nextValue: `${value.slice(0, selection.start)}${insertedText}${value.slice(selection.end)}`,
  selectionStart,
  selectionEnd,
});

const wrapSelection = (
  value: string,
  selection: EditorSelection,
  before: string,
  after: string,
  fallbackText: string,
): EditorResult => {
  const selectedText = value.slice(selection.start, selection.end);
  const innerText = selectedText || fallbackText;
  const insertedText = `${before}${innerText}${after}`;
  const innerStart = selection.start + before.length;

  return replaceSelection(
    value,
    selection,
    insertedText,
    innerStart,
    innerStart + innerText.length,
  );
};

const prefixLines = (
  value: string,
  selection: EditorSelection,
  getPrefix: (index: number) => string,
): EditorResult => {
  const lineRange = getLineRange(value, selection);
  const selectedLines = value.slice(lineRange.start, lineRange.end).split('\n');
  const transformedLines = selectedLines.map((line, index) => `${getPrefix(index)}${line}`);
  const insertedText = transformedLines.join('\n');

  return replaceSelection(
    value,
    lineRange,
    insertedText,
    lineRange.start,
    lineRange.start + insertedText.length,
  );
};

const getBlockSpacing = (value: string, selection: EditorSelection) => {
  const beforeText = value.slice(0, selection.start);
  const afterText = value.slice(selection.end);

  const prefix =
    beforeText.length === 0
      ? ''
      : beforeText.endsWith('\n\n')
        ? ''
        : beforeText.endsWith('\n')
          ? '\n'
          : '\n\n';
  const suffix =
    afterText.length === 0
      ? ''
      : afterText.startsWith('\n\n')
        ? ''
        : afterText.startsWith('\n')
          ? '\n'
          : '\n\n';

  return { prefix, suffix };
};

const insertStandaloneSnippet = (
  value: string,
  selection: EditorSelection,
  snippet: string,
  cursorOffsetStart: number,
  cursorOffsetEnd: number = cursorOffsetStart,
): EditorResult => {
  const { prefix, suffix } = getBlockSpacing(value, selection);
  const insertedText = `${prefix}${snippet}${suffix}`;

  return replaceSelection(
    value,
    selection,
    insertedText,
    selection.start + prefix.length + cursorOffsetStart,
    selection.start + prefix.length + cursorOffsetEnd,
  );
};

const insertLink = (value: string, selection: EditorSelection): EditorResult => {
  const selectedText = value.slice(selection.start, selection.end);
  const linkText = selectedText || 'link text';
  const url = 'https://example.com';
  const insertedText = `[${linkText}](${url})`;
  const urlStart = selection.start + linkText.length + 3;
  const textStart = selection.start + 1;

  return replaceSelection(
    value,
    selection,
    insertedText,
    selectedText ? urlStart : textStart,
    selectedText ? urlStart + url.length : textStart + linkText.length,
  );
};

const insertTableTemplate = (value: string, selection: EditorSelection): EditorResult =>
  insertStandaloneSnippet(
    value,
    selection,
    '| Column | Value |\n| --- | --- |\n| Item | Data |',
    2,
    8,
  );

type ToolbarAction = {
  icon: LucideIcon;
  label: string;
  onSelect: (value: string, selection: EditorSelection) => EditorResult;
};

const TOOLBAR_ACTIONS: ToolbarAction[] = [
  {
    icon: Heading2,
    label: 'Heading 2',
    onSelect: (value, selection) => prefixLines(value, selection, () => '## '),
  },
  {
    icon: Heading3,
    label: 'Heading 3',
    onSelect: (value, selection) => prefixLines(value, selection, () => '### '),
  },
  {
    icon: Bold,
    label: 'Bold',
    onSelect: (value, selection) => wrapSelection(value, selection, '**', '**', 'bold text'),
  },
  {
    icon: Italic,
    label: 'Italic',
    onSelect: (value, selection) => wrapSelection(value, selection, '*', '*', 'italic text'),
  },
  {
    icon: Link2,
    label: 'Link',
    onSelect: insertLink,
  },
  {
    icon: List,
    label: 'Bulleted list',
    onSelect: (value, selection) => prefixLines(value, selection, () => '- '),
  },
  {
    icon: ListOrdered,
    label: 'Numbered list',
    onSelect: (value, selection) => prefixLines(value, selection, (index) => `${index + 1}. `),
  },
  {
    icon: ListTodo,
    label: 'Task list',
    onSelect: (value, selection) => prefixLines(value, selection, () => '- [ ] '),
  },
  {
    icon: Quote,
    label: 'Block quote',
    onSelect: (value, selection) => prefixLines(value, selection, () => '> '),
  },
  {
    icon: Code,
    label: 'Inline code',
    onSelect: (value, selection) => wrapSelection(value, selection, '`', '`', 'code'),
  },
  {
    icon: SquareCode,
    label: 'Code block',
    onSelect: (value, selection) =>
      insertStandaloneSnippet(value, selection, '```\n\n```', 4),
  },
  {
    icon: Minus,
    label: 'Horizontal rule',
    onSelect: (value, selection) => insertStandaloneSnippet(value, selection, '---', 0, 3),
  },
  {
    icon: Table2,
    label: 'Table',
    onSelect: insertTableTemplate,
  },
];

export const MarkdownEditorField = ({
  label,
  value,
  onChange,
  placeholder,
  className,
  minHeightClassName = 'min-h-[120px]',
}: MarkdownEditorFieldProps) => {
  const [mode, setMode] = useState<'write' | 'preview'>('write');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const applyResult = (result: EditorResult) => {
    onChange(result.nextValue);

    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) {
        return;
      }

      textarea.focus();
      textarea.setSelectionRange(result.selectionStart, result.selectionEnd);
    });
  };

  return (
    <div className={className}>
      <div className="mb-1 flex items-center justify-between gap-3">
        <Label className="block text-xs text-muted-foreground">{label}</Label>
        <span className="text-xs text-muted-foreground">
          Markdown supported: headings, lists, links, code.
        </span>
      </div>
      <Tabs value={mode} onValueChange={(nextValue) => setMode(nextValue as 'write' | 'preview')}>
        <TabsList className="h-8">
          <TabsTrigger value="write" className="px-2 py-1 text-xs">
            Write
          </TabsTrigger>
          <TabsTrigger value="preview" className="px-2 py-1 text-xs">
            Preview
          </TabsTrigger>
        </TabsList>
        <TabsContent value="write" className="mt-2">
          <TooltipProvider delayDuration={150}>
            <div className="mb-2 flex flex-wrap items-center gap-1 rounded-md border bg-muted/20 p-1">
              {TOOLBAR_ACTIONS.map(({ icon: Icon, label: actionLabel, onSelect }) => (
                <Tooltip key={actionLabel}>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={actionLabel}
                      className="h-8 w-8 shrink-0"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        const textarea = textareaRef.current;
                        if (!textarea) {
                          return;
                        }

                        applyResult(onSelect(value, getSelection(textarea)));
                      }}
                    >
                      <Icon className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{actionLabel}</TooltipContent>
                </Tooltip>
              ))}

              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Markdown help"
                    className="ml-auto h-8 w-8 shrink-0"
                    onMouseDown={(event) => event.preventDefault()}
                  >
                    <CircleHelp className="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-80 space-y-3">
                  <div>
                    <h4 className="text-sm font-semibold">Markdown examples</h4>
                    <p className="text-xs text-muted-foreground">
                      Toolbar inserts GitHub-flavored markdown.
                    </p>
                  </div>
                  <div className="space-y-2">
                    {HELP_EXAMPLES.map((item) => (
                      <div key={item.label} className="space-y-1">
                        <p className="text-xs font-medium text-foreground">{item.label}</p>
                        <pre className="overflow-x-auto rounded-md bg-muted px-2 py-1 text-[11px] leading-4 text-muted-foreground">
                          {item.example}
                        </pre>
                      </div>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </TooltipProvider>

          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            className={cn(minHeightClassName)}
          />
        </TabsContent>
        <TabsContent value="preview" className="mt-2">
          <MarkdownContent
            content={value}
            placeholder={MARKDOWN_PREVIEW_EMPTY_STATE}
            className={minHeightClassName}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
};
