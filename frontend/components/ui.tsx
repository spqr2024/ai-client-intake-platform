"use client";

/**
 * Shared UI primitives.
 *
 * Every page previously hand-rolled its own "Loading…", empty and error
 * markup, which drifted in wording and skipped accessibility semantics.
 * These components centralize the three async states plus the small pieces
 * (badges, cards, pagination) so behavior and a11y are consistent everywhere.
 */

import Link from "next/link";
import { ReactNode } from "react";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
    />
  );
}

/** Skeleton rows — a shaped placeholder reads as "content is coming",
 *  where a bare spinner reads as "something might be broken". */
export function SkeletonRows({ rows = 5, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-lg bg-slate-100" />
      ))}
    </div>
  );
}

export function LoadingState({ label = "Loading…", rows = 5 }: { label?: string; rows?: number }) {
  return (
    <div>
      <p className="sr-only" role="status">
        {label}
      </p>
      <SkeletonRows rows={rows} />
    </div>
  );
}

export function EmptyState({
  icon = "📭",
  title,
  description,
  action,
}: {
  icon?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-white p-10 text-center">
      <div className="text-4xl" aria-hidden="true">
        {icon}
      </div>
      <h3 className="mt-3 font-semibold text-slate-800">{title}</h3>
      {description && (
        <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">{description}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-center">
      <div className="text-3xl" aria-hidden="true">
        ⚠️
      </div>
      <p className="mt-2 font-medium text-rose-800">Something went wrong</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-rose-700">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 focus-visible:ring-offset-2"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function Toast({
  kind,
  message,
  onDismiss,
}: {
  kind: "ok" | "err";
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div
      role={kind === "err" ? "alert" : "status"}
      className={`flex items-start justify-between gap-3 rounded-lg px-3 py-2 text-sm ${
        kind === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"
      }`}
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss message"
          className="shrink-0 rounded px-1 opacity-60 transition hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-current"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export function Badge({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

export function Card({
  title,
  children,
  actions,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="font-semibold text-slate-800">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

/** Shared focus-visible treatment: keyboard users always see where they are. */
export const focusRing =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2";

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  if (total <= limit) return null;
  return (
    <nav
      aria-label="Pagination"
      className="mt-4 flex items-center justify-between gap-4 text-sm text-slate-600"
    >
      <span aria-live="polite">
        Showing <b>{offset + 1}</b>–<b>{Math.min(offset + limit, total)}</b> of <b>{total}</b>
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChange(Math.max(0, offset - limit))}
          disabled={page <= 1}
          className={`rounded-lg border border-slate-200 px-3 py-1.5 transition hover:bg-slate-100 disabled:opacity-40 ${focusRing}`}
        >
          ← Prev
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button
          onClick={() => onChange(offset + limit)}
          disabled={page >= pages}
          className={`rounded-lg border border-slate-200 px-3 py-1.5 transition hover:bg-slate-100 disabled:opacity-40 ${focusRing}`}
        >
          Next →
        </button>
      </div>
    </nav>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className={`text-sm text-indigo-600 hover:underline ${focusRing}`}>
      {children}
    </Link>
  );
}
