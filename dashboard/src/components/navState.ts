"use client";

import { useSyncExternalStore } from "react";

/**
 * Shared state for the mobile navigation drawer.
 *
 * The drawer lives in the Sidebar but is opened from the TopBar (the
 * hamburger), so the two sibling components need one source of truth. A tiny
 * external store keeps them decoupled without pulling a context provider into
 * the server-rendered root layout.
 */

let open = false;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function setMobileNavOpen(next: boolean) {
  if (open === next) return;
  open = next;
  emit();
}

export function toggleMobileNav() {
  setMobileNavOpen(!open);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const getSnapshot = () => open;
const getServerSnapshot = () => false;

export function useMobileNavOpen() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
