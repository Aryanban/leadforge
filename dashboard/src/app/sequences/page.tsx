"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Send,
  Plus,
  Loader2,
  Save,
  Eye,
  Trash2,
  Clock,
  Users,
} from "lucide-react";
import { api, CampaignItem } from "@/lib/api";
import { SequenceDetail } from "@/components/SequenceDetail";
import { FestivalHook } from "@/components/IndiaKit";

type Step = { subject: string; subject_b: string; body_text: string; delay_days: number };

const VARIABLES = [
  "{{business_name}}",
  "{{first_name}}",
  "{{city}}",
  "{{category}}",
  "{{phone}}",
  "{{ai_icebreaker}}",
];

const STATUS_TABS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "paused", label: "Paused" },
  { key: "draft", label: "Draft" },
  { key: "completed", label: "Completed" },
];

const STATUS_STYLE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
  draft: "bg-slate-50 text-slate-600 border-slate-200",
  completed: "bg-blue-50 text-blue-700 border-blue-200",
};

/**
 * Sequences — the Apollo "Sequences" surface in one page.
 *
 * Previously split across /campaigns (list + detail) and /sequences (builder
 * only), which confused the mental model. Now: a stat-tabbed table (Apollo's
 * status tabs) where a row opens the detail slide-over, and "New Sequence"
 * opens the step builder (Apollo's vertical timeline: steps separated by
 * "wait N days" connectors). Every step is plain text you own.
 */
