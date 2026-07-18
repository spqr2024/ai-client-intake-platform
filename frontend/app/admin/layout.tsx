"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, getToken, setToken, UserOut } from "@/lib/api";

const NAV = [
  { href: "/admin", label: "Leads", icon: "📋" },
  { href: "/admin/analytics", label: "Analytics", icon: "📊" },
  { href: "/admin/workflows", label: "Workflows", icon: "🔀", adminOnly: true },
  { href: "/admin/kb", label: "Knowledge Base", icon: "📚" },
  { href: "/admin/settings", label: "Settings", icon: "⚙️", adminOnly: true },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserOut | null>(null);
  const isLogin = pathname === "/admin/login";

  useEffect(() => {
    if (isLogin) return;
    if (!getToken()) {
      router.replace("/admin/login");
      return;
    }
    api<UserOut>("/api/auth/me", {}, true).then(setUser).catch(() => {});
  }, [isLogin, router, pathname]);

  if (isLogin) return <>{children}</>;

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <Link href="/" className="flex items-center gap-2 px-5 py-5 text-lg font-bold text-indigo-700">
          🧭 IntakeAI
        </Link>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.filter((item) => !item.adminOnly || user?.role === "admin").map((item) => {
            const active =
              item.href === "/admin" ? pathname === "/admin" || pathname.startsWith("/admin/leads") : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  active ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <span>{item.icon}</span> {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-100 p-4">
          {user && (
            <div className="mb-2 text-sm">
              <div className="font-medium text-slate-800">{user.name}</div>
              <div className="text-xs text-slate-400">{user.email} · {user.role}</div>
            </div>
          )}
          <button
            onClick={() => {
              setToken(null);
              router.push("/admin/login");
            }}
            className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-8">{children}</main>
    </div>
  );
}
