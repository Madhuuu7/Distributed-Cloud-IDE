import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { errorMessage, projectsApi, workspacesApi } from '../services/api';
import type { Member, Project, Role, WorkspaceDetail } from '../types';
import { Badge, Button, EmptyState, Panel, type Tone } from '../components/ui';

const ROLES: Role[] = ['viewer', 'editor', 'owner'];

const ROLE_TONE: Record<Role, Tone> = {
  viewer: 'neutral',
  editor: 'info',
  owner: 'good'
};

const ROLE_HINT: Record<Role, string> = {
  viewer: 'Can read files and ask the AI, but not write or run code',
  editor: 'Can read, write, run code, and start fix runs',
  owner: 'Everything an editor can do, plus managing members'
};

export default function WorkspaceDetailPage() {
  const { workspaceId } = useParams();
  const navigate = useNavigate();

  const [workspace, setWorkspace] = useState<WorkspaceDetail | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Role>('editor');
  const [message, setMessage] = useState('');

  const load = async () => {
    if (!workspaceId) return;

    try {
      const [detail, memberList, projectList] = await Promise.all([
        workspacesApi.get(workspaceId),
        workspacesApi.members(workspaceId),
        projectsApi.list()
      ]);

      setWorkspace(detail.data);
      setMembers(memberList.data);
      setProjects(projectList.data.filter((p) => p.workspace_id === Number(workspaceId)));
    } catch (error) {
      setMessage(errorMessage(error, 'Could not load the workspace'));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const invite = async () => {
    if (!workspaceId || !inviteEmail.trim()) return;

    setMessage('');

    try {
      await workspacesApi.invite(workspaceId, { email: inviteEmail.trim(), role: inviteRole });
      setInviteEmail('');
      await load();
    } catch (error) {
      // The API distinguishes "no such user" from "already a member"; passing
      // its message through is more useful than a generic failure.
      setMessage(errorMessage(error, 'Could not add that member'));
    }
  };

  const changeRole = async (member: Member, role: Role) => {
    if (!workspaceId) return;

    setMessage('');

    try {
      await workspacesApi.setRole(workspaceId, member.user_id, role);
      await load();
    } catch (error) {
      setMessage(errorMessage(error, 'Could not change that role'));
    }
  };

  const remove = async (member: Member) => {
    if (!workspaceId) return;
    if (!window.confirm(`Remove ${member.email} from this workspace?`)) return;

    setMessage('');

    try {
      await workspacesApi.removeMember(workspaceId, member.user_id);
      await load();
    } catch (error) {
      setMessage(errorMessage(error, 'Could not remove that member'));
    }
  };

  const destroy = async () => {
    if (!workspace) return;
    if (
      !window.confirm(
        `Delete "${workspace.name}"? Its projects are returned to their owners, not deleted.`
      )
    ) {
      return;
    }

    try {
      await workspacesApi.delete(workspace.id);
      navigate('/workspaces', { replace: true });
    } catch (error) {
      setMessage(errorMessage(error, 'Could not delete the workspace'));
    }
  };

  if (!workspace) {
    return <p className="text-sm text-slate-400">{message || 'Loading...'}</p>;
  }

  const isOwner = workspace.role === 'owner';

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-white">{workspace.name}</h1>
            <Badge tone={ROLE_TONE[workspace.role]} title={ROLE_HINT[workspace.role]}>
              you are {workspace.role}
            </Badge>
          </div>

          <p className="mt-1 text-sm text-slate-400">
            {workspace.member_count} member{workspace.member_count === 1 ? '' : 's'} &middot;{' '}
            {workspace.project_count} project{workspace.project_count === 1 ? '' : 's'}
          </p>
        </div>

        {isOwner && (
          <Button variant="danger" onClick={destroy}>
            Delete workspace
          </Button>
        )}
      </header>

      {message && <p className="text-sm text-red-400">{message}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Members"
          actions={
            /* Controls the caller cannot use are hidden rather than shown
               disabled - the API would reject them with a 403 anyway. */
            isOwner ? <span className="text-xs text-slate-600">you can manage roles</span> : null
          }
          bodyClassName=""
        >
          {isOwner && (
            <div className="flex gap-2 border-b border-slate-800 p-4">
              <input
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && invite()}
                placeholder="teammate@example.com"
                className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand-500"
              />

              <select
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value as Role)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-2 text-sm text-slate-300 outline-none focus:border-brand-500"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>

              <Button variant="primary" onClick={invite} disabled={!inviteEmail.trim()}>
                Add
              </Button>
            </div>
          )}

          <ul className="divide-y divide-slate-800">
            {members.map((member) => (
              <li key={member.user_id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-slate-200">
                    {member.full_name || member.email}
                  </p>
                  <p className="truncate text-xs text-slate-600">{member.email}</p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {isOwner ? (
                    <select
                      value={member.role}
                      onChange={(event) => changeRole(member, event.target.value as Role)}
                      title={ROLE_HINT[member.role]}
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300 outline-none focus:border-brand-500"
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Badge tone={ROLE_TONE[member.role]}>{member.role}</Badge>
                  )}

                  {isOwner && (
                    <button
                      onClick={() => remove(member)}
                      title={`Remove ${member.email}`}
                      className="text-slate-600 transition hover:text-red-400"
                    >
                      &times;
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Projects" bodyClassName="">
          {projects.length === 0 ? (
            <EmptyState
              title="No projects shared here yet"
              hint="Create a project from the dashboard and assign it to this workspace."
            />
          ) : (
            <ul className="divide-y divide-slate-800">
              {projects.map((project) => (
                <li key={project.id}>
                  <Link
                    to={`/ide/${project.id}`}
                    className="block px-4 py-3 text-sm text-slate-200 transition hover:bg-slate-800/50"
                  >
                    {project.name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
