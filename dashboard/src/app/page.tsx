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
  Info,
  ShieldAlert,
  PartyPopper,
  Moon,
  Database
} from "lucide-react";
import dynamic from "next/dynamic";
import { api, DashboardStats, TaskItem, TimeSeriesResponse } from "@/lib/api";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  Skeleton,
  StatsSkeleton,
  StatusLive,
  TableSkeleton,
} from "@/components/PageStates";

/**
 * The activity chart is loaded on demand.
 *
 * `recharts` and its d3 dependencies are ~100 kB of JavaScript, and they
 * were ending up in the *shared* chunk - so every route (the inbox, the
 * scraper, the settings page, the lead database) downloaded a charting
 * library that only the overview ever renders. Importing the chart module
 * through `next/dynamic` moves recharts into a chunk that is fetched only
 * when this page actually shows the chart.
 */
const ActivityChart = dynamic(() => import("@/components/ActivityChart"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center" aria-hidden="true">
      <Skeleton className="h-[85%] w-full rounded-xl" />
    </div>
  ),
});

/**
 * The readiness strip at the top of the dashboard.
 *
 * It is deliberately NOT the shared `IndiaReadiness` banner: that one only
 * renders when there is something to say, so it used to appear a beat after
 * the first paint and shove the whole dashboard down (the single biggest
 * layout shift on this page). This version always occupies the same box,
 * says what it found, and never moves anything.
 */
