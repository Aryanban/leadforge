"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Briefcase,
  Building2,
  CheckCircle2,
  Loader2,
  Mail,
  MapPin,
  MessageCircle,
  Phone,
  Search,
  SearchX,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  api,
  PeopleFacets,
  PeopleQuery,
  PeopleStats,
  PersonRow,
} from "@/lib/api";
import { EmptyState, ErrorState, StatusLive, TableSkeleton } from "@/components/PageStates";

/** People per page — the backend paginates on the same number. */
const PAGE_SIZE = 25;

/** Seniority bands, in the order the API reports them. */
const SENIORITY_ORDER = [
  "owner",
  "c_level",
  "vp",
  "director",
  "head",
  "manager",
  "senior",
  "staff",
  "other",
  "unknown",
];

const SENIORITY_LABELS: Record<string, string> = {
  owner: "Owner / Founder",
  c_level: "C-Level / MD",
  vp: "VP / Deputy MD",
  director: "Director",
  head: "Head of Function",
  manager: "Manager",
  senior: "Senior / Lead",
  staff: "Staff / Associate",
  other: "Other",
  unknown: "Unknown",
};

const TIER_LABELS: Record<string, string> = {
  metro: "Metro",
  tier_2: "Tier 2",
  tier_3: "Tier 3",
};

/** Filter chips that are currently applied, so they can be removed one by one. */
type ActiveFilter = { key: keyof PeopleQuery; label: string; value: string };

/**
 * People — the Apollo "People" view: one row per human, with the company
 * attributes joined in and every column filterable.
 *
 * The distinction that matters here is *person* versus *business target*.
 * LeadForge's discovery finds companies; the people behind them are read
 * off the company's own site. A row with a name and a role is a person. A
 * row without one is the business with a phone and a WhatsApp number, and
 * it says so rather than inventing a founder.
 */
