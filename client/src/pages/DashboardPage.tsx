const projects = [
  { name: 'Portfolio App', language: 'TypeScript', updated: '2h ago' },
  { name: 'API Service', language: 'Python', updated: 'Today' },
  { name: 'ML Notebook', language: 'JavaScript', updated: 'Yesterday' }
];

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6">
        <p className="text-sm uppercase tracking-[0.3em] text-brand-400">Overview</p>
        <h1 className="mt-3 text-3xl font-semibold text-white">Your cloud workspace is ready</h1>
        <p className="mt-3 max-w-2xl text-sm text-slate-400">
          Start by opening an IDE workspace, editing files, and running code from the built-in environment.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {projects.map((project) => (
          <div key={project.name} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <p className="text-sm text-slate-400">Project</p>
            <h2 className="mt-2 text-lg font-semibold text-white">{project.name}</h2>
            <p className="mt-2 text-sm text-slate-500">Language: {project.language}</p>
            <p className="mt-4 text-sm text-brand-400">Updated {project.updated}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
