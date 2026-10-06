import { ExecutionPathCard } from '@/features/catalog/components/ExecutionPathCard';
import type { SourceDirectoryOut } from '@/types';

interface SourceDirectoriesProps {
  directories?: SourceDirectoryOut[];
}

export const SourceDirectories = ({ directories = [] }: SourceDirectoriesProps) => {
  if (directories.length === 0) return null;

  return (
    <section className="min-w-0 space-y-3" aria-label="Performance Source Directories">
      <div className="space-y-1">
        <h3 className="text-lg font-semibold">Performance Source Directories</h3>
        <p className="text-sm text-muted-foreground">
          Original performance-data directories observed during ingestion. These paths may no longer
          exist and are separate from simulation output.
        </p>
      </div>
      {(['staging', 'archive'] as const).map((kind) => {
        const paths = directories.filter((directory) => directory.kind === kind);
        if (paths.length === 0) return null;

        return (
          <ExecutionPathCard
            key={kind}
            kind={kind}
            title={kind === 'staging' ? 'Staging' : 'Archive'}
            paths={paths.map(({ id, path }) => ({ id, url: path, label: path }))}
            emptyText="No source directories available."
          />
        );
      })}
    </section>
  );
};
