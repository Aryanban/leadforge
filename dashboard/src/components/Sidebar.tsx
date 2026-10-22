"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  LayoutDashboard,
  Search,
  Users,
  Send,
  Settings,
  Target,
  Sparkles,
  PanelLeftClose,
  PanelLeftOpen,
  BookOpen,
  Inbox,
  Building2,
  Activity,
  Plug,
  UserRound,
  X,
} from "lucide-react";
import {
  getMobileNavTrigger,
  MOBILE_NAV_PANEL_ID,
  MOBILE_NAV_TRIGGER_ID,
  setMobileNavOpen,
  useMobileNavOpen,
} from "@/components/navState";
import { FOCUS_RING } from "@/components/focusRing";

type NavItem = { href: string; label: string; icon: typeof LayoutDashboard };
type NavGroup = { title: string; items: NavItem[] };

/**
 * Apollo-style navigation: grouped sections (Engage / Prospect / Deliverability
 * / Setup) rather than a flat list, so someone switching from Apollo finds their
 * bearings immediately. Collapsible rail for focus mode.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    title: "Engage",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/sequences", label: "Sequences", icon: Send },
      { href: "/inbox", label: "Inbox", icon: Inbox },
    ],
  },
  {
    title: "Prospect",
    items: [
      { href: "/find", label: "AI Lead Finder", icon: Target },
      { href: "/scrape", label: "Scrape Leads", icon: Search },
      { href: "/leads", label: "Lead Database", icon: Users },
      { href: "/people", label: "People", icon: UserRound },
      { href: "/companies", label: "Companies", icon: Building2 },
    ],
  },
  {
    title: "Deliverability",
    items: [{ href: "/email-health", label: "Email Health", icon: Activity }],
  },
  {
    title: "Setup",
    items: [
      { href: "/setup", label: "Connections", icon: Plug },
      { href: "/settings", label: "Mailboxes & Settings", icon: Settings },
    ],
  },
];

const COLLAPSE_KEY = "leadforge.sidebar.collapsed";

function useIsActive() {
  const pathname = usePathname();
  return (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
}

/**
 * The nav list itself. Shared by the desktop rail and the mobile drawer so
 * both expose exactly the same destinations.
 *
 * `label` keeps the two <nav> landmarks distinguishable for screen-reader
 * users (they are never on screen at the same time, but landmarks are
 * addressed by name, not by position).
 */
