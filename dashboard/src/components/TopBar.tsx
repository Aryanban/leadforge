"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Search, Command, Sparkles, Menu } from "lucide-react";
import {
  MOBILE_NAV_PANEL_ID,
  MOBILE_NAV_TRIGGER_ID,
  setMobileNavTrigger,
  toggleMobileNav,
  useMobileNavOpen,
} from "@/components/navState";
import { FOCUS_RING } from "@/components/focusRing";

/**
 * TopBar — Apollo's most recognisable affordance is the global search that
 * always sits at the top and can reach any object. Ours searches leads and
 * jumps straight to the filtered database, with "Cmd/Ctrl+K" to focus it
 * from anywhere (muscle memory most Apollo users already have).
 */
export function TopBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  /** Polite live region: tells screen-reader users the search was submitted. */
  const [status, setStatus] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const mobileNavOpen = useMobileNavOpen();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    // Announce the submit — a screen-reader user gets no other confirmation
    // that the search actually ran.
    setStatus(term ? `Searching for ${term}` : "Showing all leads");
    router.push(term ? `/leads?search=${encodeURIComponent(term)}` : "/leads");
  };

  return (
    <div className="h-14 shrink-0 border-b border-slate-200 bg-white flex items-center gap-2 sm:gap-3 px-3 sm:px-5">
      {/* Mobile: the rail is hidden below md, so the nav lives behind this button */}
      <button
        ref={(el) => {
          triggerRef.current = el;
          setMobileNavTrigger(el);
        }}
        id={MOBILE_NAV_TRIGGER_ID}
        onClick={toggleMobileNav}
        aria-label="Open navigation"
        aria-expanded={mobileNavOpen}
        aria-controls={MOBILE_NAV_PANEL_ID}
        title="Open navigation"
        className={`md:hidden p-1.5 -ml-0.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 motion-safe:transition-colors ${FOCUS_RING}`}
      >
        <Menu aria-hidden="true" className="w-5 h-5" />
      </button>

      <form onSubmit={submit} className="relative flex-1 max-w-2xl">
        <Search
          aria-hidden="true"
          className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
        />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search leads, businesses, phone numbers…"
          aria-label="Search leads"
          className={`w-full h-9 pl-9 pr-3 sm:pr-20 rounded-lg border border-slate-200 bg-slate-50 text-[13px] text-slate-800 placeholder:text-slate-400 focus:bg-white focus:border-blue-300 ${FOCUS_RING}`}
        />
        <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-0.5 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-500">
          <Command aria-hidden="true" className="w-2.5 h-2.5" />K
        </kbd>
      </form>

      <div className="hidden md:flex items-center gap-2 ml-auto">
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-50 border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold text-slate-600">
          <Sparkles aria-hidden="true" className="w-3.5 h-3.5 text-blue-600" />
          Self-hosted · no lead credits
        </span>
      </div>

      {/* Visually hidden, but NOT display:none — screen readers announce it. */}
      <p role="status" aria-live="polite" className="sr-only">
        {status}
      </p>
    </div>
  );
}
