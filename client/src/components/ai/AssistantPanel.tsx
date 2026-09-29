import { useEffect, useRef, useState } from 'react';
import { streamChat } from '../../services/api';
import type { ChatTurn, Citation } from '../../types';
import { Badge, Button, EmptyState } from '../ui';

type Props = {
  projectId: number;
  /** Jump the editor to a cited range, so a citation is checkable in one click. */
  onOpenCitation: (citation: Citation) => void;
};

export default function AssistantPanel({ projectId, onOpenCitation }: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);

  const abortRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Cancel an in-flight stream when the panel unmounts. Without this the
  // token callback keeps firing against a component that is gone.
  useEffect(() => () => abortRef.current?.(), []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns]);

  const send = () => {
    const question = draft.trim();

    if (!question || streaming) return;

    setDraft('');
    setStreaming(true);
    setTurns((previous) => [
      ...previous,
      { role: 'user', content: question },
      { role: 'assistant', content: '', pending: true }
    ]);

    /** Rewrite the trailing assistant turn as deltas arrive. */
    const updateLast = (change: Partial<ChatTurn>) => {
      setTurns((previous) => {
        const next = [...previous];
        const last = next[next.length - 1];

        next[next.length - 1] = { ...last, ...change };

        return next;
      });
    };

    abortRef.current = streamChat(
      { message: question, conversation_id: conversationId, project_id: projectId },
      {
        onCitations: (citations, id) => {
          setConversationId(id);
          updateLast({ citations });
        },
        onToken: (text) => {
          setTurns((previous) => {
            const next = [...previous];
            const last = next[next.length - 1];

            next[next.length - 1] = { ...last, content: last.content + text };

            return next;
          });
        },
        onDone: () => {
          updateLast({ pending: false });
          setStreaming(false);
        },
        onError: (detail) => {
          updateLast({ content: detail, pending: false });
          setStreaming(false);
        }
      }
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {turns.length === 0 ? (
          <EmptyState
            title="Ask about this codebase"
            hint="Answers are grounded in the indexed files and cite the lines they used. Click a citation to jump there."
          />
        ) : (
          turns.map((turn, index) => (
            <div key={index} className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {turn.role === 'user' ? 'You' : 'Assistant'}
              </p>

              <div
                className={`rounded-xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
                  turn.role === 'user'
                    ? 'bg-slate-800 text-slate-100'
                    : 'bg-slate-950/60 text-slate-300'
                }`}
              >
                {turn.content}
                {turn.pending && (
                  <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-brand-400 align-middle" />
                )}
              </div>

              {turn.citations && turn.citations.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {turn.citations.map((citation, position) => (
                    <button
                      key={position}
                      onClick={() => onOpenCitation(citation)}
                      title={`Relevance ${citation.score.toFixed(2)} - click to open`}
                      className="rounded-full bg-brand-500/15 px-2 py-0.5 font-mono text-xs text-brand-200 transition hover:bg-brand-500/30"
                    >
                      {citation.path}:{citation.start_line}-{citation.end_line}
                      {citation.symbol && ` (${citation.symbol})`}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="shrink-0 border-t border-slate-800 p-3">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter is a newline, the convention everywhere
            // else a developer types into a chat box.
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder="How does token verification work?"
          className="w-full resize-none rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand-500"
        />

        <div className="mt-2 flex items-center justify-between">
          <Badge tone="info">grounded in this project</Badge>

          {streaming ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                abortRef.current?.();
                setStreaming(false);
                setTurns((previous) => {
                  const next = [...previous];
                  next[next.length - 1] = { ...next[next.length - 1], pending: false };
                  return next;
                });
              }}
            >
              Stop
            </Button>
          ) : (
            <Button variant="primary" size="sm" onClick={send} disabled={!draft.trim()}>
              Ask
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
