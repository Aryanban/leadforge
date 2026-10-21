import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { FirstRunWizard } from "@/components/FirstRunWizard";
import { Toaster } from "@/components/Toaster";
import { MainFocus } from "@/components/MainFocus";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "LeadForge",
  description: "Lead Generation System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} flex h-screen overflow-hidden`}>
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          {/* The TopBar is the page banner — a landmark, so assistive tech
              can jump straight to it. <main> stays the only main landmark. */}
          <header className="shrink-0">
            <TopBar />
          </header>
          <main
            id="main-content"
            tabIndex={-1}
            className="flex-1 overflow-y-auto bg-slate-50/60 p-4 sm:p-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
          >
            {children}
          </main>
        </div>
        {/* First-run setup: shows only while a required connection is missing */}
        <FirstRunWizard />
        {/* App-wide notifications (replaces blocking browser dialogs) */}
        <Toaster />
        {/* Moves focus to <main> after a keyboard navigation */}
        <MainFocus />
      </body>
    </html>
  );
}
