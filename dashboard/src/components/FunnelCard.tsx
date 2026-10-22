"use client";

import { useMemo } from "react";

/**
 * The pipeline funnel.
 *
 * Four flat counters cannot answer the only question that matters: *where
 * does the pipeline leak?* A list of 500 businesses that produced 12
 * emails and 1 reply looks identical to a list of 12 businesses that
 * produced 1 email and 1 reply, and the operator cannot tell which part
 * to fix.
 *
 * Each stage shows its own count and the conversion from the stage above
 * it, so the biggest drop is the one that is obvious.
 */

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
  hint: string;
}

export interface FunnelResponse {
  days: number;
  stages: FunnelStage[];
  rates: Record<string, number | null>;
  by_source: Array<{ source: string; count: number }>;
  by_mailbox: Array<{
    email: string;
    sent: number;
    opened: number;
    replied: number;
    bounced: number;
    open_rate: number | null;
    reply_rate: number | null;
    bounce_rate: number | null;
  }>;
  reply_categories: Array<{ category: string; count: number }>;
}

/** Bar colour by stage: neutral for the top, then by how healthy the stage is. */
function barClass(index: number, total: number): string {
  if (index === 0) return "bg-slate-700";
  if (index >= total - 3) return "bg-emerald-500";
  if (index >= total - 6) return "bg-blue-500";
  return "bg-slate-400";
}

export default function FunnelCard({
  funnel,
  loading,
}: {
  funnel: FunnelResponse | null;
  loading?: boolean;
}) {
  const max = useMemo(
    () => Math.max(1, ...(funnel?.stages || []).map((s) => s.count)),
    [funnel],
  );

  if (loading) {
    return (
      <div
        aria-hidden="true"
        className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs"
      >
        <div className="h-3 w-40 animate-pulse rounded-md bg-slate-200/70" />
        <div className="mt-4 space-y-2.5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-6 animate-pulse rounded-md bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  if (!funnel || !funnel.stages?.length) {
    return null;
  }

  return (
    <section
      aria-labelledby="funnel-heading"
      className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="funnel-heading" className="text-sm font-bold text-slate-900">
          Where the pipeline leaks
        </h2>
        <span className="text-[11px] text-slate-500">
          last {funnel.days} days
        </span>
      </div>
      <p className="mt-0.5 text-xs text-slate-500">
        Each bar is a real count. The percentage is the conversion from the
        stage above it, so the biggest drop is the one worth fixing.
      </p>

      <ol className="mt-4 space-y-2">
        {funnel.stages.map((stage, i) => {
          const prev = i > 0 ? funnel.stages[i - 1] : null;
          const conversion =
            prev && prev.count > 0
              ? Math.round((stage.count / prev.count) * 100)
              : null;
          const width = Math.max(2, Math.round((stage.count / max) * 100));
          const isLast = i === funnel.stages.length - 1;
          return (
            <li key={stage.key} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-3">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-slate-700" title={stage.hint}>
                  {stage.label}
                </p>
              </div>
              <div className="h-6 w-full overflow-hidden rounded-md bg-slate-100">
                <div
                  className={`flex h-full items-center rounded-md ${barClass(i, funnel.stages.length)} transition-[width] duration-500`}
                  style={{ width: `${width}%` }}
                />
              </div>
              <div className="flex items-baseline gap-2 text-right">
                <span className="text-sm font-bold tabular-nums text-slate-900">
                  {stage.count}
                </span>
                {conversion !== null && !isLast && (
                  <span
                    className={`text-[10px] tabular-nums ${
                      conversion < 20 ? "text-red-600" : "text-slate-500"
                    }`}
                    title={`${conversion}% of the previous stage`}
                  >
                    {conversion}%
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {funnel.by_source?.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Where the businesses came from
          </h3>
          <ul className="mt-2 space-y-1">
            {funnel.by_source.slice(0, 6).map((s) => (
              <li key={s.source} className="flex items-center justify-between text-xs">
                <span className="truncate text-slate-700">{s.source}</span>
                <span className="tabular-nums font-semibold text-slate-900">{s.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {funnel.by_mailbox?.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Per mailbox
          </h3>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                  <th scope="col" className="py-1 pr-3 font-semibold">Mailbox</th>
                  <th scope="col" className="py-1 pr-3 text-right font-semibold">Sent</th>
                  <th scope="col" className="py-1 pr-3 text-right font-semibold">Opened</th>
                  <th scope="col" className="py-1 pr-3 text-right font-semibold">Replied</th>
                  <th scope="col" className="py-1 text-right font-semibold">Bounced</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {funnel.by_mailbox.map((m) => (
                  <tr key={m.email}>
                    <td className="py-1.5 pr-3 truncate text-slate-700">{m.email}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-slate-600">
                      {m.sent}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-slate-600">
                      {m.opened}
                      {m.open_rate !== null && (
                        <span className="ml-1 text-[10px] text-slate-500">{m.open_rate}%</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-slate-600">
                      {m.replied}
                      {m.reply_rate !== null && (
                        <span className="ml-1 text-[10px] text-slate-500">{m.reply_rate}%</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right tabular-nums text-slate-600">
                      {m.bounced}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
