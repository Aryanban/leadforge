"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Plug,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Mail,
  Copy,
  Check,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import { api, SetupStatus } from "@/lib/api";

/**
 * Connections — the one-stop page that makes LeadForge fully functional.
 *
 * Everything a user must insert lives here (or links one click away): the
 * SMTP mailbox (the only hard requirement for sending), IMAP for reply
 * detection, and a transparent readout of the environment knobs
 * (TRACKING_DOMAIN, PROXY_LIST, SECRET_KEY) with exact remediation steps.
 * AI features need no key — icebreakers and scoring are on-device.
 */
export default function SetupPage() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  // Inline quick settings (TRACKING_DOMAIN / PROXY_LIST) — live apply + .env persist.
  const [editValue, setEditValue] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api.getSetupStatus());
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saveSetting = async (key: string) => {
    setSavingKey(key);
    setSaveMsg(null);
    try {
      const res = await api.updateSetupSetting(key, editValue[key] ?? "");
      setSaveMsg(
        `${res.label} saved — ${res.persisted ? "persists across restarts" : "applied for this session"}` +
          (res.restart_required ? " · restart the backend for this one to take effect" : ""),
      );
      await load();
    } catch (e: any) {
      setSaveMsg(e.message || "That value isn't valid — check the format.");
    } finally {
      setSavingKey(null);
    }
  };

  const rerunWizard = () => {
    try {
      localStorage.removeItem("leadforge.setup.v1");
    } catch {
      /* private mode */
    }
    window.location.reload();
  };

  const mcpSnippet =
    '{\n  "mcpServers": {\n    "leadforge": {\n      "command": "/absolute/path/to/leadforge/.venv/bin/python",\n      "args": ["-m", "app.mcp_server"],\n      "cwd": "/absolute/path/to/leadforge/backend"\n    }\n  }\n}';

  const copyMcp = async () => {
    try {
      await navigator.clipboard.writeText(mcpSnippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      /* clipboard blocked — the block below is selectable text */
    }
  };


  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Connections</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Everything you need to make LeadForge fully functional, in one place.
        </p>
      </div>

      <button
        onClick={rerunWizard}
        className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50/60 px-4 py-2.5 text-sm font-semibold text-blue-700 hover:bg-blue-50 transition-colors"
      >
        <Sparkles className="w-4 h-4" />
        Run the guided setup wizard (recommended for first-time users)
      </button>

      {loading ? (
        <div className="text-center py-12 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
          Checking connections...
        </div>
      ) : !status ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Could not reach the backend. Is it running on port 8000?
        </div>
      ) : (
        <>
          {/* Readiness banner */}
          <div
            className={`rounded-2xl border p-5 ${
              status.ready ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"
            }`}
          >
            <div className="flex items-center gap-2.5">
              {status.ready ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              ) : (
                <AlertCircle className="w-5 h-5 text-amber-600" />
              )}
              <h2 className="text-sm font-bold text-slate-900">
                {status.ready
                  ? "Ready to send"
                  : "Almost there — one required connection is missing"}
              </h2>
              <button
                onClick={load}
                className="ml-auto p-1.5 rounded-lg hover:bg-white/60 text-slate-400"
                aria-label="Re-check"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-xs text-slate-600 mt-1.5">
              Database: <span className="font-semibold">{status.db_type}</span> ·
              API base: <span className="font-semibold">{status.api_url}</span>
            </p>
          </div>

          {/* Checklist */}
          <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100">
            {status.checks.map((c) => (
              <div key={c.key} className="flex items-start gap-3 p-4">
                {c.ok ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                ) : c.required ? (
                  <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-slate-900 flex items-center gap-2 flex-wrap">
                    {c.label}
                    {c.required ? (
                      <span className="rounded bg-red-50 border border-red-200 px-1.5 py-0.5 text-[10px] font-bold text-red-600">
                        required
                      </span>
                    ) : (
                      <span className="rounded bg-slate-50 border border-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
                        optional
                      </span>
                    )}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{c.detail}</p>
                </div>
                {c.href && (
                  <Link
                    href={c.href}
                    className="shrink-0 text-[11px] font-bold text-blue-600 hover:underline mt-0.5"
                  >
                    Fix →
                  </Link>
                )}
              </div>
            ))}
          </div>

          {/* AI note — no key needed */}
          <div className="rounded-2xl border border-blue-200 bg-blue-50/60 p-4 flex items-start gap-2.5">
            <Sparkles className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
            <div>
              <p className="text-[13px] font-semibold text-slate-900">No AI API key needed</p>
              <p className="text-[11px] text-slate-600 mt-0.5 leading-relaxed">{status.ai_note}</p>
            </div>
          </div>

          {/* Quick settings — deploy-critical values, editable in place */}
          <section className="space-y-3" id="quick-settings">
            <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Quick settings — saved for you, no need to edit files
            </h2>
            {saveMsg && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-800">
                {saveMsg}
              </div>
            )}
            <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100">
              {(["TRACKING_DOMAIN", "PROXY_LIST"] as const).map((key) => {
                const cfg = status.runtime_settings?.[key];
                if (!cfg) return null;
                return (
                  <div key={key} className="p-4 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[13px] font-semibold text-slate-900">{cfg.label}</span>
                      <code className="text-[10px] font-mono text-slate-400">{key}</code>
                      {cfg.restart_required && (
                        <span className="rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
                          restart needed
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        value={editValue[key] ?? cfg.value}
                        onChange={(e) => setEditValue((prev) => ({ ...prev, [key]: e.target.value }))}
                        placeholder={cfg.placeholder}
                        className="flex-1 h-9 px-3 rounded-xl border border-slate-200 bg-slate-50/50 text-xs font-mono focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
                        aria-label={cfg.label}
                      />
                      <button
                        onClick={() => saveSetting(key)}
                        disabled={savingKey === key}
                        className="inline-flex items-center gap-1 rounded-xl bg-slate-900 text-white px-3.5 h-9 text-xs font-semibold hover:bg-slate-800 disabled:opacity-50"
                      >
                        {savingKey === key && <Loader2 className="w-3 h-3 animate-spin" />}
                        Save
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Mailboxes */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5" /> Sending mailboxes ({status.mailboxes.length})
            </h2>
            {status.mailboxes.map((m) => (
              <div key={m.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[13px] font-bold text-slate-900">{m.email}</span>
                  {m.is_active ? (
                    <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">
                      <ShieldCheck className="w-3 h-3" /> active
                    </span>
                  ) : (
                    <span className="rounded-lg bg-slate-50 border border-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
                      inactive
                    </span>
                  )}
                  {m.health_paused && (
                    <span className="rounded-lg bg-red-50 border border-red-200 px-1.5 py-0.5 text-[10px] font-bold text-red-700">
                      health-paused
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  SMTP {m.smtp_host}:{m.smtp_port} · limit {m.daily_limit}/day ·
                  IMAP {m.imap_host ? `${m.imap_host}:${m.imap_port}` : "auto-detect"}
                </p>
                <div className="flex items-center gap-3 mt-2">
                  <Link
                    href="/email-health"
                    className="text-[11px] font-bold text-blue-600 hover:underline"
                  >
                    Manage & poll replies →
                  </Link>
                </div>
              </div>
            ))}
            <Link
              href="/settings"
              className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors"
            >
              <Plug className="w-4 h-4" />
              {status.mailboxes.length === 0 ? "Add your first mailbox" : "Add another mailbox"}
            </Link>
          </section>

          {/* Environment keys */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Environment settings (backend/.env) — all optional except SECRET_KEY in production
            </h2>
            <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100">
              {status.env_keys.map((e) => (
                <div key={e.key} className="flex items-start gap-3 px-4 py-2.5">
                  <code className="text-[11px] font-mono font-bold text-slate-800 shrink-0 w-40">
                    {e.key}
                  </code>
                  <p className="text-[11px] text-slate-500 flex-1">{e.note}</p>
                  {e.required && (
                    <span className="shrink-0 rounded bg-red-50 border border-red-200 px-1.5 py-0.5 text-[10px] font-bold text-red-600">
                      required
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* MCP snippet */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Agent access (MCP) — optional, for Claude/Cursor users
            </h2>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] text-slate-500 mb-2">
                Paste into your editor&apos;s MCP config, replacing the two absolute paths with
                yours. Gives an AI agent all 17 LeadForge tools.
              </p>
              <pre className="rounded-lg bg-slate-900 text-slate-100 p-3 text-[11px] font-mono overflow-x-auto">
                {mcpSnippet}
              </pre>
              <button
                onClick={copyMcp}
                className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied ? "Copied" : "Copy snippet"}
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

