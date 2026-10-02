import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Badge, Button, EmptyState, Panel, formatCost } from './index';

describe('formatCost', () => {
  it('calls free free, rather than printing $0.00', () => {
    // The mock provider prices every call at zero. "$0.00" in a spend column
    // reads as a broken dashboard; "free" reads as the point.
    expect(formatCost(0)).toBe('free');
  });

  it('collapses sub-cent amounts, which is most single calls', () => {
    expect(formatCost(0.0004)).toBe('<$0.01');
    expect(formatCost(0.009999)).toBe('<$0.01');
  });

  it('prints two decimals from a cent upward', () => {
    expect(formatCost(0.01)).toBe('$0.01');
    expect(formatCost(1.5)).toBe('$1.50');
    expect(formatCost(12.345)).toBe('$12.35');
  });
});

describe('Panel', () => {
  it('renders a header only when there is something to put in it', () => {
    const { container } = render(<Panel>body</Panel>);

    expect(container.querySelector('header')).toBeNull();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('renders the title and actions when given', () => {
    render(
      <Panel title="AI usage" actions={<button>Refresh</button>}>
        body
      </Panel>
    );

    expect(screen.getByRole('heading', { name: 'AI usage' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
  });
});

describe('Button', () => {
  it('stays clickable by default and blocks clicks when disabled', () => {
    render(
      <>
        <Button>Ask</Button>
        <Button disabled>Stop</Button>
      </>
    );

    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();
  });
});

describe('Badge and EmptyState', () => {
  it('exposes the tooltip text a badge is given', () => {
    render(<Badge title="Responses are generated locally">mock AI</Badge>);

    expect(screen.getByTitle('Responses are generated locally')).toHaveTextContent('mock AI');
  });

  it('shows the hint alongside the title', () => {
    render(<EmptyState title="Ask about this codebase" hint="Answers cite the lines they used." />);

    expect(screen.getByText('Ask about this codebase')).toBeInTheDocument();
    expect(screen.getByText('Answers cite the lines they used.')).toBeInTheDocument();
  });
});
