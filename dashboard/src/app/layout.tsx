import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { FirstRunWizard } from "@/components/FirstRunWizard";
import { Toaster } from "@/components/Toaster";

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
          <TopBar />
          <main className="flex-1 overflow-y-auto bg-slate-50/60 p-4 sm:p-6">{children}</main>
        </div>
        {/* First-run setup: shows only while a required connection is missing */}
        <FirstRunWizard />
        {/* App-wide notifications (replaces blocking browser dialogs) */}
        <Toaster />
      </body>
    </html>
  );
}
