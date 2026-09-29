import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { errorMessage, projectsApi, workspacesApi } from '../services/api';
import type { Project, Workspace } from '../types';
import { Badge } from '../components/ui';

export default function DashboardPage() {
  const navigate = useNavigate();

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectName, setProjectName] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  // Empty string means "keep it private to me" - the API takes null for that.
  const [workspaceId, setWorkspaceId] = useState('');

  const loadProjects = async () => {
    try {
      const { data } = await projectsApi.list();
      setProjects(data);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'Could not load your projects'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();

    // A failure here is not worth an error banner: without the list the
    // selector just offers "private", which is the default anyway.
    workspacesApi
      .list()
      .then((response) => setWorkspaces(response.data))
      .catch(() => setWorkspaces([]));
  }, []);

  const createProject = async (event: FormEvent) => {
    event.preventDefault();

    const name = projectName.trim();

    if (!name) return;

    setCreating(true);

    try {
      await projectsApi.create({
        name,
        workspace_id: workspaceId ? Number(workspaceId) : null
      });
      setProjectName('');
      await loadProjects();
    } catch (err) {
      setError(errorMessage(err, 'Could not create the project'));
    } finally {
      setCreating(false);
    }
  };

  const deleteProject = async (project: Project) => {
    if (!window.confirm(`Delete "${project.name}" and all of its files?`)) {
      return;
    }

    try {
      await projectsApi.delete(project.id);
      await loadProjects();
    } catch (err) {
      setError(errorMessage(err, 'Could not delete the project'));
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6">
        <h1 className="text-3xl font-bold text-white">Your projects</h1>

        <p className="mt-2 text-slate-400">
          Each project is an isolated workspace. Code runs in a throwaway container.
        </p>

        <form onSubmit={createProject} className="mt-6 flex gap-3">
          <input
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
            placeholder="New project name"
            value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
          />

          {workspaces.length > 0 && (
            <select
              value={workspaceId}
              onChange={(event) => setWorkspaceId(event.target.value)}
              title="Share this project with a workspace, or keep it to yourself"
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-300 focus:border-brand-500 focus:outline-none"
            >
              <option value="">Private to me</option>
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          )}

          <button
            type="submit"
            disabled={creating || !projectName.trim()}
            className="rounded-lg bg-brand-500 px-5 py-2 font-medium text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </form>

        {error && (
          <p role="alert" className="mt-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-400">
            {error}
          </p>
        )}
      </section>

      {loading ? (
        <p className="text-slate-500">Loading projects...</p>
      ) : projects.length === 0 ? (
        <section className="rounded-2xl border border-dashed border-slate-800 p-10 text-center">
          <p className="text-slate-400">No projects yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Create your first one above to open the editor.
          </p>
        </section>
      ) : (
        <section className="grid gap-4 md:grid-cols-3">
          {projects.map((project) => (
            <div
              key={project.id}
              className="flex flex-col rounded-2xl border border-slate-800 bg-slate-900 p-5"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="min-w-0 truncate text-xl font-semibold text-white">
                  {project.name}
                </h2>

                {/* A project's sharing state is the thing most worth knowing at
                    a glance - it decides who else can change it. */}
                {project.workspace_id !== null && (
                  <Badge tone="info" title="Shared with a workspace">
                    shared
                  </Badge>
                )}
              </div>

              <div className="mt-5 flex gap-2">
                <button
                  onClick={() => navigate(`/ide/${project.id}`)}
                  className="rounded bg-brand-500 px-4 py-2 text-white transition hover:bg-brand-600"
                >
                  Open IDE
                </button>

                <button
                  onClick={() => deleteProject(project)}
                  className="rounded border border-slate-700 px-4 py-2 text-slate-300 transition hover:border-red-500/50 hover:text-red-400"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
