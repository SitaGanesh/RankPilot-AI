import type { AuditStatus, CrawlStatus } from "@/types/api";

const labels: Record<AuditStatus | CrawlStatus, string> = {
  pending: "Pending",
  collecting: "Collecting",
  collected: "Collected",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  fetching: "Fetching",
  fetched: "Fetched",
  skipped: "Skipped",
};

export function StatusBadge({ status }: { status: AuditStatus | CrawlStatus }) {
  const tone =
    status === "failed"
      ? "border-red-200 bg-red-50 text-red-700"
      : status === "fetched" || status === "collected" || status === "completed"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : status === "fetching" || status === "collecting" || status === "running"
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : "border-slate-200 bg-slate-50 text-slate-600";

  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tone}`}>
      {labels[status]}
    </span>
  );
}
