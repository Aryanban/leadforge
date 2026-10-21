"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Loader2, RefreshCw, Mail, AlertTriangle, ShieldCheck, Plug } from "lucide-react";
import { api, MailboxItem } from "@/lib/api";
import { CardSkeleton, EmptyState, ErrorState, StatusLive } from "@/components/PageStates";

/**
 * Email Health — Apollo's Email Health tab, self-hosted edition.
 * Every number is real engine state: rolling 24h budgets, warmup ramps
 * (new mailboxes start at 10/day, ramp over 14 days), reputation scores,
 * and health-paused mailboxes (held out of rotation until reviewed).
 */
export default function EmailHealthPage() {
  const [mailboxes, setMailboxes] = useState<MailboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pollingId, setPollingId] = useState<number | null>(null);
  const [pollMessage, setPollMessage] = useState<string | null>(null);
  // Inline IMAP editor (reply detection host/port override).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState(993);
  const [imapSaving, setImapSaving] = useState(false);
  const [imapError, setImapError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      setMailboxes(await api.getMailboxes());
    } catch (err: any) {
      setMailboxes([]);
      setLoadError(
        err?.message || "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pollNow = async (id: number) => {
    setPollingId(id);
    try {
      const res = await api.pollReplies(id);
      setPollMessage(
        res.error
          ? `Poll failed: ${res.error}`
          : `Scanned ${res.seen ?? 0} · ${res.matched ?? 0} matched · ${res.replies ?? 0} new repl${res.replies === 1 ? "y" : "ies"}${res.opt_outs ? ` · ${res.opt_outs} opt-out(s) suppressed` : ""}`,
      );
    } catch (e: any) {
      setPollMessage(e.message || "Poll failed.");
    } finally {
      setPollingId(null);
    }
  };

  const rampStage = (mb: MailboxItem) => {
    const created = mb.created_at ? new Date(mb.created_at) : null;
    if (!created) return "unknown age";
    const days = Math.max(0, Math.floor((Date.now() - created.getTime()) / 86400000));
    return days < 14 ? `ramping · day ${days}/14` : "fully warmed";
  };

  const startImapEdit = (mb: MailboxItem) => {
    setEditingId(mb.id);
    setImapHost(mb.imap_host ?? "");
    setImapPort(mb.imap_port ?? 993);
    setImapError(null);
  };

  const saveImap = async () => {
    if (editingId === null) return;
    setImapSaving(true);
    setImapError(null);
    try {
      await api.updateMailboxImap(editingId, imapHost.trim() || null, imapPort);
      setEditingId(null);
      await load();
    } catch (e: any) {
      setImapError(e.message || "Could not save IMAP settings.");
    } finally {
      setImapSaving(false);
    }
  };

  const healthPct = (mb: MailboxItem) => Math.round((mb.health_score ?? 1) * 100);
  const healthColor = (pct: number) =>
    pct >= 90 ? "bg-emerald-500" : pct >= 75 ? "bg-amber-400" : "bg-red-500";

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      {/* Screen-reader announcement of the loading state. */}
      <StatusLive loading={loading} loadingLabel="Loading mailbox health…" />

      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Email Health</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Mailbox reputation, warmup progress, and daily budgets. Health-paused mailboxes are held
          out of rotation until reviewed.
        </p>
      </div>

      {pollMessage && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs font-medium text-blue-800">
          {pollMessage}
        </div>
      )}

      {/* Inline error with a retry — a toast disappears, this stays. */}
      {loadError && !loading && (
        <ErrorState
          title="Could not load mailbox health"
          message={loadError}
          onRetry={load}
        />
      )}

      {loading ? (
        <div className="min-h-[280px] grid gap-4 md:grid-cols-2" aria-hidden="true">
          <CardSkeleton lines={3} />
          <CardSkeleton lines={3} />
        </div>
      ) : mailboxes.length === 0 ? (
        <EmptyState
          icon={<Plug className="h-5 w-5" />}
          title="No mailboxes yet"
          description="Add your first sending mailbox to see its reputation, warmup progress and daily budget."
          action={
            <a
              href="/settings"
              className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
            >
              <Plug className="w-3.5 h-3.5" /> Add a mailbox
            </a>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {mailboxes.map((mb) => {
            const pct = healthPct(mb);
            const used = mb.sent_today ?? 0;
            const limit = mb.daily_limit ?? 50;
            const usedPct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
            return (
              <div key={mb.id} className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-slate-900 truncate">{mb.email}</p>
                    <p className="text-[11px] text-slate-500">{mb.smtp_host}:{mb.smtp_port}</p>
                  </div>
                  {mb.health_paused ? (
                    <span className="shrink-0 inline-flex items-center gap-1 rounded-lg bg-red-50 border border-red-200 px-2 py-0.5 text-[11px] font-bold text-red-700">
                      <AlertTriangle className="w-3 h-3" /> health-paused
                    </span>
                  ) : mb.is_active ? (
                    <span className="shrink-0 inline-flex items-center gap-1 rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
                      <ShieldCheck className="w-3 h-3" /> active
                    </span>
                  ) : (
                    <span className="shrink-0 rounded-lg bg-slate-50 border border-slate-200 px-2 py-0.5 text-[11px] font-bold text-slate-500">
                      inactive
                    </span>
                  )}
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1.5">
                    <span className="font-semibold flex items-center gap-1">
                      <Activity className="w-3 h-3" /> Reputation
                    </span>
                    <span className="tabular-nums font-bold text-slate-700">{pct}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div className={`h-full rounded-full ${healthColor(pct)}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1.5">
                    <span className="font-semibold">Daily budget</span>
                    <span className="tabular-nums">
                      <span className="font-bold text-slate-700">{used}</span> / {limit}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full rounded-full bg-blue-500" style={{ width: `${usedPct}%` }} />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span className="text-[11px] text-slate-500 capitalize">{rampStage(mb)}</span>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => (editingId === mb.id ? setEditingId(null) : startImapEdit(mb))}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600"
                    >
                      IMAP settings
                    </button>
                    <button
                      onClick={() => pollNow(mb.id)}
                      disabled={pollingId === mb.id}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600 disabled:opacity-50"
                    >
                      {pollingId === mb.id ? <Loader2 className="w-3 h-3 motion-safe:animate-spin motion-reduce:animate-pulse" /> : <RefreshCw className="w-3 h-3" />}
                      Poll replies
                    </button>
                  </div>
                </div>

                {editingId === mb.id && (
                  <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3 space-y-2">
                    <p className="text-[11px] text-slate-600 leading-relaxed">
                      Where should reply detection read from? Leave <strong>empty</strong> to
                      auto-derive from your SMTP host (smtp.gmail.com → imap.gmail.com), or
                      enter a custom IMAP host below.
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      <input
                        value={imapHost}
                        onChange={(e) => setImapHost(e.target.value)}
                        placeholder="imap.example.com (auto if empty)"
                        className="col-span-2 h-9 px-2.5 rounded-lg border border-slate-200 text-xs font-mono bg-white"
                        aria-label="IMAP host"
                      />
                      <input
                        type="number"
                        value={imapPort}
                        onChange={(e) => setImapPort(parseInt(e.target.value) || 993)}
                        className="h-9 px-2.5 rounded-lg border border-slate-200 text-xs font-mono text-center bg-white"
                        aria-label="IMAP port"
                      />
                    </div>
                    {imapError && (
                      <p className="text-[11px] font-medium text-red-700">{imapError}</p>
                    )}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={saveImap}
                        disabled={imapSaving}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-600 text-white px-3 py-1.5 text-[11px] font-semibold hover:bg-blue-700 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                      >
                        {imapSaving && <Loader2 className="w-3 h-3 motion-safe:animate-spin motion-reduce:animate-pulse" />}
                        Save
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