function NavList({
  collapsed,
  onNavigate,
  label,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  label: string;
}) {
  const isActive = useIsActive();
  return (
    <nav aria-label={label} className="p-2.5 space-y-4">
      {NAV_GROUPS.map((group) => (
        <div key={group.title}>
          {!collapsed && (
            <div className="px-2.5 pb-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-600">
              {group.title}
            </div>
          )}
          <div className="space-y-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium motion-safe:transition-colors ${FOCUS_RING} ${
                    active
                      ? "bg-blue-50 text-blue-700 font-semibold"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  } ${collapsed ? "justify-center" : ""}`}
                >
                  <Icon
                    aria-hidden="true"
                    className={`w-4 h-4 shrink-0 ${active ? "text-blue-600" : "text-slate-500"}`}
                  />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                  {/* Collapsed rail: the label is gone visually, so keep it for
                      screen readers (the title attribute is only a fallback). */}
                  {collapsed && <span className="sr-only">{item.label}</span>}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function BrandMark({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex items-center gap-2 overflow-hidden">
      <div
        aria-hidden="true"
        className="w-8 h-8 shrink-0 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-sm"
      >
        LF
      </div>
      {!collapsed && (
        <div className="min-w-0">
          {/*
            The brand is NOT a heading. Every page renders its own <h1>
            ("Lead Database", "Overview"), so an <h1> here gave the app two
            level-1 headings on every page - which is both an accessibility
            problem and a document-outline problem for screen readers.
            The product name is a label, not a section heading.
          */}
          <p className="font-bold text-sm tracking-tight text-slate-900 leading-none truncate">
            LeadForge
          </p>
          <span className="text-[11px] text-slate-600 font-semibold tracking-wider uppercase">
            Sales Platform
          </span>
        </div>
      )}
    </div>
  );
}

function PromoCard() {
  return (
    <div className="p-3 bg-gradient-to-br from-blue-50 to-indigo-50/60 rounded-xl border border-blue-100/70">
      <div className="flex items-center gap-1.5 text-[11px] font-bold text-blue-900 mb-0.5">
        <Sparkles aria-hidden="true" className="w-3.5 h-3.5 text-blue-600" />
        Live lead data
      </div>
      <p className="text-[11px] text-blue-800 leading-relaxed">
        Scraped fresh, verified, India-ready — no per-lead credits.
      </p>
    </div>
  );
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const mobileOpen = useMobileNavOpen();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  /** Where focus came from when the drawer opened — we put it back on close. */
  const returnFocusRef = useRef<HTMLElement | null>(null);
  /** Guard so a plain page load never steals focus for the hamburger. */
  const wasOpenRef = useRef(false);

  // Remember the operator's choice: collapsing is a preference, not a
  // per-session accident.
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* storage blocked; default expanded */
    }
  }, []);

  const toggle = () => {
    setCollapsed((v) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, v ? "0" : "1");
      } catch {
        /* ignore */
      }
      return !v;
    });
  };

  /**
   * Drawer lifecycle: move focus in on open, trap Tab while open, close on
   * Escape, and hand focus back to the hamburger on close.
   */
  useEffect(() => {
    if (mobileOpen) {
      wasOpenRef.current = true;
      // Remember the trigger so focus can go back there when we close.
      returnFocusRef.current = (document.activeElement as HTMLElement) ?? null;

      const focusTimer = window.setTimeout(() => {
        (closeBtnRef.current ?? panelRef.current)?.focus();
      }, 0);

      const onKey = (e: KeyboardEvent) => {
        // Escape closes the drawer.
        if (e.key === "Escape") {
          e.preventDefault();
          setMobileNavOpen(false);
          return;
        }
        if (e.key !== "Tab") return;
        const panel = panelRef.current;
        if (!panel) return;
        const focusables = Array.from(
          panel.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => el.getClientRects().length > 0);
        if (focusables.length === 0) {
          e.preventDefault();
          panel.focus();
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey) {
          if (active === first || !panel.contains(active)) {
            e.preventDefault();
            last.focus();
          }
        } else if (active === last || !panel.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      };
      document.addEventListener("keydown", onKey, true);
      return () => {
        window.clearTimeout(focusTimer);
        document.removeEventListener("keydown", onKey, true);
      };
    }

    // Closed: send focus back to the hamburger that opened us. Only if the
    // drawer was actually open — a plain page load must not steal focus.
    if (!wasOpenRef.current) return;
    wasOpenRef.current = false;
    const target = returnFocusRef.current;
    returnFocusRef.current = null;
    if (target && document.contains(target)) {
      target.focus();
    } else {
      const trigger =
        getMobileNavTrigger() ??
        document.getElementById(MOBILE_NAV_TRIGGER_ID);
      trigger?.focus();
    }
  }, [mobileOpen]);

  // A tap on the dimmed backdrop closes the drawer.
  const closeMobile = () => setMobileNavOpen(false);

  return (
    <>
      {/* Desktop rail — hidden below md so a phone keeps the full width for content.
          <aside> is a complementary landmark: everything inside it is
          therefore "contained by a landmark" for screen readers. */}
      <aside
        aria-label="Primary"
        className={`${
          collapsed ? "w-[68px]" : "w-60"
        } hidden md:flex shrink-0 border-r border-slate-200 bg-white flex-col justify-between min-h-screen motion-safe:transition-all motion-safe:duration-200`}
      >
        <div>
          {/* Brand + collapse toggle */}
          <header className="h-14 flex items-center justify-between px-3 border-b border-slate-100">
            <BrandMark collapsed={collapsed} />
            <button
              onClick={toggle}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className={`p-1 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 ${FOCUS_RING}`}
            >
              {collapsed ? (
                <PanelLeftOpen aria-hidden="true" className="w-4 h-4" />
              ) : (
                <PanelLeftClose aria-hidden="true" className="w-4 h-4" />
              )}
            </button>
          </header>

          {/* Grouped nav */}
          <NavList collapsed={collapsed} label="Main" />
        </div>

        {!collapsed && (
          <footer className="p-3 border-t border-slate-100 space-y-2">
            <PromoCard />
            <Link
              href="/setup"
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-50 ${FOCUS_RING}`}
            >
              <BookOpen aria-hidden="true" className="w-3 h-3" /> API &amp; Docs
            </Link>
          </footer>
        )}
      </aside>

      {/* Mobile drawer — every page reachable from a 390px phone */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
            onClick={closeMobile}
            aria-hidden="true"
          />
          <div
            id={MOBILE_NAV_PANEL_ID}
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            tabIndex={-1}
            className="relative w-72 max-w-[85vw] h-full bg-white border-r border-slate-200 shadow-xl flex flex-col overflow-y-auto"
          >
            {/* role="presentation": inside a dialog a bare <header> would expose
                a second banner landmark. The dialog itself is the container. */}
            <header
              role="presentation"
              className="h-14 shrink-0 flex items-center justify-between px-3 border-b border-slate-100"
            >
              <BrandMark collapsed={false} />
              <button
                ref={closeBtnRef}
                onClick={closeMobile}
                aria-label="Close navigation"
                className={`p-1 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 ${FOCUS_RING}`}
              >
                <X aria-hidden="true" className="w-5 h-5" />
              </button>
            </header>

            <NavList collapsed={false} onNavigate={closeMobile} label="Mobile" />

            <footer
              role="presentation"
              className="mt-auto p-3 border-t border-slate-100 space-y-2"
            >
              <PromoCard />
              <Link
                href="/setup"
                onClick={closeMobile}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-50 ${FOCUS_RING}`}
              >
                <BookOpen aria-hidden="true" className="w-3 h-3" /> API &amp; Docs
              </Link>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
