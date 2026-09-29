import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import AuthCard from '../components/auth/AuthCard';
import { useAuth } from '../hooks/useAuth';
import { authApi, errorMessage } from '../services/api';

const MIN_PASSWORD_LENGTH = 8;

export default function SignupPage() {
  const navigate = useNavigate();
  const { signIn, status } = useAuth();

  const [fullName, setFullName] = useState('');
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

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setSubmitting(true);

    try {
      const { data } = await authApi.signup({
        full_name: fullName || undefined,
        email,
        password
      });

      await signIn(data.access_token);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Could not create your account'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Create your account" subtitle="Start building in the cloud">
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="Full name"
          autoComplete="name"
          className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
        />

        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Email"
          autoComplete="email"
          required
          className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
        />

        <div>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
          />
          <p className="mt-1 text-xs text-slate-500">
            At least {MIN_PASSWORD_LENGTH} characters.
          </p>
        </div>

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
          {submitting ? 'Creating account...' : 'Create account'}
        </button>

        <p className="text-center text-sm text-slate-400">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-400 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
