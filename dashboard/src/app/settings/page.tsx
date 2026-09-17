"use client";

import { useState, useEffect } from "react";
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
  ShieldCheck
} from "lucide-react";
import { api, MailboxItem } from "@/lib/api";

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
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { success: boolean; message: string }>>({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [copiedPlatform, setCopiedPlatform] = useState<string | null>(null);

  // Form state
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formHost, setFormHost] = useState("smtp.gmail.com");
  const [formPort, setFormPort] = useState(587);
  const [formFirstName, setFormFirstName] = useState("Outreach");
  const [formLastName, setFormLastName] = useState("Team");
  const [formLimit, setFormLimit] = useState(50);
  const [submitting, setSubmitting] = useState(false);

  const fetchMailboxes = async () => {
    try {
      setLoading(true);
      const data = await api.getMailboxes();
      setMailboxes(data);
    } catch (err) {
      console.warn("Could not fetch mailboxes:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMailboxes();
  }, []);

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
      fetchMailboxes();
    } catch (err: any) {
      alert(`Failed to delete: ${err.message}`);
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
      fetchMailboxes();
    } catch (err: any) {
      alert(`Error saving mailbox: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
          Settings & SMTP Infrastructure
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Configure sender mailboxes, test credentials, and monitor daily deliverability quotas.
        </p>
      </div>

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
            <div className="p-8 text-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
              Loading mailboxes...
            </div>
          ) : mailboxes && mailboxes.length > 0 ? (
            mailboxes.map((mb) => {
              const testRes = testResults[mb.id];
              return (
                <div
                  key={mb.id}
                  className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-blue-600" />
                      <span className="font-bold text-sm text-slate-900">{mb.email}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-100 text-emerald-800">
                        Active
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Host: <code className="font-mono">{mb.smtp_host}:{mb.smtp_port}</code> | Sender:{" "}
                      <strong>{mb.first_name} {mb.last_name}</strong> | Limit:{" "}
                      <strong>{mb.sent_today} / {mb.daily_limit} sent today</strong>
                    </p>

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
                          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
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
                      className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="Delete Mailbox"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="p-8 text-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
              No SMTP mailboxes connected yet. Add one above to begin sending campaigns!
            </div>
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
            <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Database Engine</span>
            <div className="font-bold text-slate-800 text-sm">Async SQLite / PostgreSQL</div>
            <p className="text-[11px] text-slate-500 mt-1">Dual-mode zero-install local & cloud</p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/70">
            <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Scraper Engine</span>
            <div className="font-bold text-slate-800 text-sm">Playwright Headless + HTTP</div>
            <p className="text-[11px] text-slate-500 mt-1">Zero paid API key dependencies</p>
          </div>
          <div className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/70">
            <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Anti-Spam Throttling</span>
            <div className="font-bold text-emerald-600 text-sm">15s Jitter Delay Enabled</div>
            <p className="text-[11px] text-slate-500 mt-1">Protects sender IP and domain health</p>
          </div>
        </div>
      </div>

      {/* Add Mailbox Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="font-bold text-base text-slate-900">Connect SMTP Mailbox</h3>
                <p className="text-xs text-slate-500 mt-0.5">Use your Gmail App Password, Zoho, or custom domain</p>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
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
                <label className="font-semibold text-slate-700 block mb-1">Email Address *</label>
                <input
                  type="email"
                  required
                  placeholder="e.g. outreach@yourdomain.com"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Password or App Password *</label>
                <input
                  type="password"
                  required
                  placeholder="••••••••••••••••"
                  value={formPassword}
                  onChange={(e) => setFormPassword(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
                <p className="text-[10px] text-slate-400 mt-1">
                  For Gmail, use a 16-character Google App Password (not your personal login password).
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="font-semibold text-slate-700 block mb-1">SMTP Host *</label>
                  <input
                    type="text"
                    required
                    value={formHost}
                    onChange={(e) => setFormHost(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Port</label>
                  <input
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
                  <label className="font-semibold text-slate-700 block mb-1">Sender First Name</label>
                  <input
                    type="text"
                    value={formFirstName}
                    onChange={(e) => setFormFirstName(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Sender Last Name</label>
                  <input
                    type="text"
                    value={formLastName}
                    onChange={(e) => setFormLastName(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Daily Sending Limit</label>
                <input
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
                  className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-xs"
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
