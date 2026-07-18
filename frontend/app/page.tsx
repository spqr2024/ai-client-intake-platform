"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ChatWidget from "@/components/ChatWidget";
import { api, Branding } from "@/lib/api";
import { Lang, t } from "@/lib/i18n";

const FEATURES = ["feature1", "feature2", "feature3"] as const;
const FEATURE_ICONS = ["🤖", "⚡", "📊"];

export default function LandingPage() {
  const [lang, setLang] = useState<Lang>("en");
  const [branding, setBranding] = useState<Branding | null>(null);

  useEffect(() => {
    api<Branding>("/api/public/branding?workspace=default").then(setBranding).catch(() => {});
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-b from-indigo-50 via-white to-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2 text-lg font-bold text-indigo-700">
          <span>🧭</span> {branding?.company_name || "IntakeAI"}
        </div>
        <nav className="flex items-center gap-4 text-sm">
          <button
            onClick={() => setLang(lang === "en" ? "uk" : "en")}
            className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
          >
            {lang === "en" ? "🇺🇦 Українська" : "🇬🇧 English"}
          </button>
          <Link
            href="/admin"
            className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white transition hover:bg-slate-700"
          >
            {t(lang, "adminLink")}
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-4xl px-6 pb-20 pt-16 text-center">
        <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-5xl">
          {branding?.hero_title || t(lang, "heroTitle")}
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
          {branding?.hero_subtitle || t(lang, "heroSubtitle")}
        </p>
        <div className="mt-8 flex justify-center">
          <span className="rounded-full bg-indigo-100 px-4 py-2 text-sm font-medium text-indigo-700">
            👉 {t(lang, "heroCta")} — {lang === "en" ? "bottom right corner" : "у правому нижньому куті"}
          </span>
        </div>
      </section>

      <section className="mx-auto grid max-w-5xl gap-6 px-6 pb-24 sm:grid-cols-3">
        {FEATURES.map((key, i) => (
          <div
            key={key}
            className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm transition hover:shadow-md"
          >
            <div className="text-3xl">{FEATURE_ICONS[i]}</div>
            <h3 className="mt-3 font-semibold text-slate-900">{t(lang, `${key}Title`)}</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{t(lang, `${key}Text`)}</p>
          </div>
        ))}
      </section>

      <footer className="border-t border-slate-100 py-8 text-center text-xs text-slate-400">
        AI Client Intake Platform — portfolio demo. FastAPI · Next.js · Postgres · Docker
      </footer>

      <ChatWidget lang={lang} branding={branding} workspace="default" />
    </main>
  );
}
