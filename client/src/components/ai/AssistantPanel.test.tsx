/**
 * The assistant panel. The claim the whole project rests on is that an answer
 * can be checked against the code, which means a citation has to say where it
 * came from and open that place when clicked.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Citation } from '../../types';

const streamChat = vi.fn();

vi.mock('../../services/api', () => ({
  streamChat: (...args: unknown[]) => streamChat(...args)
}));

const { default: AssistantPanel } = await import('./AssistantPanel');

const CITATIONS: Citation[] = [
  { path: 'retrieval.py', symbol: 'blend', start_line: 44, end_line: 47, score: 0.91 },
  { path: 'rate_limit.py', symbol: null, start_line: 19, end_line: 32, score: 0.77 }
];

/** Drives streamChat's callbacks as a real reply would. */
function replyWith(text: string, citations: Citation[] = CITATIONS) {
  streamChat.mockImplementation((_payload, handlers) => {
    handlers.onCitations?.(citations, 7);
    handlers.onToken?.(text);
    handlers.onDone?.(7);

    return vi.fn();
  });
}

async function ask(question: string) {
  const user = userEvent.setup();

  await user.type(screen.getByRole('textbox'), question);
  await user.click(screen.getByRole('button', { name: 'Ask' }));

  return user;
}

describe('AssistantPanel', () => {
  beforeEach(() => {
    streamChat.mockReset();
  });

  it('starts with the empty state and no way to send nothing', () => {
    render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);

    expect(screen.getByText('Ask about this codebase')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
  });

  it('shows the question and the streamed answer', async () => {
    replyWith('Thirty percent keyword, seventy percent vector.');

    render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);
    await ask('How is the score blended?');

    await waitFor(() =>
      expect(screen.getByText('Thirty percent keyword, seventy percent vector.')).toBeInTheDocument()
    );
    expect(screen.getByText('How is the score blended?')).toBeInTheDocument();
  });

  it('renders each citation as file, line range and symbol', async () => {
    replyWith('answer');

    render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);
    await ask('where is blend?');

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retrieval\.py:44-47 \(blend\)/ })).toBeInTheDocument()
    );

    // A chunk with no enclosing function still cites its lines.
    expect(screen.getByRole('button', { name: /rate_limit\.py:19-32/ })).toBeInTheDocument();
  });

  it('opens the cited range when a citation is clicked', async () => {
    const onOpenCitation = vi.fn();
    replyWith('answer');

    render(<AssistantPanel projectId={1} onOpenCitation={onOpenCitation} />);
    const user = await ask('where is blend?');

    await waitFor(() => screen.getByRole('button', { name: /retrieval\.py:44-47/ }));
    await user.click(screen.getByRole('button', { name: /retrieval\.py:44-47/ }));

    expect(onOpenCitation).toHaveBeenCalledWith(CITATIONS[0]);
  });

  it('sends the project id so the answer is grounded in this codebase', async () => {
    replyWith('answer');

    render(<AssistantPanel projectId={42} onOpenCitation={vi.fn()} />);
    await ask('anything');

    expect(streamChat).toHaveBeenCalledWith(
      expect.objectContaining({ project_id: 42, message: 'anything' }),
      expect.anything()
    );
  });

  it('continues the same conversation on the second question', async () => {
    replyWith('answer');

    render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);
    await ask('first');

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(1));
    await ask('second');

    expect(streamChat).toHaveBeenLastCalledWith(
      expect.objectContaining({ conversation_id: 7 }),
      expect.anything()
    );
  });

  it('sends on Enter and inserts a newline on Shift+Enter', async () => {
    replyWith('answer');
    const user = userEvent.setup();

    render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);

    const box = screen.getByRole('textbox');

    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two');
    expect(streamChat).not.toHaveBeenCalled();

    await user.type(box, '{Enter}');
    expect(streamChat).toHaveBeenCalledTimes(1);
  });

  it('shows the reason when the stream fails', async () => {
    streamChat.mockImplementation((_payload, handlers) => {
      handlers.onError?.('Rate limit exceeded. Try again in 31s.');
      return vi.fn();
    });

    render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);
    await ask('anything');

    await waitFor(() =>
      expect(screen.getByText('Rate limit exceeded. Try again in 31s.')).toBeInTheDocument()
    );
  });

  it('aborts the stream when the panel unmounts', async () => {
    const abort = vi.fn();
    streamChat.mockImplementation(() => abort);

    const { unmount } = render(<AssistantPanel projectId={1} onOpenCitation={vi.fn()} />);
    await ask('anything');

    unmount();

    // Without this the token callback fires against a component that is gone.
    expect(abort).toHaveBeenCalled();
  });
});