function HomeReadiness() {
  const [notes, setNotes] = useState<
    Array<{ kind: "warn" | "fest"; title: string; detail: string }> | null
  >(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getIndiaAdvisor()
      .then((r) => {
        if (cancelled) return;
        const found: Array<{ kind: "warn" | "fest"; title: string; detail: string }> = [];
        if (r.auth && !r.auth.ok) {
          found.push({
            kind: "warn",
            title: `Sender auth incomplete for ${r.auth.domain}`,
            detail: r.auth.warnings.join(" "),
          });
        }
        if (r.quiet_hours_now) {
          found.push({
            kind: "warn",
            title: "TRAI quiet hours (21:00–09:00 IST)",
            detail: "Hold promotional SMS/voice until morning. Email is unaffected.",
          });
        }
        if (r.festival?.festival) {
          found.push({
            kind: "fest",
            title: `${r.festival.emoji} ${r.festival.festival} window — seasonal hook available`,
            detail: r.festival.hinglish_line || r.festival.subject_hook || "",
          });
        }
        setNotes(found);
      })
      .catch(() => {
        if (!cancelled) setNotes([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasWarn = (notes ?? []).some((n) => n.kind === "warn");
  const shell = hasWarn
    ? "border-amber-200 bg-amber-50/70"
    : "border-slate-200 bg-white";

  return (
    <div
      className={`h-[112px] rounded-2xl border p-4 shadow-xs ${shell} ${
        notes === null ? "animate-pulse" : ""
      }`}
    >
      {notes === null ? (
        <div className="flex h-full items-start gap-2" aria-hidden="true">
          <Skeleton className="mt-0.5 h-4 w-4 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-56" />
            <Skeleton className="h-2.5 w-full max-w-[420px]" />
          </div>
        </div>
      ) : notes.length === 0 ? (
        <div className="flex h-full items-start gap-2.5">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-slate-800">India readiness — all clear</p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
              No sender-auth warnings, no TRAI quiet hours, no seasonal hold. Campaigns can send now.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex h-full items-start gap-2.5">
          <div
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
              hasWarn ? "bg-amber-100 text-amber-700" : "bg-purple-100 text-purple-700"
            }`}
          >
            {hasWarn ? <ShieldAlert className="h-4 w-4" /> : <PartyPopper className="h-4 w-4" />}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold text-slate-800">
              India readiness — {notes.length} note{notes.length > 1 ? "s" : ""}
            </p>
            <ul className="mt-1 space-y-1">
              {notes.slice(0, 2).map((n, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[11px] leading-relaxed">
                  {n.kind === "fest" ? (
                    <PartyPopper className="mt-0.5 h-3 w-3 shrink-0 text-purple-600" />
                  ) : (
                    <Moon className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" />
                  )}
                  <span>
                    <strong className="font-semibold text-slate-800">{n.title}.</strong>{" "}
                    <span className="text-slate-600">{n.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [series, setSeries] = useState<TimeSeriesResponse | null>(null);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
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
      setError(
        err instanceof Error && err.message
          ? err.message
          : "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const hasSends = (series?.totals.sent ?? 0) > 0;

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Screen-reader announcement of the dashboard's loading state. */}
      <StatusLive loading={loading} loadingLabel="Loading your dashboard…" />

      {/* Header */}
      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Autonomous Outreach Hub
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time lead scanning, website contact enrichment, and automated cold email campaigns.
          </p>
        </div>
        <div className="flex items-center gap-3 sm:justify-end">
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "motion-safe:animate-spin motion-reduce:animate-pulse text-blue-600" : ""}`} />
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

      {/* Inline error — the toast is transient, this stays on screen. */}
      {error && (
        <ErrorState
          title="Could not load the dashboard"
          message={error}
          onRetry={loadData}
        />
      )}

      {/* India readiness: auth, quiet hours, festival hooks — advisory only.
          Fixed height so it can never shove the page down when it lands. */}
      <HomeReadiness />

      {/* Tasks — Apollo home's actionable checklist, computed from real state.
          Always rendered (and a fixed height) so the card cannot appear
          halfway down the page and move everything under it. */}
      <div className="h-[150px] rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
          <ListChecks className="w-3.5 h-3.5" /> Needs attention
        </h2>
        {loading ? (
          <div className="space-y-1.5" aria-hidden="true">
            <Skeleton className="h-9 w-full rounded-xl" />
            <Skeleton className="h-9 w-4/5 rounded-xl" />
          </div>
        ) : tasks.length > 0 ? (
          <div className="space-y-1.5 overflow-y-auto h-[98px]">
            {tasks.map((t) => (
              <Link
                key={t.key}
                href={t.href}
                className="flex items-center gap-2.5 rounded-xl px-3 py-2 hover:bg-slate-50 transition-colors group"
              >
                {t.severity === "high" ? (
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                ) : (
                  <Info className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                )}
                <span className="text-[13px] text-slate-700 flex-1 truncate">{t.label}</span>
                <ArrowUpRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-blue-500 shrink-0" />
              </Link>
            ))}
          </div>
        ) : (
          <div className="flex h-[98px] items-center gap-2.5 rounded-xl bg-emerald-50/60 px-3 py-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
            <p className="text-[13px] text-slate-600">
              Nothing needs attention — every mailbox is verified and no suppression is pending.
            </p>
          </div>
        )}
      </div>

      {/* 30-day activity chart — real per-day send activity. Always rendered
          (with an empty state) so the block cannot appear late and move the
          page down. */}
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Outreach activity · last {series?.period_days ?? 30} days
          </h2>
          {series && (
            <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
              <span><span className="font-bold text-slate-700">{series.totals.sent}</span> sent</span>
              <span><span className="font-bold text-slate-700">{series.totals.opened}</span> opened</span>
              <span><span className="font-bold text-slate-700">{series.totals.replied}</span> replied</span>
              <span><span className="font-bold text-slate-700">{series.totals.open_rate}%</span> open rate</span>
              <span className="font-bold text-slate-700">{series.totals.reply_rate}% reply rate</span>
            </div>
          )}
        </div>
        <div className="h-56">
          {loading ? (
            <div className="flex h-full items-center justify-center" aria-hidden="true">
              <Skeleton className="h-[85%] w-full rounded-xl" />
            </div>
          ) : hasSends && series ? (
            <ActivityChart series={series} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-slate-200 bg-slate-50/40 text-center">
              <Mail className="h-5 w-5 text-slate-500" />
              <p className="text-xs font-semibold text-slate-600">No outreach sent in the last 30 days</p>
              <p className="text-[11px] text-slate-500">
                Pick leads in the database, add them to a sequence and launch it.
              </p>
              <Link
                href="/sequences"
                className="mt-1 inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-blue-700"
              >
                <Send className="w-3 h-3" /> Open sequences
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      {loading ? (
        <StatsSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Leads</span>
              <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <Building2 className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-3xl font-extrabold text-slate-900">{stats?.total_leads ?? 0}</div>
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
              <div className="text-3xl font-extrabold text-slate-900">{stats?.verified_contacts ?? 0}</div>
              <p className="text-xs text-slate-500 mt-1">
                DNS MX &amp; SMTP handshake verified
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
              <div className="text-3xl font-extrabold text-slate-900">{stats?.emails_sent ?? 0}</div>
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
      )}

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
              className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
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
            <table className="w-full table-fixed text-left text-xs">
              <colgroup>
                <col style={{ width: "30%" }} />
                <col style={{ width: "18%" }} />
                <col style={{ width: "24%" }} />
                <col style={{ width: "16%" }} />
                <col style={{ width: "12%" }} />
              </colgroup>
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
                {loading ? (
                  <TableSkeleton rows={5} columns={5} rowClassName="h-[46px]" cellClassName="px-4 py-3.5" />
                ) : stats?.recent_leads && stats.recent_leads.length > 0 ? (
                  stats.recent_leads.map((lead) => (
                    <tr key={lead.id} className="h-[46px] hover:bg-slate-50/80 transition-colors">
                      <td className="px-5 py-3.5 font-medium text-slate-900 max-w-[220px]">
                        <a
                          href={lead.maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(lead.name)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-blue-600 inline-flex items-center gap-1.5 truncate group max-w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
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
                          <span className="text-slate-500 italic">Not enriched</span>
                        )}
                      </td>
                      <td className="px-4 py-3.5 text-slate-600 font-mono text-[11px]">
                        {lead.phone || "—"}
                      </td>
                      <td className="px-4 py-3.5 text-right font-medium text-amber-700">
                        {lead.rating ? `★ ${lead.rating}` : "—"}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-5 py-8">
                      <EmptyState
                        icon={<Database className="h-5 w-5" />}
                        title="No leads discovered yet"
                        description="Run your first scrape and the newest businesses will show up here with their contact details."
                        action={
                          <Link
                            href="/scrape"
                            className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700"
                          >
                            <Search className="w-3.5 h-3.5" /> Scrape leads
                          </Link>
                        }
                        secondaryAction={
                          <Link
                            href="/leads"
                            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50"
                          >
                            <Users className="w-3.5 h-3.5" /> Open lead database
                          </Link>
                        }
                      />
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
            {loading ? (
              <>
                <CardSkeleton lines={1} />
                <CardSkeleton lines={1} />
                <CardSkeleton lines={1} />
                <CardSkeleton lines={1} />
                <CardSkeleton lines={1} />
              </>
            ) : stats?.recent_jobs && stats.recent_jobs.length > 0 ? (
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
              <div className="py-4">
                <EmptyState
                  icon={<Sparkles className="h-5 w-5" />}
                  title="No scrape jobs yet"
                  description="Start a Google Maps scrape and the job history will show up here."
                  action={
                    <Link
                      href="/scrape"
                      className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700"
                    >
                      <Search className="w-3.5 h-3.5" /> New scrape job
                    </Link>
                  }
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
