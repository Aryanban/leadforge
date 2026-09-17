"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  Users,
  Mail,
  Settings,
  Sparkles,
  ExternalLink,
  Target
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: "Overview", icon: LayoutDashboard },
    { href: "/find", label: "Find Best Leads", icon: Target },
    { href: "/scrape", label: "Scrape Leads", icon: Search },
    { href: "/leads", label: "Lead Database", icon: Users },
    { href: "/campaigns", label: "Email Campaigns", icon: Mail },
    { href: "/settings", label: "Mailboxes & Setup", icon: Settings },
  ];

  return (
    <div className="w-64 border-r border-slate-200 bg-white flex flex-col justify-between shrink-0 min-h-screen">
      <div>
        <div className="h-16 flex items-center justify-between px-6 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-base shadow-sm">
              LF
            </div>
            <div>
              <h1 className="font-bold text-base tracking-tight text-slate-900 leading-none">LeadForge</h1>
              <span className="text-[10px] text-slate-400 font-medium tracking-wide uppercase">Outreach Engine</span>
            </div>
          </div>
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
        </div>

        <nav className="p-4 space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-semibold shadow-xs"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-blue-600" : "text-slate-400"}`} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="p-4 border-t border-slate-100 space-y-3">
        <div className="p-3 bg-gradient-to-br from-blue-50 to-indigo-50/50 rounded-xl border border-blue-100/60">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-900 mb-1">
            <Sparkles className="w-3.5 h-3.5 text-blue-600" />
            Zero-API-Key Scraping
          </div>
          <p className="text-[11px] text-blue-700/80 leading-relaxed">
            Free automated Google Maps & website enrichment with zero per-lead fees.
          </p>
        </div>

        <a
          href="https://plotbook.webforge.me"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between px-3 py-2 text-xs text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-50 transition-colors"
        >
          <span>PlotBook Maps</span>
          <ExternalLink className="w-3 h-3 text-slate-400" />
        </a>
      </div>
    </div>
  );
}
