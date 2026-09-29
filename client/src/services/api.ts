import axios, { AxiosError } from 'axios';
import type {
  ChatResponse,
  Citation,
  ExecutionResult,
  ExplainResponse,
  FileNode,
  FixRun,
  FixRunDetail,
  IndexStatus,
  Member,
  Project,
  Provider,
  ReviewResponse,
  Role,
  SearchResponse,
  UsageResponse,
  User,
  Workspace,
  WorkspaceDetail
} from '../types';

const TOKEN_KEY = 'token';

// Endpoints where a 401 means "wrong password", not "session expired".
const PUBLIC_PATHS = ['/auth/login', '/auth/signup'];

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

let onUnauthorized: (() => void) | null = null;

/** Lets AuthProvider react to an expired token without a full page reload. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000
});

api.interceptors.request.use((config) => {
  const token = getToken();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const path = error.config?.url ?? '';
    const isPublic = PUBLIC_PATHS.some((publicPath) => path.startsWith(publicPath));

    if (error.response?.status === 401 && !isPublic) {
      clearToken();
      onUnauthorized?.();
    }

    return Promise.reject(error);
  }
);

/** Pulls a readable message out of a FastAPI error response. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    // Pydantic validation errors arrive as an array of objects.
    if (Array.isArray(detail) && detail.length > 0) {
      return detail[0]?.msg ?? fallback;
    }

    if (!error.response) {
      return 'Cannot reach the server. Is the backend running?';
    }
  }

  return fallback;
}

export const authApi = {
  login: (payload: { email: string; password: string }) =>
    api.post<{ access_token: string }>('/auth/login', payload),

  signup: (payload: { email: string; password: string; full_name?: string }) =>
    api.post<{ access_token: string }>('/auth/signup', payload),

  me: () => api.get<User>('/auth/me')
};

export const projectsApi = {
  list: () => api.get<Project[]>('/projects'),

  create: (payload: { name: string; workspace_id?: number | null }) =>
    api.post<Project>('/projects', payload),

  get: (projectId: string | number) => api.get<Project>(`/projects/${projectId}`),

  delete: (projectId: number) => api.delete(`/projects/${projectId}`)
};

export const filesApi = {
  list: (projectId: string | number) => api.get<FileNode[]>(`/projects/${projectId}/files`),

  create: (projectId: string | number, payload: { name: string; content?: string }) =>
    api.post<FileNode>(`/projects/${projectId}/files`, payload),

  get: (fileId: number) => api.get<FileNode>(`/projects/file/${fileId}`),

  update: (fileId: number, payload: { content: string }) =>
    api.put<FileNode>(`/projects/file/${fileId}`, payload),

  delete: (fileId: number) => api.delete(`/projects/file/${fileId}`)
};

export const executeApi = {
  languages: () => api.get<{ languages: string[] }>('/execute/languages'),

  run: (payload: { language: string; code: string }) =>
    api.post<ExecutionResult>('/execute', payload)
};

export default api;

export const workspacesApi = {
  list: () => api.get<Workspace[]>('/workspaces'),

  create: (payload: { name: string; description?: string }) =>
    api.post<WorkspaceDetail>('/workspaces', payload),

  get: (workspaceId: string | number) =>
    api.get<WorkspaceDetail>(`/workspaces/${workspaceId}`),

  delete: (workspaceId: number) => api.delete(`/workspaces/${workspaceId}`),

  members: (workspaceId: string | number) =>
    api.get<Member[]>(`/workspaces/${workspaceId}/members`),

  invite: (workspaceId: string | number, payload: { email: string; role: Role }) =>
    api.post<Member>(`/workspaces/${workspaceId}/members`, payload),

  setRole: (workspaceId: string | number, userId: number, role: Role) =>
    api.patch<Member>(`/workspaces/${workspaceId}/members/${userId}`, { role }),

  removeMember: (workspaceId: string | number, userId: number) =>
    api.delete(`/workspaces/${workspaceId}/members/${userId}`)
};

export const aiApi = {
  providers: () => api.get<Provider[]>('/ai/providers'),

  chat: (payload: {
    message: string;
    conversation_id?: number | null;
    project_id?: number | null;
    use_rag?: boolean;
  }) => api.post<ChatResponse>('/ai/chat', payload),

  explain: (payload: { file_id: number; start_line?: number; end_line?: number }) =>
    api.post<ExplainResponse>('/ai/explain', payload),

  review: (payload: { project_id: number; file_ids?: number[] }) =>
    api.post<ReviewResponse>('/ai/review', payload),

  usage: (days = 30) => api.get<UsageResponse>(`/ai/usage?days=${days}`)
};

export const searchApi = {
  status: (projectId: string | number) =>
    api.get<IndexStatus>(`/projects/${projectId}/index`),

  reindex: (projectId: string | number) =>
    api.post<IndexStatus>(`/projects/${projectId}/index`),

  search: (payload: { query: string; project_id: number; k?: number }) =>
    api.post<SearchResponse>('/search', payload)
};

export const fixApi = {
  list: (projectId: string | number) =>
    api.get<FixRun[]>(`/fix-runs?project_id=${projectId}`),

  create: (payload: {
    project_id: number;
    instruction: string;
    test_command?: string | null;
    max_iterations?: number;
  }) => api.post<FixRun>('/fix-runs', payload),

  get: (runId: number) => api.get<FixRunDetail>(`/fix-runs/${runId}`),

  apply: (runId: number) =>
    api.post<{ run_id: number; applied_paths: string[]; message: string }>(
      `/fix-runs/${runId}/apply`
    ),

  cancel: (runId: number) => api.post<FixRun>(`/fix-runs/${runId}/cancel`)
};

type StreamHandlers = {
  onCitations?: (citations: Citation[], conversationId: number) => void;
  onToken?: (text: string) => void;
  onDone?: (conversationId: number) => void;
  onError?: (detail: string) => void;
};

/**
 * Stream a chat reply over Server-Sent Events.
 *
 * Not `EventSource`: that only issues GET requests and cannot send a body or
 * an Authorization header, and this endpoint needs both. `fetch` with a
 * ReadableStream is the way to consume SSE from a POST.
 *
 * Returns an abort function so a component can cancel the stream on unmount -
 * without it, a token callback fires against a component that no longer
 * exists.
 */
