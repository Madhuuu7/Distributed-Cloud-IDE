import { useEffect, useState } from 'react';
import { aiApi, errorMessage } from '../services/api';
import type { UsageResponse } from '../types';
import { Badge, Button, EmptyState, Panel } from '../components/ui';

/**
 * Chart ink.
 *
 * brand-500 (#4f46e5) measures 2.84:1 against this page's surface (#0f172a),
 * under the 3:1 a chart mark needs, so the bars use brand-400 instead. Bars
 * are a single series, so there is no second hue to tell apart and no legend
 * to print - the panel title names the measure.
 */
const BAR = '#818cf8';
const BAR_HOVER = '#a5b4fc';

type Measure = 'cost' | 'tokens';

export default function UsagePage() {
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [days, setDays] = useState(30);
  const [measure, setMeasure] = useState<Measure | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const { data } = await aiApi.usage(days);
        setUsage(data);

        // Default to whichever measure actually has values. With the mock
        // provider every call is free, so a cost chart would be a flat row of
        // zeros - technically correct and completely useless.
        setMeasure((current) => current ?? (data.total_cost_usd > 0 ? 'cost' : 'tokens'));
      } catch (error) {
        setMessage(errorMessage(error, 'Could not load usage'));
      }
    })();
  }, [days]);

  if (message) return <p className="text-sm text-red-400">{message}</p>;
  if (!usage || !measure) return <p className="text-sm text-slate-400">Loading...</p>;

  const isFree = usage.total_cost_usd === 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">AI usage</h1>
          <p className="mt-1 text-sm text-slate-400">
            Every model call is recorded, including the ones served from cache.
          </p>
        </div>

        <div className="flex gap-1">
          {[7, 30, 90].map((option) => (
            <Button
              key={option}
              size="sm"
              variant={days === option ? 'primary' : 'ghost'}
              onClick={() => setDays(option)}
            >
              {option}d
            </Button>
          ))}
        </div>
      </header>

      {isFree && (
        <p className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs text-slate-400">
          Every call in this window cost nothing - the active provider is free or
          mocked. Set <code className="text-slate-300">AI_PRICE_PROMPT_PER_MTOK</code> and{' '}
          <code className="text-slate-300">AI_PRICE_COMPLETION_PER_MTOK</code> once you are
          on a paid key, or spend will keep reading as $0.00.
        </p>
      )}

      {/* A KPI row, not a chart. Four headline numbers are a row of stat tiles;
          turning them into a grouped bar chart would make them harder to read. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Spend"
          value={usage.total_cost_usd === 0 ? '$0.00' : `$${usage.total_cost_usd.toFixed(4)}`}
          detail={`${usage.total_tokens.toLocaleString()} tokens`}
        />
        <StatTile
          label="Calls"
          value={usage.total_calls.toLocaleString()}
          detail={`across ${usage.by_feature.length} feature${usage.by_feature.length === 1 ? '' : 's'}`}
        />
        <StatTile
          label="Cache hit rate"
          value={`${Math.round(usage.cache_hit_rate * 100)}%`}
          detail={
            usage.estimated_savings_usd > 0
              ? `saved $${usage.estimated_savings_usd.toFixed(4)}`
              : 'no spend to save yet'
          }
          meter={usage.cache_hit_rate}
        />
        <StatTile
          label="Avg tokens / call"
          value={
            usage.total_calls
              ? Math.round(usage.total_tokens / usage.total_calls).toLocaleString()
              : '0'
          }
          detail="prompt + completion"
        />
      </div>

      <Panel
        title={measure === 'cost' ? 'Spend per day' : 'Tokens per day'}
        actions={
          <div className="flex items-center gap-2">
            {/* One measure at a time. Two y-scales on one chart is the single
                most common way to make a dashboard lie. */}
            <Button
              size="sm"
              variant={measure === 'tokens' ? 'primary' : 'ghost'}
              onClick={() => setMeasure('tokens')}
            >
              Tokens
            </Button>
            <Button
              size="sm"
              variant={measure === 'cost' ? 'primary' : 'ghost'}
              onClick={() => setMeasure('cost')}
            >
              Cost
            </Button>
            <Button size="sm" onClick={() => setShowTable((previous) => !previous)}>
              {showTable ? 'Chart' : 'Table'}
            </Button>
          </div>
        }
      >
        {usage.by_day.length === 0 ? (
          <EmptyState title="No calls in this window" hint="Ask the assistant something first." />
        ) : showTable ? (
          <DayTable usage={usage} />
        ) : (
          <DailyColumns days={usage.by_day} measure={measure} />
        )}
      </Panel>

      <Panel title="By feature">
        {usage.by_feature.length === 0 ? (
          <EmptyState title="Nothing recorded yet" />
        ) : (
          <FeatureBars features={usage.by_feature} measure={measure} />
        )}
      </Panel>
    </div>
  );
}

function StatTile({
  label,
  value,
  detail,
  meter
}: {
  label: string;
  value: string;
  detail: string;
  meter?: number;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white tabular-nums">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>

      {/* A single ratio against a limit is a meter, not a two-slice pie. */}
      {meter !== undefined && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full rounded-full"
            style={{ width: `${Math.round(meter * 100)}%`, background: BAR }}
          />
        </div>
      )}
    </div>
  );
}

