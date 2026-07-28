import { ReactNode } from 'react';

type AuthCardProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
};

export default function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl items-center justify-center px-4 py-10">
      <div className="grid w-full overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 shadow-2xl lg:grid-cols-[1.1fr_0.9fr]">
        <div className="hidden bg-gradient-to-br from-brand-500 to-slate-700 p-10 lg:flex lg:flex-col lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.3em] text-slate-200">Portfolio Build</p>
            <h1 className="mt-4 text-3xl font-semibold text-white">Distributed Cloud IDE</h1>
            <p className="mt-4 max-w-md text-sm leading-6 text-slate-200">
              A polished full-stack workspace for editing, running, and collaborating on code in a modern cloud-style experience.
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/10 p-4 text-sm text-slate-100">
            Built with React, FastAPI, SQLAlchemy, Monaco Editor, and JWT authentication.
          </div>
        </div>

        <div className="p-8 sm:p-10">
          <div className="mb-8">
            <h2 className="text-2xl font-semibold text-white">{title}</h2>
            <p className="mt-2 text-sm text-slate-400">{subtitle}</p>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
