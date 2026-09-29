import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();

  const handleSignOut = () => {
    signOut();
    navigate('/login', { replace: true });
  };

  const isDashboard = location.pathname.startsWith('/dashboard');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <Link to="/dashboard" className="text-xl font-semibold tracking-wide text-white">
            Distributed Cloud IDE
          </Link>

          <nav className="flex items-center gap-3">
            <Link
              to="/dashboard"
              className={`rounded px-3 py-2 text-sm transition ${
                isDashboard ? 'bg-brand-500 text-white' : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              Dashboard
            </Link>

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
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
