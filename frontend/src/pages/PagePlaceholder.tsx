// Shared shell for routes whose feature UI hasn't been implemented yet by its
// story (E10/E11). Each page below renders this with its own story id/title
// until the corresponding generator agent replaces the body with the real
// feature component from src/features/.

interface PagePlaceholderProps {
  storyId: string;
  title: string;
}

export function PagePlaceholder({ storyId, title }: PagePlaceholderProps) {
  return (
    <div className="mx-auto max-w-3xl p-8">
      <span className="inline-block rounded bg-navy-950 px-2 py-1 font-mono text-xs text-amber-400">
        {storyId}
      </span>
      <h1 className="mt-3 text-xl font-semibold text-navy-950">{title}</h1>
      <p className="mt-2 text-sm text-slate-700">
        This page is scaffolded and routed but its feature UI has not been
        built yet.
      </p>
    </div>
  );
}
