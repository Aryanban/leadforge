"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Languages, PartyPopper } from "lucide-react";
import { api, IndiaCopyKit } from "@/lib/api";

/**
 * The India copy kit, in the place the operator writes the email.
 *
 * The festival hook and the Hinglish closers already existed and were
 * already served by the API - but they were only reachable by calling the
 * API by hand. The copy kit on the overview tells the operator that a
 * festival window is open; it does not help them write the greeting.
 *
 * Everything here is opt-in: the panel offers lines, and inserting one is
 * the operator's decision. Nothing is auto-inserted into a send.
 */
export default function CopyKitPanel({
  onInsert,
}: {
  /** Inserts a line of copy at the end of the current step's body. */
  onInsert: (text: string) => void;
}) {
  const [kit, setKit] = useState<IndiaCopyKit | null>(null);
  const [open, setOpen] = useState(false);
  // The selected regional language.
  //
  // Every hook has to be called on every render, so this one is declared
  // *before* the `if (!kit) return null` below. Declaring it after that
  // return made the hook count depend on whether the kit had loaded, and
  // React threw error #310 the moment it did - which crashed the whole
  // sequence builder, not just this panel.
  const [chosenLanguage, setChosenLanguage] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.getIndiaCopy();
        if (!cancelled) setKit(res);
      } catch {
        /* The panel is optional; its absence must not break the editor. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!kit) return null;

  const festival = kit.festival;
  const hasFestival = Boolean(festival?.festival);
  const closers = kit.hinglish_closers || [];
  const regional = kit.regional_closers || [];
  const checklist = kit.culture_checklist;

  // One language selector for the regional lines, so the panel does not
  // become a wall of seven scripts.
  //
  // The selected language is *derived* rather than stored on first render,
  // because the kit arrives after the first render - a state value seeded
  // then would be empty forever.
  const languages = Array.from(new Set(regional.map((r) => r.language)));
  const language = languages.includes(chosenLanguage)
    ? chosenLanguage
    : (languages[0] || "");
  const regionalForLanguage = regional.filter((r) => r.language === language);

  // Nothing to offer: no festival window, no closers, no regional lines.
  if (!hasFestival && closers.length === 0 && regional.length === 0) return null;

  return (
    <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50/50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] font-semibold text-amber-800 transition-colors hover:bg-amber-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-inset"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
        )}
        <Languages className="h-3.5 w-3.5 shrink-0" />
        <span>India copy kit</span>
        {hasFestival && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">
            <PartyPopper className="h-3 w-3" />
            {festival.emoji} {festival.festival} window
          </span>
        )}
      </button>

      {open && (
        <div className="space-y-3 border-t border-amber-200 px-3 py-3">
          {hasFestival && (
            <div>
              <p className="text-[11px] font-semibold text-amber-900">
                Seasonal greeting
              </p>
              <p className="mt-0.5 text-[11px] text-amber-800">
                {festival.subject_hook || festival.hinglish_line}
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => onInsert("{{festival_line}}")}
                  className="rounded-lg border border-amber-300 bg-white px-2 py-1 font-mono text-[10px] font-semibold text-amber-800 transition-colors hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1"
                >
                  {"{{festival_line}}"}
                </button>
                {festival.hinglish_line && (
                  <button
                    type="button"
                    onClick={() => onInsert(festival.hinglish_line as string)}
                    className="rounded-lg border border-amber-300 bg-white px-2 py-1 text-[10px] font-medium text-amber-800 transition-colors hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1"
                  >
                    Insert the line
                  </button>
                )}
              </div>
            </div>
          )}

          {closers.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-amber-900">
                Hinglish closers
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {closers.map((c) => (
                  <li key={c.hinglish}>
                    <button
                      type="button"
                      onClick={() => onInsert(c.hinglish)}
                      title={c.english}
                      className="w-full rounded-lg border border-amber-200 bg-white px-2 py-1.5 text-left text-[11px] text-amber-900 transition-colors hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1"
                    >
                      {c.hinglish}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {regional.length > 0 && (
            <div>
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold text-amber-900">
                  Regional languages
                </p>
                <label className="flex items-center gap-1.5">
                  <span className="sr-only">Language</span>
                  <select
                    value={language}
                    onChange={(e) => setChosenLanguage(e.target.value)}
                    aria-label="Regional language"
                    className="h-7 rounded-lg border border-amber-200 bg-white pl-2 pr-6 text-[11px] font-medium text-amber-900 focus:outline-none focus:ring-2 focus:ring-amber-500/30"
                  >
                    {languages.map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="mt-0.5 text-[10px] text-amber-700">
                A tier-2 owner may read this and not English. Keep it to one
                short line.
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {regionalForLanguage.map((r) => (
                  <li key={`${r.language}-${r.text}`}>
                    <button
                      type="button"
                      onClick={() => onInsert(r.text)}
                      title={r.english}
                      className="w-full rounded-lg border border-amber-200 bg-white px-2 py-1.5 text-left text-[11px] text-amber-900 transition-colors hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1"
                    >
                      {r.text}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {checklist && (checklist.do?.length || checklist.dont?.length) ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {checklist.do?.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-emerald-800">Do</p>
                  <ul className="mt-1 space-y-0.5">
                    {checklist.do.map((d) => (
                      <li key={d} className="text-[11px] text-slate-700">
                        • {d}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {checklist.dont?.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-red-700">Avoid</p>
                  <ul className="mt-1 space-y-0.5">
                    {checklist.dont.map((d) => (
                      <li key={d} className="text-[11px] text-slate-700">
                        • {d}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
