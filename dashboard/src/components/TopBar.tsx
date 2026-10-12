"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Search, Command, Sparkles } from "lucide-react";

/**
 * TopBar — Apollo's most recognisable affordance is the global search that
 * always sits at the top and can reach any object. Ours searches leads and
 * jumps straight to the filtered database, with "Cmd/Ctrl+K" to focus it
 * from anywhere (muscle memory most Apollo users already have).
 */
export function TopBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

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
    router.push(term ? `/leads?search=${encodeURIComponent(term)}` : "/leads");
  };

  return (
    <div className="h-14 shrink-0 border-b border-slate-200 bg-white flex items-center gap-3 px-5">
      <form onSubmit={submit} className="relative flex-1 max-w-2xl">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search leads, businesses, phone numbers…"
          className="w-full h-9 pl-9 pr-20 rounded-lg border border-slate-200 bg-slate-50 text-[13px] text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:bg-white focus:border-blue-300"
        />
        <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-0.5 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-400">
          <Command className="w-2.5 h-2.5" />K
        </kbd>
      </form>

      <div className="hidden md:flex items-center gap-2 ml-auto">
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-50 border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold text-slate-600">
          <Sparkles className="w-3.5 h-3.5 text-blue-600" />
          Self-hosted · no lead credits
        </span>
      </div>
    </div>
  );
}