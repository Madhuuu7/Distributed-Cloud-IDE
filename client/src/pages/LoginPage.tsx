import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import AuthCard from '../components/auth/AuthCard';
import { useAuth } from '../hooks/useAuth';
import { authApi, errorMessage } from '../services/api';

export default function LoginPage() {
  const navigate = useNavigate();
  const { signIn, status } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated') {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const { data } = await authApi.login({ email, password });
      await signIn(data.access_token);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Invalid email or password'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Welcome back" subtitle="Sign in to your workspace">
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Email"
          autoComplete="email"
          required
          className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
        />

        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          required
          className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
        />

        {error && (
          <p role="alert" className="rounded-lg bg-red-500/10 p-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand-500 p-3 font-medium text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>

        <p className="text-center text-sm text-slate-400">
          Need an account?{' '}
          <Link to="/signup" className="text-brand-400 hover:underline">
            Create one
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
