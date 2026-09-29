export type User = {
  id: number;
  email: string;
  full_name?: string | null;
  created_at: string;
};

export type Project = {
  id: number;
  name: string;
  owner_id: number;
};

export type FileNode = {
  id: number;
  project_id: number;
  name: string;
  path: string;
  content: string;
  language: string;
};

export type ExecutionResult = {
  stdout: string;
  stderr: string;
  exit_code: number | null;
  duration_ms: number;
  timed_out: boolean;
  backend: string;
};
