/**
 * Renders a unified diff with the usual colouring.
 *
 * The diff is computed on the server from the before and after file contents,
 * so this only has to display it - it never has to cope with a malformed diff
 * a model emitted.
 */
export default function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n');

  return (
    <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-[11px] leading-relaxed">
      {lines.map((line, index) => {
        // Order matters: `+++` and `---` are file headers, not additions and
        // removals, so they have to be matched before the single-character
        // prefixes.
        let className = 'text-slate-500';

        if (line.startsWith('+++') || line.startsWith('---')) {
          className = 'text-slate-400 font-semibold';
        } else if (line.startsWith('@@')) {
          className = 'text-brand-300';
        } else if (line.startsWith('+')) {
          className = 'bg-emerald-500/10 text-emerald-300';
        } else if (line.startsWith('-')) {
          className = 'bg-red-500/10 text-red-300';
        }

        return (
          <div key={index} className={`${className} whitespace-pre-wrap px-1`}>
            {line || ' '}
          </div>
        );
      })}
    </pre>
  );
}
