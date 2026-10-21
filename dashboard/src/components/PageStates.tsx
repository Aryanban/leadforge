"use client";

import type { ReactNode } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";

/**
 * PageStates — the loading / empty / error primitives every list surface in
 * the dashboard shares.
 *
 * The skeletons are deliberately *sized like the real thing* (same row
 * heights, same card heights). A generic spinner in a short box makes the
 * page jump when the data lands: everything under it moves down and the
 * user's cursor ends up over a different button. A skeleton that occupies
 * the same box as the final content removes the jump entirely.
 */

/** One pulsing placeholder block. Purely decorative. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-slate-200/70 ${className}`}
    />
  );
}

/**
 * Table-shaped skeleton. Render it inside a `<tbody>`: it produces `<tr>`
 * rows that are exactly as tall as the real rows, so the table height (and
 * everything below it — pagination, action bars) does not move when the
 * rows are replaced by real data.
 */
export function TableSkeleton({
  rows = 8,
  columns = 5,
  rowClassName = "h-[85px]",
  cellClassName = "px-4 py-4",
  /** Width of the first cell's bar — the "name" column is usually wider. */
  firstColumnWidth = "w-[220px]",
}: {
  rows?: number;
  columns?: number;
  rowClassName?: string;
  cellClassName?: string;
  firstColumnWidth?: string;
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className={rowClassName}>
          {Array.from({ length: columns }).map((__, c) => (
            <td key={c} className={cellClassName}>
              <Skeleton className={`h-3 ${c === 0 ? firstColumnWidth : "w-[72px]"}`} />
              {c === 0 && <Skeleton className="h-2.5 mt-2 w-[60%] max-w-[180px]" />}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** Card-shaped skeleton for list surfaces that are cards, not tables. */
export function CardSkeleton({
  className = "",
  lines = 2,
}: {
  className?: string;
  lines?: number;
}) {
  return (
    <div
      aria-hidden="true"
      className={`rounded-2xl border border-slate-200 bg-white p-4 ${className}`}
    >
      <div className="flex items-center gap-2">
        <Skeleton className="h-3.5 w-44" />
        <Skeleton className="h-3.5 w-16 rounded-full" />
      </div>
      <div className="mt-2 space-y-1.5">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className="h-2.5 w-full max-w-[240px]" />
        ))}
      </div>
    </div>
  );
}

/** KPI-tile skeletons — same box as the real stat cards. */
export function StatsSkeleton({
  count = 4,
  className = "",
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-4 ${className}`}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs"
        >
          <div className="flex items-center justify-between">
            <Skeleton className="h-2.5 w-24" />
            <Skeleton className="h-8 w-8 rounded-lg" />
          </div>
          <Skeleton className="mt-3 h-7 w-24" />
          <Skeleton className="mt-2 h-2.5 w-36" />
        </div>
      ))}
    </div>
  );
}

/**
 * Inline, persistent error state with a retry affordance.
 *
 * A toast disappears; a screen-reader user who did not hear it (or who is
 * not looking at the corner of the screen) is left staring at an empty
 * table. This is the real signal: it stays on screen until the data
 * arrives, and it offers the way out.
 */
export function ErrorState({
  message,
  onRetry,
  title = "Could not load this data",
  className = "",
}: {
  message: string;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 ${className}`}
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-bold text-red-800">{title}</p>
        <p className="mt-0.5 text-xs text-red-700">{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        >
          <RotateCw className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * Empty state that says what to do next.
 *
 * `action` is the primary "do this" button, `secondaryAction` the escape
 * hatch. A filtered-empty list must offer "clear the filter", not "scrape
 * more leads" — the data is there, the user is just looking at too little
 * of it.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  className = "",
}: {
  icon?: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  secondaryAction?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center ${className}`}
    >
      {icon && (
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
          {icon}
        </div>
      )}
      <h2 className="text-sm font-bold text-slate-900">{title}</h2>
      <div className="mx-auto mt-1 max-w-md text-xs text-slate-600">{description}</div>
      {(action || secondaryAction) && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}

/**
 * Screen-reader announcement of the page's loading state.
 *
 * The visible skeleton is meaningless to a screen reader, so the loading
 * state is announced politely instead. `aria-busy` tells assistive tech
 * that the region is still settling.
 */
export function StatusLive({
  loading,
  loadingLabel = "Loading…",
  idleLabel = "",
}: {
  loading: boolean;
  loadingLabel?: string;
  idleLabel?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-busy={loading}
      className="sr-only"
    >
      {loading ? loadingLabel : idleLabel}
    </div>
  );
}

/** Small pill used for the "what can I do here" hints. */
export function HintPill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600">
      {children}
    </span>
  );
}
