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

/** Id of the hamburger button that opens the drawer (TopBar). */
export const MOBILE_NAV_TRIGGER_ID = "lf-mobile-nav-trigger";
/** Id of the mobile drawer panel (Sidebar), referenced by aria-controls. */
export const MOBILE_NAV_PANEL_ID = "lf-mobile-nav";

/**
 * The hamburger button that opens the drawer. It lives in the TopBar, the
 * drawer lives in the Sidebar, so the Sidebar needs a handle on it to hand
 * keyboard focus back when the drawer closes.
 */
let triggerEl: HTMLElement | null = null;

export function setMobileNavTrigger(el: HTMLElement | null) {
  triggerEl = el;
}

export function getMobileNavTrigger() {
  return triggerEl;
}

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
