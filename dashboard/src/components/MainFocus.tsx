"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

/**
 * Moves focus to the main landmark after a client-side navigation.
 *
 * Without this, a keyboard or screen-reader user who follows a link stays
 * focused on the link they pressed - which now belongs to the *previous*
 * page. The next Tab press dumps them back at the top of the navigation
 * instead of into the content they asked for. The WAI-ARIA authoring
 * practice for a single-page app is to move focus to the main region after
 * a route change.
 *
 * It only does so when the navigation was *keyboard* driven. Moving focus
 * on every click would yank the mouse user out of whatever they were
 * pointing at, which is its own kind of hostile.
 */
export function MainFocus() {
  const pathname = usePathname();
  const previousPath = useRef<string | null>(null);

  useEffect(() => {
    const main = document.getElementById("main-content");
    if (!main) return;

    // The very first render is not a navigation.
    if (previousPath.current === null) {
      previousPath.current = pathname;
      return;
    }
    const changed = previousPath.current !== pathname;
    previousPath.current = pathname;
    if (!changed) return;

    const active = document.activeElement as HTMLElement | null;
    const cameFromNav =
      !!active &&
      active !== document.body &&
      active.getAttribute("href") !== null;

    if (!cameFromNav) return;

    // tabIndex={-1} on <main> is what makes this focusable.
    main.focus({ preventScroll: true });
  }, [pathname]);

  return null;
}
