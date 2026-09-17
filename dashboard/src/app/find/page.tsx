"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Target,
  Sparkles,
  Loader2,
  ArrowRight,
  Flame,
  Zap,
  Mail,
  Phone,
  MessageCircle,
  Globe,
  MapPin,
  BadgeCheck,
  Wand2,
  Database,
  RefreshCw,
} from "lucide-react";
import { api, ICPDraft, RankedLead, DiscoveryJob } from "@/lib/api";

const EMPTY_DRAFT: ICPDraft = {
  name: "",
  niche: "",
  area: "",
  keywords: [],
  exclude_keywords: [],
  min_score: 45,
  preset: "outreach_quality",
  signal_weights: null,
  preferred_sources: null,
};

export default function FindLeadsPage() {
  const [intentText, setIntentText] = useState("");
  const [draft, setDraft] = useState<ICPDraft>(EMPTY_DRAFT);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [maxResults, setMaxResults] = useState(20);
  const [job, setJob] = useState<DiscoveryJob | null>(null);
  const [ranked, setRanked] = useState<RankedLead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [parsing, setParsing] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [ranking, setRanking] = useState(false);

  const hasDraft = Boolean(draft.niche);

  const handleParse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!intentText.trim()) return;
    try {
      setParsing(true);
      setError(null);
      const parsed = await api.parseIcp(intentText);
      setDraft(parsed);
    } catch (err: any) {
      setError(err.message || "Could not parse that intent");
    } finally {
      setParsing(false);
    }
  };

  const saveProfile = async (): Promise<number> => {
    if (profileId) {
      await api.updateIcp(profileId, draft);
      return profileId;
    }
    const created = await api.createIcp(draft);
    setProfileId(created.id);
    return created.id;
  };

  const pollJob = useCallback(async (jobId: number) => {
    const poll = async () => {
      try {
        const current = await api.getDiscoveryJob(jobId);
        setJob(current);
        if (current.status === "completed") {
          setRanked(current.result?.ranked_leads ?? []);
          setDiscovering(false);
          return;
        }
        if (current.status === "failed") {
          setError(current.error || "Discovery failed. Check the backend logs.");
          setDiscovering(false);
          return;
        }
        setTimeout(poll, 2000);
      } catch (err: any) {
        setError(err.message || "Lost contact with the discovery job");
        setDiscovering(false);
      }
    };
    poll();
  }, []);

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError(null);
      setRanked(null);
      setDiscovering(true);
      const id = await saveProfile();
      const res = await api.startDiscovery({
        niche: draft.niche,
        area: draft.area || null,
        icp_profile_id: id,
        max_results: maxResults,
      });
      setJob({
        id: res.job_id,
        query: `${draft.niche} in ${draft.area || ""}`.trim(),
        status: res.status,
        total_found: 0,
        leads_saved: 0,
        error: null,
        icp_profile_id: id,
        result: null,
        created_at: null,
        finished_at: null,
      });
      pollJob(res.job_id);
    } catch (err: any) {
      setError(err.message || "Could not start discovery");
      setDiscovering(false);
    }
  };

  const handleRankExisting = async () => {
    try {
      setError(null);
      setRanking(true);
      const id = await saveProfile();
      const res = await api.rankLeads(id, 50);
      setRanked(res.ranked_leads);
    } catch (err: any) {
      setError(err.message || "Could not rank existing leads");
    } finally {
      setRanking(false);
    }
  };

  useEffect(() => {
    return () => setDiscovering(false);
  }, []);

  const updateDraft = (patch: Partial<ICPDraft>) => setDraft((d) => ({ ...d, ...patch }));

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">Find the Best Leads</h1>
        <p className="text-sm text-slate-500 mt-1">
          Describe what you sell and where. LeadForge learns which sources produce the highest-quality leads for that niche,
          enriches their contacts, and ranks the best ones first.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-medium text-rose-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Step 1 — Describe intent */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-blue-600 text-white text-xs font-bold flex items-center justify-center">1</span>
            <h2 className="font-bold text-slate-900 text-sm">Describe your ideal lead</h2>
          </div>
          <form onSubmit={handleParse} className="space-y-3">
            <textarea
              rows={3}
              placeholder="e.g. Dentists in South Delhi with verified emails and no website"
              value={intentText}
              onChange={(e) => setIntentText(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all resize-none"
            />
            <button
              type="submit"
              disabled={parsing || !intentText.trim()}
              className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white h-9 px-4 transition-colors shadow-xs disabled:opacity-50"
            >
              {parsing ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5 mr-1.5" />}
              Draft my ICP
            </button>
          </form>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Try signals like &ldquo;verified emails&rdquo;, &ldquo;no website&rdquo;, &ldquo;running ads&rdquo;, or &ldquo;best leads&rdquo;
            to tune the scoring model.
          </p>
        </div>

        {/* Step 2 — Refine ICP */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-blue-600 text-white text-xs font-bold flex items-center justify-center">2</span>
            <h2 className="font-bold text-slate-900 text-sm">Refine the ideal customer profile</h2>
          </div>

          {!hasDraft ? (
            <p className="text-xs text-slate-400 italic py-6 text-center">
              Draft an ICP above, or fill the fields manually below.
            </p>
          ) : null}

          <div className="grid grid-cols-2 gap-3 text-xs">
            <label className="block">
              <span className="font-semibold text-slate-700 block mb-1">Niche</span>
              <input
                value={draft.niche}
                onChange={(e) => updateDraft({ niche: e.target.value })}
                placeholder="Dentists"
                className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </label>
            <label className="block">
              <span className="font-semibold text-slate-700 block mb-1">Area</span>
              <input
                value={draft.area || ""}
                onChange={(e) => updateDraft({ area: e.target.value })}
                placeholder="South Delhi"
                className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </label>
            <label className="block">
              <span className="font-semibold text-slate-700 block mb-1">Scoring preset</span>
              <select
                value={draft.preset}
                onChange={(e) => updateDraft({ preset: e.target.value as ICPDraft["preset"] })}
                className="w-full h-9 px-3 rounded-lg border border-slate-200 bg-white focus:outline-none"
              >
                <option value="outreach_quality">Outreach quality (deliverability first)</option>
                <option value="agency_opportunity">Agency opportunity (weak web presence = prospect)</option>
              </select>
            </label>
            <label className="block">
              <span className="font-semibold text-slate-700 block mb-1">Minimum score: {draft.min_score}</span>
              <input
                type="range"
                min={10}
                max={100}
                value={draft.min_score}
                onChange={(e) => updateDraft({ min_score: Number(e.target.value) })}
                className="w-full h-9 accent-blue-600"
              />
            </label>
            <label className="col-span-2 block">
              <span className="font-semibold text-slate-700 block mb-1">Must-match keywords (comma separated)</span>
              <input
                value={draft.keywords.join(", ")}
                onChange={(e) =>
                  updateDraft({ keywords: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
                }
                placeholder="dental, clinic"
                className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </label>
            <label className="col-span-2 block">
              <span className="font-semibold text-slate-700 block mb-1">Exclude keywords</span>
              <input
                value={draft.exclude_keywords.join(", ")}
                onChange={(e) =>
                  updateDraft({ exclude_keywords: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
                }
                placeholder="franchise, chain"
                className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </label>
          </div>
        </div>
      </div>

      {/* Step 3 — Run */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-blue-600 text-white text-xs font-bold flex items-center justify-center">3</span>
            <div>
              <h2 className="font-bold text-slate-900 text-sm">Find &amp; enrich the best leads</h2>
              <p className="text-[11px] text-slate-500">
                {hasDraft
                  ? `${draft.niche}${draft.area ? ` in ${draft.area}` : ""} · min score ${draft.min_score}`
                  : "Draft or fill an ICP first"}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="text-[11px] font-semibold text-slate-600 flex items-center gap-2">
              Leads
              <input
                type="range"
                min={5}
                max={50}
                value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                className="accent-blue-600"
              />
              <span className="font-mono text-slate-900">{maxResults}</span>
            </label>
            <button
              onClick={handleRankExisting}
              disabled={ranking || !hasDraft}
              className="inline-flex items-center justify-center rounded-xl text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 h-9 px-3.5 transition-colors shadow-xs disabled:opacity-50"
              title="Rank the leads already in your database against this ICP"
            >
              {ranking ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Database className="w-3.5 h-3.5 mr-1.5" />}
              Rank existing DB
            </button>
            <button
              onClick={handleDiscover}
              disabled={discovering || !hasDraft}
              className="inline-flex items-center justify-center rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white h-9 px-4 transition-colors shadow-xs disabled:opacity-50"
            >
              {discovering ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  {job?.status === "running" ? "Enriching & ranking…" : "Starting discovery…"}
                </>
              ) : (
                <>
                  <Target className="w-3.5 h-3.5 mr-1.5" />
                  Find Best Leads
                  <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Ranked results */}
      {ranked !== null && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-slate-900 text-sm flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-600" />
              {ranked.length} lead{ranked.length === 1 ? "" : "s"} passed your ICP gate
            </h2>
            <button
              onClick={() => setRanked(null)}
              className="text-xs text-slate-400 hover:text-slate-700 inline-flex items-center gap-1"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Clear
            </button>
          </div>

          {ranked.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
              No leads reached the minimum score of {draft.min_score}. Try lowering the gate, broadening the niche,
              or running discovery with more results.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {ranked.map((lead) => (
                <LeadCard key={lead.business_id} lead={lead} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LeadCard({ lead }: { lead: RankedLead }) {
  const tierStyles =
    lead.tier === "HOT"
      ? "bg-rose-50 text-rose-700 border-rose-200"
      : lead.tier === "WARM"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : "bg-slate-100 text-slate-600 border-slate-200";

  const TierIcon = lead.tier === "HOT" ? Flame : lead.tier === "WARM" ? Zap : Sparkles;
  const cleanPhone = lead.phone ? lead.phone.replace(/[^0-9]/g, "") : "";
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    `${lead.name} ${lead.address || ""}`.trim()
  )}`;
  const socials = lead.contacts.flatMap((c) => Object.entries(c.social_links || {}));

  return (
    <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <a
            href={mapsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="font-bold text-slate-900 hover:text-blue-600 transition-colors inline-flex items-center gap-1.5"
          >
            <span className="truncate">{lead.name}</span>
            <MapPin className="w-3.5 h-3.5 text-red-500 shrink-0" />
          </a>
          <div className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
            {lead.address || lead.industry || "No address listed"}
          </div>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold border shrink-0 ${tierStyles}`}
        >
          <TierIcon className="w-3 h-3" />
          {lead.score} {lead.tier}
        </span>
      </div>

      {lead.badges.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {lead.badges.map((badge) => (
            <span
              key={badge}
              className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-blue-50 text-blue-700 border border-blue-100"
            >
              {badge}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11px]">
        {lead.phone ? (
          <a href={`tel:${lead.phone}`} className="inline-flex items-center gap-1 text-slate-700 hover:text-blue-600 font-mono">
            <Phone className="w-3 h-3 text-slate-400" />
            {lead.phone}
          </a>
        ) : null}
        {cleanPhone ? (
          <a
            href={`https://wa.me/${cleanPhone}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-emerald-600 hover:text-emerald-700"
          >
            <MessageCircle className="w-3 h-3" />
            WhatsApp
          </a>
        ) : null}
        {lead.website ? (
          <a
            href={lead.website.startsWith("http") ? lead.website : `https://${lead.website}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 max-w-[160px] truncate"
          >
            <Globe className="w-3 h-3 shrink-0" />
            <span className="truncate">{lead.website.replace(/^https?:\/\/|\/$/g, "")}</span>
          </a>
        ) : null}
        {lead.rating ? (
          <span className="inline-flex items-center gap-1 text-amber-600 font-medium">
            ★ {lead.rating} <span className="text-slate-400">({lead.reviews_count || 0})</span>
          </span>
        ) : null}
      </div>

      {lead.contacts.length > 0 && (
        <div className="space-y-1 border-t border-slate-100 pt-2.5">
          {lead.contacts.map((contact) => (
            <div key={contact.id} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1.5 text-slate-700 min-w-0">
                <Mail className="w-3 h-3 text-slate-400 shrink-0" />
                <span className="truncate font-mono">{contact.email || "No email found"}</span>
              </span>
              {contact.is_verified ? (
                <span className="inline-flex items-center gap-1 text-emerald-700 font-bold shrink-0">
                  <BadgeCheck className="w-3 h-3" /> Verified
                </span>
              ) : contact.email ? (
                <span className="text-amber-700 font-medium shrink-0">Unverified</span>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {socials.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-slate-100 pt-2.5">
          {socials.map(([platform, url]) => (
            <a
              key={`${platform}-${url}`}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium bg-slate-50 text-slate-600 border border-slate-200 hover:text-blue-700 capitalize"
            >
              {platform}
            </a>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-1 border-t border-slate-100 pt-2.5">
        {Object.entries(lead.signal_breakdown).map(([signal, weight]) => (
          <span
            key={signal}
            title={`${signal} contributed ${weight} points to this score`}
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono ${
              weight >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
            }`}
          >
            {signal} {weight >= 0 ? "+" : ""}
            {weight}
          </span>
        ))}
      </div>
    </div>
  );
}
