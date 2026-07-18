import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "AI Client Intake Platform",
  description:
    "Conversational AI intake that qualifies leads 24/7 — chat, CRM, Telegram alerts and analytics.",
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
