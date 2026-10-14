"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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
  MailCheck,
  BookOpen,
  Inbox,
  Building2,
  Activity,
} from "lucide-react";

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
      { href: "/companies", label: "Companies", icon: Building2 },
    ],
  },
  {
    title: "Deliverability",
    items: [{ href: "/email-health", label: "Email Health", icon: Activity }],
  },
  {
    title: "Setup",
    items: [{ href: "/settings", label: "Mailboxes & Setup", icon: Settings }],
  },
];

const COLLAPSE_KEY = "leadforge.sidebar.collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

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

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div
      className={`${
        collapsed ? "w-[68px]" : "w-60"
      } shrink-0 border-r border-slate-200 bg-white flex flex-col justify-between min-h-screen transition-all duration-200`}
    >
      <div>
        {/* Brand + collapse toggle */}
        <div className="h-14 flex items-center justify-between px-3 border-b border-slate-100">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="w-8 h-8 shrink-0 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
              LF
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <h1 className="font-bold text-sm tracking-tight text-slate-900 leading-none truncate">
                  LeadForge
                </h1>
                <span className="text-[9px] text-slate-400 font-semibold tracking-wider uppercase">
                  Sales Platform
                </span>
              </div>
            )}
          </div>
          <button
            onClick={toggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
          >
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>

        {/* Grouped nav */}
        <nav className="p-2.5 space-y-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.title}>
              {!collapsed && (
                <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
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
                      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors ${
                        active
                          ? "bg-blue-50 text-blue-700 font-semibold"
                          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                      } ${collapsed ? "justify-center" : ""}`}
                    >
                      <Icon className={`w-4 h-4 shrink-0 ${active ? "text-blue-600" : "text-slate-400"}`} />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      {!collapsed && (
        <div className="p-3 border-t border-slate-100 space-y-2">
          <div className="p-3 bg-gradient-to-br from-blue-50 to-indigo-50/60 rounded-xl border border-blue-100/70">
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-blue-900 mb-0.5">
              <Sparkles className="w-3.5 h-3.5 text-blue-600" />
              Live lead data
            </div>
            <p className="text-[10px] text-blue-700/80 leading-relaxed">
              Scraped fresh, verified, India-ready — no per-lead credits.
            </p>
          </div>
          <a
            href="/docs"
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-50"
          >
            <BookOpen className="w-3 h-3" /> API & Docs
          </a>
        </div>
      )}
    </div>
  );
}
