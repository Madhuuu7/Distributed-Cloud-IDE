import { Link } from 'react-router-dom';
import AuthCard from '../components/auth/AuthCard';

export default function LoginPage() {
  return (
    <AuthCard title="Welcome back" subtitle="Sign in to continue your workspace">
      <form className="space-y-4">
        <div>
          <label className="mb-2 block text-sm text-slate-300">Email</label>
          <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none ring-0" placeholder="you@example.com" />
        </div>
        <div>
          <label className="mb-2 block text-sm text-slate-300">Password</label>
          <input type="password" className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none ring-0" placeholder="••••••••" />
        </div>
        <button type="button" className="w-full rounded-lg bg-brand-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-700">
          Sign in
        </button>
      </form>

      <p className="mt-6 text-sm text-slate-400">
        New here?{' '}
        <Link to="/signup" className="font-medium text-brand-400">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
