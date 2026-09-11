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
  ExternalLink
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
      const res = await api.enrichLead(businessId);
      alert(`Enrichment complete! Found ${res.emails_found || 0} emails (${res.verified_emails || 0} verified).`);
      fetchLeads();
    } catch (err: any) {
      alert(`Enrichment notice: ${err.message}`);
    } finally {
      setEnrichingId(null);
    }
  };

  const handleBulkEnrich = async () => {
    try {
      setBulkEnrichLoading(true);
      const res = await api.enrichAll(25);
      alert(res.message || "Bulk website enrichment started in background!");
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

          <a
            href={api.exportCsvUrl}
            download="leadforge_leads.csv"
            className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
          >
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Export CSV
          </a>

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
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
                    Loading leads database...
                  </td>
                </tr>
              ) : leads && leads.length > 0 ? (
                leads.map((lead) => {
                  const contact = lead.primary_contact;
                  const cleanPhone = lead.phone ? lead.phone.replace(/[^0-9]/g, "") : "";
                  const waUrl = contact?.whatsapp_link || (cleanPhone ? `https://wa.me/${cleanPhone}` : null);

                  return (
                    <tr key={lead.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-5 py-4 max-w-[240px]">
                        <div className="font-bold text-slate-900 truncate">{lead.name}</div>
                        <div className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">{lead.address || "Address not listed"}</div>
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
                        ) : lead.website ? (
                          <button
                            onClick={() => handleEnrichSingle(lead.id)}
                            disabled={enrichingId === lead.id}
                            className="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:text-blue-800 font-semibold"
                          >
                            {enrichingId === lead.id ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Crawling...
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-3 h-3" />
                                Enrich Email
                              </>
                            )}
                          </button>
                        ) : (
                          <span className="text-slate-400 italic text-[11px]">No contact</span>
                        )}
                      </td>

                      <td className="px-4 py-4 whitespace-nowrap text-amber-600 font-medium text-[11px]">
                        {lead.rating ? `★ ${lead.rating} (${lead.reviews_count || 0})` : "—"}
                      </td>

                      <td className="px-5 py-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => handleDelete(lead.id)}
                          className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors"
                          title="Delete Lead"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
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
    </div>
  );
}
