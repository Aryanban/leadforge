"use client";

import { useState, useEffect } from "react";
import { 
  Users, 
  Search, 
  Download, 
  Phone, 
  Globe, 
  MessageCircle, 
  Mail, 
  CheckCircle2, 
  Sparkles, 
  Trash2, 
  Plus, 
  RefreshCw,
  Loader2,
  ExternalLink,
  MapPin,
  Share2,
  Database,
  Flame,
  Zap,
  ShieldCheck,
  Upload,
  Wand2,
  Copy,
  Check,
  FileText,
  AlertTriangle
} from "lucide-react";
import { api, LeadItem } from "@/lib/api";

export default function LeadsPage() {
  const [leads, setLeads] = useState<LeadItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [industryFilter, setIndustryFilter] = useState("");
  const [hasEmailFilter, setHasEmailFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [enrichingId, setEnrichingId] = useState<number | null>(null);
  const [bulkEnrichLoading, setBulkEnrichLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [syncWebhookUrl, setSyncWebhookUrl] = useState("");
  const [syncingTwenty, setSyncingTwenty] = useState(false);

  // CSV Import State
  const [showImportModal, setShowImportModal] = useState(false);
  const [importCsvText, setImportCsvText] = useState("");
  const [importingCsv, setImportingCsv] = useState(false);

  // AI Icebreaker State
  const [activeIcebreaker, setActiveIcebreaker] = useState<any | null>(null);
  const [loadingIcebreakerId, setLoadingIcebreakerId] = useState<number | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Cold Email Spam Checker State
  const [showSpamModal, setShowSpamModal] = useState(false);
  const [spamSubject, setSpamSubject] = useState("Quick question regarding {{business_name}}");
  const [spamBody, setSpamBody] = useState("Hi {{first_name}},\n\nSaw your impressive work with {{business_name}} in {{city}}.\n{{ai_icebreaker}}\n\nWould you be open to a brief 4-minute chat this Thursday to see how we're solving this for other {{category}} leaders?\n\nBest regards,\nAryan");
  const [spamResult, setSpamResult] = useState<any | null>(null);
  const [checkingSpam, setCheckingSpam] = useState(false);

  const [newLead, setNewLead] = useState({
    name: "",
    phone: "",
    email: "",
    website: "",
    address: "",
    industry: "Real Estate Agency"
  });

  const fetchLeads = async () => {
    try {
      setLoading(true);
      const emailFilterParam = hasEmailFilter === "true" ? true : hasEmailFilter === "false" ? false : undefined;
      const res = await api.getLeads({
        page,
        limit: 20,
        search: search || undefined,
        industry: industryFilter || undefined,
        has_email: emailFilterParam,
      });
      setLeads(res.leads);
      setTotal(res.total);
    } catch (err) {
      console.warn("Could not fetch live leads, using demo fallback:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLeads();
  }, [page, industryFilter, hasEmailFilter]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchLeads();
  };

  const handleEnrichSingle = async (businessId: number) => {
    try {
      setEnrichingId(businessId);
      const res: any = await api.enrichLead(businessId);
      const emailCount = res.emails_found || 0;
      const phoneCount = res.phones_found || 0;
      const verifiedCount = res.verified_emails || 0;
      alert(`Multi-Source Search Complete!\n• Emails Found: ${emailCount} (${verifiedCount} verified deliverable)\n• Discovered Phone Numbers: ${phoneCount}\n• Discovered Website: ${res.website || "None"}`);
      fetchLeads();
    } catch (err: any) {
      alert(`Search notice: ${err.message}`);
    } finally {
      setEnrichingId(null);
    }
  };

  const handleBulkEnrich = async () => {
    try {
      setBulkEnrichLoading(true);
      const res = await api.enrichAll(25);
      alert(res.message || "Deep web contact enrichment started in background across DuckDuckGo & websites!");
      setTimeout(() => fetchLeads(), 3000);
    } catch (err: any) {
      alert(`Failed to trigger bulk enrichment: ${err.message}`);
    } finally {
      setBulkEnrichLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to remove this lead?")) return;
    try {
      await api.deleteLead(id);
      fetchLeads();
    } catch (err: any) {
      alert(`Failed to delete lead: ${err.message}`);
    }
  };

  const handleCreateLead = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newLead.name.trim()) return;
    try {
      await api.createLead(newLead);
      setShowAddModal(false);
      setNewLead({ name: "", phone: "", email: "", website: "", address: "", industry: "Real Estate Agency" });
      fetchLeads();
    } catch (err: any) {
      alert(`Failed to add lead: ${err.message}`);
    }
  };

  const handleSyncTwenty = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!syncWebhookUrl) return;
    try {
      setSyncingTwenty(true);
      const res = await api.exportTwentyCrm(syncWebhookUrl);
      alert(`Sync successful! ${res.synced_companies || 0} companies pushed to target webhook.`);
      setShowSyncModal(false);
    } catch (err: any) {
      alert(`Sync notice: ${err.message}`);
    } finally {
      setSyncingTwenty(false);
    }
  };

  const handleImportCsv = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importCsvText.trim()) return;
    try {
      setImportingCsv(true);
      const res = await api.importCsv(importCsvText.trim());
      alert(`Import Successful!\n• Imported Leads: ${res.imported}\n• Skipped: ${res.skipped}\n• Total Processed: ${res.total_rows_processed}`);
      setShowImportModal(false);
      setImportCsvText("");
      fetchLeads();
    } catch (err: any) {
      alert(`CSV Import failed: ${err.message}`);
    } finally {
      setImportingCsv(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) setImportCsvText(content);
    };
    reader.readAsText(file);
  };

  const handleShowIcebreaker = async (leadId: number) => {
    try {
      setLoadingIcebreakerId(leadId);
      const res = await api.getIcebreaker(leadId);
      setActiveIcebreaker(res);
    } catch (err: any) {
      alert(`Icebreaker generation notice: ${err.message}`);
    } finally {
      setLoadingIcebreakerId(null);
    }
  };

  const handleRunSpamCheck = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    try {
      setCheckingSpam(true);
      const res = await api.checkSpam(spamSubject, spamBody);
      setSpamResult(res);
    } catch (err: any) {
      alert(`Spam analysis notice: ${err.message}`);
    } finally {
      setCheckingSpam(false);
    }
  };

  const copyText = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Lead Database
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Total {total} businesses discovered. Verified emails, phone numbers, and WhatsApp links ready for outreach.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleBulkEnrich}
            disabled={bulkEnrichLoading}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white h-9 px-3.5 transition-colors shadow-xs"
          >
            {bulkEnrichLoading ? (
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            )}
            Auto-Enrich Missing Emails
          </button>

          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
            title="Import custom lead lists from CSV"
          >
            <Upload className="w-3.5 h-3.5 mr-1.5 text-blue-600" />
            Import CSV
          </button>

          <a
            href={api.exportCsvUrl}
            download="leadforge_leads.csv"
            className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
          >
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Export CSV
          </a>

          <button
            onClick={() => {
              setShowSpamModal(true);
              if (!spamResult) handleRunSpamCheck();
            }}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold border border-purple-200 bg-purple-50/80 hover:bg-purple-100 text-purple-700 h-9 px-3.5 transition-colors shadow-xs"
            title="Score cold email deliverability and spam risk"
          >
            <ShieldCheck className="w-3.5 h-3.5 mr-1.5" />
            Spam Checker
          </button>

          <button
            onClick={() => setShowSyncModal(true)}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold border border-indigo-200 bg-indigo-50/80 hover:bg-indigo-100 text-indigo-700 h-9 px-3.5 transition-colors shadow-xs"
            title="Sync directly to Twenty CRM, HubSpot, or Zapier"
          >
            <Share2 className="w-3.5 h-3.5 mr-1.5" />
            Twenty CRM / Sync
          </button>

          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white h-9 px-3.5 transition-colors shadow-xs"
          >
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            Add Lead
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs">
        <form onSubmit={handleSearch} className="flex flex-col md:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by business name, address, phone, or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 bg-slate-50/50 text-xs text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto">
            <select
              value={hasEmailFilter}
              onChange={(e) => setHasEmailFilter(e.target.value)}
              className="h-10 px-3 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-700 focus:outline-none"
            >
              <option value="all">All Contacts</option>
              <option value="true">Has Email</option>
              <option value="false">Missing Email</option>
            </select>

            <button
              type="submit"
              className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 h-10 px-4 transition-colors shrink-0"
            >
              Search
            </button>
          </div>
        </form>
      </div>

      {/* Leads Table */}
      <div className="rounded-2xl border border-slate-200/80 bg-white shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
              <tr>
                <th className="px-5 py-3">Business & Address</th>
                <th className="px-3 py-3">Score & Status</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Phone & WhatsApp</th>
                <th className="px-4 py-3">Website</th>
                <th className="px-4 py-3">Contact Email</th>
                <th className="px-4 py-3">Rating</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
                    Loading leads database...
                  </td>
                </tr>
              ) : leads && leads.length > 0 ? (
                leads.map((lead) => {
                  const contact = lead.primary_contact;
                  const cleanPhone = lead.phone ? lead.phone.replace(/[^0-9]/g, "") : "";
                  const waUrl = contact?.whatsapp_link || (cleanPhone ? `https://wa.me/${cleanPhone}` : null);

                    const mapsUrl = lead.maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((lead.name + " " + (lead.address || "")).trim())}`;

                    return (
                    <tr key={lead.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-5 py-4 max-w-[260px]">
                        <div className="flex items-center gap-1.5">
                          <a
                            href={mapsUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-bold text-slate-900 hover:text-blue-600 transition-colors inline-flex items-center gap-1.5 group max-w-full"
                            title="Open Google Maps listing in new tab"
                          >
                            <span className="truncate">{lead.name}</span>
                            <MapPin className="w-3.5 h-3.5 text-red-500 shrink-0 group-hover:scale-110 transition-transform" />
                          </a>
                        </div>
                        <div className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                          {lead.address || "Address not listed"}
                        </div>
                        {lead.latitude && lead.longitude && (
                          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                            📍 {lead.latitude.toFixed(4)}, {lead.longitude.toFixed(4)}
                          </div>
                        )}
                      </td>

                      {/* Score & Tier */}
                      <td className="px-3 py-4 whitespace-nowrap">
                        <div className="flex flex-col gap-1 items-start">
                          {lead.lead_tier === "HOT" ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-rose-50 text-rose-700 border border-rose-200 shadow-2xs">
                              <Flame className="w-3 h-3 text-rose-500 fill-rose-500" />
                              {lead.lead_score || 85} HOT
                            </span>
                          ) : lead.lead_tier === "WARM" ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                              <Zap className="w-3 h-3 text-amber-500 fill-amber-500" />
                              {lead.lead_score || 55} WARM
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                              ❄️ {lead.lead_score || 35} COLD
                            </span>
                          )}

                          {lead.is_claimed === false && (
                            <span
                              className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-orange-100 text-orange-800 tracking-tight cursor-help"
                              title="Unclaimed Google Business Profile — Top target for marketing & claim services"
                            >
                              Unclaimed GBP
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="px-4 py-4 whitespace-nowrap">
                        <span className="inline-block px-2.5 py-0.5 bg-slate-100 rounded-md text-[11px] font-medium text-slate-700">
                          {lead.industry || "General"}
                        </span>
                      </td>

                      <td className="px-4 py-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          {lead.phone ? (
                            <a
                              href={`tel:${lead.phone}`}
                              className="inline-flex items-center gap-1 font-mono text-[11px] text-slate-700 hover:text-blue-600"
                            >
                              <Phone className="w-3 h-3 text-slate-400" />
                              {lead.phone}
                            </a>
                          ) : (
                            <span className="text-slate-400 italic text-[11px]">No phone</span>
                          )}

                          {waUrl && (
                            <a
                              href={waUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors"
                              title="Chat on WhatsApp"
                            >
                              <MessageCircle className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>
                      </td>

                      <td className="px-4 py-4 whitespace-nowrap">
                        {lead.website ? (
                          <a
                            href={lead.website.startsWith("http") ? lead.website : `https://${lead.website}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-[11px] font-medium max-w-[140px] truncate"
                          >
                            <Globe className="w-3 h-3 shrink-0" />
                            <span className="truncate">{lead.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}</span>
                            <ExternalLink className="w-2.5 h-2.5 shrink-0 text-slate-400" />
                          </a>
                        ) : (
                          <span className="text-slate-400 italic text-[11px]">No website</span>
                        )}
                      </td>

                      <td className="px-4 py-4">
                        {contact?.email ? (
                          <div className="space-y-0.5">
                            <div className="flex items-center gap-1.5 font-mono text-[11px] text-slate-800">
                              <Mail className="w-3 h-3 text-slate-400 shrink-0" />
                              <span className="truncate max-w-[180px]">{contact.email}</span>
                            </div>
                            <div>
                              {contact.is_verified ? (
                                <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-100 text-emerald-800">
                                  ✓ Verified Deliverable
                                </span>
                              ) : (
                                <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-medium bg-amber-50 text-amber-700">
                                  Unverified
                                </span>
                              )}
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleEnrichSingle(lead.id)}
                            disabled={enrichingId === lead.id}
                            className="inline-flex items-center gap-1 text-[11px] text-indigo-700 hover:text-indigo-900 font-semibold bg-indigo-50 hover:bg-indigo-100 border border-indigo-200/60 px-2 py-1 rounded-md transition-colors shadow-2xs"
                            title="Search web & websites to discover email and phone numbers"
                          >
                            {enrichingId === lead.id ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin text-indigo-600" />
                                Searching Web...
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-3 h-3 text-indigo-600" />
                                Find Web Contacts
                              </>
                            )}
                          </button>
                        )}
                      </td>

                      <td className="px-4 py-4 whitespace-nowrap text-amber-600 font-medium text-[11px]">
                        {lead.rating ? `★ ${lead.rating} (${lead.reviews_count || 0})` : "—"}
                      </td>

                      <td className="px-5 py-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleShowIcebreaker(lead.id)}
                            disabled={loadingIcebreakerId === lead.id}
                            className="text-slate-400 hover:text-purple-600 p-1.5 rounded-lg hover:bg-purple-50 transition-colors"
                            title="Generate AI Icebreaker Hook"
                          >
                            {loadingIcebreakerId === lead.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-600" />
                            ) : (
                              <Wand2 className="w-3.5 h-3.5 text-purple-600" />
                            )}
                          </button>
                          <a
                            href={mapsUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-blue-600 p-1.5 rounded-lg hover:bg-blue-50 transition-colors"
                            title="View on Google Maps"
                          >
                            <MapPin className="w-3.5 h-3.5 text-red-500" />
                          </a>
                          <button
                            onClick={() => handleEnrichSingle(lead.id)}
                            disabled={enrichingId === lead.id}
                            className="text-slate-400 hover:text-indigo-600 p-1.5 rounded-lg hover:bg-indigo-50 transition-colors"
                            title="Deep Web Contact Search"
                          >
                            {enrichingId === lead.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                            ) : (
                              <Sparkles className="w-3.5 h-3.5" />
                            )}
                          </button>
                          <button
                            onClick={() => handleDelete(lead.id)}
                            className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors"
                            title="Delete Lead"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-slate-400">
                    No leads found matching your criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="p-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
          <span>Showing {leads.length} of {total} leads</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50"
            >
              Previous
            </button>
            <span className="font-semibold text-slate-900">Page {page}</span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={leads.length < 20}
              className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Add Lead Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-base text-slate-900">Add New Lead</h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateLead} className="space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Business Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Royal Associates Rohini"
                  value={newLead.name}
                  onChange={(e) => setNewLead({ ...newLead, name: e.target.value })}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Phone Number</label>
                  <input
                    type="text"
                    placeholder="+91 98..."
                    value={newLead.phone}
                    onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Email Address</label>
                  <input
                    type="email"
                    placeholder="contact@company.com"
                    value={newLead.email}
                    onChange={(e) => setNewLead({ ...newLead, email: e.target.value })}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Website URL</label>
                <input
                  type="text"
                  placeholder="https://company.com"
                  value={newLead.website}
                  onChange={(e) => setNewLead({ ...newLead, website: e.target.value })}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Address / Location</label>
                <input
                  type="text"
                  placeholder="e.g. Sector 24, Rohini, New Delhi"
                  value={newLead.address}
                  onChange={(e) => setNewLead({ ...newLead, address: e.target.value })}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-xs"
                >
                  Save Lead
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Twenty CRM / Webhook Sync Modal */}
      {showSyncModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Database className="w-5 h-5 text-indigo-600" />
                <h3 className="font-bold text-base text-slate-900">Twenty CRM & Webhook Sync</h3>
              </div>
              <button
                onClick={() => setShowSyncModal(false)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Export or sync your enriched leads into open-source <strong>Twenty CRM</strong>, HubSpot, or automate outreach flows via Zapier / Make webhooks.
            </p>

            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-2 text-xs">
              <div className="font-semibold text-slate-800">Option 1: Direct JSON Download</div>
              <p className="text-slate-500 text-[11px]">
                Download standard Twenty CRM formatted JSON (`companies` & `people` schema).
              </p>
              <a
                href={api.exportTwentyCrmUrl}
                download="leadforge_twenty_export.json"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-300 font-semibold text-slate-700 hover:bg-slate-100 shadow-2xs"
              >
                <Download className="w-3.5 h-3.5" />
                Download Twenty CRM JSON
              </a>
            </div>

            <form onSubmit={handleSyncTwenty} className="space-y-3 pt-2 text-xs">
              <div className="font-semibold text-slate-800">Option 2: Push to Webhook URL</div>
              <input
                type="url"
                required
                placeholder="https://app.twenty.com/rest/companies or Zapier webhook..."
                value={syncWebhookUrl}
                onChange={(e) => setSyncWebhookUrl(e.target.value)}
                className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 text-xs"
              />

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowSyncModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={syncingTwenty}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold shadow-xs disabled:opacity-50"
                >
                  {syncingTwenty ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Share2 className="w-3.5 h-3.5" />}
                  Push Leads Sync
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Import CSV Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-xl w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-blue-600" />
                <h3 className="font-bold text-base text-slate-900">Import Leads from CSV</h3>
              </div>
              <button
                onClick={() => setShowImportModal(false)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Upload a CSV file or paste raw CSV text. Automatically detects headers like <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">name</code>, <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">phone</code>, <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">email</code>, <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">website</code>, and <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">address</code>.
            </p>

            <form onSubmit={handleImportCsv} className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1.5">Choose .csv File</label>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileUpload}
                  className="block w-full text-xs text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 border border-slate-200 rounded-lg cursor-pointer"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1.5">Or Paste Raw CSV Content</label>
                <textarea
                  rows={6}
                  value={importCsvText}
                  onChange={(e) => setImportCsvText(e.target.value)}
                  placeholder="name,phone,email,website,city,category&#10;Apex Dental,555-0192,dr@apexdental.com,https://apexdental.com,Austin,Dentist"
                  className="w-full p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20 font-mono text-xs text-slate-800"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 font-medium text-xs text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={importingCsv || !importCsvText.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-xs disabled:opacity-50"
                >
                  {importingCsv ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                  Import Leads
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Icebreaker / Hook Modal */}
      {activeIcebreaker && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-2xl w-full p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Wand2 className="w-5 h-5 text-purple-600" />
                <div>
                  <h3 className="font-bold text-base text-slate-900">
                    AI Cold Outreach Hooks — {activeIcebreaker.business_name}
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Industry: {activeIcebreaker.industry || "Local Business"} • 1-on-1 personalized copy ready for outreach
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveIcebreaker(null)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            {/* Primary Full Opening Hook */}
            <div className="p-4 bg-gradient-to-br from-purple-50/60 to-indigo-50/60 border border-purple-200/70 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-purple-900 uppercase tracking-wide">
                  Primary 1-on-1 Cold Email Hook
                </span>
                <button
                  onClick={() => copyText(activeIcebreaker.full_opening_hook, "full_hook")}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-white border border-purple-200 text-purple-700 text-xs font-semibold hover:bg-purple-50 transition-colors shadow-2xs"
                >
                  {copiedKey === "full_hook" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === "full_hook" ? "Copied!" : "Copy"}
                </button>
              </div>
              <p className="text-sm font-medium text-slate-800 leading-relaxed bg-white/70 p-3 rounded-lg border border-purple-100 font-sans">
                &ldquo;{activeIcebreaker.full_opening_hook}&rdquo;
              </p>
            </div>

            {/* Sub-components & Angles */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Alternative Hook */}
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-700">Alternative Angle</span>
                  <button
                    onClick={() => copyText(activeIcebreaker.alternative_hook, "alt_hook")}
                    className="text-slate-500 hover:text-purple-600 p-1"
                    title="Copy"
                  >
                    {copiedKey === "alt_hook" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <p className="text-xs text-slate-600 italic leading-relaxed">
                  &ldquo;{activeIcebreaker.alternative_hook}&rdquo;
                </p>
              </div>

              {/* Genuine Compliment */}
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-700">Genuine Compliment</span>
                  <button
                    onClick={() => copyText(activeIcebreaker.compliment, "compliment")}
                    className="text-slate-500 hover:text-purple-600 p-1"
                    title="Copy"
                  >
                    {copiedKey === "compliment" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <p className="text-xs text-slate-600 italic leading-relaxed">
                  &ldquo;{activeIcebreaker.compliment}&rdquo;
                </p>
              </div>

              {/* Industry Pain Point */}
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-700">Industry Pain Point</span>
                  <button
                    onClick={() => copyText(activeIcebreaker.pain_point, "pain_point")}
                    className="text-slate-500 hover:text-purple-600 p-1"
                    title="Copy"
                  >
                    {copiedKey === "pain_point" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <p className="text-xs text-slate-600 italic leading-relaxed">
                  &ldquo;{activeIcebreaker.pain_point}&rdquo;
                </p>
              </div>

              {/* Low Friction CTA */}
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-700">Low-Friction Call-to-Action</span>
                  <button
                    onClick={() => copyText(activeIcebreaker.call_to_action, "cta")}
                    className="text-slate-500 hover:text-purple-600 p-1"
                    title="Copy"
                  >
                    {copiedKey === "cta" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <p className="text-xs text-slate-600 italic leading-relaxed">
                  &ldquo;{activeIcebreaker.call_to_action}&rdquo;
                </p>
              </div>
            </div>

            {/* Suggested Subject Line */}
            {activeIcebreaker.suggested_subject_line && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between text-xs">
                <div>
                  <span className="font-semibold text-slate-700 mr-2">Subject:</span>
                  <span className="font-mono text-slate-800">{activeIcebreaker.suggested_subject_line}</span>
                </div>
                <button
                  onClick={() => copyText(activeIcebreaker.suggested_subject_line, "subject")}
                  className="inline-flex items-center gap-1 text-slate-500 hover:text-purple-600 text-[11px] font-medium"
                >
                  {copiedKey === "subject" ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  {copiedKey === "subject" ? "Copied" : "Copy"}
                </button>
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setActiveIcebreaker(null)}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs shadow-xs"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Spam Checker Modal */}
      {showSpamModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-2xl w-full p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-purple-600" />
                <div>
                  <h3 className="font-bold text-base text-slate-900">Cold Email Deliverability & Spam Checker</h3>
                  <p className="text-[11px] text-slate-500">
                    Analyze trigger words, link density, formatting, and spam score to reach the inbox
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowSpamModal(false)}
                className="text-slate-400 hover:text-slate-600 font-bold text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleRunSpamCheck} className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Subject Line</label>
                <input
                  type="text"
                  required
                  value={spamSubject}
                  onChange={(e) => setSpamSubject(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500/20 text-xs font-sans"
                  placeholder="e.g. Quick question regarding {{business_name}}"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Email Body Text</label>
                <textarea
                  rows={6}
                  required
                  value={spamBody}
                  onChange={(e) => setSpamBody(e.target.value)}
                  className="w-full p-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500/20 text-xs font-sans leading-relaxed"
                  placeholder="Paste your cold email copy..."
                />
              </div>

              <div className="flex justify-between items-center pt-1">
                <div className="text-[11px] text-slate-400">
                  Supported variables: <code className="font-mono text-purple-600">&#123;&#123;business_name&#125;&#125;</code>, <code className="font-mono text-purple-600">&#123;&#123;first_name&#125;&#125;</code>, <code className="font-mono text-purple-600">&#123;&#123;city&#125;&#125;</code>
                </div>
                <button
                  type="submit"
                  disabled={checkingSpam}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs shadow-xs disabled:opacity-50"
                >
                  {checkingSpam ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                  Analyze Deliverability
                </button>
              </div>
            </form>

            {/* Spam Analysis Report */}
            {spamResult && (
              <div className="mt-4 p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex items-baseline gap-1">
                      <span className={`text-3xl font-extrabold ${
                        spamResult.score >= 80 ? "text-emerald-600" : spamResult.score >= 60 ? "text-amber-600" : "text-rose-600"
                      }`}>
                        {spamResult.score}
                      </span>
                      <span className="text-xs text-slate-400 font-bold">/100</span>
                    </div>

                    <span className={`px-2.5 py-1 rounded-full text-[11px] font-extrabold tracking-wide uppercase ${
                      spamResult.tier === "EXCELLENT"
                        ? "bg-emerald-100 text-emerald-800"
                        : spamResult.tier === "GOOD"
                        ? "bg-blue-100 text-blue-800"
                        : spamResult.tier === "NEEDS_IMPROVEMENT"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-rose-100 text-rose-800"
                    }`}>
                      {spamResult.tier.replace(/_/g, " ")}
                    </span>
                  </div>

                  <span className="text-xs font-medium text-slate-500">
                    {spamResult.is_safe ? "✓ Safe for Sending" : "⚠️ High Spam Risk"}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${
                      spamResult.score >= 80 ? "bg-emerald-500" : spamResult.score >= 60 ? "bg-amber-500" : "bg-rose-500"
                    }`}
                    style={{ width: `${Math.min(100, Math.max(5, spamResult.score))}%` }}
                  />
                </div>

                {/* Trigger Words */}
                {(spamResult.high_risk_words?.length > 0 || spamResult.moderate_risk_words?.length > 0) ? (
                  <div className="space-y-1.5 pt-1">
                    <div className="text-[11px] font-bold text-slate-700">Spam Trigger Words Detected:</div>
                    <div className="flex flex-wrap gap-1.5">
                      {spamResult.high_risk_words?.map((w: string, i: number) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 text-rose-800 text-[10px] font-semibold">
                          ⚠️ {w} (High Risk)
                        </span>
                      ))}
                      {spamResult.moderate_risk_words?.map((w: string, i: number) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-semibold">
                          {w}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg">
                    ✓ Zero spam trigger words detected.
                  </div>
                )}

                {/* Warnings / Recommendations */}
                {(spamResult.recommendations?.length > 0 || spamResult.warnings?.length > 0) && (
                  <div className="space-y-1.5 pt-1 border-t border-slate-200/80">
                    <div className="text-[11px] font-bold text-slate-700">Deliverability Recommendations:</div>
                    <ul className="text-xs text-slate-600 space-y-1 pl-4 list-disc">
                      {spamResult.recommendations?.map((rec: string, i: number) => (
                        <li key={i}>{rec}</li>
                      ))}
                      {spamResult.warnings?.map((warn: string, i: number) => (
                        <li key={i} className="text-amber-700">{warn}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowSpamModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs shadow-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
