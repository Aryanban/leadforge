"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { 
  Search, 
  Sparkles, 
  Loader2, 
  CheckCircle2, 
  AlertCircle, 
  ArrowRight, 
  RefreshCw,
  Sliders,
  Globe2,
  MapPin
} from "lucide-react";
import { api, ScrapeJob } from "@/lib/api";

const PRESET_QUERIES = [
  { label: "Rohini Property Dealers", query: "Real Estate Agents & Property Dealers in Rohini Delhi" },
  { label: "Sector 24 Rohini Brokers", query: "Property Dealers Sector 24 Rohini Delhi" },
  { label: "Pitampura Real Estate", query: "Property Consultants in Pitampura Delhi" },
  { label: "North Delhi Architects", query: "Architects and Interior Designers North Delhi" },
  { label: "Commercial Developers", query: "Commercial Property Developers & Builders Delhi NCR" },
];

export default function ScrapePage() {
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(20);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [activeJob, setActiveJob] = useState<ScrapeJob | null>(null);
  const [jobs, setJobs] = useState<ScrapeJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [enrichStatus, setEnrichStatus] = useState<string | null>(null);

  const fetchJobs = async () => {
    try {
      setLoadingJobs(true);
      const data = await api.getJobs();
      setJobs(data);
    } catch (err) {
      console.warn("Could not fetch jobs:", err);
    } finally {
      setLoadingJobs(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  // Poll active job status while running
  useEffect(() => {
    if (!activeJobId) return;

    const interval = setInterval(async () => {
      try {
        const job = await api.getJob(activeJobId);
        setActiveJob(job);
        if (job.status === "completed" || job.status === "failed") {
          clearInterval(interval);
          fetchJobs();
        }
      } catch (err) {
        console.error("Polling job status failed:", err);
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [activeJobId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    try {
      setIsSubmitting(true);
      const res = await api.startScrape(query.trim(), maxResults);
      setActiveJobId(res.job_id);
      setActiveJob({
        id: res.job_id,
        query: query.trim(),
        status: "pending",
        total_found: 0,
        leads_saved: 0,
        error: null,
        created_at: new Date().toISOString(),
        finished_at: null,
      });
      fetchJobs();
    } catch (err: any) {
      alert(`Scrape failed to start: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEnrichAll = async () => {
    try {
      setEnrichStatus("Enriching websites for emails...");
      const res = await api.enrichAll(25);
      setEnrichStatus(res.message || "Enrichment initiated in background!");
      setTimeout(() => setEnrichStatus(null), 6000);
    } catch (err: any) {
      setEnrichStatus(`Enrichment failed: ${err.message}`);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
          Google Maps Lead Scraper
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Extract business listings, phone numbers, websites, and addresses directly from Google Maps without expensive paid API keys.
        </p>
      </div>

      {/* Main Scrape Form */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-6 sm:p-7 shadow-xs space-y-6">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-blue-600" />
              Target Search Query & Location
            </label>
            <div className="flex gap-3">
              <div className="relative flex-1">
                <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="e.g. Real Estate Agents in Rohini Sector 24 Delhi"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full h-11 pl-10 pr-4 rounded-xl border border-slate-200 bg-slate-50/50 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-medium"
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting || !query.trim()}
                className="inline-flex items-center justify-center rounded-xl text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 h-11 px-5 transition-colors shadow-xs shrink-0"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    Start Scraping
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Quick Presets */}
          <div className="space-y-2">
            <span className="text-xs font-medium text-slate-500">Quick Presets:</span>
            <div className="flex flex-wrap gap-2">
              {PRESET_QUERIES.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => setQuery(p.query)}
                  className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 text-slate-600 transition-all font-medium"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Settings Row */}
          <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sliders className="w-4 h-4 text-slate-400" />
              <label className="text-xs text-slate-600 font-medium">Max Leads to Extract:</label>
              <select
                value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                className="h-8 px-2.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-800 focus:outline-none"
              >
                <option value={10}>10 Leads (Fast Test)</option>
                <option value={20}>20 Leads (Recommended)</option>
                <option value={50}>50 Leads (Deep Scan)</option>
                <option value={100}>100 Leads (Comprehensive)</option>
              </select>
            </div>

            <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              Anti-detection jitter enabled
            </div>
          </div>
        </form>
      </div>

      {/* Active Job Progress Banner */}
      {activeJob && (
        <div className="rounded-2xl border border-blue-200 bg-blue-50/60 p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              {activeJob.status === "running" || activeJob.status === "pending" ? (
                <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
              ) : activeJob.status === "completed" ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-600" />
              )}
              <div>
                <h3 className="font-bold text-sm text-slate-900">
                  {activeJob.status === "running"
                    ? "Scraping in Progress..."
                    : activeJob.status === "pending"
                    ? "Job Queued..."
                    : activeJob.status === "completed"
                    ? "Scrape Completed Successfully!"
                    : "Scrape Job Failed"}
                </h3>
                <p className="text-xs text-slate-600 mt-0.5">
                  Query: <span className="font-semibold text-slate-800">"{activeJob.query}"</span>
                </p>
              </div>
            </div>

            <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
              activeJob.status === "completed"
                ? "bg-emerald-100 text-emerald-800"
                : activeJob.status === "running"
                ? "bg-blue-100 text-blue-800 animate-pulse"
                : activeJob.status === "failed"
                ? "bg-red-100 text-red-800"
                : "bg-slate-100 text-slate-700"
            }`}>
              {activeJob.status}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-white p-3.5 rounded-xl border border-blue-100">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400">Total Found</span>
              <div className="text-lg font-bold text-slate-800">{activeJob.total_found}</div>
            </div>
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400">Leads Saved</span>
              <div className="text-lg font-bold text-emerald-600">{activeJob.leads_saved}</div>
            </div>
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400">Deduplication</span>
              <div className="text-lg font-bold text-slate-800">Active</div>
            </div>
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400">Started</span>
              <div className="text-xs font-medium text-slate-600 mt-1">
                {activeJob.created_at ? new Date(activeJob.created_at).toLocaleTimeString() : "Just now"}
              </div>
            </div>
          </div>

          {activeJob.status === "completed" && (
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Link
                href="/leads"
                className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 h-9 px-4 transition-colors"
              >
                View Discovered Leads <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
              </Link>
              <button
                onClick={handleEnrichAll}
                className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-blue-300 bg-white hover:bg-blue-50 text-blue-700 h-9 px-4 transition-colors"
              >
                <Globe2 className="w-3.5 h-3.5 mr-1.5" />
                Enrich Websites for Emails
              </button>
              {enrichStatus && (
                <span className="text-xs text-blue-700 font-medium animate-fade-in">
                  {enrichStatus}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Scrape History Table */}
      <div className="rounded-2xl border border-slate-200/80 bg-white shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-base text-slate-900">Scrape Task History</h3>
            <p className="text-xs text-slate-500 mt-0.5">Past queries and extracted leads</p>
          </div>
          <button
            onClick={fetchJobs}
            disabled={loadingJobs}
            className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-8 px-3 transition-colors shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loadingJobs ? "animate-spin text-blue-600" : ""}`} />
            Refresh History
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
              <tr>
                <th className="px-5 py-3">Search Query</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Leads Extracted</th>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {jobs && jobs.length > 0 ? (
                jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-5 py-3.5 font-medium text-slate-900">
                      {j.query}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        j.status === "completed"
                          ? "bg-emerald-100 text-emerald-800"
                          : j.status === "running"
                          ? "bg-blue-100 text-blue-800 animate-pulse"
                          : j.status === "failed"
                          ? "bg-red-100 text-red-800"
                          : "bg-slate-100 text-slate-700"
                      }`}>
                        {j.status}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-semibold text-slate-800">
                      {j.leads_saved} leads
                    </td>
                    <td className="px-4 py-3.5 text-slate-500">
                      {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        href="/leads"
                        className="text-xs font-semibold text-blue-600 hover:text-blue-700"
                      >
                        View Leads
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-slate-400">
                    No scrape jobs recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