export default function PeoplePage() {
  const [rows, setRows] = useState<PersonRow[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [stats, setStats] = useState<PeopleStats | null>(null);
  const [facets, setFacets] = useState<PeopleFacets | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- filter state ---
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [seniority, setSeniority] = useState("");
  const [city, setCity] = useState("");
  const [marketTier, setMarketTier] = useState("");
  const [hasEmail, setHasEmail] = useState<"" | "yes" | "no">("");
  const [decisionOnly, setDecisionOnly] = useState(false);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [personOnly, setPersonOnly] = useState(true);
  const [sort, setSort] = useState("created");
  const [desc, setDesc] = useState(true);

  const searchRef = useRef<HTMLInputElement>(null);

  // Debounce the search so a keystroke does not fire a request each time.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = useMemo<PeopleQuery>(() => {
    const q: PeopleQuery = {
      page,
      limit: PAGE_SIZE,
      sort,
      desc,
      person_only: personOnly,
    };
    if (debouncedSearch.trim()) q.search = debouncedSearch.trim();
    if (seniority) q.seniority = seniority;
    if (city) q.city = city;
    if (marketTier) q.market_tier = marketTier;
    if (hasEmail === "yes") q.has_email = true;
    if (hasEmail === "no") q.has_email = false;
    if (decisionOnly) q.decision_makers_only = true;
    if (verifiedOnly) q.verified_only = true;
    return q;
  }, [
    page, sort, desc, personOnly, debouncedSearch, seniority, city,
    marketTier, hasEmail, decisionOnly, verifiedOnly,
  ]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getPeople(query);
      setRows(res.people);
      setTotal(res.total);
      setPages(Math.max(1, res.pages));
    } catch (err: any) {
      setRows([]);
      setTotal(0);
      setError(
        err?.message || "The backend did not answer. Check that it is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    load();
  }, [load]);

  // Stats and facets change only when the population changes, not when the
  // filters do — they describe the whole workspace.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, f] = await Promise.all([api.getPeopleStats(), api.getPeopleFacets()]);
        if (!cancelled) {
          setStats(s);
          setFacets(f);
        }
      } catch {
        /* The table still works without the summary; do not blank the page. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [personOnly]);

  const activeFilters = useMemo<ActiveFilter[]>(() => {
    const out: ActiveFilter[] = [];
    if (debouncedSearch.trim())
      out.push({ key: "search", label: "Search", value: debouncedSearch.trim() });
    if (seniority)
      out.push({
        key: "seniority",
        label: "Role",
        value: SENIORITY_LABELS[seniority] || seniority,
      });
    if (city) out.push({ key: "city", label: "City", value: city });
    if (marketTier)
      out.push({
        key: "market_tier",
        label: "Market",
        value: TIER_LABELS[marketTier] || marketTier,
      });
    if (hasEmail)
      out.push({
        key: "has_email",
        label: "Email",
        value: hasEmail === "yes" ? "Has email" : "No email",
      });
    if (decisionOnly)
      out.push({
        key: "decision_makers_only",
        label: "Role",
        value: "Decision makers only",
      });
    if (verifiedOnly)
      out.push({ key: "verified_only", label: "Email", value: "Verified only" });
    if (!personOnly)
      out.push({
        key: "person_only",
        label: "Rows",
        value: "Including business targets",
      });
    return out;
  }, [
    debouncedSearch, seniority, city, marketTier, hasEmail, decisionOnly,
    verifiedOnly, personOnly,
  ]);

  const clearFilter = (key: keyof PeopleQuery) => {
    setPage(1);
    switch (key) {
      case "search": setSearch(""); setDebouncedSearch(""); break;
      case "seniority": setSeniority(""); break;
      case "city": setCity(""); break;
      case "market_tier": setMarketTier(""); break;
      case "has_email": setHasEmail(""); break;
      case "decision_makers_only": setDecisionOnly(false); break;
      case "verified_only": setVerifiedOnly(false); break;
      case "person_only": setPersonOnly(true); break;
    }
  };

  const clearAll = () => {
    setSearch(""); setDebouncedSearch("");
    setSeniority(""); setCity(""); setMarketTier("");
    setHasEmail(""); setDecisionOnly(false); setVerifiedOnly(false);
    setPersonOnly(true);
    setPage(1);
  };

  // "/" focuses the search box, Escape clears it - the same shortcuts the
  // rest of the dashboard uses.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "Escape" && typing && target === searchRef.current) {
        setSearch("");
        setDebouncedSearch("");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const hasFilters = activeFilters.length > 0;

  return (
    <div className="p-6 space-y-5 max-w-[1500px] mx-auto">
      <StatusLive loading={loading} loadingLabel="Loading your people…" />

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">People</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {stats
              ? `${stats.total_people} identified ${stats.total_people === 1 ? "person" : "people"} · ${stats.decision_makers} decision makers · ${stats.with_email} with a verified channel`
              : "One row per human, with the company attributes joined in."}
          </p>
        </div>
        <div className="relative sm:justify-self-end">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            ref={searchRef}
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search people or companies…  ( / )"
            aria-label="Search people by name, title, company or city"
            className="h-9 w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 text-xs text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300 sm:w-72"
          />
        </div>
      </div>

      {/* Summary tiles */}
      {stats && (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Identified people"
            value={stats.total_people}
            hint={
              stats.total_contacts
                ? `${stats.coverage}% of ${stats.total_contacts} contacts`
                : undefined
            }
            icon={<Sparkles className="h-4 w-4" />}
          />
          <StatTile
            label="Decision makers"
            value={stats.decision_makers}
            hint="Owner, C-level, VP, director, head"
            icon={<Briefcase className="h-4 w-4" />}
          />
          <StatTile
            label="With an email"
            value={stats.with_email}
            hint={`${stats.verified} verified deliverable`}
            icon={<Mail className="h-4 w-4" />}
          />
          <StatTile
            label="Business targets"
            value={stats.business_targets}
            hint="No person identified yet"
            icon={<Building2 className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Filter bar */}
      <div className="rounded-2xl border border-slate-200 bg-white p-3.5 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <FilterSelect
            label="Role"
            value={seniority}
            onChange={(v) => { setSeniority(v); setPage(1); }}
            options={SENIORITY_ORDER.map((s) => ({
              value: s,
              label: SENIORITY_LABELS[s] || s,
              count: facets?.seniority.find((f) => f.value === s)?.count,
            }))}
          />
          <FilterSelect
            label="City"
            value={city}
            onChange={(v) => { setCity(v); setPage(1); }}
            options={(facets?.city || []).map((f) => ({
              value: f.value,
              label: f.value,
              count: f.count,
            }))}
            emptyLabel="No cities yet"
          />
          <FilterSelect
            label="Market"
            value={marketTier}
            onChange={(v) => { setMarketTier(v); setPage(1); }}
            options={(facets?.market_tier || []).map((f) => ({
              value: f.value,
              label: TIER_LABELS[f.value] || f.value,
              count: f.count,
            }))}
          />
          <FilterSelect
            label="Email"
            value={hasEmail}
            onChange={(v) => { setHasEmail(v as "" | "yes" | "no"); setPage(1); }}
            options={[
              { value: "yes", label: "Has email" },
              { value: "no", label: "No email" },
            ]}
          />
          <FilterSelect
            label="Sort"
            value={sort}
            onChange={(v) => { setSort(v); setPage(1); }}
            options={[
              { value: "created", label: "Newest first" },
              { value: "name", label: "Name A–Z" },
              { value: "seniority", label: "Role" },
              { value: "company", label: "Company" },
              { value: "employees", label: "Company size" },
              { value: "score", label: "Lead score" },
            ]}
          />

          <div className="h-5 w-px bg-slate-200 mx-0.5" aria-hidden="true" />

          <Toggle
            pressed={decisionOnly}
            onChange={(v) => { setDecisionOnly(v); setPage(1); }}
            label="Decision makers only"
          />
          <Toggle
            pressed={verifiedOnly}
            onChange={(v) => { setVerifiedOnly(v); setPage(1); }}
            label="Verified only"
          />
          <Toggle
            pressed={!personOnly}
            onChange={(v) => { setPersonOnly(!v); setPage(1); }}
            label="Show business targets"
            hint="Rows with a phone but no identified person"
          />
        </div>

        {hasFilters && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-3">
            <span className="text-[11px] font-medium text-slate-500">Filters:</span>
            {activeFilters.map((f) => (
              <button
                key={`${f.key}-${f.value}`}
                type="button"
                onClick={() => clearFilter(f.key)}
                className="inline-flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
                aria-label={`Remove filter: ${f.label} ${f.value}`}
              >
                <span className="text-blue-500">{f.label}:</span> {f.value}
                <X className="h-3 w-3" />
              </button>
            ))}
            <button
              type="button"
              onClick={clearAll}
              className="text-[11px] font-semibold text-slate-500 underline underline-offset-2 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {error && !loading && (
        <ErrorState
          title="Could not load your people"
          message={error}
          onRetry={load}
        />
      )}

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            {hasFilters ? (
              <EmptyState
                icon={<SearchX className="h-5 w-5" />}
                title="No people match these filters"
                description="Your filters are narrower than your data. Clear one to widen the search."
                action={
                  <button
                    onClick={clearAll}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                  >
                    <X className="w-3.5 h-3.5" /> Clear filters
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon={<Sparkles className="h-5 w-5" />}
                title="No people identified yet"
                description="LeadForge reads the decision maker off each company's own website — the name and role on its About or Contact page. Scrape or import some businesses, then enrich them to find the people behind them."
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
                    href="/leads"
                    className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                  >
                    Open the Lead Database
                  </a>
                }
              />
            )}
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full min-w-[1100px] table-fixed text-left">
                <colgroup>
                  <col style={{ width: "24%" }} />
                  <col style={{ width: "16%" }} />
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "12%" }} />
                  <col style={{ width: "16%" }} />
                </colgroup>
                <thead>
                  <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                    <th scope="col" className="px-5 py-3 font-semibold">Person</th>
                    <th scope="col" className="px-4 py-3 font-semibold">Role</th>
                    <th scope="col" className="px-4 py-3 font-semibold">Company</th>
                    <th scope="col" className="px-4 py-3 font-semibold">Location</th>
                    <th scope="col" className="px-4 py-3 font-semibold">Reach</th>
                    <th scope="col" className="px-4 py-3 font-semibold text-right">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((p) => (
                    <PersonRowDesktop key={p.id} person={p} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden divide-y divide-slate-100">
              {rows.map((p) => (
                <PersonRowMobile key={p.id} person={p} />
              ))}
            </div>
          </>
        )}

        {pages > 1 && (
          <div className="border-t border-slate-200 px-5 py-3 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">
              Page {page} of {pages} · {total} people
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 disabled:opacity-40 hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 disabled:opacity-40 hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
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

/* -------------------------------------------------------------------------- */

function StatTile({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: number;
  hint?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-xs">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </span>
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
          {icon}
        </span>
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  emptyLabel = "No options yet",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string; count?: number }>;
  emptyLabel?: string;
}) {
  const id = `filter-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div className="flex items-center gap-1.5">
      <label
        htmlFor={id}
        className="text-[11px] font-medium text-slate-500 whitespace-nowrap"
      >
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 rounded-lg border border-slate-200 bg-white pl-2 pr-7 text-[11px] font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
      >
        <option value="">All</option>
        {options.length === 0 && (
          <option value="" disabled>
            {emptyLabel}
          </option>
        )}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
            {o.count !== undefined ? ` (${o.count})` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

function Toggle({
  pressed,
  onChange,
  label,
  hint,
}: {
  pressed: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => onChange(!pressed)}
      title={hint}
      className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 ${
        pressed
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
      }`}
    >
      {pressed ? (
        <CheckCircle2 className="h-3.5 w-3.5" />
      ) : (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 rounded-full border border-slate-300"
        />
      )}
      {label}
    </button>
  );
}

