"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken, logout, NotificationOut, UserOut } from "@/lib/api";
import { focusRing } from "@/components/ui";

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
  const buttonRef = useRef<HTMLButtonElement>(null);

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
    function onPointerDown(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && open) {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const unread = items.filter((n) => !n.read).length;

  return (
    <div className="relative" ref={panelRef}>
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        className={`relative rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 ${focusRing}`}
      >
        <span aria-hidden="true">🔔</span>
        {unread > 0 && (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white"
          >
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="absolute left-0 top-11 z-50 max-h-96 w-80 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-semibold">Notifications</span>
            <button
              onClick={() =>
                api("/api/notifications/read-all", { method: "POST" }, true).then(load)
              }
              className={`rounded text-xs text-indigo-600 hover:underline ${focusRing}`}
            >
              Mark all read
            </button>
          </div>
          {items.length === 0 && (
            <p className="p-4 text-sm text-slate-400">No notifications yet.</p>
          )}
          <ul>
            {items.map((n) => (
              <li key={n.id}>
                <Link
                  href={n.link ? new URL(n.link, window.location.origin).pathname : "#"}
                  onClick={() => {
                    api(`/api/notifications/${n.id}/read`, { method: "POST" }, true).then(load);
                    setOpen(false);
                  }}
                  className={`block border-b border-slate-50 px-4 py-2.5 text-sm transition hover:bg-slate-50 ${focusRing} ${
                    n.read ? "opacity-60" : ""
                  }`}
                >
                  <div className="font-medium text-slate-800">{n.title}</div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{n.body}</div>
                  <div className="mt-0.5 text-[10px] text-slate-400">
                    {new Date(n.created_at).toLocaleString()}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserOut | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const isLogin = pathname === "/admin/login";

  useEffect(() => {
    if (isLogin) return;
    if (!getToken()) {
      router.replace("/admin/login");
      return;
    }
    api<UserOut>("/api/auth/me", {}, true).then(setUser).catch(() => {});
  }, [isLogin, router, pathname]);

  // Route changes close the mobile drawer, otherwise it covers the new page.
  useEffect(() => setNavOpen(false), [pathname]);

  if (isLogin) return <>{children}</>;

  const visibleNav = NAV.filter((item) => !item.adminOnly || user?.role === "admin");

  const navLinks = (
    <ul className="space-y-1">
      {visibleNav.map((item) => {
        const active =
          item.href === "/admin"
            ? pathname === "/admin" || pathname.startsWith("/admin/leads")
            : pathname.startsWith(item.href);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${focusRing} ${
                active ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <span aria-hidden="true">{item.icon}</span> {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );

  const footer = (
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
        className={`w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100 ${focusRing}`}
      >
        Sign out
      </button>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <a
        href="#main-content"
        className="sr-only rounded-lg bg-indigo-600 px-4 py-2 text-white focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50"
      >
        Skip to main content
      </a>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <button
          onClick={() => setNavOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={navOpen}
          className={`rounded-lg p-2 text-slate-600 transition hover:bg-slate-100 ${focusRing}`}
        >
          <span aria-hidden="true">☰</span>
        </button>
        <Link href="/" className="flex items-center gap-2 font-bold text-indigo-700">
          <span aria-hidden="true">🧭</span> IntakeAI
        </Link>
        <NotificationBell />
      </header>

      {/* Mobile drawer */}
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={() => setNavOpen(false)}
            aria-hidden="true"
          />
          <nav
            aria-label="Main navigation"
            className="absolute left-0 top-0 flex h-full w-64 max-w-[85vw] flex-col bg-white shadow-xl"
          >
            <div className="flex items-center justify-between px-5 py-4">
              <span className="font-bold text-indigo-700">🧭 IntakeAI</span>
              <button
                onClick={() => setNavOpen(false)}
                aria-label="Close navigation menu"
                className={`rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 ${focusRing}`}
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3">{navLinks}</div>
            {footer}
          </nav>
        </div>
      )}

      <div className="flex">
        {/* Desktop sidebar */}
        <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex lg:min-h-screen">
          <div className="flex items-center justify-between px-5 py-5">
            <Link
              href="/"
              className={`flex items-center gap-2 text-lg font-bold text-indigo-700 ${focusRing}`}
            >
              <span aria-hidden="true">🧭</span> IntakeAI
            </Link>
            <NotificationBell />
          </div>
          <nav aria-label="Main navigation" className="flex-1 px-3">
            {navLinks}
          </nav>
          {footer}
        </aside>

        <main id="main-content" className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
