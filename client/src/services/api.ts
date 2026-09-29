import axios, { AxiosError } from 'axios';
import type { ExecutionResult, FileNode, Project, User } from '../types';

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

  create: (payload: { name: string }) => api.post<Project>('/projects', payload),

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
