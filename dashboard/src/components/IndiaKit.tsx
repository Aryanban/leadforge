"use client";

import { useEffect, useState } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Moon,
  PartyPopper,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api, IndiaAdvisorReport } from "@/lib/api";

/**
 * IndiaReadiness — the one banner that answers "am I safe to send?"
 * Shows ONLY when there is something to say. Advisory: links to the fix,
 * never gates. All-green + no festival = renders nothing.
 */
export function IndiaReadiness({ domain }: { domain?: string }) {
  const [report, setReport] = useState<IndiaAdvisorReport | null>(null);
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getIndiaAdvisor(domain)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [domain]);

  if (failed || !report) return null;

  const items: Array<{ kind: "warn" | "fest"; title: string; detail: string }> = [];

  if (report.auth && !report.auth.ok) {
    items.push({
      kind: "warn",
      title: `Sender auth incomplete for ${report.auth.domain}`,
      detail: report.auth.warnings.join(" "),
    });
  }
  if (report.quiet_hours_now) {
    items.push({
      kind: "warn",
      title: "TRAI quiet hours (21:00–09:00 IST)",
      detail: "Hold promotional SMS/voice until morning. Email is unaffected.",
    });
  }
  if (report.festival?.festival) {
    items.push({
      kind: "fest",
      title: `${report.festival.emoji} ${report.festival.festival} window — seasonal hook available`,
      detail: report.festival.hinglish_line || report.festival.subject_hook || "",
    });
  }

  if (items.length === 0) return null;

  const hasWarn = items.some((i) => i.kind === "warn");
  const shown = expanded ? items : items.slice(0, 2);

  return (
    <div
      className={`rounded-2xl border p-4 ${
        hasWarn ? "border-amber-200 bg-amber-50/70" : "border-purple-200 bg-purple-50/60"
      }`}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <div className="flex items-center gap-2">
          {hasWarn ? (
            <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600" />
          ) : (
            <PartyPopper className="h-4 w-4 shrink-0 text-purple-600" />
          )}
          <span className="text-xs font-bold text-slate-800">
            India readiness — {items.length} note{items.length > 1 ? "s" : ""}
          </span>
        </div>
        {items.length > 2 ? (
          expanded ? (
            <ChevronUp className="h-3.5 w-3.5 text-slate-500" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
          )
        ) : null}
      </button>
      <ul className="mt-2 space-y-1.5">
        {shown.map((it, idx) => (
          <li key={idx} className="flex items-start gap-2 text-xs leading-relaxed">
            {it.kind === "fest" ? (
              <PartyPopper className="mt-0.5 h-3.5 w-3.5 shrink-0 text-purple-600" />
            ) : (
              <Moon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
            )}
            <span>
              <strong className="font-semibold text-slate-800">{it.title}.</strong>{" "}
              <span className="text-slate-600">{it.detail}</span>
            </span>
          </li>
        ))}
      </ul>
      {!expanded && items.length > 2 && (
        <p className="mt-1 text-[11px] text-slate-500">+{items.length - 2} more — tap to expand</p>
      )}
    </div>
  );
}

/**
 * FestivalHook — tiny inline chip for the campaign composer. One click copies
 * the Hinglish greeting; the operator pastes where it fits. Nothing auto-inserts.
 */
export function FestivalHook() {
  const [line, setLine] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .getIndiaCopy()
      .then((kit) => {
        if (kit.festival?.hinglish_line) setLine(kit.festival.hinglish_line);
      })
      .catch(() => {});
  }, []);

  if (!line) return null;

  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(line).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex items-center gap-1.5 rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-1 text-[11px] font-semibold text-purple-700 hover:bg-purple-100"
      title="Copy the festival greeting, paste it where it fits. Nothing is auto-inserted."
    >
      <PartyPopper className="h-3.5 w-3.5" />
      {copied ? "Copied!" : line}
    </button>
  );
}


/**
 * AuthBadge — compact SPF/DKIM/DMARC status for one mailbox domain.
 * Green = all three pass. Amber = names exactly what is missing.
 */
export function AuthBadge({ domain }: { domain: string }) {
  const [report, setReport] = useState<IndiaAdvisorReport["auth"] | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api
      .getIndiaAdvisor(domain)
      .then((r) => {
        if (!cancelled) setReport(r.auth);
      })
      .catch(() => {
        if (!cancelled) setReport(null);
      });
    return () => {
      cancelled = true;
    };
  }, [domain]);

  if (report === undefined)
    return <span className="text-[11px] text-slate-400">checking DNS…</span>;
  if (report === null) return null;
  if (report.ok)
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700"
        title="SPF, DKIM and DMARC all publish correctly."
      >
        <ShieldCheck className="h-3 w-3" /> auth ok
      </span>
    );
  const missing = [
    !report.spf_ok && "SPF",
    !report.dkim_ok && "DKIM",
    !report.dmarc_ok && "DMARC",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800"
      title={report.warnings.join(" ")}
    >
      <ShieldAlert className="h-3 w-3" /> missing {missing}
    </span>
  );
}

/**
 * TrustBadge — why this lead's score carries a source adjustment.
 * JustDial/Sulekha → amber "verify phone"; Maps/website → green note.
 */
export function TrustBadge({ trust, modifier }: { trust?: number | null; modifier?: number }) {
  if (trust == null) return null;
  if (trust < 0.75)
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800"
        title="Self-listed directory: shared leads and stale numbers are common. Re-check the phone before a full sequence."
      >
        <ShieldAlert className="h-3 w-3" /> verify phone
      </span>
    );
  if (trust >= 0.9)
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700"
        title="Live or first-party source — this lead's data refreshes itself."
      >
        <ShieldCheck className="h-3 w-3" /> trusted source
      </span>
    );
  return null;
}
