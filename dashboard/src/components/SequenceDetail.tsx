"use client";

import { useEffect, useState } from "react";
import { X, Play, Pause, Loader2, Users, Mail, Trophy, AlertTriangle } from "lucide-react";
import { api, StepStat, CampaignTargetItem } from "@/lib/api";
import { toast } from "@/components/Toaster";

const STATUS_STYLE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
  draft: "bg-slate-50 text-slate-600 border-slate-200",
  completed: "bg-blue-50 text-blue-700 border-blue-200",
};

/**
 * Apollo-style sequence detail slide-over: status + actions, per-step stats
 * (with A/B variant comparison and winner badge), and the explicit target
 * list. Everything comes from real API state — no stored analytics.
 */
export function SequenceDetail({
  campaignId,
  onClose,
}: {
  campaignId: number;
  onClose: () => void;
}) {
  const [camp, setCamp] = useState<any | null>(null);
  const [stats, setStats] = useState<StepStat[]>([]);
  const [targets, setTargets] = useState<CampaignTargetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmLaunch, setConfirmLaunch] = useState(false);

  const load = async () => {
    try {
      const [c, s, t] = await Promise.all([
        api.getCampaign(campaignId),
        api.getStepStats(campaignId),
        api.getCampaignTargets(campaignId),
      ]);
      setCamp(c);
      setStats(s.steps);
      setTargets(t.targets);
    } catch {
      setCamp(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  const act = async (kind: "launch" | "pause") => {
    setBusy(true);
    try {
      const res = kind === "launch"
        ? await api.launchCampaign(campaignId)
        : await api.pauseCampaign(campaignId);
      setMessage(res.message || "Done.");
      if (kind === "launch") {
        toast.success("Sequence launched", res.message || "Sending has started.");
      } else {
        toast.info("Sequence paused", res.message || "Sending is paused.");
      }
      await load();
    } catch (e: any) {
      setMessage(e.message || "Action failed.");
      toast.error(kind === "launch" ? "Could not launch sequence" : "Could not pause sequence", e.message);
    } finally {
      setBusy(false);
      setConfirmLaunch(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <div className="relative w-full max-w-xl h-full bg-white border-l border-slate-200 shadow-xl flex flex-col">
        <div className="h-14 shrink-0 border-b border-slate-200 flex items-center gap-3 px-5">
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
          ) : (
            <>
              <h2 className="text-sm font-bold text-slate-900 truncate">
                {camp?.name ?? `Campaign #${campaignId}`}
              </h2>
              <span
                className={`shrink-0 rounded-lg border px-2 py-0.5 text-[11px] font-semibold capitalize ${
                  STATUS_STYLE[camp?.status] ?? STATUS_STYLE.draft
                }`}
              >
                {camp?.status}
              </span>
            </>
          )}
          <button
            onClick={onClose}
            aria-label="Close"
            className="ml-auto p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {message && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs font-medium text-blue-800">
              {message}
            </div>
          )}

          <div className="flex items-center gap-2">
            {camp?.status !== "active" ? (
              <button
                onClick={() => setConfirmLaunch(true)}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 text-white px-4 py-2 text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Launch
              </button>
            ) : (
              <button
                onClick={() => act("pause")}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500 text-white px-4 py-2 text-xs font-semibold hover:bg-amber-600 disabled:opacity-50"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Pause className="w-3.5 h-3.5" />}
                Pause
              </button>
            )}
          </div>

          <section>
            <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5" /> Sequence steps & performance
            </h3>
            <div className="space-y-2">
              {stats.length === 0 && !loading && (
                <p className="text-xs text-slate-400">No steps.</p>
              )}
              {stats.map((s) => (
                <div key={s.step_id} className="rounded-xl border border-slate-200 p-3.5">
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 rounded-lg bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
                      Step {s.step_number}
                    </span>
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-slate-900 truncate">{s.subject}</p>
                      {s.subject_b && (
                        <p className="text-[11px] text-slate-500 truncate">Variant B: {s.subject_b}</p>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    <span>{s.sent} sent</span>
                    <span>{s.replied} replied</span>
                    <span>{s.bounced} bounced</span>
                    <span className="font-semibold text-slate-700">{s.reply_rate}% reply rate</span>
                    {s.variants?.winner && (
                      <span className="inline-flex items-center gap-1 rounded-lg bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
                        <Trophy className="w-3 h-3" /> Winner: {s.variants.winner.toUpperCase()}
                      </span>
                    )}
                  </div>
                  {s.variants && (
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {(["a", "b"] as const).map((v) => (
                        <div
                          key={v}
                          className={`rounded-lg border p-2 text-[11px] ${
                            s.variants?.winner === v
                              ? "border-amber-300 bg-amber-50"
                              : "border-slate-200 bg-slate-50/50"
                          }`}
                        >
                          <span className="font-bold uppercase">{v}</span>: {s.variants![v].sent} sent, {s.variants![v].replied} replied ({s.variants![v].reply_rate}%)
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Recipients ({targets.length})
            </h3>
            <div className="rounded-xl border border-slate-200 divide-y divide-slate-100 max-h-72 overflow-y-auto">
              {targets.length === 0 && (
                <p className="text-xs text-slate-400 p-3">No recipients yet.</p>
              )}
              {targets.map((t) => (
                <div key={t.contact_id} className="flex items-center gap-3 px-3.5 py-2.5">
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold text-slate-900 truncate">
                      {t.name || t.email || `Contact #${t.contact_id}`}
                    </p>
                    {t.business_name && (
                      <p className="text-[11px] text-slate-500 truncate">{t.business_name}</p>
                    )}
                  </div>
                  {t.is_verified && (
                    <span className="ml-auto shrink-0 rounded-lg bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">
                      verified
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* Launch confirmation — this sends real cold email, so the operator
          gets to see the blast radius before anything leaves the building. */}
      {confirmLaunch && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setConfirmLaunch(false)} />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="launch-confirm-title"
            className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl space-y-4"
          >
            <div className="flex items-start gap-3">
              <span className="w-9 h-9 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-4 h-4" />
              </span>
              <div className="min-w-0">
                <h3 id="launch-confirm-title" className="text-sm font-bold text-slate-900">
                  Launch this sequence now?
                </h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                  Real cold email starts going out to your recipients. This cannot be
                  unsent.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">
                  Recipients
                </span>
                <div className="text-xl font-extrabold text-slate-900">{targets.length}</div>
                <div className="text-[11px] text-slate-500">email{targets.length === 1 ? "" : "s"} in this blast</div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">
                  Steps
                </span>
                <div className="text-xl font-extrabold text-slate-900">{stats.length}</div>
                <div className="text-[11px] text-slate-500">
                  email{stats.length === 1 ? "" : "s"} in the sequence
                </div>
              </div>
            </div>

            {targets.length === 0 && (
              <p className="text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                This sequence has no recipients — add contacts before launching.
              </p>
            )}

            <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-100">
              <button
                onClick={() => setConfirmLaunch(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs"
              >
                Cancel
              </button>
              <button
                onClick={() => act("launch")}
                disabled={busy || targets.length === 0}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs disabled:opacity-50"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Launch {targets.length} recipient{targets.length === 1 ? "" : "s"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
