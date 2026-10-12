"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Send,
  Plus,
  Trash2,
  Clock,
  Mail,
  Sparkles,
  Save,
  Loader2,
  Eye,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { FestivalHook } from "@/components/IndiaKit";

type Step = { subject: string; body_text: string; delay_days: number };

const VARIABLES = [
  "{{business_name}}",
  "{{first_name}}",
  "{{city}}",
  "{{category}}",
  "{{phone}}",
  "{{ai_icebreaker}}",
];

/**
 * Sequence builder — Apollo's step timeline in miniature.
 *
 * Apollo's defining pattern is a vertical list of email steps separated by
 * "wait N days" connectors. We reproduce that shape so the mental model
 * transfers, but every step is plain text you own (no token limits, no
 * per-send pricing).
 */
export default function SequencesPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<Step[]>([
    { subject: "Quick question about {{business_name}}", body_text: "", delay_days: 0 },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewIdx, setPreviewIdx] = useState<number | null>(null);
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(null);

  const updateStep = (idx: number, patch: Partial<Step>) =>
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));

  const addStep = () =>
    setSteps((prev) => [...prev, { subject: "", body_text: "", delay_days: 3 }]);

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
    if (!name.trim()) {
      setError("Give the sequence a name.");
      return;
    }
    if (steps.some((s) => !s.subject.trim() || !s.body_text.trim())) {
      setError("Every step needs a subject and a body.");
      return;
    }
    try {
      setSaving(true);
      setError(null);
      await api.createCampaign({ name: name.trim(), steps });
      router.push("/campaigns");
    } catch (e: any) {
      setError(e.message || "Could not save the sequence.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">New Sequence</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Build a multi-step follow-up. Each step sends only if the lead hasn&apos;t
            replied — replies and bounces stop the sequence automatically.
          </p>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold h-9 px-4 shadow-xs"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Save Sequence
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-800">
          {error}
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
          Sequence name
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Rohini Realtors — 3-step intro"
          className="mt-1.5 w-full h-10 px-3.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        />
      </div>

{/* Step timeline */}
      <div className="space-y-1">
        {steps.map((step, idx) => (
          <div key={idx}>
            {/* Wait connector between steps (Apollo's signature) */}
            {idx > 0 && (
              <div className="flex items-center gap-2 py-2.5 pl-1">
                <div className="w-7 flex justify-center">
                  <Clock className="w-4 h-4 text-slate-300" />
                </div>
                <span className="text-[11px] font-semibold text-slate-500">Wait</span>
                <input
                  type="number"
                  min={0}
                  value={step.delay_days}
                  onChange={(e) => updateStep(idx, { delay_days: Number(e.target.value) })}
                  className="w-16 h-7 px-2 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
                <span className="text-[11px] font-semibold text-slate-500">
                  day(s) after the previous email
                </span>
              </div>
            )}

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-lg bg-blue-50 text-blue-700 text-[11px] font-bold">
                    {idx + 1}
                  </span>
                  <span className="text-[13px] font-bold text-slate-800">Email step {idx + 1}</span>
                  {idx === 0 && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                      starts the sequence
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => doPreview(idx)}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-blue-700 px-2 py-1 rounded-md hover:bg-slate-50"
                  >
                    <Eye className="w-3.5 h-3.5" /> Preview
                  </button>
                  {steps.length > 1 && (
                    <button
                      onClick={() => removeStep(idx)}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-red-600 px-2 py-1 rounded-md hover:bg-red-50"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Remove
                    </button>
                  )}
                </div>
              </div>

              <input
                value={step.subject}
                onChange={(e) => updateStep(idx, { subject: e.target.value })}
                placeholder="Subject line"
                className="w-full h-10 px-3.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />

              <textarea
                value={step.body_text}
                onChange={(e) => updateStep(idx, { body_text: e.target.value })}
                placeholder={"Hi {{first_name}},\n\nSaw {{business_name}} in {{city}}…"}
                rows={7}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-[13px] leading-relaxed text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 resize-y"
              />

              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mr-0.5">
                  + insert
                </span>
                {VARIABLES.map((v) => (
                  <button
                    key={v}
                    onClick={() => insertVar(idx, v)}
                    className="px-2 py-0.5 rounded-md bg-slate-50 border border-slate-200 text-[10px] font-mono text-slate-600 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200"
                  >
                    {v}
                  </button>
                ))}
                {idx === 0 && <FestivalHook />}
              </div>

              {previewIdx === idx && preview && (
                <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3.5 space-y-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-blue-700">
                    Rendered with sample lead data
                  </span>
                  <div className="text-[13px] font-bold text-slate-900">{preview.subject}</div>
                  <div className="text-[12px] text-slate-700 whitespace-pre-wrap leading-relaxed border-t border-blue-100 pt-2">
                    {preview.body}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={addStep}
        className="w-full rounded-2xl border-2 border-dashed border-slate-200 py-3.5 text-xs font-semibold text-slate-500 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50/40 inline-flex items-center justify-center gap-1.5"
      >
        <Plus className="w-4 h-4" /> Add follow-up step
      </button>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 flex items-start gap-3">
        <Users className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Saving creates the sequence as a <strong>draft</strong>. Next, pick leads on the{" "}
          <a href="/leads" className="text-blue-600 font-semibold hover:underline">
            Lead Database
          </a>{" "}
          and choose <strong>Add to Sequence</strong> — a sequence only ever emails the leads you
          explicitly selected.
        </p>
      </div>

      <p className="text-[11px] text-slate-400 flex flex-wrap items-center gap-1.5">
        <Mail className="w-3.5 h-3.5" /> A step is skipped automatically for leads who replied,
        bounced, or unsubscribed.
        <Send className="w-3.5 h-3.5 ml-1" /> Sends rotate across your mailboxes under the warmup
        and reputation limits.
      </p>
    </div>
  );
}