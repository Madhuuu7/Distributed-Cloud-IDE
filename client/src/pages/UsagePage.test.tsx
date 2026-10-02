/**
 * The usage dashboard, including the single-day case that produced a duplicate
 * React key: the chart labels the first and last column, and with one day those
 * are the same index, so the label was rendered twice on the same x.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UsageResponse } from '../types';

const usage = vi.fn();

vi.mock('../services/api', () => ({
  aiApi: { usage: (...args: unknown[]) => usage(...args) },
  errorMessage: (_error: unknown, fallback: string) => fallback
}));

const { default: UsagePage } = await import('./UsagePage');

function response(overrides: Partial<UsageResponse> = {}): UsageResponse {
  return {
    days: 30,
    total_calls: 16,
    total_tokens: 12325,
    total_cost_usd: 0,
    cache_hit_rate: 0.1875,
    estimated_savings_usd: 0,
    by_day: [{ day: '2026-10-02', calls: 16, tokens: 12325, cost_usd: 0 }],
    by_feature: [
      { feature: 'chat', calls: 10, tokens: 8023, cost_usd: 0 },
      { feature: 'review', calls: 2, tokens: 3133, cost_usd: 0 },
      { feature: 'explain', calls: 4, tokens: 1169, cost_usd: 0 }
    ],
    ...overrides
  };
}

/** The axis label for a day, formatted exactly as the chart formats it. */
function axisLabel(day: string): string {
  return new Date(day).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function svgText(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg text')).map((node) => node.textContent ?? '');
}

describe('UsagePage', () => {
  beforeEach(() => {
    usage.mockReset();
  });

  it('renders a single day without duplicating the date label', async () => {
    // One day is both the first and the last column. Before the fix this drew
    // two <text> nodes at the same position under the same key.
    usage.mockResolvedValue({ data: response() });

    const { container } = render(<UsagePage />);

    await waitFor(() => expect(screen.getByText('16')).toBeInTheDocument());

    const label = axisLabel('2026-10-02');
    const occurrences = svgText(container).filter((text) => text === label);

    expect(occurrences).toHaveLength(1);
  });

  it('labels both ends when there is more than one day', async () => {
    usage.mockResolvedValue({
      data: response({
        by_day: [
          { day: '2026-09-30', calls: 4, tokens: 1000, cost_usd: 0 },
          { day: '2026-10-01', calls: 6, tokens: 2000, cost_usd: 0 },
          { day: '2026-10-02', calls: 6, tokens: 3000, cost_usd: 0 }
        ]
      })
    });

    const { container } = render(<UsagePage />);

    await waitFor(() => expect(screen.getByText('16')).toBeInTheDocument());

    const texts = svgText(container);

    expect(texts).toContain(axisLabel('2026-09-30'));
    expect(texts).toContain(axisLabel('2026-10-02'));

    // A label per column collides at 30 days, so the middle stays unlabelled.
    expect(texts).not.toContain(axisLabel('2026-10-01'));
  });

  it('defaults to tokens when every call was free', async () => {
    // A cost chart on the mock provider is a flat row of zeros: correct and
    // useless. The page is supposed to pick the measure that has values.
    usage.mockResolvedValue({ data: response() });

    render(<UsagePage />);

    await waitFor(() => expect(screen.getByText('Tokens per day')).toBeInTheDocument());
  });

  it('says why spend is zero instead of looking broken', async () => {
    usage.mockResolvedValue({ data: response() });

    render(<UsagePage />);

    await waitFor(() =>
      expect(screen.getByText(/cost nothing/i)).toBeInTheDocument()
    );
  });

  it('shows every feature in the breakdown', async () => {
    usage.mockResolvedValue({ data: response() });

    render(<UsagePage />);

    await waitFor(() => expect(screen.getByText('chat')).toBeInTheDocument());
    expect(screen.getByText('review')).toBeInTheDocument();
    expect(screen.getByText('explain')).toBeInTheDocument();
  });

  it('reports a failed load rather than spinning forever', async () => {
    usage.mockRejectedValue(new Error('boom'));

    render(<UsagePage />);

    await waitFor(() =>
      expect(screen.getByText('Could not load usage')).toBeInTheDocument()
    );
  });
});
