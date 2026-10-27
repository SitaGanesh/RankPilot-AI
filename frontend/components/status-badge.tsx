import type { AuditStatus, CrawlStatus } from "@/types/api";

const labels: Partial<Record<AuditStatus | CrawlStatus, string>> = {
  pending: "Pending",
  queued: "Queued",
  collecting: "Collecting",
  collected: "Collected",
  running: "Running",
  waiting_for_access: "Waiting for access",
  waiting_for_approval: "Waiting for approval",
  completed: "Completed",
  completed_with_limitations: "Completed (limitations)",
  failed: "Failed",
  cancelled: "Cancelled",
  fetching: "Fetching",
  fetched: "Fetched",
  processing: "Processing",
  discovered: "Discovered",
  skipped: "Skipped",
};

export function StatusBadge({ status }: { status: AuditStatus | CrawlStatus }) {
  const tone =
    status === "failed" || status === "cancelled"
      ? "border-red-200 bg-red-50 text-red-700"
      : status === "fetched" || status === "collected" || status === "completed"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : status === "fetching" || status === "collecting" || status === "running"
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : "border-slate-200 bg-slate-50 text-slate-600";

  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tone}`}>
      {labels[status] || status}
    </span>
  );
}
