import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { aiApi } from '../../services/api';
import type { Provider } from '../../types';

const NAV = [
  { to: '/dashboard', label: 'Projects' },
  { to: '/workspaces', label: 'Workspaces' },
  { to: '/usage', label: 'Usage' }
];

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();

  const [provider, setProvider] = useState<Provider | null>(null);

  useEffect(() => {
    // Which model is answering is worth knowing at all times: an assistant
    // running on the mock provider gives plausible-looking output that means
    // nothing, and that is very easy to forget mid-demo.
    aiApi
      .providers()
      .then(({ data }) => setProvider(data.find((item) => item.active) ?? null))
      .catch(() => setProvider(null));
  }, []);

  const handleSignOut = () => {
    signOut();
    navigate('/login', { replace: true });
  };

  // The IDE needs the full viewport, so it opts out of the centred page width.
  const isIDE = location.pathname.startsWith('/ide/');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur">
        <div
          className={`flex items-center justify-between gap-4 px-6 py-4 ${
            isIDE ? '' : 'mx-auto max-w-7xl'
          }`}
        >
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="text-lg font-semibold tracking-wide text-white">
              AI Collab Platform
            </Link>

            <nav className="flex items-center gap-1">
              {NAV.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`rounded px-3 py-2 text-sm transition ${
                    location.pathname.startsWith(item.to)
                      ? 'bg-brand-500 text-white'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {provider && (
              <span
                title={
                  provider.name === 'mock'
                    ? 'Responses are generated locally and cost nothing. Set AI_PROVIDER for real output.'
                    : `Answers come from ${provider.model}`
                }
                className={`hidden rounded-full px-2.5 py-1 text-xs font-medium sm:inline ${
                  provider.name === 'mock'
                    ? 'bg-amber-500/15 text-amber-300'
                    : 'bg-emerald-500/15 text-emerald-300'
                }`}
              >
                {provider.name === 'mock' ? 'mock AI' : provider.model}
              </span>
            )}

            {user && (
              <span className="hidden text-sm text-slate-400 sm:inline" title={user.email}>
                {user.full_name || user.email}
              </span>
            )}

            <button
              onClick={handleSignOut}
              className="rounded px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className={isIDE ? 'px-6 py-4' : 'mx-auto max-w-7xl px-6 py-8'}>
        <Outlet />
      </main>
    </div>
  );
}
