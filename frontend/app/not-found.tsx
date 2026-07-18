import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className="text-4xl" aria-hidden="true">
          🧭
        </div>
        <h1 className="mt-3 text-lg font-bold text-slate-900">Page not found</h1>
        <p className="mt-2 text-sm text-slate-500">
          That page doesn&apos;t exist. It may have been moved or deleted.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <Link
            href="/"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
          >
            Home
          </Link>
          <Link
            href="/admin"
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 transition hover:bg-slate-100"
          >
            Dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
