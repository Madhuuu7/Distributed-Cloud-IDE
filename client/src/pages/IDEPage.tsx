import { useEffect, useRef } from 'react';
import * as monaco from 'monaco-editor';

export default function IDEPage() {
  const editorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!editorRef.current) return;

    const editor = monaco.editor.create(editorRef.current, {
      value: 'console.log("Hello from Distributed Cloud IDE")',
      language: 'javascript',
      theme: 'vs-dark',
      automaticLayout: true
    });

    return () => editor.dispose();
  }, []);

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
        <h2 className="text-lg font-semibold text-white">Explorer</h2>
        <ul className="mt-4 space-y-2 text-sm text-slate-400">
          <li className="rounded bg-slate-800 px-3 py-2">src/main.ts</li>
          <li className="rounded px-3 py-2 hover:bg-slate-800">src/app.ts</li>
          <li className="rounded px-3 py-2 hover:bg-slate-800">README.md</li>
        </ul>
      </aside>

      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80">
        <div className="border-b border-slate-800 px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-white">main.ts</p>
              <p className="text-xs text-slate-500">JavaScript • Unsaved changes</p>
            </div>
            <button className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white">
              Run Code
            </button>
          </div>
        </div>
        <div ref={editorRef} className="h-[560px]" />
      </section>
    </div>
  );
}
