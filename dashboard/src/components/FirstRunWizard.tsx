"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Rocket,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Mail,
  X,
  Wand2,
} from "lucide-react";
import { api, ProviderPreset } from "@/lib/api";
import { FOCUS_RING } from "@/components/focusRing";

const STORAGE_KEY = "leadforge.setup.v1";

/**
 * First-run wizard — for people who are NOT technically savvy.
 *
 * Three plain-English steps: pick your email provider (presets fill every
 * host/port; the help box says exactly where to find an app password),
 * connect + live-test the mailbox, optionally set the public URL for
 * unsubscribe links. Shown only while a required connection is missing;
 * skippable, and re-openable forever from the Connections page.
 */
export function FirstRunWizard() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0); // 0 welcome · 1 provider · 2 mailbox · 3 URL · 4 done
  const [providers, setProviders] = useState<ProviderPreset[]>([]);
  const [provider, setProvider] = useState<ProviderPreset | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState(587);
  const [imapHost, setImapHost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warned, setWarned] = useState(false);
  const [tracking, setTracking] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await api.getSetupStatus();
        if (cancelled) return;
        setTracking(status.api_url || "");
        const state = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
        if (!status.ready && state !== "done" && state !== "skipped") {
          try {
            const prov = await api.getProviderPresets();
            setProviders(prov.providers);
          } catch {
            /* presets are an enhancement; the wizard still works manually */
          }
          setOpen(true);
        }
      } catch {
        /* backend unreachable — stay quiet, Connections page shows the error */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const finish = (state: "done" | "skipped") => {
    try {
      localStorage.setItem(STORAGE_KEY, state);
    } catch {
      /* private mode — the flag just won't persist */
    }
    setOpen(false);
  };

  // Move focus into the wizard when it opens so keyboard users are not left
  // behind on the page underneath, and keep Tab inside the dialog while it is
  // open (it is a modal — the page behind it is not reachable).
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => dialogRef.current?.focus(), 0);

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusables = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
        )
      ).filter((el) => el.getClientRects().length > 0);
      if (focusables.length === 0) {
        e.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !dialog.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const pick = (p: ProviderPreset) => {
    setProvider(p);
    setSmtpHost(p.smtp_host);
    setSmtpPort(p.smtp_port);
    setImapHost(p.imap_host);
    setStep(2);
    setError(null);
    setWarned(false);
  };

  const connect = async () => {
    setBusy(true);
    setError(null);
    setWarned(false);
    try {
      const mb = await api.createMailbox({
        email: email.trim(),
        password,
        smtp_host: smtpHost.trim(),
        smtp_port: smtpPort,
      });
      if (imapHost.trim()) {
        try {
          await api.updateMailboxImap(mb.id, imapHost.trim());
        } catch {
          /* IMAP is optional — reply detection just won't run for this box */
        }
      }
      const test = await api.testMailbox(mb.id);
      if (!test.success) {
        setWarned(true);
        setError(test.message);
        setBusy(false);
        return; // stay on the form: retry, or continue anyway
      }
      setStep(3);
    } catch (e: any) {
      setError(e.message || "Could not connect that mailbox. Check the address and password.");
    } finally {
      setBusy(false);
    }
  };

  const saveTracking = async (next: boolean) => {
    setBusy(true);
    setNote(null);
    setError(null);
    if (next) {
      try {
        await api.updateSetupSetting("TRACKING_DOMAIN", tracking.trim());
      } catch (e: any) {
        setError(e.message || "That URL doesn't look right — it must start with http:// or https://");
        setBusy(false);
        return;
      }
    }
    setBusy(false);
    setStep(4);
    try {
      localStorage.setItem(STORAGE_KEY, "done");
    } catch {
      /* private mode — flag just won't persist */
    }
  };

  if (!open) return null;

  const stepTitles = ["Welcome", "Your email provider", "Connect mailbox"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/50" aria-hidden="true" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="lf-wizard-title"
        tabIndex={-1}
        className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl overflow-hidden focus-visible:outline-none"
      >
        {/* Header */}
        <div className="border-b border-slate-200 px-6 py-4 flex items-center gap-3">
          <span
            aria-hidden="true"
            className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center"
          >
            <Wand2 className="w-4 h-4" />
          </span>
          <div>
            <h2 id="lf-wizard-title" className="text-sm font-bold text-slate-900">
              {step < 4 ? stepTitles[step] || "Almost done!" : "You're all set!"}
            </h2>
            <div className="flex items-center gap-1.5 mt-1">
              {[0, 1, 2, 3].map((i) => (
                <span
                  key={i}
                  className={`h-1 w-6 rounded-full motion-safe:transition-colors ${
                    step >= i ? "bg-blue-500" : "bg-slate-200"
                  }`}
                />
              ))}
            </div>
          </div>
          <button
            onClick={() => finish(step === 4 ? "done" : "skipped")}
            aria-label={step === 4 ? "Close" : "Skip setup"}
            className={`ml-auto p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 ${FOCUS_RING}`}
          >
            <X aria-hidden="true" className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 max-h-[70vh] overflow-y-auto">
          {step === 0 && (
            <div className="space-y-4">
              <h3 className="text-lg font-bold text-slate-900">
                Let&apos;s get you sending in about 2 minutes.
              </h3>
              <ul className="space-y-2.5 text-[13px] text-slate-600">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                  <span>
                    <strong>Step 1:</strong> Pick your email provider — we fill in all the
                    technical settings for you.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                  <span>
                    <strong>Step 2:</strong> Paste your email and an app password — we test the
                    connection live.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                  <span>
                    <strong>Step 3 (optional):</strong> Your public URL so recipients can
                    unsubscribe with one click.
                  </span>
                </li>
              </ul>
              <p className="text-[11px] text-slate-600">
                No credit card, no API keys, no AI keys needed. Everything runs on your machine.
              </p>
              <button
                onClick={() => setStep(1)}
                className={`w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 text-white py-2.5 text-sm font-semibold hover:bg-blue-700 ${FOCUS_RING}`}
              >
                Get started <ArrowRight aria-hidden="true" className="w-4 h-4" />
              </button>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <p className="text-[13px] text-slate-600">
                Where will outreach emails come from? Pick your provider:
              </p>
              <div className="grid grid-cols-1 gap-2">
                {providers.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => pick(p)}
                    className={`rounded-xl border border-slate-200 px-4 py-3 text-left hover:border-blue-400 hover:bg-blue-50/40 motion-safe:transition-colors ${FOCUS_RING}`}
                  >
                    <span className="text-sm font-semibold text-slate-900">{p.label}</span>
                  </button>
                ))}
              </div>
              {!provider && (
                <p className="text-[11px] text-slate-600">
                  Not sure? Gmail and Outlook are the most common.
                </p>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              {provider && (
                <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-3.5">
                  <p className="text-[11px] font-bold text-blue-800 uppercase tracking-wide mb-1">
                    How to get your password for {provider.label}
                  </p>
                  <p className="text-[12px] text-slate-700 leading-relaxed">{provider.howto}</p>
                </div>
              )}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email address</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@gmail.com"
                  className={`w-full h-10 px-3 rounded-xl border border-slate-200 bg-slate-50/50 text-sm focus:bg-white focus:outline-none focus:border-blue-300 ${FOCUS_RING}`}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  App password{" "}
                  <span className="font-normal text-slate-600">
                    (the special one, not your login password)
                  </span>
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="16-character app password"
                  className={`w-full h-10 px-3 rounded-xl border border-slate-200 bg-slate-50/50 text-sm focus:bg-white focus:outline-none focus:border-blue-300 ${FOCUS_RING}`}
                />
              </div>
              <details className="rounded-xl border border-slate-200 px-3.5 py-2.5">
                <summary
                  className={`text-[11px] font-semibold text-slate-500 cursor-pointer ${FOCUS_RING}`}
                >
                  Advanced — server settings (auto-filled, expand to edit)
                </summary>
                <div className="grid grid-cols-3 gap-2 mt-2.5">
                  <input
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                    className={`col-span-2 h-9 px-2.5 rounded-lg border border-slate-200 text-xs font-mono ${FOCUS_RING}`}
                    aria-label="SMTP host"
                  />
                  <input
                    type="number"
                    value={smtpPort}
                    onChange={(e) => setSmtpPort(parseInt(e.target.value) || 587)}
                    className={`h-9 px-2.5 rounded-lg border border-slate-200 text-xs font-mono text-center ${FOCUS_RING}`}
                    aria-label="SMTP port"
                  />
                </div>
                <p className="text-[11px] text-slate-600 mt-1.5">
                  Reply detection will use {imapHost || "your provider's IMAP"} automatically.
                </p>
              </details>

              {error && (
                <div
                  className={`rounded-xl border px-4 py-2.5 text-xs font-medium ${
                    warned
                      ? "border-amber-200 bg-amber-50 text-amber-800"
                      : "border-red-200 bg-red-50 text-red-700"
                  }`}
                >
                  {warned ? `Connection test failed: ${error}` : error}
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setStep(1)}
                  className={`rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 ${FOCUS_RING}`}
                >
                  Back
                </button>
                <button
                  onClick={connect}
                  disabled={busy || !email.trim() || !password || !smtpHost.trim()}
                  className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 text-white py-2.5 text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 ${FOCUS_RING}`}
                >
                  {busy ? (
                    <Loader2 aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin motion-reduce:animate-pulse" />
                  ) : (
                    <Mail aria-hidden="true" className="w-4 h-4" />
                  )}
                  Connect &amp; test
                </button>
              </div>
              {warned && (
                <button
                  onClick={() => setStep(3)}
                  className={`w-full text-[11px] font-semibold text-slate-600 hover:text-slate-800 ${FOCUS_RING}`}
                >
                  Continue anyway (I&apos;ll fix it later from Settings)
                </button>
              )}
            </div>
          )}


          {step === 3 && (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Where does LeadForge live on the internet?
                </h3>
                <p className="text-[12px] text-slate-600 mt-1 leading-relaxed">
                  Recipients see this URL in the <strong>unsubscribe link</strong> of every
                  email. If you&apos;re running this only on your own computer, keep what&apos;s
                  here and click Skip — you can set it later on the Connections page.
                </p>
              </div>
              <input
                value={tracking}
                onChange={(e) => setTracking(e.target.value)}
                placeholder="https://api.yourdomain.com"
                className={`w-full h-10 px-3 rounded-xl border border-slate-200 bg-slate-50/50 text-sm font-mono focus:bg-white focus:outline-none focus:border-blue-300 ${FOCUS_RING}`}
                aria-label="Public backend URL"
              />
              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-medium text-red-700">
                  {error}
                </div>
              )}
              {note && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-700">
                  {note}
                </div>
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setStep(2)}
                  className={`rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 ${FOCUS_RING}`}
                >
                  Back
                </button>
                <button
                  onClick={() => saveTracking(true)}
                  disabled={busy}
                  className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 text-white py-2.5 text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 ${FOCUS_RING}`}
                >
                  {busy ? <Loader2 aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin motion-reduce:animate-pulse" /> : null}
                  Save &amp; finish
                </button>
              </div>
              <button
                onClick={() => saveTracking(false)}
                className={`w-full text-[11px] font-semibold text-slate-600 hover:text-slate-800 ${FOCUS_RING}`}
              >
                Skip this step
              </button>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4 text-center py-2">
              <span className="mx-auto w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Rocket className="w-6 h-6" />
              </span>
              <h3 className="text-lg font-bold text-slate-900">You&apos;re ready to send! 🎉</h3>
              <p className="text-[13px] text-slate-600 max-w-sm mx-auto">
                Next: find leads, add them to a sequence, and launch. You can always come back to
                this checklist from <strong>Connections</strong>.
              </p>
              <div className="flex items-center gap-2 pt-1">
                <Link
                  href="/find"
                  onClick={() => finish("done")}
                  className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 text-white py-2.5 text-sm font-semibold hover:bg-blue-700 ${FOCUS_RING}`}
                >
                  Find leads <ArrowRight aria-hidden="true" className="w-4 h-4" />
                </Link>
                <Link
                  href="/sequences"
                  onClick={() => finish("done")}
                  className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 ${FOCUS_RING}`}
                >
                  Build a sequence
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


