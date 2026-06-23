import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  CodeToggle,
  CreateLink,
  diffSourcePlugin,
  DiffSourceToggleWrapper,
  headingsPlugin,
  InsertTable,
  InsertThematicBreak,
  linkDialogPlugin,
  linkPlugin,
  listsPlugin,
  ListsToggle,
  markdownShortcutPlugin,
  MDXEditor,
  type MDXEditorMethods,
  quotePlugin,
  tablePlugin,
  thematicBreakPlugin,
  toolbarPlugin,
  UndoRedo,
} from '@mdxeditor/editor';
import { useEffect, useRef, useState } from 'react';

import { MarkdownContent } from '@/components/shared/MarkdownContent';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

interface MarkdownEditorFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  minHeightClassName?: string;
}

const MARKDOWN_PREVIEW_EMPTY_STATE = 'Nothing to preview yet.';

const MarkdownEditorToolbar = () => (
  <DiffSourceToggleWrapper options={['rich-text', 'source']}>
    <UndoRedo />
    <BlockTypeSelect />
    <BoldItalicUnderlineToggles />
    <CodeToggle />
    <ListsToggle options={['bullet', 'number', 'check']} />
    <CreateLink />
    <InsertTable />
    <InsertThematicBreak />
  </DiffSourceToggleWrapper>
);

const createEditorPlugins = () => [
  headingsPlugin(),
  listsPlugin(),
  quotePlugin(),
  thematicBreakPlugin(),
  markdownShortcutPlugin(),
  linkPlugin(),
  linkDialogPlugin(),
  tablePlugin(),
  diffSourcePlugin({ viewMode: 'rich-text' }),
  toolbarPlugin({
    toolbarClassName: 'sb-mdxeditor-toolbar',
    toolbarContents: () => <MarkdownEditorToolbar />,
  }),
];

const createInitialPlugins = () => createEditorPlugins();

export const MarkdownEditorField = ({
  label,
  value,
  onChange,
  placeholder,
  className,
  minHeightClassName = 'min-h-[120px]',
}: MarkdownEditorFieldProps) => {
  const editorRef = useRef<MDXEditorMethods | null>(null);
  const lastMarkdownRef = useRef(value);
  const [plugins] = useState(createInitialPlugins);
  const [mode, setMode] = useState<'edit' | 'preview'>('edit');

  useEffect(() => {
    if (value === lastMarkdownRef.current) {
      return;
    }

    editorRef.current?.setMarkdown(value);
    lastMarkdownRef.current = value;
  }, [value]);

  return (
    <div className={className}>
      <div className="mb-1 flex items-center justify-between gap-3">
        <Label className="block text-xs text-muted-foreground">{label}</Label>
        <span className="text-xs text-muted-foreground">
          Rich text editor with markdown source mode.
        </span>
      </div>

      <Tabs value={mode} onValueChange={(nextValue) => setMode(nextValue as 'edit' | 'preview')}>
        <TabsList className="h-8">
          <TabsTrigger value="edit" className="px-2 py-1 text-xs">
            Edit
          </TabsTrigger>
          <TabsTrigger value="preview" className="px-2 py-1 text-xs">
            Preview
          </TabsTrigger>
        </TabsList>
        <TabsContent value="edit" className="mt-2">
          <div
            className={cn('sb-mdxeditor-shell rounded-md border bg-background', minHeightClassName)}
          >
            <MDXEditor
              ref={editorRef}
              markdown={value}
              placeholder={placeholder}
              className="sb-mdxeditor"
              contentEditableClassName={cn('sb-mdxeditor-content', minHeightClassName)}
              plugins={plugins}
              onChange={(nextMarkdown, initialMarkdownNormalize) => {
                lastMarkdownRef.current = nextMarkdown;

                if (initialMarkdownNormalize && nextMarkdown === value) {
                  return;
                }

                onChange(nextMarkdown);
              }}
            />
          </div>
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
