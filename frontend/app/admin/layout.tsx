"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken, logout, NotificationOut, UserOut } from "@/lib/api";

const NAV = [
  { href: "/admin", label: "Leads", icon: "📋" },
  { href: "/admin/analytics", label: "Analytics", icon: "📊" },
  { href: "/admin/prompts", label: "Prompts", icon: "🧠", adminOnly: true },
  { href: "/admin/workflows", label: "Workflows", icon: "🔀", adminOnly: true },
  { href: "/admin/kb", label: "Knowledge Base", icon: "📚" },
  { href: "/admin/audit", label: "Audit Log", icon: "🛡️", adminOnly: true },
  { href: "/admin/settings", label: "Settings", icon: "⚙️", adminOnly: true },
];

function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationOut[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    api<NotificationOut[]>("/api/notifications?limit=20", {}, true)
      .then(setItems)
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const unread = items.filter((n) => !n.read).length;

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(!open)}
        className="relative rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
        title="Notifications"
      >
        🔔
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute left-0 top-11 z-50 max-h-96 w-80 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-semibold">Notifications</span>
            <button
              onClick={() =>
                api("/api/notifications/read-all", { method: "POST" }, true).then(load)
              }
              className="text-xs text-indigo-600 hover:underline"
            >
              Mark all read
            </button>
          </div>
          {items.length === 0 && (
            <p className="p-4 text-sm text-slate-400">No notifications yet.</p>
          )}
          {items.map((n) => (
            <Link
              key={n.id}
              href={n.link ? new URL(n.link, window.location.origin).pathname : "#"}
              onClick={() => {
                api(`/api/notifications/${n.id}/read`, { method: "POST" }, true).then(load);
                setOpen(false);
              }}
              className={`block border-b border-slate-50 px-4 py-2.5 text-sm transition hover:bg-slate-50 ${
                n.read ? "opacity-60" : ""
              }`}
            >
              <div className="font-medium text-slate-800">{n.title}</div>
              <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{n.body}</div>
              <div className="mt-0.5 text-[10px] text-slate-400">
                {new Date(n.created_at).toLocaleString()}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

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
        <div className="flex items-center justify-between px-5 py-5">
          <Link href="/" className="flex items-center gap-2 text-lg font-bold text-indigo-700">
            🧭 IntakeAI
          </Link>
          <NotificationBell />
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.filter((item) => !item.adminOnly || user?.role === "admin").map((item) => {
            const active =
              item.href === "/admin"
                ? pathname === "/admin" || pathname.startsWith("/admin/leads")
                : pathname.startsWith(item.href);
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
              <div className="text-xs text-slate-400">
                {user.email} · {user.role}
              </div>
            </div>
          )}
          <button
            onClick={async () => {
              await logout();
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
