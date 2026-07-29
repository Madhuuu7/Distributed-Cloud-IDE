import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 10000
});

export const authApi = {
  login: (payload: { email: string; password: string }) => api.post('/auth/login', payload),
  signup: (payload: { email: string; password: string; full_name?: string }) => api.post('/auth/signup', payload)
};

export const projectsApi = {
  list: () => api.get('/projects'),

  create: (payload: { name: string }) =>
    api.post('/projects', payload),

  delete: (projectId: number) =>
    api.delete(`/projects/${projectId}`)
};

export const filesApi = {
  list: (projectId: string) =>
    api.get(`/projects/${projectId}/files`),

  create: (
    projectId: string,
    payload: { name: string; content?: string }
  ) =>
    api.post(`/projects/${projectId}/files`, payload),

  get: (fileId: number) =>
    api.get(`/projects/file/${fileId}`),

  update: (
    fileId: number,
    payload: { content: string }
  ) =>
    api.put(`/projects/file/${fileId}`, payload)
};

export default api;
