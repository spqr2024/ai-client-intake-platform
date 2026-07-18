import { SkeletonRows } from "@/components/ui";

export default function AdminLoading() {
  return (
    <div>
      <p className="sr-only" role="status">
        Loading page…
      </p>
      <div className="mb-6 h-8 w-48 animate-pulse rounded-lg bg-slate-100" aria-hidden="true" />
      <SkeletonRows rows={6} />
    </div>
  );
}
