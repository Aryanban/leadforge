"use client";

import { useCallback, useEffect, useState } from "react";
import { Inbox as InboxIcon, Mail, RefreshCw, FilterX, Send } from "lucide-react";
import { api, InboxItem, InboxResponse } from "@/lib/api";
import { CardSkeleton, EmptyState, ErrorState, StatusLive } from "@/components/PageStates";

const CATEGORY_TABS = [
  { key: "", label: "All" },
  { key: "interested", label: "Interested" },
  { key: "not_interested", label: "Not interested" },
  { key: "opt_out", label: "Opt-outs" },
  { key: "out_of_office", label: "Away" },
  { key: "other", label: "Other" },
];

const CATEGORY_STYLE: Record<string, string> = {
  interested: "bg-emerald-50 text-emerald-700 border-emerald-200",
  not_interested: "bg-slate-50 text-slate-600 border-slate-200",
  opt_out: "bg-red-50 text-red-700 border-red-200",
  out_of_office: "bg-blue-50 text-blue-700 border-blue-200",
  other: "bg-amber-50 text-amber-700 border-amber-200",
};

const CATEGORY_LABEL: Record<string, string> = {
  interested: "Interested",
  not_interested: "Not interested",
  opt_out: "Opted out",
  out_of_office: "Away",
  other: "Needs triage",
};

/**
 * Inbox — inbound replies, detected by the IMAP reply poller (thread
 * attribution via stored Message-IDs). Category badges are rule-based
 * first-pass: agents triage, humans confirm. Opt-outs are suppressed
 * workspace-wide at capture time — nothing here can re-send to them.
 */
export default function InboxPage() {
  const [data, setData] = useState<InboxResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setData(await api.listInbox(tab || undefined));
    } catch (err: any) {
      setData(null);
      setError(
        err?.message || "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  const recategorize = async (sendId: number, category: string) => {
    setSavingId(sendId);
    try {
      await api.setReplyCategory(sendId, category);
      await load();
    } catch {
      /* keep the old badge on failure */
    } finally {
      setSavingId(null);
    }
  };

  const fmtDate = (iso: string | null) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  const totalReplies = Object.values(data?.counts ?? {}).reduce((a, b) => a + b, 0);

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      {/* Screen-reader announcement of the loading state. */}
      <StatusLive loading={loading} loadingLabel="Loading your replies…" />

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Inbox</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Inbound replies detected via IMAP threading. Opt-outs are suppressed workspace-wide the
            moment they land.
          </p>
        </div>
        <a
          href="/email-health"
          className="inline-flex items-center gap-1.5 justify-self-start rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600 transition-colors sm:justify-self-end focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Poll now
        </a>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        {CATEGORY_TABS.map((t) => {
          const count = t.key === "" ? totalReplies : data?.counts?.[t.key] ?? 0;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold border transition-colors ${
                tab === t.key
                  ? "bg-slate-900 text-white border-slate-900"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {t.label}
              <span className={tab === t.key ? "text-slate-300" : "text-slate-500"}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* Inline error with a retry — a toast disappears, this stays. */}
      {error && !loading && (
        <ErrorState
          title="Could not load your replies"
          message={error}
          onRetry={load}
        />
      )}

      {loading ? (
        <div className="min-h-[320px] space-y-3" aria-hidden="true">
          <CardSkeleton lines={2} />
          <CardSkeleton lines={2} />
          <CardSkeleton lines={2} />
        </div>
      ) : !data || data.items.length === 0 ? (
        tab ? (
          /* Filtered to nothing — the replies are there, the filter is narrow. */
          <EmptyState
            icon={<FilterX className="h-5 w-5" />}
            title={`No ${CATEGORY_LABEL[tab]?.toLowerCase() ?? tab} replies`}
            description={
              totalReplies > 0
                ? `You have ${totalReplies} repl${totalReplies === 1 ? "y" : "ies"} in total, but none of them are in this category right now.`
                : "Replies are matched by message-threading when the poller sweeps your mailboxes."
            }
            action={
              <button
                onClick={() => setTab("")}
                className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700"
              >
                Show all replies
              </button>
            }
          />
        ) : (
          <EmptyState
            icon={<InboxIcon className="h-5 w-5" />}
            title="No replies yet"
            description="Replies are matched by message-threading when the poller sweeps your mailboxes (every 5 minutes, or hit “Poll now” on Email Health)."
            action={
              <a
                href="/email-health"
                className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Poll mailboxes
              </a>
            }
            secondaryAction={
              <a
                href="/sequences"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
              >
                <Send className="w-3.5 h-3.5" /> Send your first sequence
              </a>
            }
          />
        )
      ) : (
        <div className="space-y-3">
          {data.items.map((item: InboxItem) => (
            <div key={item.send_id} className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold text-slate-900 truncate">
                      {item.contact_name || item.contact_email || `Contact #${item.send_id}`}
                    </span>
                    <span
                      className={`rounded-lg border px-2 py-0.5 text-[10px] font-bold ${
                        CATEGORY_STYLE[item.category] ?? CATEGORY_STYLE.other
                      }`}
                    >
                      {CATEGORY_LABEL[item.category] ?? item.category}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {item.contact_email}
                    {item.business_name ? ` · ${item.business_name}` : ""}
                    {item.campaign_name ? ` · ${item.campaign_name}` : ""}
                    {item.replied_at ? ` · ${fmtDate(item.replied_at)}` : ""}
                  </p>
                </div>
                <select
                  value={item.category}
                  disabled={savingId === item.send_id}
                  onChange={(e) => recategorize(item.send_id, e.target.value)}
                  className="shrink-0 h-8 rounded-lg border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 focus:outline-none disabled:opacity-50"
                  aria-label={`Reclassify the reply from ${item.contact_email ?? item.contact_name ?? item.send_id}`}
                >
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              {item.step_subject && (
                <p className="mt-2.5 flex items-center gap-1.5 text-[11px] text-slate-500">
                  <Mail className="w-3 h-3" /> replied to: <span className="text-slate-600">{item.step_subject}</span>
                </p>
              )}
              {item.reply_body && (
                <pre className="mt-2 rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-[12px] text-slate-700 whitespace-pre-wrap font-sans max-h-40 overflow-y-auto">
                  {item.reply_body}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
