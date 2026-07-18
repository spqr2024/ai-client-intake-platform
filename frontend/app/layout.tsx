import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "cyrillic"],
  display: "swap",
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
const title = "AI Client Intake Platform — conversational lead qualification";
const description =
  "Replace static contact forms with an AI assistant that interviews prospects 24/7, " +
  "captures budget and timeline, scores every lead and hands your team a ready-to-act brief.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: title, template: "%s · IntakeAI" },
  description,
  applicationName: "IntakeAI",
  keywords: [
    "AI intake",
    "lead qualification",
    "conversational forms",
    "CRM",
    "FastAPI",
    "Next.js",
  ],
  openGraph: {
    type: "website",
    url: siteUrl,
    title,
    description,
    siteName: "IntakeAI",
  },
  twitter: { card: "summary_large_image", title, description },
  // The public landing page should be indexable; the admin area is excluded
  // via its own metadata below and is behind authentication regardless.
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} bg-white font-sans text-slate-900 antialiased`}>
        {children}
      </body>
    </html>
  );
}
