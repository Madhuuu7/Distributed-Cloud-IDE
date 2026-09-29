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
  workspace_id: number | null;
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

// --- Workspaces -------------------------------------------------------------

/** Ordered by privilege; `roleAtLeast` in `lib/roles.ts` depends on the order. */
export type Role = 'viewer' | 'editor' | 'owner';

export type Workspace = {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
};

export type WorkspaceDetail = Workspace & {
  /** The caller's own role, so the UI can hide controls they cannot use. */
  role: Role;
  member_count: number;
  project_count: number;
};

export type Member = {
  user_id: number;
  email: string;
  full_name: string | null;
  role: Role;
  joined_at: string;
};

// --- AI ---------------------------------------------------------------------

export type Provider = {
  name: string;
  model: string;
  configured: boolean;
  active: boolean;
  embedding_active: boolean;
  embedding_dimensions: number;
  price_per_mtok: { prompt: number; completion: number };
};

/** Where an answer came from, so a claim can be checked against the code. */
export type Citation = {
  path: string;
  symbol: string | null;
  start_line: number;
  end_line: number;
  score: number;
};

export type ChatResponse = {
  conversation_id: number;
  message: string;
  citations: Citation[];
  provider: string;
  model: string;
  cached: boolean;
  tokens: number;
  cost_usd: number;
  latency_ms: number;
};

export type ChatTurn = {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  /** Set while an assistant turn is still streaming in. */
  pending?: boolean;
  cached?: boolean;
};

export type Severity = 'info' | 'minor' | 'major' | 'critical';

export type Finding = {
  path: string;
  line: number;
  severity: Severity;
  message: string;
  suggestion: string | null;
};

export type ReviewResponse = {
  findings: Finding[];
  files_reviewed: number;
  cached: boolean;
  cost_usd: number;
};

export type ExplainResponse = {
  explanation: string;
  path: string;
  start_line: number;
  end_line: number;
  cached: boolean;
  cost_usd: number;
};

export type UsageResponse = {
  days: number;
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  cache_hit_rate: number;
  estimated_savings_usd: number;
  by_day: { day: string; calls: number; tokens: number; cost_usd: number }[];
  by_feature: { feature: string; calls: number; tokens: number; cost_usd: number }[];
};

// --- Retrieval --------------------------------------------------------------

export type IndexStatus = {
  project_id: number;
  status: 'empty' | 'building' | 'ready' | 'failed';
  chunk_count: number;
  embedding_model: string | null;
  dimensions: number | null;
  indexed_at: string | null;
  /** True when files changed after the index was built. */
  stale: boolean;
  error: string | null;
};

export type SearchResult = {
  path: string;
  symbol: string | null;
  language: string;
  start_line: number;
  end_line: number;
  text: string;
  score: number;
  /** Both rankers are surfaced so a surprising result can be explained. */
  keyword_score: number;
  vector_score: number;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
  searched_chunks: number;
};

// --- Agentic fix runs -------------------------------------------------------

export type FixStatus =
  | 'queued'
  | 'running'
  | 'awaiting_approval'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export type FixIteration = {
  iteration: number;
  reasoning: string | null;
  stdout: string | null;
  stderr: string | null;
  exit_code: number | null;
  passed: boolean;
  created_at: string;
};

export type FixRun = {
  id: number;
  project_id: number;
  instruction: string;
  test_command: string | null;
  status: FixStatus;
  max_iterations: number;
  summary: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type FixRunDetail = FixRun & {
  iterations: FixIteration[];
  /** Derived server-side from before/after file contents. */
  diff: string | null;
};
