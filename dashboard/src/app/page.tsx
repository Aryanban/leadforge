"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { 
  Users, 
  Building2, 
  Send, 
  CheckCircle2, 
  Search, 
  ArrowUpRight, 
  Download, 
  Mail, 
  RefreshCw,
  Sparkles,
  Phone,
  MapPin,
  ExternalLink,
  ListChecks,
  AlertTriangle,
  Info
} from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend
} from "recharts";
import { api, DashboardStats, TaskItem, TimeSeriesResponse } from "@/lib/api";
import { IndiaReadiness } from "@/components/IndiaKit";

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [series, setSeries] = useState<TimeSeriesResponse | null>(null);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      // Real data only — an offline/empty backend shows empty states, never
      // fake demo numbers (old behaviour lied to the operator about their
      // actual outreach volume).
      const [data, ts, taskRes] = await Promise.all([
        api.getStats(),
        api.getTimeseries(30),
        api.getTasks(),
      ]);
      setStats(data);
      setSeries(ts);
      setTasks(taskRes.tasks ?? []);
    } catch (err) {
      console.warn("Could not fetch dashboard data:", err);
      setStats(null);
      setSeries(null);
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Autonomous Outreach Hub
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time lead scanning, website contact enrichment, and automated cold email campaigns.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin text-blue-600" : ""}`} />
            Refresh
          </button>
          <Link
            href="/scrape"
            className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 h-9 px-4 transition-colors shadow-xs"
          >
            <Search className="w-3.5 h-3.5 mr-1.5" />
            New Scrape Job
          </Link>
        </div>
      </div>

      {/* India readiness: auth, quiet hours, festival hooks — advisory only */}
      <IndiaReadiness />

      {/* Tasks — Apollo home's actionable checklist, computed from real state */}
      {tasks.length > 0 && (
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
            <ListChecks className="w-3.5 h-3.5" /> Needs attention
          </h2>
          <div className="space-y-1.5">
            {tasks.map((t) => (
              <Link
                key={t.key}
                href={t.href}
                className="flex items-center gap-2.5 rounded-xl px-3 py-2 hover:bg-slate-50 transition-colors group"
              >
                {t.severity === "high" ? (
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                ) : (
                  <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                )}
                <span className="text-[13px] text-slate-700 flex-1 truncate">{t.label}</span>
                <ArrowUpRight className="w-3.5 h-3.5 text-slate-300 group-hover:text-blue-500 shrink-0" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 30-day activity chart — real per-day send activity */}
      {series && series.totals.sent > 0 && (
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Outreach activity · last {series.period_days} days
            </h2>
            <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
              <span><span className="font-bold text-slate-700">{series.totals.sent}</span> sent</span>
              <span><span className="font-bold text-slate-700">{series.totals.opened}</span> opened</span>
              <span><span className="font-bold text-slate-700">{series.totals.replied}</span> replied</span>
              <span><span className="font-bold text-slate-700">{series.totals.open_rate}%</span> open rate</span>
              <span className="font-bold text-slate-700">{series.totals.reply_rate}% reply rate</span>
            </div>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series.days} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "#94a3b8" }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #e2e8f0" }}
                  labelStyle={{ color: "#64748b" }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="sent" stroke="#2563eb" strokeWidth={2} dot={false} name="Sent" />
                <Line type="monotone" dataKey="opened" stroke="#7c3aed" strokeWidth={2} dot={false} name="Opened" />
                <Line type="monotone" dataKey="replied" stroke="#059669" strokeWidth={2} dot={false} name="Replied" />
                <Line type="monotone" dataKey="bounced" stroke="#dc2626" strokeWidth={2} dot={false} name="Bounced" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Leads</span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
              <Building2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-slate-900">{stats?.total_leads ?? "..."}</div>
            {/* No fake delta here: the API exposes no period-scoped discovery
                count, so we show the absolute total instead of claiming every
                lead was found this month. */}
            <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
              businesses in your database
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Verified Emails</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-slate-900">{stats?.verified_contacts ?? "..."}</div>
            <p className="text-xs text-slate-500 mt-1">
              DNS MX & SMTP handshake verified
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Emails Sent</span>
            <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <Send className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-slate-900">{stats?.emails_sent ?? "..."}</div>
            <p className="text-xs text-slate-500 mt-1">
              {series
                ? `${series.totals.sent} sent in the last ${series.period_days} days`
                : "Across active campaigns"}
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Open Rate</span>
            <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
              <Mail className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-slate-900">{stats?.open_rate ? `${stats.open_rate}%` : "0%"}</div>
            <p className="text-xs text-slate-500 mt-1">
              Tracked via 1x1 pixel telemetry
            </p>
          </div>
        </div>
      </div>

      {/* Quick Launch Panel */}
      <div className="rounded-2xl border border-blue-200 bg-gradient-to-r from-blue-50/70 via-indigo-50/40 to-white p-6 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-600" />
              <h3 className="text-base font-bold text-slate-900">Run Automated Lead Generation</h3>
            </div>
            <p className="text-xs text-slate-600">
              Scan Google Maps for local real estate agents, enrich their websites for direct contact emails, and launch outreach campaigns.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/scrape"
              className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 h-9 px-4 transition-colors shadow-xs"
            >
              <Search className="w-3.5 h-3.5 mr-1.5" />
              Scan Google Maps
            </Link>
            <a
              href={api.exportCsvUrl}
              download="leads.csv"
              className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              Export CSV
            </a>
            <Link
              href="/campaigns"
              className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs"
            >
              <Mail className="w-3.5 h-3.5 mr-1.5" />
              Campaign Studio
            </Link>
          </div>
        </div>
      </div>

      {/* Tables: Recent Leads & Recent Jobs */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent Leads - 2 columns */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-200/80 bg-white shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h3 className="font-bold text-base text-slate-900">Recent Discovered Leads</h3>
              <p className="text-xs text-slate-500 mt-0.5">Businesses discovered from recent searches</p>
            </div>
            <Link
              href="/leads"
              className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
            >
              View All Leads <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="px-5 py-3">Business Name</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Contact Email</th>
                  <th className="px-4 py-3">Phone</th>
                  <th className="px-4 py-3 text-right">Rating</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stats?.recent_leads && stats.recent_leads.length > 0 ? (
                  stats.recent_leads.map((lead) => (
                    <tr key={lead.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-5 py-3.5 font-medium text-slate-900 max-w-[220px]">
                        <a
                          href={lead.maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(lead.name)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-blue-600 inline-flex items-center gap-1.5 truncate group max-w-full"
                          title="View on Google Maps"
                        >
                          <span className="truncate">{lead.name}</span>
                          <MapPin className="w-3 h-3 text-red-500 shrink-0 group-hover:scale-110 transition-transform" />
                        </a>
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">
                        <span className="inline-block px-2 py-0.5 bg-slate-100 rounded-md text-[11px] font-medium text-slate-700">
                          {lead.industry}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">
                        {lead.email ? (
                          <div className="flex items-center gap-1.5">
                            <span className="truncate max-w-[160px] font-mono text-[11px]">{lead.email}</span>
                            {lead.is_verified && (
                              <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-100 text-emerald-700">
                                ✓
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-400 italic">Not enriched</span>
                        )}
                      </td>
                      <td className="px-4 py-3.5 text-slate-600 font-mono text-[11px]">
                        {lead.phone || "—"}
                      </td>
                      <td className="px-4 py-3.5 text-right font-medium text-amber-600">
                        {lead.rating ? `★ ${lead.rating}` : "—"}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-slate-400">
                      No leads scanned yet. Run your first scrape above!
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Scrape Jobs - 1 column */}
        <div className="rounded-2xl border border-slate-200/80 bg-white shadow-xs overflow-hidden flex flex-col">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h3 className="font-bold text-base text-slate-900">Scrape Jobs</h3>
              <p className="text-xs text-slate-500 mt-0.5">Execution history</p>
            </div>
            <Link
              href="/scrape"
              className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
            >
              New Job <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="p-4 space-y-3 flex-1 overflow-y-auto">
            {stats?.recent_jobs && stats.recent_jobs.length > 0 ? (
              stats.recent_jobs.map((job) => (
                <div key={job.id} className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/50 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-semibold text-slate-800 line-clamp-1">{job.query}</p>
                    <span
                      className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        job.status === "completed"
                          ? "bg-emerald-100 text-emerald-800"
                          : job.status === "running"
                          ? "bg-blue-100 text-blue-800 animate-pulse"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {job.status}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span>Leads saved: <strong className="text-slate-700 font-bold">{job.leads_saved}</strong></span>
                    <span>{job.created_at ? new Date(job.created_at).toLocaleDateString() : ""}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400 text-center py-6">No jobs recorded yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