export function streamChat(
  payload: { message: string; conversation_id?: number | null; project_id?: number | null },
  handlers: StreamHandlers
): () => void {
  const controller = new AbortController();
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  (async () => {
    try {
      const response = await fetch(`${baseUrl}/ai/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken() ?? ''}`
        },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      if (!response.ok || !response.body) {
        handlers.onError?.(`The assistant returned ${response.status}.`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      for (;;) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line. A frame can arrive split
        // across chunks, so anything after the last separator stays buffered
        // until the rest of it turns up.
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          const eventLine = frame.split('\n').find((line) => line.startsWith('event:'));
          const dataLine = frame.split('\n').find((line) => line.startsWith('data:'));

          if (!eventLine || !dataLine) continue;

          const event = eventLine.slice(6).trim();
          const data = JSON.parse(dataLine.slice(5).trim());

          if (event === 'citations') {
            handlers.onCitations?.(data.citations, data.conversation_id);
          } else if (event === 'token') {
            handlers.onToken?.(data.text);
          } else if (event === 'done') {
            handlers.onDone?.(data.conversation_id);
          } else if (event === 'error') {
            handlers.onError?.(data.detail);
          }
        }
      }
    } catch (error) {
      // An abort is the caller's own doing, not a failure to report.
      if ((error as Error)?.name !== 'AbortError') {
        handlers.onError?.('Lost the connection to the assistant.');
      }
    }
  })();

  return () => controller.abort();
}