function SeniorityBadge({ person }: { person: PersonRow }) {
  if (!person.is_person) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
        Business target
      </span>
    );
  }
  if (person.seniority === "unknown") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
        Role unknown
      </span>
    );
  }
  const tone =
    person.is_decision_maker
      ? "bg-emerald-50 text-emerald-700"
      : "bg-slate-100 text-slate-600";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${tone}`}
    >
      {person.is_decision_maker && <ShieldCheck className="h-3 w-3" />}
      {person.seniority_label}
    </span>
  );
}

function ReachCell({ person }: { person: PersonRow }) {
  if (person.email) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 truncate">
        <Mail className="h-3.5 w-3.5 shrink-0 text-slate-400" />
        <span className="truncate">{person.email}</span>
        {person.is_verified && (
          <ShieldCheck
            className="h-3.5 w-3.5 shrink-0 text-emerald-600"
            aria-label="Verified deliverable"
          />
        )}
      </span>
    );
  }
  if (person.whatsapp_link) {
    return (
      <a
        href={person.whatsapp_link}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
      >
        <MessageCircle className="h-3.5 w-3.5 shrink-0" />
        WhatsApp
      </a>
    );
  }
  if (person.phone) {
    return (
      <a
        href={`tel:${person.phone}`}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
      >
        <Phone className="h-3.5 w-3.5 shrink-0 text-slate-400" />
        <span className="truncate">{person.phone}</span>
      </a>
    );
  }
  return <span className="text-xs text-slate-400">—</span>;
}

function PersonRowDesktop({ person }: { person: PersonRow }) {
  return (
    <tr className="h-[57px] hover:bg-slate-50/80 transition-colors">
      <td className="px-5 py-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            aria-hidden="true"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-bold text-slate-600"
          >
            {(person.first_name || person.name || "?").charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">
              {person.name || "—"}
            </p>
            {person.email && (
              <p className="truncate text-[11px] text-slate-500">{person.email}</p>
            )}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <p className="truncate text-xs text-slate-700">{person.title || "—"}</p>
        <div className="mt-1">
          <SeniorityBadge person={person} />
        </div>
      </td>
      <td className="px-4 py-3">
        <p className="truncate text-xs font-medium text-slate-800">
          {person.business_name || "—"}
        </p>
        {person.industry && (
          <p className="truncate text-[11px] text-slate-500">{person.industry}</p>
        )}
      </td>
      <td className="px-4 py-3">
        <p className="truncate text-xs text-slate-700">
          {person.city || "—"}
          {person.state ? `, ${person.state}` : ""}
        </p>
        {person.market_tier && (
          <p className="text-[11px] text-slate-500">
            {TIER_LABELS[person.market_tier] || person.market_tier}
          </p>
        )}
      </td>
      <td className="px-4 py-3">
        <ReachCell person={person} />
      </td>
      <td className="px-4 py-3 text-right">
        {person.lead_score !== null ? (
          <span className="text-sm font-semibold tabular-nums text-slate-700">
            {Math.round(person.lead_score)}
          </span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </td>
    </tr>
  );
}

function PersonRowMobile({ person }: { person: PersonRow }) {
  return (
    <div className="p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900 truncate">
            {person.name || "—"}
          </p>
          <p className="text-xs text-slate-600 truncate">
            {person.title || person.business_name || "—"}
          </p>
        </div>
        <SeniorityBadge person={person} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
        {person.city && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {person.city}
            {person.state ? `, ${person.state}` : ""}
          </span>
        )}
        {person.business_name && (
          <span className="inline-flex items-center gap-1">
            <Building2 className="h-3 w-3" />
            {person.business_name}
          </span>
        )}
      </div>
      <div className="pt-0.5">
        <ReachCell person={person} />
      </div>
    </div>
  );
}
