/**
 * The SSE reader, which is the one piece of frontend logic with a real failure
 * mode: frames arrive in whatever chunks the network hands over, so a frame
 * split across two reads has to survive until the rest of it turns up. A naive
 * parser passes every hand-written test and drops tokens against a real server.
 */

import { describe, expect, it, vi } from 'vitest';
import { streamChat } from './api';

/** Feeds the given chunks to streamChat as a ReadableStream, exactly as written. */
function mockStream(chunks: string[], ok = true, status = 200) {
  const encoder = new TextEncoder();

  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    }
  });

  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok, status, body: ok ? body : null })
  );
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Resolves once streamChat reports done or error. */
function collect(chunks: string[], ok = true, status = 200) {
  mockStream(chunks, ok, status);

  return new Promise<{
    tokens: string[];
    citations: unknown[];
    conversationId: number | null;
    error: string | null;
  }>((resolve) => {
    const tokens: string[] = [];
    let citations: unknown[] = [];
    let conversationId: number | null = null;

    streamChat(
      { message: 'how does the rate limiter work?', project_id: 1 },
      {
        onToken: (text) => tokens.push(text),
        onCitations: (received, id) => {
          citations = received;
          conversationId = id;
        },
        onDone: (id) => resolve({ tokens, citations, conversationId: id, error: null }),
        onError: (detail) =>
          resolve({ tokens, citations, conversationId, error: detail })
      }
    );
  });
}

describe('streamChat', () => {
  it('reads citations, tokens and done from a well-formed stream', async () => {
    const result = await collect([
      frame('citations', {
        citations: [{ path: 'rate_limit.py', start_line: 19, end_line: 32, score: 0.82 }],
        conversation_id: 7
      }),
      frame('token', { text: 'The limiter ' }),
      frame('token', { text: 'keeps a deque.' }),
      frame('done', { conversation_id: 7 })
    ]);

    expect(result.error).toBeNull();
    expect(result.tokens.join('')).toBe('The limiter keeps a deque.');
    expect(result.citations).toHaveLength(1);
    expect(result.conversationId).toBe(7);
  });

  it('reassembles a frame split across two chunks', async () => {
    // The split lands mid-JSON, which is what a real socket does.
    const whole = frame('token', { text: 'tokens must survive a split' });
    const cut = Math.floor(whole.length / 2);

    const result = await collect([
      whole.slice(0, cut),
      whole.slice(cut),
      frame('done', { conversation_id: 1 })
    ]);

    expect(result.tokens.join('')).toBe('tokens must survive a split');
  });

  it('handles several frames delivered in a single chunk', async () => {
    const result = await collect([
      frame('token', { text: 'a' }) + frame('token', { text: 'b' }) + frame('token', { text: 'c' }),
      frame('done', { conversation_id: 2 })
    ]);

    expect(result.tokens).toEqual(['a', 'b', 'c']);
  });

  it('surfaces an error frame as an error rather than text', async () => {
    const result = await collect([frame('error', { detail: 'Rate limit exceeded' })]);

    expect(result.error).toBe('Rate limit exceeded');
    expect(result.tokens).toEqual([]);
  });

  it('reports a non-200 response instead of hanging', async () => {
    const result = await collect([], false, 503);

    expect(result.error).toContain('503');
  });

  it('ignores a trailing partial frame rather than throwing on bad JSON', async () => {
    // A stream cut off mid-frame must not take the whole reply down.
    const result = await collect([
      frame('token', { text: 'delivered' }),
      frame('done', { conversation_id: 3 }),
      'event: token\ndata: {"text": "never clo'
    ]);

    expect(result.tokens).toEqual(['delivered']);
    expect(result.error).toBeNull();
  });

  it('aborting stops the stream without reporting an error', async () => {
    mockStream([frame('token', { text: 'x' })]);

    const onError = vi.fn();
    const abort = streamChat({ message: 'hello', project_id: 1 }, { onError });

    abort();

    await new Promise((resolve) => setTimeout(resolve, 10));

    // An abort is the caller's own doing, not a failure worth surfacing.
    expect(onError).not.toHaveBeenCalledWith('Lost the connection to the assistant.');
  });
});
