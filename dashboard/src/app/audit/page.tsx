"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Search } from "lucide-react";
import { api, AuditEvent, AuditResponse } from "@/lib/api";
import { EmptyState, ErrorState, StatusLive, TableSkeleton } from "@/components/PageStates";

/**
 * The full audit log.
 *
 * Every decision the product made about a lead, with the reason. The
 * question this answers is "why did this lead get no email?" - which is
 * the question an operator asks when a campaign underperforms, and the one
 * that used to require reading the source.
 */
export default function AuditPage() {
  const [data, setData] = useState<AuditResponse | null>(null);
  const [types, setTypes] = useState<
    Array<{ event_type: string; label: string; count: number }>
  >([]);
  const [eventType, setEventType] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const PAGE_SIZE = 50;

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getAuditEvents({
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        event_type: eventType || undefined,
      });
      setData(res);
    } catch (err: any) {
      setData(null);
      setError(
        err?.message || "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, [page, eventType]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.getAuditTypes();
        if (!cancelled) setTypes(res.types || []);
      } catch {
        /* The filter is optional. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const events = data?.events ?? [];

  return (
    <div className="p-6 space-y-5 max-w-[1200px] mx-auto">
      <StatusLive loading={loading} loadingLabel="Loading the activity log…" />

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Activity log
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {total} recorded {total === 1 ? "decision" : "decisions"} - every
            send, bounce, suppression and deferral, with the reason.
          </p>
        </div>
        <div className="flex items-center gap-1.5 sm:justify-self-end">
          <label htmlFor="audit-type" className="text-[11px] font-medium text-slate-500">
            Event
          </label>
          <select
            id="audit-type"
            value={eventType}
            onChange={(e) => {
              setEventType(e.target.value);
              setPage(1);
            }}
            className="h-9 rounded-xl border border-slate-200 bg-white pl-2 pr-7 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
          >
            <option value="">All events</option>
            {types
              .filter((t) => t.count > 0)
              .map((t) => (
                <option key={t.event_type} value={t.event_type}>
                  {t.label} ({t.count})
                </option>
              ))}
          </select>
        </div>
      </div>

      {error && !loading && (
        <ErrorState
          title="Could not load the activity log"
          message={error}
          onRetry={load}
        />
      )}

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        {loading ? (
          <div className="p-4">
            <table className="w-full">
              <tbody>
                <TableSkeleton rows={8} columns={3} rowClassName="h-[49px]" cellClassName="px-4 py-3" />
              </tbody>
            </table>
          </div>
        ) : events.length === 0 ? (
          <div className="p-6">
            {eventType ? (
              <EmptyState
                icon={<Search className="h-5 w-5" />}
                title="No events of that kind"
                description="Nothing has been recorded under that filter yet."
                action={
                  <button
                    onClick={() => {
                      setEventType("");
                      setPage(1);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700"
                  >
                    Show all events
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon={<Activity className="h-5 w-5" />}
                title="Nothing has happened yet"
                description="Once a sequence sends its first email, every decision it makes - and why - shows up here. Nothing is recorded until then, so an empty log means an untouched workspace rather than a broken one."
              />
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] table-fixed text-left">
              <colgroup>
                <col style={{ width: "22%" }} />
                <col style={{ width: "46%" }} />
                <col style={{ width: "16%" }} />
                <col style={{ width: "16%" }} />
              </colgroup>
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <th scope="col" className="px-5 py-3 font-semibold">Event</th>
                  <th scope="col" className="px-4 py-3 font-semibold">What happened</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Target</th>
                  <th scope="col" className="px-4 py-3 font-semibold text-right">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {events.map((e: AuditEvent) => (
                  <tr key={e.id} className="h-[49px] hover:bg-slate-50/80 transition-colors">
                    <td className="px-5 py-3 text-xs font-medium text-slate-700">
                      {e.event_label}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-800">
                      {e.summary || "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {e.entity_type
                        ? `${e.entity_type} #${e.entity_id ?? "—"}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-slate-500 tabular-nums">
                      {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="border-t border-slate-200 px-5 py-3 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">
              Page {page} of {pages} · {total} events
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 disabled:opacity-40 hover:border-slate-300"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 disabled:opacity-40 hover:border-slate-300"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
