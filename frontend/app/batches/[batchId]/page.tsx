"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Compass,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Filter,
  Globe,
  Image as ImageIcon,
  Layers,
  Link2,
  Loader2,
  MapPin,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";

import { cancelBatch, getBatchReport, resumeBatch, retryBatch } from "@/lib/api";
import type { BatchReport, BatchTargetReport, BatchTopIssue } from "@/types/api";

function statusClass(status: string) {
  if (status === "completed") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "failed") return "bg-red-50 text-red-700 border-red-200";
  if (status === "partial") return "bg-amber-50 text-amber-700 border-amber-200";
  if (status === "running") return "bg-blue-50 text-blue-700 border-blue-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function severityClass(sev: string) {
  if (sev === "critical") return "bg-red-100 text-red-800 border-red-200";
  if (sev === "high") return "bg-orange-100 text-orange-800 border-orange-200";
  if (sev === "medium") return "bg-amber-100 text-amber-800 border-amber-200";
  if (sev === "low") return "bg-blue-100 text-blue-800 border-blue-200";
  return "bg-slate-100 text-slate-700 border-slate-200";
}

function metric(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : value.toString();
}

function scoreColor(score: number | null | undefined) {
  if (score === null || score === undefined) return "text-slate-400";
  if (score >= 80) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function BatchReportPage() {
  return (
    <Suspense fallback={<main className="p-8 text-sm text-slate-500">Loading saved report…</main>}>
      <BatchReportContent />
    </Suspense>
  );
}

function BatchReportContent() {
  const [report, setReport] = useState<BatchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Filters & sorting
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [analysisFilter, setAnalysisFilter] = useState<string>("all");
  const [sortField, setSortField] = useState<"position" | "url" | "http" | "timing">("position");
  const [sortAsc, setSortAsc] = useState(true);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);

  const params = useParams<{ batchId: string }>();
  const batchId = params.batchId;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await getBatchReport(batchId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load the batch report.");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Polling if batch is running
  useEffect(() => {
    if (!report || (report.batch.status !== "running" && report.batch.status !== "pending")) return;
    const timer = window.setInterval(async () => {
      try {
        setReport(await getBatchReport(batchId));
      } catch {
        // ignore transient poll error
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [report, batchId]);

  async function handleRetry() {
    if (!batchId) return;
    setActionLoading("retry");
    try {
      await retryBatch(batchId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry batch");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleResume() {
    if (!batchId) return;
    setActionLoading("resume");
    try {
      await resumeBatch(batchId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume batch");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCancel() {
    if (!batchId) return;
    setActionLoading("cancel");
    try {
      await cancelBatch(batchId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel batch");
    } finally {
      setActionLoading(null);
    }
  }

  // Aggregate HTML link metrics
  const linkStats = useMemo(() => {
    let totalInternal = 0;
    let totalExternal = 0;
    let totalBroken = 0;
    let totalImages = 0;
    for (const t of report?.targets ?? []) {
      totalInternal += t.internal_link_count ?? 0;
      totalExternal += t.external_link_count ?? 0;
      totalBroken += t.broken_link_count ?? 0;
      totalImages += t.image_count ?? 0;
    }
    return {
      totalLinks: totalInternal + totalExternal,
      totalInternal,
      totalExternal,
      totalBroken,
      totalImages,
    };
  }, [report]);

  // Urgent URLs needing immediate attention
  const urgentTargets = useMemo(() => {
    if (!report?.targets) return [];
    return report.targets
      .filter((t) => {
        const scores = t.scores ?? {};
        const scoreVals = Object.values(scores).filter((s): s is number => typeof s === "number");
        const lowestScore = scoreVals.length > 0 ? Math.min(...scoreVals) : 100;
        return (
          t.status === "failed" ||
          t.analysis_status === "failed" ||
          t.analysis_status === "partial" ||
          lowestScore < 60
        );
      })
      .slice(0, 6);
  }, [report]);

  // Location comparison breakdown
  const locationComparison = useMemo(() => {
    if (!report?.targets) return [];
    return report.targets
      .filter((t) => /(?:cities|countries)\//i.test(t.submitted_url))
      .map((t) => {
        const match = t.submitted_url.match(/(?:cities|countries)\/([^/?#]+)/i);
        const locationName = match
          ? match[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
          : "Other";
        return {
          target: t,
          location: locationName,
          scores: t.scores ?? {},
        };
      });
  }, [report]);

  const severityCounts = useMemo(() => {
    if (report?.summary?.severity_counts) {
      return report.summary.severity_counts;
    }
    const counts: Record<string, number> = {};
    for (const f of report?.findings ?? []) {
      const sev = typeof f.severity === "string" ? f.severity : "unknown";
      counts[sev] = (counts[sev] ?? 0) + 1;
    }
    return counts;
  }, [report]);

  const topIssues: BatchTopIssue[] = useMemo(() => {
    if (report?.summary?.top_issues?.length) {
      return report.summary.top_issues;
    }
    const issues = new Map<string, BatchTopIssue>();
    for (const f of report?.findings ?? []) {
      const st = String(f.status ?? "");
      const sev = String(f.severity ?? "low");
      if (st === "fail" || st === "warn") {
        const id = String(f.check_id ?? f.id ?? "issue");
        const existing = issues.get(id);
        const url = String(f.url ?? "");
        if (existing) {
          if (!existing.affected_urls.includes(url)) {
            existing.affected_count += 1;
            if (existing.affected_urls.length < 10) existing.affected_urls.push(url);
          }
        } else {
          issues.set(id, {
            check_id: id,
            title: String(f.title ?? id),
            severity: sev,
            agent_id: String(f.agent_id ?? ""),
            status: st,
            recommendation: String(f.recommendation ?? ""),
            why_it_matters: String(f.why_it_matters ?? ""),
            affected_count: 1,
            affected_urls: [url],
          });
        }
      }
    }
    return Array.from(issues.values()).sort((a, b) => b.affected_count - a.affected_count).slice(0, 10);
  }, [report]);

  // Filtered and sorted targets
  const visibleTargets = useMemo(() => {
    if (!report?.targets) return [];
    return report.targets
      .filter((t: BatchTargetReport) => {
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchSubmitted = t.submitted_url.toLowerCase().includes(q);
          const matchFinal = t.final_url?.toLowerCase().includes(q);
          if (!matchSubmitted && !matchFinal) return false;
        }
        if (statusFilter !== "all" && t.status !== statusFilter) return false;
        if (analysisFilter !== "all" && t.analysis_status !== analysisFilter) return false;
        return true;
      })
      .sort((a, b) => {
        let diff = 0;
        if (sortField === "position") diff = a.position - b.position;
        else if (sortField === "url") diff = a.submitted_url.localeCompare(b.submitted_url);
        else if (sortField === "http") diff = (a.response_status ?? 0) - (b.response_status ?? 0);
        else if (sortField === "timing") diff = (a.timing_ms ?? 0) - (b.timing_ms ?? 0);
        return sortAsc ? diff : -diff;
      });
  }, [report, searchQuery, statusFilter, analysisFilter, sortField, sortAsc]);

  if (loading && !report) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] p-8 text-slate-500">
        <div className="mx-auto flex max-w-7xl items-center gap-3">
          <Loader2 className="animate-spin text-indigo-600" size={20} />
          <span>Loading saved batch report…</span>
        </div>
      </main>
    );
  }

  if (error && !report) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] p-8">
        <div className="mx-auto max-w-7xl">
          <Link href="/" className="text-sm font-semibold text-indigo-600 hover:text-indigo-800">
            <ArrowLeft className="mr-1 inline" size={15} /> Back to Dashboard
          </Link>
          <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-red-700">
            <AlertCircle className="mr-2 inline" size={18} />
            {error}
          </div>
        </div>
      </main>
    );
  }

  if (!report) return null;

  const batch = report.batch;
  const summary = report.summary;
  const isRunning = batch.status === "running" || batch.status === "pending";

  function downloadJSON() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `batch-${batch.id}-report.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  return (
    <main className="min-h-screen bg-[#f8fafc] px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Navigation & Export Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <Link href="/" className="hover:text-indigo-600">
              Home
            </Link>
            <span>/</span>
            <Link href="/batches" className="hover:text-indigo-600">
              Batch Audits
            </Link>
            <span>/</span>
            <span className="font-semibold text-slate-800">{batch.id.slice(0, 8)}…</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void load()}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
            <a
              href={`/backend-api/batches/${batch.id}/export/?type=targets&format=csv`}
              download={`batch-${batch.id}-targets.csv`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              <FileSpreadsheet size={13} /> Targets CSV
            </a>
            <a
              href={`/backend-api/batches/${batch.id}/export/?type=findings&format=csv`}
              download={`batch-${batch.id}-findings.csv`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              <FileSpreadsheet size={13} /> Findings CSV
            </a>
            <button
              onClick={downloadJSON}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
            >
              <Download size={13} /> JSON
            </button>
          </div>
        </div>

        {/* Header Hero Card */}
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-600">
                  Batch SEO Audit Report
                </span>
                {isRunning && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                    <Loader2 size={11} className="animate-spin" /> In Progress
                  </span>
                )}
              </div>
              <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                Batch {batch.id.slice(0, 8)}…
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>{batch.total_count} Target URLs</span>
                <span>•</span>
                <span>
                  Key: <span className="font-mono text-slate-700">{batch.idempotency_key}</span>
                </span>
                <span>•</span>
                <span>{batch.allow_internal_discovery ? "Spidering enabled" : "Fixed URL list"}</span>
                <span>•</span>
                <span>Created: {formatDate(batch.created_at)}</span>
                {batch.started_at && (
                  <>
                    <span>•</span>
                    <span>Started: {formatDate(batch.started_at)}</span>
                  </>
                )}
                {batch.finished_at && (
                  <>
                    <span>•</span>
                    <span>Finished: {formatDate(batch.finished_at)}</span>
                  </>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusClass(
                  batch.status,
                )}`}
              >
                Crawl: {batch.status}
              </span>
              {batch.status === "cancelled" ? null : (
                <>
                  {(batch.status === "partial" || batch.status === "pending") && (
                    <button
                      onClick={handleResume}
                      disabled={actionLoading !== null}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm hover:bg-indigo-100 disabled:opacity-50"
                    >
                      {actionLoading === "resume" ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <RefreshCw size={13} />
                      )}
                      Resume Batch
                    </button>
                  )}
                  {(batch.status === "failed" || batch.status === "partial") && (
                    <button
                      onClick={handleRetry}
                      disabled={actionLoading !== null}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {actionLoading === "retry" ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <RefreshCw size={13} />
                      )}
                      Retry Failed
                    </button>
                  )}
                  {isRunning && (
                    <button
                      onClick={handleCancel}
                      disabled={actionLoading !== null}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
                    >
                      <XCircle size={13} /> Cancel
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </header>

        {/* High-Level Score & Crawl Metrics */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Overall Audit Score</p>
            <p className={`mt-2 text-2xl font-bold ${scoreColor(summary?.overall_score)}`}>
              {summary?.overall_score !== null && summary?.overall_score !== undefined
                ? `${Math.round(summary.overall_score)}%`
                : "—"}
            </p>
            <p className="mt-1 text-xs text-slate-400">Mean across 4 agents</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Crawled Success</p>
            <p className="mt-2 text-2xl font-bold text-emerald-600">{batch.completed_count}</p>
            <p className="mt-1 text-xs text-slate-400">of {batch.total_count} pages</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Failed Crawls</p>
            <p className="mt-2 text-2xl font-bold text-red-600">{batch.failed_count}</p>
            <p className="mt-1 text-xs text-slate-400">{batch.skipped_count} skipped</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Total Findings</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">{report.findings.length}</p>
            <p className="mt-1 text-xs text-slate-400">across audited targets</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Critical Issues</p>
            <p className="mt-2 text-2xl font-bold text-red-600">{severityCounts["critical"] ?? 0}</p>
            <p className="mt-1 text-xs text-slate-400">Urgent fix needed</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">High Issues</p>
            <p className="mt-2 text-2xl font-bold text-orange-600">{severityCounts["high"] ?? 0}</p>
            <p className="mt-1 text-xs text-slate-400">Opportunity blocks</p>
          </div>
        </section>

        {/* Extracted HTML Links & Navigation Graph Breakdown */}
        <section className="rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-50/70 to-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Link2 size={18} className="text-indigo-600" />
                <h2 className="font-bold text-slate-900">HTML Parser & Link Extraction Architecture</h2>
              </div>
              <p className="mt-0.5 text-xs text-slate-600">
                Summary of internal anchor links, outbound links, and image assets extracted directly from page DOMs.
              </p>
            </div>
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-bold text-indigo-800">
              {linkStats.totalLinks} Total Parsed Links
            </span>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs">
              <span className="text-xs font-medium text-slate-500">Internal Navigation Links</span>
              <p className="mt-1 text-xl font-bold text-slate-900">{linkStats.totalInternal}</p>
              <p className="mt-0.5 text-[11px] text-slate-400">same-domain anchor hops</p>
            </div>
            <div className="rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs">
              <span className="text-xs font-medium text-slate-500">External Outbound Links</span>
              <p className="mt-1 text-xl font-bold text-slate-900">{linkStats.totalExternal}</p>
              <p className="mt-0.5 text-[11px] text-slate-400">third-party destinations</p>
            </div>
            <div className="rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs">
              <span className="text-xs font-medium text-slate-500">Images & Media Resources</span>
              <p className="mt-1 text-xl font-bold text-slate-900">{linkStats.totalImages}</p>
              <p className="mt-0.5 text-[11px] text-slate-400">img tags evaluated for Alt text</p>
            </div>
            <div className="rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs">
              <span className="text-xs font-medium text-slate-500">Broken Link Detections</span>
              <p className="mt-1 text-xl font-bold text-red-600">{linkStats.totalBroken}</p>
              <p className="mt-0.5 text-[11px] text-slate-400">HTTP errors / broken links</p>
            </div>
          </div>
        </section>

        {/* Agent Performance Averages Bar */}
        {summary?.agent_averages && (
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                Agent Performance Averages
              </h2>
              <span className="text-xs text-slate-400">Weighted point averages</span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { key: "onpage", label: "On-Page SEO", icon: Sparkles, desc: "Titles, Headings, Meta" },
                { key: "technical", label: "Technical SEO", icon: CheckCircle2, desc: "Crawlability, HTTP, Timing" },
                { key: "ib_conversion", label: "Content & Conversion", icon: ShieldAlert, desc: "Content quality and conversion signals" },
                { key: "visibility", label: "Search Visibility", icon: TrendingUp, desc: "Indexing & Authority" },
              ].map(({ key, label, icon: Icon, desc }) => {
                const score = summary.agent_averages[key];
                return (
                  <div
                    key={key}
                    className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/70 p-3.5"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="grid size-8 place-items-center rounded-lg bg-white text-indigo-600 shadow-2xs">
                        <Icon size={16} />
                      </div>
                      <div>
                        <p className="text-xs font-bold text-slate-800">{label}</p>
                        <p className="text-[11px] text-slate-400">{desc}</p>
                      </div>
                    </div>
                    <span className={`text-base font-bold ${scoreColor(score)}`}>
                      {score !== null && score !== undefined ? `${Math.round(score)}%` : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* URLs That Need Immediate Attention */}
        {urgentTargets.length > 0 && (
          <section className="overflow-hidden rounded-2xl border border-red-200 bg-white shadow-sm">
            <div className="border-b border-red-100 bg-red-50/50 p-5">
              <div className="flex items-center gap-2 text-red-800">
                <ShieldAlert size={18} />
                <h2 className="font-bold">URLs Requiring Immediate Attention ({urgentTargets.length} pages)</h2>
              </div>
              <p className="mt-0.5 text-xs text-red-950/70">
                Targets that failed crawling, experienced partial agent evaluation, or scored below 60%.
              </p>
            </div>
            <div className="divide-y divide-slate-100">
              {urgentTargets.map((item) => {
                const scores = item.scores ?? {};
                return (
                  <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 p-4 hover:bg-slate-50/60">
                    <div className="max-w-2xl">
                      <p className="font-mono text-xs font-bold text-slate-900 truncate" title={item.submitted_url}>
                        {item.submitted_url}
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <span>HTTP {item.response_status ?? "Error"}</span>
                        <span>•</span>
                        <span className="text-red-600 font-semibold">
                          {item.error ? item.error : "Low evaluation score on primary SEO checks"}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="font-mono text-xs">
                        <span className={scoreColor(scores["onpage"])}>OP:{scores["onpage"] ? Math.round(scores["onpage"]) : "—"}%</span>{" "}
                        <span className={scoreColor(scores["ib_conversion"])}>Content:{scores["ib_conversion"] ? Math.round(scores["ib_conversion"]) : "—"}%</span>
                      </div>
                      <Link
                        href={`/batches/${batch.id}/targets/${item.id}`}
                        className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white shadow-2xs hover:bg-red-700"
                      >
                        Inspect Issue <ArrowRight size={13} />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Cross-Location Benchmark Matrix */}
        {locationComparison.length > 0 && (
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-5">
              <div className="flex items-center gap-2">
                <MapPin size={18} className="text-indigo-600" />
                <h2 className="font-bold text-slate-900">
                  Cross-Location SEO Benchmark ({locationComparison.length} Cities Audited)
                </h2>
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                Compare page performance across geographic landing pages to identify localized optimization gaps.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-5 py-3">Location</th>
                    <th className="px-4 py-3">URL</th>
                    <th className="px-3 py-3">On-Page</th>
                    <th className="px-3 py-3">Technical</th>
                    <th className="px-3 py-3">Content & CRO</th>
                    <th className="px-3 py-3">Parsed Links</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {locationComparison.map(({ target: t, location, scores }) => (
                    <tr key={t.id} className="hover:bg-slate-50/70">
                      <td className="px-5 py-3 font-bold text-slate-900">{location}</td>
                      <td className="max-w-xs break-all px-4 py-3 font-mono text-slate-500 truncate" title={t.submitted_url}>
                        {t.submitted_url}
                      </td>
                      <td className={`px-3 py-3 font-bold ${scoreColor(scores["onpage"])}`}>
                        {scores["onpage"] !== undefined && scores["onpage"] !== null ? `${Math.round(scores["onpage"])}%` : "—"}
                      </td>
                      <td className={`px-3 py-3 font-bold ${scoreColor(scores["technical"])}`}>
                        {scores["technical"] !== undefined && scores["technical"] !== null ? `${Math.round(scores["technical"])}%` : "—"}
                      </td>
                      <td className={`px-3 py-3 font-bold ${scoreColor(scores["ib_conversion"])}`}>
                        {scores["ib_conversion"] !== undefined && scores["ib_conversion"] !== null ? `${Math.round(scores["ib_conversion"])}%` : "—"}
                      </td>
                      <td className="px-3 py-3 text-slate-600 font-mono">
                        {(t.internal_link_count ?? 0) + (t.external_link_count ?? 0)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/batches/${batch.id}/targets/${t.id}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                        >
                          View <ExternalLink size={12} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Top Issues Across Batch */}
        {topIssues.length > 0 && (
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-5">
              <h2 className="font-bold text-slate-900">Executive Priority: Top Issues Across Batch</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Highest-severity findings aggregated across all audited pages, ranked by impact and frequency.
              </p>
            </div>
            <div className="divide-y divide-slate-100">
              {topIssues.map((issue) => {
                const isExpanded = selectedIssueId === issue.check_id;
                return (
                  <div key={issue.check_id} className="p-4 hover:bg-slate-50/50 sm:p-5">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-md border px-2 py-0.5 text-xs font-semibold capitalize ${severityClass(
                              issue.severity,
                            )}`}
                          >
                            {issue.severity}
                          </span>
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                            {issue.agent_id}
                          </span>
                          <h3 className="font-semibold text-slate-800">{issue.title}</h3>
                        </div>
                        {issue.why_it_matters && (
                          <p className="text-xs text-slate-500">
                            <strong className="text-slate-700">Why it matters:</strong> {issue.why_it_matters}
                          </p>
                        )}
                        {issue.recommendation && (
                          <p className="text-xs text-slate-600">
                            <strong className="text-indigo-600">Action:</strong> {issue.recommendation}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => setSelectedIssueId(isExpanded ? null : issue.check_id)}
                        className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
                      >
                        {issue.affected_count} {issue.affected_count === 1 ? "URL" : "URLs"} affected{" "}
                        {isExpanded ? "▲" : "▼"}
                      </button>
                    </div>

                    {isExpanded && (
                      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <p className="mb-1 text-xs font-semibold text-slate-700">Affected URLs:</p>
                        <ul className="space-y-1 font-mono text-xs text-slate-600">
                          {issue.affected_urls.map((url) => (
                            <li key={url} className="truncate">
                              • {url}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* URL Target Reports Table */}
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-bold text-slate-900">URL Inventory & Reports ({visibleTargets.length} of {report.targets.length})</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Detailed table showing crawl status, timing, parsed HTML links count, and scores.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter URL…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-8 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-xs outline-none focus:border-indigo-500 focus:bg-white"
                />
              </div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-700 outline-none focus:border-indigo-500"
              >
                <option value="all">All Crawl Status</option>
                <option value="completed">Crawl Completed</option>
                <option value="failed">Crawl Failed</option>
                <option value="skipped">Crawl Skipped</option>
              </select>
              <select
                value={analysisFilter}
                onChange={(e) => setAnalysisFilter(e.target.value)}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-700 outline-none focus:border-indigo-500"
              >
                <option value="all">All Analysis Status</option>
                <option value="completed">Analysis Completed</option>
                <option value="partial">Analysis Partial</option>
                <option value="failed">Analysis Failed</option>
                <option value="pending">Analysis Pending</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th
                    className="cursor-pointer px-4 py-3"
                    onClick={() => {
                      setSortField("position");
                      setSortAsc(!sortAsc);
                    }}
                  >
                    #
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3"
                    onClick={() => {
                      setSortField("url");
                      setSortAsc(!sortAsc);
                    }}
                  >
                    Target URL
                  </th>
                  <th
                    className="cursor-pointer px-3 py-3"
                    onClick={() => {
                      setSortField("http");
                      setSortAsc(!sortAsc);
                    }}
                  >
                    HTTP
                  </th>
                  <th
                    className="cursor-pointer px-3 py-3"
                    onClick={() => {
                      setSortField("timing");
                      setSortAsc(!sortAsc);
                    }}
                  >
                    Timing
                  </th>
                  <th className="px-3 py-3">Parsed Links</th>
                  <th className="px-3 py-3">Crawl</th>
                  <th className="px-3 py-3">Analysis</th>
                  <th className="px-3 py-3">Agent Scores</th>
                  <th className="px-4 py-3 text-right">Report</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibleTargets.map((targetItem: BatchTargetReport) => {
                  const scores = targetItem.scores ?? {};
                  const internalCount = targetItem.internal_link_count ?? 0;
                  const externalCount = targetItem.external_link_count ?? 0;
                  return (
                    <tr key={targetItem.id} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3.5 font-mono text-xs text-slate-400">
                        {targetItem.position + 1}
                      </td>
                      <td className="max-w-md px-4 py-3.5">
                        <span className="block truncate font-medium text-slate-900" title={targetItem.submitted_url}>
                          {targetItem.submitted_url}
                        </span>
                        {targetItem.final_url && targetItem.final_url !== targetItem.submitted_url && (
                          <span
                            className="block truncate text-xs text-slate-400"
                            title={`Redirected to: ${targetItem.final_url}`}
                          >
                            ↳ {targetItem.final_url}
                          </span>
                        )}
                        {targetItem.error && (
                          <span className="block truncate text-xs text-red-500" title={targetItem.error}>
                            Error: {targetItem.error}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3.5 font-mono text-xs text-slate-700">
                        {metric(targetItem.response_status)}
                      </td>
                      <td className="px-3 py-3.5 text-xs text-slate-500">
                        {targetItem.timing_ms !== null && targetItem.timing_ms !== undefined
                          ? `${Math.round(targetItem.timing_ms)}ms`
                          : "—"}
                      </td>
                      <td className="px-3 py-3.5 font-mono text-xs text-slate-600">
                        <span title="Internal links">{internalCount} int</span> ·{" "}
                        <span title="External links" className="text-slate-400">{externalCount} ext</span>
                      </td>
                      <td className="px-3 py-3.5">
                        <span
                          className={`inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold capitalize ${statusClass(
                            targetItem.status,
                          )}`}
                        >
                          {targetItem.status}
                        </span>
                      </td>
                      <td className="px-3 py-3.5">
                        <span
                          className={`inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold capitalize ${statusClass(
                            targetItem.analysis_status,
                          )}`}
                        >
                          {targetItem.analysis_status}
                        </span>
                      </td>
                      <td className="px-3 py-3.5 text-xs">
                        <div className="flex items-center gap-1.5 font-mono text-[11px]">
                          <span title="On-Page" className={scoreColor(scores["onpage"])}>
                            OP:
                            {scores["onpage"] !== undefined && scores["onpage"] !== null
                              ? `${Math.round(scores["onpage"])}%`
                              : "—"}
                          </span>
                          <span className="text-slate-300">|</span>
                          <span title="Technical" className={scoreColor(scores["technical"])}>
                            TC:
                            {scores["technical"] !== undefined && scores["technical"] !== null
                              ? `${Math.round(scores["technical"])}%`
                              : "—"}
                          </span>
                          <span className="text-slate-300">|</span>
                          <span title="Content & Conversion" className={scoreColor(scores["ib_conversion"])}>
                            Content:
                            {scores["ib_conversion"] !== undefined && scores["ib_conversion"] !== null
                              ? `${Math.round(scores["ib_conversion"])}%`
                              : "—"}
                          </span>
                          <span className="text-slate-300">|</span>
                          <span title="Visibility" className={scoreColor(scores["visibility"])}>
                            VS:
                            {scores["visibility"] !== undefined && scores["visibility"] !== null
                              ? `${Math.round(scores["visibility"])}%`
                              : "—"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <Link
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-indigo-600 shadow-2xs hover:bg-indigo-50"
                          href={`/batches/${batch.id}/targets/${targetItem.id}`}
                        >
                          Open <ExternalLink size={12} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
                {visibleTargets.length === 0 && (
                  <tr>
                    <td colSpan={9} className="p-8 text-center text-xs text-slate-500">
                      No targets match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Limitations Notice */}
        {report.limitations.length > 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-4 text-xs leading-relaxed text-amber-900">
            <div className="mb-1 flex items-center gap-1.5 font-semibold text-amber-950">
              <AlertTriangle size={14} /> Audit Limitations & Grounding Notice
            </div>
            {report.limitations.map((item) => (
              <p key={item}>• {item}</p>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
