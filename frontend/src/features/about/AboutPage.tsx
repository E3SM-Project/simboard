import { ExternalLink } from 'lucide-react';

const resources = [
  {
    label: 'User Documentation',
    href: 'https://simboard.readthedocs.io/en/latest/user/',
    description: 'Guides and references for using SimBoard.',
  },
  {
    label: 'Ingestion Coverage',
    href: 'https://simboard.readthedocs.io/en/latest/user/ingestion-coverage/',
    description: 'Supported HPC environments and catalog ingestion coverage.',
  },
];

export const AboutPage = () => (
  <main className="mx-auto min-h-[70vh] w-full max-w-5xl space-y-10 px-6 py-10">
    <section className="space-y-4">
      <h1 className="text-4xl font-bold tracking-tight">About SimBoard</h1>
      <p className="max-w-3xl text-lg leading-8 text-muted-foreground">
        SimBoard is a public interface for discovering, comparing, and sharing cataloged E3SM
        simulations. It helps E3SM users move from a case overview to the execution context and
        detailed records behind it.
      </p>
    </section>
    <section className="rounded-2xl border border-muted bg-white p-6 shadow-sm">
      <h2 className="text-2xl font-semibold">What you can do</h2>
      <ul className="mt-4 list-disc space-y-2 pl-5 leading-7 text-muted-foreground">
        <li>Discover cases and refine the catalog by machine, user, and execution context.</li>
        <li>Inspect grouped executions, metadata, artifacts, and linked resources.</li>
        <li>Compare selected executions and share direct links with collaborators.</li>
      </ul>
    </section>
    <section className="rounded-2xl border border-blue-200 bg-blue-50/70 p-6 text-blue-950">
      <h2 className="text-2xl font-semibold">How catalog data arrives</h2>
      <p className="mt-3 leading-7 text-blue-900">
        SimBoard automatically ingests performance archives from supported HPC environments. Current
        data is collected regularly, while historical archives are scanned daily.
      </p>
    </section>
    <section>
      <h2 className="text-2xl font-semibold">Resources</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {resources.map((resource) => (
          <a
            key={resource.href}
            href={resource.href}
            target="_blank"
            rel="noreferrer"
            className="rounded-xl border border-muted bg-white p-5 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
          >
            <span className="flex items-center gap-2 font-semibold">
              <ExternalLink className="h-4 w-4" />
              {resource.label}
            </span>
            <span className="mt-2 block text-sm leading-6 text-muted-foreground">
              {resource.description}
            </span>
          </a>
        ))}
      </div>
    </section>
  </main>
);
