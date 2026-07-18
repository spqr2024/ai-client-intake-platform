"use client";

import { useEffect } from "react";

/** Root error boundary: an uncaught render error shows a recoverable screen
 *  instead of a blank page. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled UI error:", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div
        role="alert"
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm"
      >
        <div className="text-4xl" aria-hidden="true">
          ⚠️
        </div>
        <h1 className="mt-3 text-lg font-bold text-slate-900">Something went wrong</h1>
        <p className="mt-2 text-sm text-slate-500">
          The page failed to render. You can retry, or go back to the dashboard.
        </p>
        {error.digest && (
          <p className="mt-2 font-mono text-xs text-slate-400">Reference: {error.digest}</p>
        )}
        <div className="mt-5 flex justify-center gap-2">
          <button
            onClick={reset}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
          >
            Try again
          </button>
          <a
            href="/admin"
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 transition hover:bg-slate-100"
          >
            Back to dashboard
          </a>
        </div>
      </div>
    </main>
  );
}
