"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Loader2, MapPin, Search, SearchX, X } from "lucide-react";
import { api, LeadItem } from "@/lib/api";
import { EmptyState, ErrorState, StatusLive, TableSkeleton } from "@/components/PageStates";

/** Accounts per page — the backend paginates on the same number. */
const PAGE_SIZE = 25;

/**
 * Companies — the Apollo "Accounts" view: one row per company with contact
 * coverage (total vs verified), rating, and location. Powered by the same
 * /leads endpoint as the Lead Database — the difference is presentation:
 * accounts aggregate their contacts, people (the DB) list them.
 */
export default function CompaniesPage() {
  const [rows, setRows] = useState<LeadItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getLeads({ page, limit: PAGE_SIZE, search: search || undefined });
      setRows(res.leads);
      setTotal(res.total);
    } catch (err: any) {
      setRows([]);
      setTotal(0);
      setError(
        err?.message || "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      {/* Screen-reader announcement of the loading state. */}
      <StatusLive loading={loading} loadingLabel="Loading your companies…" />

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Companies</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {total} account{total === 1 ? "" : "s"} in your workspace. Contact coverage shows how
            many addresses are verified deliverable.
          </p>
        </div>
        <div className="relative sm:justify-self-end">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search companies..."
            aria-label="Search companies by name"
            className="h-9 w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 text-xs text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300 sm:w-64"
          />
        </div>
      </div>

      {/* Inline error with a retry — the toast is transient, this is not. */}
      {error && !loading && (
        <ErrorState
          title="Could not load your companies"
          message={error}
          onRetry={load}
        />
      )}

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] table-fixed text-left">
            <colgroup>
              <col style={{ width: "30%" }} />
              <col style={{ width: "18%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: "10%" }} />
              <col style={{ width: "18%" }} />
            </colgroup>
            <thead>
              <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                <th className="px-5 py-3 font-semibold">Company</th>
                <th className="px-4 py-3 font-semibold">Industry</th>
                <th className="px-4 py-3 font-semibold text-right">Contacts</th>
                <th className="px-4 py-3 font-semibold text-right">Verified</th>
                <th className="px-4 py-3 font-semibold text-right">Rating</th>
                <th className="px-4 py-3 font-semibold">Location</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <TableSkeleton
                  rows={PAGE_SIZE}
                  columns={6}
                  rowClassName="h-[49px]"
                  cellClassName="px-4 py-3.5"
                />
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8">
                    {search.trim() ? (
                      /* Filtered to nothing — the data is there, the filter is
                         too narrow. Offer the way back. */
                      <EmptyState
                        icon={<SearchX className="h-5 w-5" />}
                        title="No companies match this search"
                        description={`Nothing in your workspace matches “${search.trim()}”. Widen the search or clear it to see every account.`}
                        action={
                          <button
                            onClick={() => { setSearch(""); setPage(1); }}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700"
                          >
                            <X className="w-3.5 h-3.5" /> Clear search
                          </button>
                        }
                      />
                    ) : (
                      /* Nothing scraped yet — point at the two ways in. */
                      <EmptyState
                        icon={<Building2 className="h-5 w-5" />}
                        title="No companies yet"
                        description="Scrape Google Maps for local businesses, or let LeadForge find and rank the best prospects for your niche."
                        action={
                          <a
                            href="/scrape"
                            className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                          >
                            <Search className="w-3.5 h-3.5" /> Scrape leads
                          </a>
                        }
                        secondaryAction={
                          <a
                            href="/find"
                            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                          >
                            Find leads
                          </a>
                        }
                      />
                    )}
                  </td>
                </tr>
              ) : (
                rows.map((b) => {
                  const contacts = b.contacts ?? [];
                  const verified = contacts.filter((c) => c.is_verified).length;
                  const mapsUrl = b.maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((b.name + " " + (b.address || "")).trim())}`;
                  return (
                    <tr key={b.id} className="h-[49px] hover:bg-slate-50/80 transition-colors">
                      <td className="px-5 py-3.5">
                        <a
                          href={mapsUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-bold text-slate-900 hover:text-blue-600 inline-flex items-center gap-1.5 max-w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                        >
                          <span className="truncate">{b.name}</span>
                          <MapPin className="w-3 h-3 text-red-500 shrink-0" />
                        </a>
                      </td>
                      <td className="px-4 py-3.5 text-xs text-slate-600 truncate">{b.industry || "—"}</td>
                      <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">{contacts.length}</td>
                      <td className="px-4 py-3.5 text-right text-sm tabular-nums">
                        <span className={verified > 0 ? "font-semibold text-emerald-700" : "text-slate-500"}>
                          {verified}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">
                        {b.rating ? `★ ${b.rating}` : "—"}
                      </td>
                      <td className="px-4 py-3.5 text-xs text-slate-500 truncate max-w-[200px]">{b.address || "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="border-t border-slate-200 px-5 py-3 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 disabled:opacity-40 hover:border-slate-300"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 disabled:opacity-40 hover:border-slate-300"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
