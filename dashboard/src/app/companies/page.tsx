"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Loader2, MapPin } from "lucide-react";
import { api, LeadItem } from "@/lib/api";

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

  const load = useCallback(async () => {
    try {
      const res = await api.getLeads({ page, limit: 25, search: search || undefined });
      setRows(res.leads);
      setTotal(res.total);
    } catch {
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / 25));


  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Companies</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {total} account{total === 1 ? "" : "s"} in your workspace. Contact coverage shows how
            many addresses are verified deliverable.
          </p>
        </div>
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search companies..."
          className="h-9 w-64 rounded-xl border border-slate-200 bg-slate-50/50 px-3 text-xs text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
        />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <table className="w-full text-left">
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
              <tr>
                <td colSpan={6} className="px-5 py-12 text-center text-slate-400">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
                  Loading companies...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-12 text-center text-sm text-slate-500">
                  No companies found. Scrape or discover leads first.
                </td>
              </tr>
            ) : (
              rows.map((b) => {
                const contacts = b.contacts ?? [];
                const verified = contacts.filter((c) => c.is_verified).length;
                const mapsUrl = b.maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((b.name + " " + (b.address || "")).trim())}`;
                return (
                  <tr key={b.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-5 py-3.5">
                      <a
                        href={mapsUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-bold text-slate-900 hover:text-blue-600 inline-flex items-center gap-1.5 max-w-full"
                      >
                        <span className="truncate">{b.name}</span>
                        <MapPin className="w-3.5 h-3.5 text-red-500 shrink-0" />
                      </a>
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-600">{b.industry || "—"}</td>
                    <td className="px-4 py-3.5 text-right text-sm text-slate-600 tabular-nums">{contacts.length}</td>
                    <td className="px-4 py-3.5 text-right text-sm tabular-nums">
                      <span className={verified > 0 ? "font-semibold text-emerald-600" : "text-slate-400"}>
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
