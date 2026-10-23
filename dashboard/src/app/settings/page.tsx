"use client";

import { useState, useEffect, useCallback } from "react";
import { 
  Settings as SettingsIcon, 
  Mail, 
  CheckCircle2, 
  AlertCircle, 
  Plus, 
  Trash2, 
  RefreshCw, 
  Server,
  Loader2,
  Send,
  Bot,
  Terminal,
  Copy,
  Check,
  Sparkles,
  ShieldCheck,
  Inbox as InboxIcon
} from "lucide-react";
import { api, MailboxItem } from "@/lib/api";
import { AuthBadge } from "@/components/IndiaKit";
import { toast } from "@/components/Toaster";
import { EmptyState, ErrorState, Skeleton, StatusLive } from "@/components/PageStates";

const PRESET_PROVIDERS = [
  { name: "Gmail", host: "smtp.gmail.com", port: 587 },
  { name: "Zoho", host: "smtp.zoho.in", port: 587 },
  { name: "Outlook / 365", host: "smtp.office365.com", port: 587 },
  { name: "Amazon SES", host: "email-smtp.us-east-1.amazonaws.com", port: 587 },
  { name: "SendGrid", host: "smtp.sendgrid.net", port: 587 },
];

export default function SettingsPage() {
  const [mailboxes, setMailboxes] = useState<MailboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { success: boolean; message: string }>>({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [copiedPlatform, setCopiedPlatform] = useState<string | null>(null);
  /**
   * Which mailboxes the operator asked us to check.
   *
   * The SPF/DKIM/DMARC probe is a live DNS lookup: a dozen sequential
   * resolver round-trips that can take the best part of a second. Doing it
   * for every mailbox on page load made this route twice as slow as every
   * other one in the app, so it is now an explicit, on-demand action.
   */
  const [authChecked, setAuthChecked] = useState<Record<number, boolean>>({});

  // Form state
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formHost, setFormHost] = useState("smtp.gmail.com");
  const [formPort, setFormPort] = useState(587);
  const [formFirstName, setFormFirstName] = useState("Outreach");
  const [formLastName, setFormLastName] = useState("Team");
  const [formLimit, setFormLimit] = useState(50);
  const [submitting, setSubmitting] = useState(false);

  const fetchMailboxes = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const data = await api.getMailboxes();
      setMailboxes(data);
    } catch (err: any) {
      console.warn("Could not fetch mailboxes:", err);
      setLoadError(
        err?.message || "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMailboxes();
  }, [fetchMailboxes]);

  const handleTestConnection = async (id: number) => {
    try {
      setTestingId(id);
      const res = await api.testMailbox(id);
      setTestResults((prev) => ({ ...prev, [id]: res }));
    } catch (err: any) {
      setTestResults((prev) => ({ ...prev, [id]: { success: false, message: err.message } }));
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to remove this mailbox?")) return;
    try {
      await api.deleteMailbox(id);
      toast.success("Mailbox removed", "The sender mailbox was deleted.");
      fetchMailboxes();
    } catch (err: any) {
      toast.error("Could not delete mailbox", err.message || "Please try again.");
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formEmail.trim() || !formPassword.trim() || !formHost.trim()) return;

    try {
      setSubmitting(true);
      await api.createMailbox({
        email: formEmail.trim(),
        password: formPassword,
        smtp_host: formHost.trim(),
        smtp_port: formPort,
        first_name: formFirstName.trim() || undefined,
        last_name: formLastName.trim() || undefined,
        daily_limit: formLimit,
      });
      setShowAddModal(false);
      setFormEmail("");
      setFormPassword("");
      toast.success("Mailbox connected", `${formEmail.trim()} is ready to send from.`);
      fetchMailboxes();
    } catch (err: any) {
      toast.error("Could not save mailbox", err.message || "Check the credentials and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Screen-reader announcement of the loading state. */}
      <StatusLive loading={loading} loadingLabel="Loading your sender mailboxes…" />

      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
          Settings &amp; SMTP Infrastructure
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Configure sender mailboxes, test credentials, and monitor daily deliverability quotas.
        </p>
      </div>

      {/* Inline error with a retry — a toast disappears, this stays. */}
      {loadError && !loading && (
        <ErrorState
          title="Could not load your mailboxes"
          message={loadError}
          onRetry={fetchMailboxes}
        />
      )}

      {/* Mailbox Section */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900">Sender Mailboxes</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Connect multiple mailboxes to distribute campaign volume and avoid spam rate-limits.
            </p>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white h-9 px-4 transition-colors shadow-xs"
          >
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            Add Mailbox
          </button>
        </div>

        <div className="space-y-3">
          {loading ? (
            /* Exactly the height of a real mailbox card, so the section below
               does not jump when the list arrives. */
            <div
              className="h-[92px] rounded-xl border border-slate-200 bg-slate-50/50 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              aria-hidden="true"
            >
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-56" />
                <Skeleton className="h-3 w-72" />
                <Skeleton className="h-3 w-40" />
              </div>
              <div className="flex items-center gap-2">
                <Skeleton className="h-8 w-32 rounded-lg" />
                <Skeleton className="h-8 w-8 rounded-lg" />
              </div>
            </div>
          ) : mailboxes && mailboxes.length > 0 ? (
            mailboxes.map((mb) => {
              const testRes = testResults[mb.id];
              return (
                <div
                  key={mb.id}
                  className="min-h-[92px] p-4 rounded-xl border border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Mail className="w-4 h-4 text-blue-600" />
                      <span className="font-bold text-sm text-slate-900">{mb.email}</span>
                      {mb.health_paused ? (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-red-100 text-red-800">
                          Paused — needs review
                        </span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-100 text-emerald-800">
                          Active
                        </span>
                      )}
                      {authChecked[mb.id] ? (
                        <AuthBadge domain={mb.email.split("@")[1] || ""} />
                      ) : (
                        <button
                          onClick={() => setAuthChecked((prev) => ({ ...prev, [mb.id]: true }))}
                          title="Check SPF, DKIM and DMARC for this sending domain (live DNS lookup)"
                          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-700"
                        >
                          <ShieldCheck className="w-3 h-3 text-blue-600" />
                          Check DNS auth
                        </button>
                      )}
                    </div>
                    <p className="text-xs text-slate-500">
                      Host: <code className="font-mono">{mb.smtp_host}:{mb.smtp_port}</code> | Sender:{" "}
                      <strong>{mb.first_name} {mb.last_name}</strong> | Limit:{" "}
                      <strong>{mb.sent_today} / {mb.daily_limit} sent today</strong>
                    </p>
                    {/* Reputation health: one glance, no docs needed. */}
                    <div
                      className="flex items-center gap-2"
                      title={
                        mb.health_paused
                          ? "Bounce rate tripped the safety threshold — review recent sends before re-enabling."
                          : "Reputation score from the last 50 sends. Bounces count double; amber means slow down."
                      }
                    >
                      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-200">
                        <div
                          className={`h-full rounded-full transition-all ${
                            (mb.health_score ?? 1) >= 0.8
                              ? "bg-emerald-500"
                              : (mb.health_score ?? 1) >= 0.5
                              ? "bg-amber-500"
                              : "bg-red-500"
                          }`}
                          style={{ width: `${Math.round((mb.health_score ?? 1) * 100)}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-semibold text-slate-500">
                        reputation {Math.round((mb.health_score ?? 1) * 100)}%
                        {mb.created_at &&
                          (Date.now() - new Date(mb.created_at).getTime()) / 86400000 < 14 &&
                          " · warming up"}
                      </span>
                    </div>

                    {testRes && (
                      <div className={`text-xs font-medium mt-1.5 flex items-center gap-1 ${
                        testRes.success ? "text-emerald-700" : "text-red-700"
                      }`}>
                        {testRes.success ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                        {testRes.message}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleTestConnection(mb.id)}
                      disabled={testingId === mb.id}
                      className="inline-flex items-center justify-center rounded-lg text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-8 px-3 transition-colors shadow-xs"
                    >
                      {testingId === mb.id ? (
                        <>
                          <Loader2 className="w-3 h-3 mr-1 motion-safe:animate-spin motion-reduce:animate-pulse" />
                          Testing...
                        </>
                      ) : (
                        <>
                          <ShieldCheck className="w-3 h-3 mr-1 text-blue-600" />
                          Test Connection
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => handleDelete(mb.id)}
                      className="p-2 text-slate-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
                      title="Delete Mailbox"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })
          ) : (
            <EmptyState
              icon={<InboxIcon className="h-5 w-5" />}
              title="No SMTP mailboxes connected yet"
              description="A sending mailbox is the one thing LeadForge needs before it can send. Connect one and the first campaign can go out."
              action={
                <button
                  onClick={() => setShowAddModal(true)}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Mailbox
                </button>
              }
              secondaryAction={
                <a
                  href="/setup"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                >
                  <Sparkles className="w-3.5 h-3.5" /> Run the setup checklist
                </a>
              }
            />
          )}
        </div>
      </div>

      {/* AI Agent Integration (MCP) */}
      <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-white via-indigo-50/20 to-blue-50/20 p-6 shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                <Sparkles className="w-3 h-3" /> AI Native
              </span>
              <h2 className="text-base font-bold text-slate-900">AI Agent Integration & Model Context Protocol (MCP)</h2>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Command LeadForge directly from Google Antigravity, Claude Desktop, or Cursor. The AI can scrape Google Maps, discover emails across the open web, and sequence outreach autonomously.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Antigravity / Claude Config */}
          <div className="p-4 rounded-xl border border-indigo-100 bg-white/80 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-slate-800 flex items-center gap-1.5">
                <Bot className="w-3.5 h-3.5 text-indigo-600" />
                Antigravity / Gemini CLI (<code>mcp_config.json</code>)
              </span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(JSON.stringify({
                    "leadforge": {
                      "command": "python",
                      "args": ["-m", "app.mcp_server"],
                      "cwd": "./backend"
                    }
                  }, null, 2));
                  setCopiedPlatform("antigravity");
                  setTimeout(() => setCopiedPlatform(null), 2000);
                }}
                className="text-[11px] text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1 cursor-pointer"
              >
                {copiedPlatform === "antigravity" ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                {copiedPlatform === "antigravity" ? "Copied!" : "Copy JSON"}
              </button>
            </div>
            <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-[10px] font-mono overflow-x-auto">
{`"leadforge": {
  "command": "python",
  "args": ["-m", "app.mcp_server"],
  "cwd": "./backend"
}`}
            </pre>
            <p className="text-[10px] text-slate-500">
              Paste into your global or local MCP config file under <code>mcpServers</code>.
            </p>
          </div>

          {/* CLI Usage */}
          <div className="p-4 rounded-xl border border-indigo-100 bg-white/80 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-slate-800 flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5 text-slate-700" />
                Direct AI Agent CLI Bridge
              </span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText('python -m app.cli scrape "Real Estate Agents in Delhi" --limit 10 --format markdown');
                  setCopiedPlatform("cli");
                  setTimeout(() => setCopiedPlatform(null), 2000);
                }}
                className="text-[11px] text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1 cursor-pointer"
              >
                {copiedPlatform === "cli" ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                {copiedPlatform === "cli" ? "Copied!" : "Copy Command"}
              </button>
            </div>
            <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-[10px] font-mono overflow-x-auto">
{`python -m app.cli scrape "Real Estate in Delhi" \\
  --limit 10 --format markdown`}
            </pre>
            <p className="text-[10px] text-slate-500">
              Outputs clean GitHub Markdown with hyperlinked Google Maps links and WhatsApp buttons.
            </p>
          </div>
        </div>
      </div>

      {/* System Information */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs space-y-4">
        <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <Server className="w-4 h-4 text-slate-600" /> System Architecture & Operational Mode
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/70">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Database Engine</span>
            <div className="font-bold text-slate-800 text-sm">Async SQLite / PostgreSQL</div>
            <p className="text-[11px] text-slate-500 mt-1">Dual-mode zero-install local & cloud</p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/70">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Scraper Engine</span>
            <div className="font-bold text-slate-800 text-sm">Playwright Headless + HTTP</div>
            <p className="text-[11px] text-slate-500 mt-1">Zero paid API key dependencies</p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/70">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Anti-Spam Throttling</span>
            <div className="font-bold text-emerald-700 text-sm">15s Jitter Delay Enabled</div>
            <p className="text-[11px] text-slate-500 mt-1">Protects sender IP and domain health</p>
          </div>
        </div>
      </div>

      {/* Add Mailbox Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h2 className="font-bold text-base text-slate-900">Connect SMTP Mailbox</h2>
                <p className="text-xs text-slate-500 mt-0.5">Use your Gmail App Password, Zoho, or custom domain</p>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-500 hover:text-slate-700 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            {/* Quick Provider Presets */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-medium text-slate-500">Quick Provider Presets:</span>
              <div className="flex flex-wrap gap-1.5">
                {PRESET_PROVIDERS.map((p) => (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => {
                      setFormHost(p.host);
                      setFormPort(p.port);
                    }}
                    className="text-[11px] px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-200 text-slate-700 transition-colors"
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleCreate} className="space-y-3 text-xs">
              <div>
                <label htmlFor="mb-email" className="font-semibold text-slate-700 block mb-1">Email Address *</label>
                <input
                  id="mb-email"
                  type="email"
                  required
                  placeholder="e.g. outreach@yourdomain.com"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div>
                <label htmlFor="mb-password" className="font-semibold text-slate-700 block mb-1">Password or App Password *</label>
                <input
                  id="mb-password"
                  type="password"
                  required
                  placeholder="••••••••••••••••"
                  value={formPassword}
                  onChange={(e) => setFormPassword(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
                <p className="text-[10px] text-slate-500 mt-1">
                  For Gmail, use a 16-character Google App Password (not your personal login password).
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label htmlFor="mb-host" className="font-semibold text-slate-700 block mb-1">SMTP Host *</label>
                  <input
                    id="mb-host"
                    type="text"
                    required
                    value={formHost}
                    onChange={(e) => setFormHost(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                <div>
                  <label htmlFor="mb-port" className="font-semibold text-slate-700 block mb-1">Port</label>
                  <input
                    id="mb-port"
                    type="number"
                    required
                    value={formPort}
                    onChange={(e) => setFormPort(Number(e.target.value))}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="mb-first" className="font-semibold text-slate-700 block mb-1">Sender First Name</label>
                  <input
                    id="mb-first"
                    type="text"
                    value={formFirstName}
                    onChange={(e) => setFormFirstName(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                <div>
                  <label htmlFor="mb-last" className="font-semibold text-slate-700 block mb-1">Sender Last Name</label>
                  <input
                    id="mb-last"
                    type="text"
                    value={formLastName}
                    onChange={(e) => setFormLastName(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="mb-limit" className="font-semibold text-slate-700 block mb-1">Daily Sending Limit</label>
                <input
                  id="mb-limit"
                  type="number"
                  min={10}
                  max={500}
                  value={formLimit}
                  onChange={(e) => setFormLimit(Number(e.target.value))}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 font-medium text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                >
                  {submitting ? "Saving..." : "Save Mailbox"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
