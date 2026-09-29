import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { errorMessage, workspacesApi } from '../services/api';
import type { Workspace } from '../types';
import { Button, EmptyState, Panel } from '../components/ui';

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState('');

  const load = async () => {
    try {
      const { data } = await workspacesApi.list();
      setWorkspaces(data);
    } catch (error) {
      setMessage(errorMessage(error, 'Could not load workspaces'));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim()) return;

    setCreating(true);
    setMessage('');

    try {
      await workspacesApi.create({ name: name.trim() });
      setName('');
      await load();
    } catch (error) {
      setMessage(errorMessage(error, 'Could not create the workspace'));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Workspaces</h1>
          <p className="mt-1 text-sm text-slate-400">
            Share projects with a team. You become the owner of anything you create here.
          </p>
        </div>

        <div className="flex gap-2">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && create()}
            placeholder="New workspace name"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand-500"
          />

          <Button variant="primary" onClick={create} disabled={creating || !name.trim()}>
            Create
          </Button>
        </div>
      </header>

      {message && <p className="text-sm text-red-400">{message}</p>}

      {workspaces.length === 0 ? (
        <Panel>
          <EmptyState
            title="No workspaces yet"
            hint="A project with no workspace stays private to you. Create one to share it."
          />
        </Panel>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((workspace) => (
            <Link
              key={workspace.id}
              to={`/workspaces/${workspace.id}`}
              className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 transition hover:border-brand-500"
            >
              <h2 className="truncate text-lg font-semibold text-white">{workspace.name}</h2>

              {workspace.description && (
                <p className="mt-1 line-clamp-2 text-sm text-slate-400">{workspace.description}</p>
              )}

              <p className="mt-4 text-xs text-slate-600">
                Created {new Date(workspace.created_at).toLocaleDateString()}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
