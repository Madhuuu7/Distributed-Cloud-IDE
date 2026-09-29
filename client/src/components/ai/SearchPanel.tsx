import { useEffect, useRef, useState } from 'react';
import { errorMessage, searchApi } from '../../services/api';
import type { IndexStatus, SearchResult } from '../../types';
import { Badge, Button, EmptyState, Spinner } from '../ui';

type Props = {
  projectId: number;
  onOpenResult: (result: SearchResult) => void;
};

export default function SearchPanel({ projectId, onOpenResult }: Props) {
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState('');

  const pollRef = useRef<number | null>(null);

  const refreshStatus = async () => {
    try {
      const { data } = await searchApi.status(projectId);
      setStatus(data);

      // Indexing is asynchronous, so keep polling while it runs rather than
      // leaving the panel showing "building" forever.
      if (data.status === 'building') {
        pollRef.current = window.setTimeout(refreshStatus, 1000);
      }
    } catch (error) {
      setMessage(errorMessage(error, 'Could not read the index status'));
    }
  };

  useEffect(() => {
    refreshStatus();

    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const reindex = async () => {
    setMessage('');

    try {
      await searchApi.reindex(projectId);
      refreshStatus();
    } catch (error) {
      setMessage(errorMessage(error, 'Could not start indexing'));
    }
  };

  const runSearch = async () => {
    if (!query.trim()) return;

    setSearching(true);
    setMessage('');

    try {
      const { data } = await searchApi.search({ query: query.trim(), project_id: projectId, k: 8 });
      setResults(data.results);

      if (data.results.length === 0) {
        setMessage(`Nothing matched across ${data.searched_chunks} chunks.`);
      }
    } catch (error) {
      setResults([]);
      setMessage(errorMessage(error, 'Search failed'));
    } finally {
      setSearching(false);
    }
  };

  const indexTone =
    status?.status === 'ready' ? (status.stale ? 'warn' : 'good') : status?.status === 'failed' ? 'bad' : 'neutral';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b border-slate-800 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <Badge tone={indexTone}>
              {status ? (status.stale && status.status === 'ready' ? 'stale' : status.status) : '...'}
            </Badge>

            {status?.status === 'ready' && (
              <span className="truncate text-xs text-slate-500">
                {status.chunk_count} chunks &middot; {status.embedding_model}
              </span>
            )}
          </div>

          <Button size="sm" onClick={reindex} disabled={status?.status === 'building'}>
            {status?.status === 'building' ? 'Indexing...' : 'Reindex'}
          </Button>
        </div>

        {/* Staleness is reported rather than silently repaired: reindexing
            costs embedding calls, so the decision stays with the user. */}
        {status?.stale && status.status === 'ready' && (
          <p className="text-xs text-amber-400/80">
            Files changed since this index was built. Reindex for accurate results.
          </p>
        )}

        {status?.error && <p className="text-xs text-red-400">{status.error}</p>}

        <div className="flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && runSearch()}
            placeholder="where do we verify tokens?"
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand-500"
          />

          <Button variant="primary" onClick={runSearch} disabled={searching || !query.trim()}>
            {searching ? '...' : 'Search'}
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {message && <p className="p-4 text-xs text-slate-500">{message}</p>}

        {!message && results.length === 0 ? (
          <EmptyState
            title="Search this project by meaning"
            hint="Results blend keyword matching with vector similarity. Both scores are shown so you can see which one found a hit."
          />
        ) : (
          <ul className="divide-y divide-slate-800">
            {results.map((result, index) => (
              <li key={index}>
                <button
                  onClick={() => onOpenResult(result)}
                  className="w-full px-4 py-3 text-left transition hover:bg-slate-800/50"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-mono text-xs text-brand-300">
                      {result.path}:{result.start_line}-{result.end_line}
                    </span>
                    <span className="shrink-0 text-xs text-slate-500">
                      {result.score.toFixed(2)}
                    </span>
                  </div>

                  {result.symbol && (
                    <p className="mt-0.5 truncate text-xs text-slate-400">{result.symbol}</p>
                  )}

                  <pre className="mt-2 max-h-24 overflow-hidden rounded bg-slate-950 p-2 font-mono text-[11px] leading-relaxed text-slate-400">
                    {result.text}
                  </pre>

                  {/* Exposing both rankers turns "why did that rank first?"
                      from an argument into a lookup. */}
                  <p className="mt-1.5 flex gap-3 text-[11px] text-slate-600">
                    <span>keyword {result.keyword_score.toFixed(2)}</span>
                    <span>vector {result.vector_score.toFixed(2)}</span>
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}

        {searching && (
          <div className="p-4">
            <Spinner label="Searching..." />
          </div>
        )}
      </div>
    </div>
  );
}
