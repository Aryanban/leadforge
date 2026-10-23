"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  Ban,
  CalendarClock,
  CheckCircle2,
  Mail,
  MailOpen,
  MessageSquareReply,
  Rocket,
  Search,
  Trophy,
  UserPlus,
} from "lucide-react";

import { api } from "@/lib/api";

export interface AuditEvent {
  id: number;
  event_type: string;
  event_label: string;
  entity_type: string | null;
  entity_id: number | null;
  actor: string;
  summary: string | null;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface AuditResponse {
  total: number;
  events: AuditEvent[];
}

/** The icon per event type. A missing one is not an error. */
const ICONS: Record<string, typeof Activity> = {
  email_sent: Mail,
  email_bounced: AlertTriangle,
  email_opened: MailOpen,
  email_replied: MessageSquareReply,
  lead_suppressed: Ban,
  send_deferred: CalendarClock,
  campaign_launched: Rocket,
  ab_winner_declared: Trophy,
  contact_identified: UserPlus,
  job_recovered: Search,
};

const TONES: Record<string, string> = {
  email_bounced: "bg-rose-50 text-rose-600",
  lead_suppressed: "bg-rose-50 text-rose-600",
  email_replied: "bg-emerald-50 text-emerald-600",
  ab_winner_declared: "bg-emerald-50 text-emerald-600",
  send_deferred: "bg-amber-50 text-amber-600",
};

/**
 * The activity feed.
 *
 * A cold-email tool makes decisions that are invisible from the outside:
 * a lead was skipped, an address was suppressed, a send was deferred at
 * 03:00 IST, a subject variant won. This is where the operator finds
 * out what happened and why.
 */
export default function ActivityFeed({
  limit = 8,
  href = "/audit",
}: {
  limit?: number;
  href?: string;
}) {
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.getAuditEvents({ limit });
        if (!cancelled) setData(res);
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || "Could not load the activity feed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  return (
    <section
      aria-labelledby="activity-heading"
      className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2
          id="activity-heading"
          className="flex items-center gap-2 text-sm font-bold text-slate-900"
        >
          <Activity className="h-4 w-4 text-slate-400" />
          What the product did
        </h2>
        <Link
          href={href}
          className="text-[11px] font-semibold text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
        >
          Full log
        </Link>
      </div>
      <p className="mt-0.5 text-xs text-slate-500">
        Every send, bounce, suppression and deferral - and why.
      </p>

      {error ? (
        <p className="mt-3 text-[11px] text-rose-700">{error}</p>
      ) : !data ? (
        <div className="mt-3 space-y-2" aria-hidden="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded-md bg-slate-100" />
          ))}
        </div>
      ) : data.events.length === 0 ? (
        <p className="mt-3 text-[11px] text-slate-500">
          Nothing yet. Once a sequence sends its first email, every decision it
          makes shows up here.
        </p>
      ) : (
        <ol className="mt-3 space-y-2">
          {data.events.map((event) => {
            const Icon = ICONS[event.event_type] || CheckCircle2;
            const tone =
              TONES[event.event_type] || "bg-slate-100 text-slate-500";
            return (
              <li key={event.id} className="flex items-start gap-2.5">
                <span
                  className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${tone}`}
                >
                  <Icon className="h-3 w-3" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs text-slate-800">
                    {event.summary || event.event_label}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {event.event_label}
                    {event.created_at
                      ? ` · ${new Date(event.created_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