export default function SequencesPage() {
  const [campaigns, setCampaigns] = useState<CampaignItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("all");
  const [detailId, setDetailId] = useState<number | null>(null);

  // Builder state
  const [builderOpen, setBuilderOpen] = useState(false);
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<Step[]>([
    { subject: "Quick question about {{business_name}}", subject_b: "", body_text: "", delay_days: 0 },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewIdx, setPreviewIdx] = useState<number | null>(null);
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setCampaigns(await api.getCampaigns());
    } catch {
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateStep = (idx: number, patch: Partial<Step>) =>
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));

  const addStep = () =>
    setSteps((prev) => [...prev, { subject: "", subject_b: "", body_text: "", delay_days: 3 }]);

  const removeStep = (idx: number) =>
    setSteps((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));

  const insertVar = (idx: number, tag: string) =>
    updateStep(idx, {
      body_text: `${steps[idx].body_text}${steps[idx].body_text ? " " : ""}${tag}`,
    });

  const doPreview = async (idx: number) => {
    try {
      setPreviewIdx(idx);
      const res = await api.previewTemplate(steps[idx].subject, steps[idx].body_text);
      setPreview({ subject: res.rendered_subject, body: res.rendered_body });
    } catch {
      setPreview(null);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.createCampaign({
        name: name.trim() || `Sequence ${new Date().toLocaleDateString()}`,
        steps: steps.map((s) => ({
          subject: s.subject,
          subject_b: s.subject_b.trim() || undefined,
          body_text: s.body_text,
          delay_days: s.delay_days,
        })),
      });
      setBuilderOpen(false);
      setName("");
      setSteps([{ subject: "Quick question about {{business_name}}", subject_b: "", body_text: "", delay_days: 0 }]);
      await load();
    } catch (e: any) {
      setError(e.message || "Could not save sequence.");
    } finally {
      setSaving(false);
    }
  };

  const filtered = campaigns.filter((c) => tab === "all" || c.status === tab);
  const tabCount = (key: string) =>
    key === "all" ? campaigns.length : campaigns.filter((c) => c.status === key).length;

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Sequences</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Multi-step cold outreach. Click a sequence to launch, pause, or inspect performance.
          </p>
        </div>
        <button
          onClick={() => setBuilderOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors shadow-xs"
        >
          <Plus className="w-4 h-4" /> New Sequence
        </button>
      </div>

      <FestivalHook />

      <div className="flex items-center gap-1.5 flex-wrap">
        {STATUS_TABS.map((t) => (
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
            <span className={tab === t.key ? "text-slate-300" : "text-slate-400"}>
              {tabCount(t.key)}
            </span>
          </button>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-semibold">Name</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 font-semibold text-right">Steps</th>
              <th className="px-4 py-3 font-semibold text-right">Recipients</th>
              <th className="px-4 py-3 font-semibold text-right">Sent</th>
              <th className="px-4 py-3 font-semibold text-right">Replied</th>
              <th className="px-4 py-3 font-semibold text-right">Reply rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
                  Loading sequences...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-5 py-12 text-center">
                  <p className="text-sm text-slate-500">
                    {campaigns.length === 0
                      ? "No sequences yet. Build one with New Sequence, then add recipients from the Lead Database."
                      : `No ${tab} sequences.`}
                  </p>
                </td>
              </tr>
            ) : (
              filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setDetailId(c.id)}
                  className="cursor-pointer hover:bg-slate-50/80 transition-colors"
                >
                  <td className="px-5 py-3.5">
                    <span className="text-sm font-bold text-slate-900">{c.name}</span>
                  </td>
                  <td className="px-4 py-3.5">
                    <span
                      className={`rounded-lg border px-2 py-0.5 text-[11px] font-semibold capitalize ${
                        STATUS_STYLE[c.status] ?? STATUS_STYLE.draft
                      }`}
                    >
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">{c.step_count}</td>
                  <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">
                    {c.contacts_selected}
                  </td>
                  <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">{c.sent_count}</td>
                  <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">{c.replied_count}</td>
                  <td className="px-4 py-3.5 text-right text-sm font-semibold text-slate-900 tabular-nums">
                    {c.reply_rate}%
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Builder dialog — Apollo's vertical step timeline in miniature */}
      {builderOpen && (
        <div className="fixed inset-0 z-30 flex items-start justify-center p-6 overflow-y-auto">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setBuilderOpen(false)} />
          <div className="relative w-full max-w-2xl my-8 rounded-2xl border border-slate-200 bg-white shadow-xl">
            <div className="border-b border-slate-200 px-6 py-4 flex items-center gap-3">
              <h2 className="text-lg font-bold text-slate-900">New Sequence</h2>
              <button
                onClick={() => setBuilderOpen(false)}
                aria-label="Close"
                className="ml-auto p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"
              >
                <Trash2 className="w-4 h-4 rotate-45" />
              </button>
            </div>

            <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">Sequence name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Q4 Dentist Outreach"
                  className="w-full h-10 px-3 rounded-xl border border-slate-200 bg-slate-50/50 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
                />
              </div>

              {steps.map((s, idx) => (
                <div key={idx} className="rounded-xl border border-slate-200 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="rounded-lg bg-blue-50 border border-blue-200 px-2 py-0.5 text-[11px] font-bold text-blue-700">
                      Step {idx + 1}
                    </span>
                    {idx > 0 && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                        <Clock className="w-3 h-3" /> wait {s.delay_days}d
                      </span>
                    )}
                    <button
                      onClick={() => removeStep(idx)}
                      disabled={steps.length <= 1}
                      className="ml-auto p-1 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 disabled:opacity-30 disabled:hover:bg-transparent"
                      aria-label={`Remove step ${idx + 1}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">Subject</label>
                    <input
                      value={s.subject}
                      onChange={(e) => updateStep(idx, { subject: e.target.value })}
                      placeholder="Subject line"
                      className="w-full h-9 px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                      Variant B subject <span className="font-normal text-slate-400">(optional A/B test)</span>
                    </label>
                    <input
                      value={s.subject_b}
                      onChange={(e) => updateStep(idx, { subject_b: e.target.value })}
                      placeholder="Second subject line for a 50/50 split test"
                      className="w-full h-9 px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">Body</label>
                    <textarea
                      value={s.body_text}
                      onChange={(e) => updateStep(idx, { body_text: e.target.value })}
                      rows={5}
                      placeholder="Email body. Use {{business_name}}, {{first_name}}, {{city}}..."
                      className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
                    />
                    <div className="flex flex-wrap gap-1 mt-2">
                      {VARIABLES.map((v) => (
                        <button
                          key={v}
                          onClick={() => insertVar(idx, v)}
                          className="rounded-lg border border-slate-200 px-1.5 py-0.5 text-[10px] font-mono text-slate-500 hover:border-blue-300 hover:text-blue-600 transition-colors"
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {idx > 0 && (
                      <div className="flex items-center gap-1.5">
                        <label className="text-[11px] font-semibold text-slate-600">Delay</label>
                        <input
                          type="number"
                          min={0}
                          value={s.delay_days}
                          onChange={(e) => updateStep(idx, { delay_days: Math.max(0, parseInt(e.target.value) || 0) })}
                          className="w-16 h-8 px-2 rounded-lg border border-slate-200 text-sm text-center"
                        />
                        <span className="text-[11px] text-slate-500">days</span>
                      </div>
                    )}
                    <button
                      onClick={() => doPreview(idx)}
                      className="ml-auto inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600"
                    >
                      <Eye className="w-3 h-3" /> Preview
                    </button>
                  </div>

                  {previewIdx === idx && preview && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-1.5">
                      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Preview (sample data)</p>
                      <p className="text-[13px] font-semibold text-slate-900">{preview.subject}</p>
                      <pre className="text-[12px] text-slate-600 whitespace-pre-wrap font-sans">{preview.body}</pre>
                    </div>
                  )}
                </div>
              ))}

              <button
                onClick={addStep}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-700"
              >
                <Plus className="w-3.5 h-3.5" /> Add follow-up step
              </button>

              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3 flex items-start gap-2.5">
                <Users className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Saving creates the sequence as a <strong>draft</strong>. Next, pick leads on the{" "}
                  <a href="/leads" className="text-blue-600 font-semibold hover:underline">
                    Lead Database
                  </a>{" "}
                  and choose <strong>Add to Sequence</strong>. Launch refuses a sequence with no
                  recipients — by design.
                </p>
              </div>

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-medium text-red-700">
                  {error}
                </div>
              )}
            </div>

            <div className="border-t border-slate-200 px-6 py-4 flex justify-end gap-2">
              <button
                onClick={() => setBuilderOpen(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs"
              >
                Cancel
              </button>
              <button
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                Save sequence
              </button>
            </div>
          </div>
        </div>
      )}

      {detailId !== null && (
        <SequenceDetail
          campaignId={detailId}
          onClose={() => {
            setDetailId(null);
            load();
          }}
        />
      )}
    </div>
  );
}
