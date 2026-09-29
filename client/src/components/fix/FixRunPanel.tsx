import { useEffect, useRef, useState } from 'react';
import { errorMessage, fixApi } from '../../services/api';
import type { FixIteration, FixRunDetail, FixStatus } from '../../types';
import { Badge, Button, EmptyState, Spinner, type Tone } from '../ui';
import DiffView from './DiffView';

const STATUS_TONE: Record<FixStatus, Tone> = {
  queued: 'neutral',
  running: 'info',
  awaiting_approval: 'warn',
  succeeded: 'good',
  failed: 'bad',
  cancelled: 'neutral'
};

const STATUS_LABEL: Record<FixStatus, string> = {
  queued: 'queued',
  running: 'running',
  awaiting_approval: 'needs your approval',
  succeeded: 'applied',
  failed: 'gave up',
  cancelled: 'cancelled'
};

const ACTIVE: FixStatus[] = ['queued', 'running'];

type Props = {
  projectId: number;
  /** Re-read the file list after a patch lands, so the editor is not stale. */
  onApplied: () => void;
};

export default function FixRunPanel({ projectId, onApplied }: Props) {
  const [run, setRun] = useState<FixRunDetail | null>(null);
  const [instruction, setInstruction] = useState('Make the failing tests pass.');
  const [testCommand, setTestCommand] = useState('');
  const [maxIterations, setMaxIterations] = useState(3);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const pollRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (pollRef.current) window.clearTimeout(pollRef.current);
    pollRef.current = null;
  };

  useEffect(() => stopPolling, []);

  const poll = async (runId: number) => {
    try {
      const { data } = await fixApi.get(runId);
      setRun(data);

      // Only keep polling while the run is genuinely in flight. A terminal
      // state polls forever otherwise, for no new information.
      if (ACTIVE.includes(data.status)) {
        pollRef.current = window.setTimeout(() => poll(runId), 1200);
      }
    } catch (error) {
      setMessage(errorMessage(error, 'Lost track of the run'));
    }
  };

  const start = async () => {
    setBusy(true);
    setMessage('');
    setRun(null);

    try {
      const { data } = await fixApi.create({
        project_id: projectId,
        instruction: instruction.trim(),
        test_command: testCommand.trim() || null,
        max_iterations: maxIterations
      });

      poll(data.id);
    } catch (error) {
      setMessage(errorMessage(error, 'Could not start the run'));
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!run) return;

    setBusy(true);

    try {
      const { data } = await fixApi.apply(run.id);
      setMessage(data.message);
      onApplied();
      poll(run.id);
    } catch (error) {
      setMessage(errorMessage(error, 'Could not apply the patch'));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!run) return;

    try {
      await fixApi.cancel(run.id);
      poll(run.id);
    } catch (error) {
      setMessage(errorMessage(error, 'Could not cancel'));
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-2 border-b border-slate-800 p-3">
        <textarea
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          rows={2}
          placeholder="What should the agent fix?"
          className="w-full resize-none rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand-500"
        />

        <div className="flex gap-2">
          <input
            value={testCommand}
            onChange={(event) => setTestCommand(event.target.value)}
            placeholder="test command (default: unittest discover)"
            title="The sandbox has no network, so pytest cannot be installed into it. Stick to the standard library."
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand-500"
          />

          <select
            value={maxIterations}
            onChange={(event) => setMaxIterations(Number(event.target.value))}
            title="Hard cap on attempts - a model that misreads a failure will otherwise retry until the budget is gone"
            className="rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-300 outline-none focus:border-brand-500"
          >
            {[1, 2, 3, 5].map((count) => (
              <option key={count} value={count}>
                {count}x
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-600">Runs your tests in the sandbox</span>

          <div className="flex gap-2">
            {run && ACTIVE.includes(run.status) && (
              <Button size="sm" onClick={cancel}>
                Cancel
              </Button>
            )}

            <Button
              variant="primary"
              size="sm"
              onClick={start}
              disabled={busy || !instruction.trim() || (run !== null && ACTIVE.includes(run.status))}
            >
              Start fix run
            </Button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {message && <p className="mb-3 text-xs text-slate-400">{message}</p>}

        {!run ? (
          <EmptyState
            title="Let the agent try a fix"
            hint="It writes a patch, runs your tests in the sandbox, reads the failure, and tries again. Nothing touches your files until you approve the diff."
          />
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge tone={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</Badge>
              {ACTIVE.includes(run.status) && <Spinner label="working" />}
            </div>

            {run.summary && <p className="text-sm text-slate-300">{run.summary}</p>}
            {run.error && <p className="text-sm text-red-400">{run.error}</p>}

            {run.status === 'awaiting_approval' && run.diff && (
              <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-amber-300">
                    Tests pass with this change
                  </p>

                  <Button variant="primary" size="sm" onClick={apply} disabled={busy}>
                    Apply patch
                  </Button>
                </div>

                <DiffView diff={run.diff} />
              </div>
            )}

            <ol className="space-y-2">
              {run.iterations.map((iteration) => (
                <IterationRow key={iteration.iteration} iteration={iteration} />
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

function IterationRow({ iteration }: { iteration: FixIteration }) {
  const [open, setOpen] = useState(false);
  const output = [iteration.stdout, iteration.stderr].filter(Boolean).join('\n');

  return (
    <li className="rounded-lg border border-slate-800 bg-slate-950/50">
      <button
        onClick={() => setOpen((previous) => !previous)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Badge tone={iteration.passed ? 'good' : 'bad'}>
            {/* Iteration 0 is the baseline run, before the agent changed
                anything - labelling it as an attempt would overstate what
                the agent did. */}
            {iteration.iteration === 0 ? 'baseline' : `try ${iteration.iteration}`}
          </Badge>

          <span className="truncate text-xs text-slate-400">
            {iteration.reasoning ?? (iteration.passed ? 'Tests passed' : 'Tests failed')}
          </span>
        </span>

        <span className="shrink-0 text-xs text-slate-600">
          {iteration.exit_code === null ? 'not run' : `exit ${iteration.exit_code}`}
        </span>
      </button>

      {open && output && (
        <pre className="max-h-48 overflow-auto border-t border-slate-800 bg-black p-3 font-mono text-[11px] whitespace-pre-wrap text-slate-400">
          {output}
        </pre>
      )}
    </li>
  );
}
