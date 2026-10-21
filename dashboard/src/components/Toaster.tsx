"use client";

import * as Toast from "@radix-ui/react-toast";
import { useSyncExternalStore } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

/**
 * Toaster — the app-wide notification surface.
 *
 * The native browser alert blocks the main thread, looks like a 1998 dialog
 * and cannot be styled; Radix Toast (already a dependency) gives us a
 * dismissible, screen-reader friendly, non-blocking notification. We keep a
 * tiny external store so any module can call `toast.success("...")` without
 * threading a hook through every component.
 */

export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let items: ToastItem[] = [];
let counter = 0;

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

// A stable reference so useSyncExternalStore never re-renders forever.
const getSnapshot = () => items;

function dismiss(id: string) {
  const next = items.filter((t) => t.id !== id);
  if (next.length === items.length) return;
  items = next;
  emit();
}

function push(kind: ToastKind, title: string, description?: string) {
  counter += 1;
  const item: ToastItem = {
    id: `lf-toast-${Date.now()}-${counter}`,
    kind,
    title,
    ...(description ? { description } : {}),
  };
  items = [...items, item];
  emit();
}

/** Imperative API used across the app. */
export const toast = {
  success: (title: string, description?: string) => push("success", title, description),
  error: (title: string, description?: string) => push("error", title, description),
  info: (title: string, description?: string) => push("info", title, description),
  dismiss,
};

const KIND_META: Record<
  ToastKind,
  { icon: typeof CheckCircle2; iconClass: string; ringClass: string }
> = {
  success: {
    icon: CheckCircle2,
    iconClass: "text-emerald-500",
    ringClass: "border-emerald-200",
  },
  error: {
    icon: AlertCircle,
    iconClass: "text-red-500",
    ringClass: "border-red-200",
  },
  info: {
    icon: Info,
    iconClass: "text-blue-500",
    ringClass: "border-blue-200",
  },
};

export function Toaster() {
  const toasts = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  return (
    <Toast.Provider swipeDirection="right" duration={5000} label="Notification">
      {toasts.map((t) => {
        const meta = KIND_META[t.kind];
        const Icon = meta.icon;
        return (
          <Toast.Root
            key={t.id}
            open
            duration={t.kind === "error" ? 8000 : 5000}
            onOpenChange={(open) => {
              if (!open) dismiss(t.id);
            }}
            className={`pointer-events-auto flex items-start gap-3 rounded-xl border bg-white p-4 shadow-lg ${
              meta.ringClass
            } data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom-2 data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-80 data-[state=closed]:slide-out-to-right-full`}
          >
            <Icon className={`w-5 h-5 shrink-0 mt-0.5 ${meta.iconClass}`} />
            <div className="min-w-0 flex-1">
              <Toast.Title className="text-[13px] font-semibold text-slate-900 leading-snug">
                {t.title}
              </Toast.Title>
              {t.description && (
                <Toast.Description className="mt-0.5 text-xs text-slate-600 leading-relaxed whitespace-pre-line break-words">
                  {t.description}
                </Toast.Description>
              )}
            </div>
            <Toast.Close
              aria-label="Dismiss notification"
              className="shrink-0 rounded-md p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </Toast.Close>
          </Toast.Root>
        );
      })}

      <Toast.Viewport className="fixed bottom-0 right-0 z-[100] flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 p-4 outline-none" />
    </Toast.Provider>
  );
}
