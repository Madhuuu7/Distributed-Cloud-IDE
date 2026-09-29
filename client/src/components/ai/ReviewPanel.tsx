import { useState } from 'react';
import { aiApi, errorMessage } from '../../services/api';
import type { Finding, Severity } from '../../types';
import { Badge, Button, EmptyState, formatCost, type Tone } from '../ui';

const SEVERITY_TONE: Record<Severity, Tone> = {
  info: 'neutral',
  minor: 'info',
  major: 'warn',
  critical: 'bad'
};

const SEVERITY_ORDER: Severity[] = ['critical', 'major', 'minor', 'info'];

type Props = {
  projectId: number;
  onOpenFinding: (finding: Finding) => void;
};

export default function ReviewPanel({ projectId, onOpenFinding }: Props) {
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [message, setMessage] = useState('');

  const review = async () => {
    setReviewing(true);
    setMessage('');

    try {
      const { data } = await aiApi.review({ project_id: projectId });

      // Worst first. A reviewer that leads with a nitpick gets skimmed.
      setFindings(
        [...data.findings].sort(
          (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
        )
      );

      setMessage(
        `Reviewed ${data.files_reviewed} file(s) - ${formatCost(data.cost_usd)}` +
          (data.cached ? ' (cached)' : '')
      );
    } catch (error) {
      setFindings(null);
      setMessage(errorMessage(error, 'Review failed'));
    } finally {
      setReviewing(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 p-3">
        <span className="text-xs text-slate-500">
          {message || 'Findings are anchored to real lines'}
        </span>

        <Button variant="primary" size="sm" onClick={review} disabled={reviewing}>
          {reviewing ? 'Reviewing...' : 'Review project'}
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {findings === null ? (
          <EmptyState
            title="No review yet"
            hint="The reviewer reports defects it can point at, and drops findings that cite a file that is not in this project."
          />
        ) : findings.length === 0 ? (
          // An empty list is a real result, not a failure. Reviewers that
          // always find something get ignored.
          <EmptyState title="No defects found" hint="Nothing worth flagging in the reviewed files." />
        ) : (
          <ul className="divide-y divide-slate-800">
            {findings.map((finding, index) => (
              <li key={index}>
                <button
                  onClick={() => onOpenFinding(finding)}
                  className="w-full px-4 py-3 text-left transition hover:bg-slate-800/50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone={SEVERITY_TONE[finding.severity]}>{finding.severity}</Badge>

                    <span className="truncate font-mono text-xs text-brand-300">
                      {finding.path}:{finding.line}
                    </span>
                  </div>

                  <p className="mt-2 text-sm leading-relaxed text-slate-300">{finding.message}</p>

                  {finding.suggestion && (
                    <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-emerald-300">
                      {finding.suggestion}
                    </pre>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
