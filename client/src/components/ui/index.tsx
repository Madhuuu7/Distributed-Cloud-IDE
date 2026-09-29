/**
 * Small shared primitives.
 *
 * The AI, search, and fix-run views repeat the same panel-and-button shapes
 * enough that inlining the Tailwind classes in each one drifts within a day.
 * These exist so a change to the surface style happens in one place.
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react';

type PanelProps = {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
};

export function Panel({ title, actions, children, className = '', bodyClassName = 'p-4' }: PanelProps) {
  return (
    <section
      className={`flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 ${className}`}
    >
      {(title || actions) && (
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
          <h2 className="truncate text-sm font-semibold text-white">{title}</h2>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}

      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
};

const VARIANTS = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600',
  ghost: 'border border-slate-700 text-slate-200 hover:border-slate-500',
  danger: 'border border-red-900/60 text-red-300 hover:border-red-600 hover:text-red-200'
};

export function Button({
  variant = 'ghost',
  size = 'md',
  className = '',
  ...props
}: ButtonProps) {
  const padding = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-2 text-sm';

  return (
    <button
      {...props}
      className={`rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${padding} ${VARIANTS[variant]} ${className}`}
    />
  );
}

const TONES = {
  neutral: 'bg-slate-800 text-slate-300',
  good: 'bg-emerald-500/15 text-emerald-300',
  warn: 'bg-amber-500/15 text-amber-300',
  bad: 'bg-red-500/15 text-red-300',
  info: 'bg-brand-500/20 text-brand-200'
};

export type Tone = keyof typeof TONES;

export function Badge({
  tone = 'neutral',
  children,
  title
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      <p className="text-sm text-slate-400">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-600">{hint}</p>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-500">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-600 border-t-brand-400" />
      {label}
    </span>
  );
}

/** Formats a cost that is usually a fraction of a cent without showing "$0.00". */
export function formatCost(usd: number): string {
  if (usd === 0) return 'free';
  if (usd < 0.01) return `<$0.01`;

  return `$${usd.toFixed(2)}`;
}
