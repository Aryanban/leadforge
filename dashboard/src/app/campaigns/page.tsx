"use client";

import { useState, useEffect } from "react";
import { 
  Mail, 
  Send, 
  Play, 
  Pause, 
  Plus, 
  RefreshCw, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  Eye,
  Sparkles,
  Loader2,
  ChevronRight
} from "lucide-react";
import { api, CampaignItem } from "@/lib/api";

const TEMPLATE_VARIABLES = [
  { tag: "{{business_name}}", label: "Business Name" },
  { tag: "{{first_name}}", label: "Contact Name" },
  { tag: "{{city}}", label: "City" },
  { tag: "{{phone}}", label: "Phone" },
  { tag: "{{category}}", label: "Category" },
  { tag: "{{website}}", label: "Website" },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<CampaignItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState<any | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  // New campaign form state
  const [campName, setCampName] = useState("");
  const [subject, setSubject] = useState("Quick question regarding your {{business_name}} property due diligence");
  const [bodyText, setBodyText] = useState(
`Hi {{first_name}},

I noticed the great work {{business_name}} is doing with property transactions in {{city}}.

Quick question: how do you currently verify original DDA plot layout plans, pocket maps, and circle rates for clients before drafting sale agreements?

We recently digitized all 362+ official DDA layout plans across all 36 Rohini sectors on PlotBook (https://plotbook.webforge.me) at native pixel zoom with instant circle rate calculations.

Would you be open to a 2-minute look to see how it can save your team hours on client due diligence?

Best regards,
PlotBook Team`
  );
  const [previewData, setPreviewData] = useState<{ rendered_subject: string; rendered_body: string } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchCampaigns = async () => {
    try {
      setLoading(true);
      const data = await api.getCampaigns();
      setCampaigns(data);
    } catch (err) {
      console.warn("Could not fetch campaigns:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCampaigns();
  }, []);

  const handleLaunch = async (id: number) => {
    try {
      setActionLoading(id);
      await api.launchCampaign(id);
      fetchCampaigns();
    } catch (err: any) {
      alert(`Launch error: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handlePause = async (id: number) => {
    try {
      setActionLoading(id);
      await api.pauseCampaign(id);
      fetchCampaigns();
    } catch (err: any) {
      alert(`Pause error: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewDetails = async (id: number) => {
    try {
      const details = await api.getCampaign(id);
      setSelectedCampaign(details);
    } catch (err: any) {
      alert(`Could not fetch details: ${err.message}`);
    }
  };

  const handleGeneratePreview = async () => {
    try {
      setPreviewLoading(true);
      const res = await api.previewTemplate(subject, bodyText);
      setPreviewData(res);
    } catch (err: any) {
      console.error(err);
    } finally {
      setPreviewLoading(false);
    }
  };

  const insertVariable = (tag: string, target: "subject" | "body") => {
    if (target === "subject") {
      setSubject((prev) => prev + " " + tag);
    } else {
      setBodyText((prev) => prev + " " + tag);
    }
  };

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!campName.trim() || !subject.trim() || !bodyText.trim()) return;

    try {
      await api.createCampaign({
        name: campName.trim(),
        steps: [
          {
            subject: subject.trim(),
            body_text: bodyText.trim(),
            delay_days: 0,
          },
        ],
      });
      setShowModal(false);
      setCampName("");
      fetchCampaigns();
    } catch (err: any) {
      alert(`Failed to create campaign: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Email Campaigns & Outreach
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Automated multi-mailbox cold outreach with dynamic variable personalization and 1x1 pixel open tracking.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchCampaigns}
            disabled={loading}
            className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin text-blue-600" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white h-9 px-4 transition-colors shadow-xs"
          >
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            New Campaign
          </button>
        </div>
      </div>

      {/* Campaigns Grid */}
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <div className="col-span-full p-12 text-center text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
            Loading campaigns...
          </div>
        ) : campaigns && campaigns.length > 0 ? (
          campaigns.map((camp) => (
            <div
              key={camp.id}
              className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs flex flex-col justify-between hover:border-slate-300 transition-colors"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-bold text-base text-slate-900 leading-snug">{camp.name}</h3>
                  <span
                    className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      camp.status === "active"
                        ? "bg-emerald-100 text-emerald-800"
                        : camp.status === "paused"
                        ? "bg-amber-100 text-amber-800"
                        : camp.status === "completed"
                        ? "bg-blue-100 text-blue-800"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {camp.status}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 bg-slate-50 p-3 rounded-xl border border-slate-100 text-center">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400">Sent</span>
                    <div className="text-base font-extrabold text-slate-800">{camp.sent_count}</div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400">Opened</span>
                    <div className="text-base font-extrabold text-blue-600">{camp.open_rate}%</div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400">Replies</span>
                    <div className="text-base font-extrabold text-emerald-600">{camp.replied_count}</div>
                  </div>
                </div>
              </div>

              <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between">
                <button
                  onClick={() => handleViewDetails(camp.id)}
                  className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  <Eye className="w-3.5 h-3.5" /> Details
                </button>

                <div className="flex items-center gap-2">
                  {camp.status === "active" ? (
                    <button
                      onClick={() => handlePause(camp.id)}
                      disabled={actionLoading === camp.id}
                      className="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100 transition-colors"
                    >
                      <Pause className="w-3 h-3" /> Pause
                    </button>
                  ) : (
                    <button
                      onClick={() => handleLaunch(camp.id)}
                      disabled={actionLoading === camp.id}
                      className="inline-flex items-center gap-1 text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors shadow-xs"
                    >
                      <Play className="w-3 h-3" /> Launch
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-full p-12 text-center text-slate-400 bg-white rounded-2xl border border-slate-200">
            No campaigns created yet. Click "New Campaign" above to get started!
          </div>
        )}
      </div>

      {/* New Campaign Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-2xl w-full p-6 shadow-xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="font-bold text-base text-slate-900">Create Cold Email Campaign</h3>
                <p className="text-xs text-slate-500 mt-0.5">Define outreach copy and dynamic personalization tags</p>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateCampaign} className="space-y-4 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Campaign Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Rohini Real Estate Agents — Blueprint Intro"
                  value={campName}
                  onChange={(e) => setCampName(e.target.value)}
                  className="w-full h-10 px-3.5 rounded-xl border border-slate-200 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              {/* Personalization Variables Chips */}
              <div className="space-y-1.5 bg-slate-50 p-3 rounded-xl border border-slate-100">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-blue-600" /> Insert Dynamic Variable:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {TEMPLATE_VARIABLES.map((v) => (
                    <button
                      key={v.tag}
                      type="button"
                      onClick={() => insertVariable(v.tag, "body")}
                      className="px-2.5 py-1 rounded-md bg-white border border-slate-200 text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 text-[11px] font-mono transition-colors"
                    >
                      {v.tag}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Email Subject *</label>
                <input
                  type="text"
                  required
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full h-10 px-3.5 rounded-xl border border-slate-200 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-slate-700">Email Body Copy (Markdown / Plain Text) *</label>
                  <button
                    type="button"
                    onClick={handleGeneratePreview}
                    className="text-blue-600 hover:text-blue-700 font-semibold text-[11px]"
                  >
                    Preview Rendered Copy
                  </button>
                </div>
                <textarea
                  rows={8}
                  required
                  value={bodyText}
                  onChange={(e) => setBodyText(e.target.value)}
                  className="w-full p-3.5 rounded-xl border border-slate-200 font-mono text-[11px] text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 leading-relaxed"
                />
              </div>

              {/* Preview Box */}
              {previewData && (
                <div className="p-4 rounded-xl bg-blue-50/50 border border-blue-100 space-y-2">
                  <span className="text-[10px] uppercase font-bold text-blue-700">Live Rendered Sample:</span>
                  <div className="font-bold text-slate-900">{previewData.rendered_subject}</div>
                  <div className="text-slate-700 whitespace-pre-wrap leading-relaxed border-t border-blue-100/60 pt-2 font-sans">
                    {previewData.rendered_body}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 font-medium text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-xs"
                >
                  Create & Save Campaign
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Campaign Details Drawer */}
      {selectedCampaign && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-2xl w-full p-6 shadow-xl max-h-[85vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="font-bold text-base text-slate-900">{selectedCampaign.name}</h3>
                <span className="text-xs text-slate-500">Status: {selectedCampaign.status}</span>
              </div>
              <button
                onClick={() => setSelectedCampaign(null)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <h4 className="font-bold text-slate-800 mb-2">Campaign Steps</h4>
                {selectedCampaign.steps?.map((s: any) => (
                  <div key={s.id} className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/50 space-y-1.5 mb-2">
                    <div className="font-bold text-slate-900">Step {s.step_number}: {s.subject}</div>
                    <p className="text-slate-600 whitespace-pre-wrap">{s.body_text}</p>
                  </div>
                ))}
              </div>

              <div>
                <h4 className="font-bold text-slate-800 mb-2">Recent Dispatch Log</h4>
                <div className="divide-y divide-slate-100 max-h-48 overflow-y-auto border border-slate-100 rounded-xl">
                  {selectedCampaign.sends && selectedCampaign.sends.length > 0 ? (
                    selectedCampaign.sends.map((snd: any) => (
                      <div key={snd.id} className="p-2.5 flex items-center justify-between text-[11px]">
                        <span className="text-slate-700">Send #{snd.id}</span>
                        <span className={`px-2 py-0.5 rounded-full font-bold ${
                          snd.status === "sent" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                        }`}>
                          {snd.status} {snd.opened && "• Opened"}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-slate-400">No sends dispatched yet.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