function DailyColumns({
  days,
  measure
}: {
  days: UsageResponse['by_day'];
  measure: Measure;
}) {
  const [hover, setHover] = useState<number | null>(null);

  const valueOf = (day: UsageResponse['by_day'][number]) =>
    measure === 'cost' ? day.cost_usd : day.tokens;

  const values = days.map(valueOf);
  const peak = Math.max(...values, 1);
  const peakIndex = values.indexOf(Math.max(...values));

  const width = 720;
  const height = 200;
  const padding = { top: 24, right: 8, bottom: 28, left: 8 };
  const plotHeight = height - padding.top - padding.bottom;
  const slot = (width - padding.left - padding.right) / days.length;
  // A 2px surface gap between adjacent bars, so they read as separate marks.
  const barWidth = Math.max(2, Math.min(slot - 2, 42));

  const format = (value: number) =>
    measure === 'cost' ? `$${value.toFixed(4)}` : value.toLocaleString();

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img">
        <title>
          {measure === 'cost' ? 'Spend' : 'Tokens'} per day over the selected window
        </title>

        {/* Recessive gridlines - present for reading values, never competing
            with the data. */}
        {[0, 0.5, 1].map((fraction) => {
          const y = padding.top + plotHeight * (1 - fraction);

          return (
            <line
              key={fraction}
              x1={padding.left}
              x2={width - padding.right}
              y1={y}
              y2={y}
              stroke="#1e293b"
              strokeWidth={1}
            />
          );
        })}

        {days.map((day, index) => {
          const value = valueOf(day);
          const barHeight = Math.max(value > 0 ? 2 : 0, (value / peak) * plotHeight);
          const x = padding.left + index * slot + (slot - barWidth) / 2;
          const y = padding.top + plotHeight - barHeight;
          const active = hover === index;

          return (
            <g key={day.day}>
              {/* Hit target spans the full slot, so a 4px bar is still easy
                  to hover. */}
              <rect
                x={padding.left + index * slot}
                y={padding.top}
                width={slot}
                height={plotHeight}
                fill="transparent"
                onMouseEnter={() => setHover(index)}
                onMouseLeave={() => setHover(null)}
              />

              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                // Rounded data-end only; the bar stays anchored to the baseline.
                rx={Math.min(4, barWidth / 2)}
                fill={active ? BAR_HOVER : BAR}
                pointerEvents="none"
              />

              {/* Label the peak only. A number over every bar is noise. */}
              {index === peakIndex && value > 0 && (
                <text
                  x={x + barWidth / 2}
                  y={y - 8}
                  textAnchor="middle"
                  className="fill-slate-400"
                  fontSize={11}
                >
                  {format(value)}
                </text>
              )}
            </g>
          );
        })}

        {/* First and last date only - a label per column collides at 30 days.
            A single day is both, so dedupe or the one label is drawn twice. */}
        {[...new Set([0, days.length - 1])].map((index) =>
          days[index] ? (
            <text
              key={days[index].day}
              x={padding.left + index * slot + slot / 2}
              y={height - 8}
              textAnchor={index === 0 ? 'start' : 'end'}
              className="fill-slate-600"
              fontSize={11}
            >
              {new Date(days[index].day).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric'
              })}
            </text>
          ) : null
        )}
      </svg>

      {hover !== null && days[hover] && (
        <div
          className="pointer-events-none absolute top-0 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs shadow-lg"
          style={{
            left: `${((hover + 0.5) / days.length) * 100}%`,
            transform: 'translateX(-50%)'
          }}
        >
          <p className="font-medium text-white">
            {new Date(days[hover].day).toLocaleDateString()}
          </p>
          <p className="mt-0.5 text-slate-400 tabular-nums">{format(valueOf(days[hover]))}</p>
          <p className="text-slate-600">{days[hover].calls} calls</p>
        </div>
      )}
    </div>
  );
}

function FeatureBars({
  features,
  measure
}: {
  features: UsageResponse['by_feature'];
  measure: Measure;
}) {
  const valueOf = (feature: UsageResponse['by_feature'][number]) =>
    measure === 'cost' ? feature.cost_usd : feature.tokens;

  // Sorted descending: a magnitude comparison is easiest to read when the
  // ranking is the layout.
  const sorted = [...features].sort((a, b) => valueOf(b) - valueOf(a));
  const peak = Math.max(...sorted.map(valueOf), 1);

  return (
    <ul className="space-y-3">
      {sorted.map((feature) => {
        const value = valueOf(feature);

        return (
          <li key={feature.feature} className="flex items-center gap-3">
            <span className="w-20 shrink-0 truncate text-xs text-slate-400">
              {feature.feature}
            </span>

            <div className="h-5 min-w-0 flex-1 overflow-hidden rounded bg-slate-950">
              <div
                className="h-full rounded"
                style={{
                  width: `${Math.max(value > 0 ? 1 : 0, (value / peak) * 100)}%`,
                  background: BAR
                }}
              />
            </div>

            <span className="w-24 shrink-0 text-right text-xs text-slate-400 tabular-nums">
              {measure === 'cost' ? `$${value.toFixed(4)}` : value.toLocaleString()}
            </span>

            <Badge tone="neutral">{feature.calls}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

/** The table view every chart here needs to stay readable without color. */
function DayTable({ usage }: { usage: UsageResponse }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="pb-2 font-medium">Day</th>
            <th className="pb-2 text-right font-medium">Calls</th>
            <th className="pb-2 text-right font-medium">Tokens</th>
            <th className="pb-2 text-right font-medium">Cost</th>
          </tr>
        </thead>

        <tbody className="divide-y divide-slate-800 text-slate-300">
          {usage.by_day.map((day) => (
            <tr key={day.day}>
              <td className="py-2">{new Date(day.day).toLocaleDateString()}</td>
              <td className="py-2 text-right tabular-nums">{day.calls}</td>
              <td className="py-2 text-right tabular-nums">{day.tokens.toLocaleString()}</td>
              <td className="py-2 text-right tabular-nums">${day.cost_usd.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
