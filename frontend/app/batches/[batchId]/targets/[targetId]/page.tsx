"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  Code,
  Compass,
  ExternalLink,
  FileText,
  Filter,
  Globe,
  HelpCircle,
  Image as ImageIcon,
  Info as InfoIcon,
  Layers,
  Link2,
  Loader2,
  Search,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";

import { getBatchTargetReport } from "@/lib/api";
import type { BatchAgentRun, BatchTargetReport } from "@/types/api";

function statusBadgeClass(status: string) {
  switch (status) {
    case "pass":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "warn":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "fail":
      return "bg-red-50 text-red-700 border-red-200";
    case "unknown":
      return "bg-slate-100 text-slate-600 border-slate-200";
    default:
      return "bg-slate-50 text-slate-500 border-slate-200";
  }
}

function severityBadgeClass(sev: string) {
  switch (sev) {
    case "critical":
      return "bg-red-100 text-red-800 border-red-200";
    case "high":
      return "bg-orange-100 text-orange-800 border-orange-200";
    case "medium":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "low":
      return "bg-blue-100 text-blue-800 border-blue-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
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

const AGENT_LABELS: Record<string, string> = {
  onpage: "On-Page SEO",
  technical: "Technical SEO",
  ib_conversion: "Content & Conversion",
  visibility: "Organic Visibility & Backlinks",
};

interface FindingItem {
  id: string;
  check_id: string;
  agent_id: string;
  title: string;
  status: string;
  severity: string;
  weight: number;
  points_earned: number | null;
  observed: string;
  expected: string;
  selector?: string | null;
  snippet_data?: {
    category?: string;
    business_relevance?: string;
    verification_steps?: string[];
  } | null;
  why_it_matters: string;
  recommendation: string;
  confidence: number;
}

type TargetTab =
  | "overview"
  | "links"
  | "onpage"
  | "technical"
  | "images"
  | "ib_content"
  | "conversion"
  | "visibility"
  | "findings"
  | "html";

export default function TargetReportPage() {
  return (
    <Suspense fallback={<main className="p-8 text-sm text-slate-500">Loading saved URL report…</main>}>
      <TargetReportContent />
    </Suspense>
  );
}

function TargetReportContent() {
  const params = useParams<{ batchId: string; targetId: string }>();
  const batchId = params.batchId;
  const targetId = Number(params.targetId);

  const [target, setTarget] = useState<BatchTargetReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Tab & filters
  const [activeTab, setActiveTab] = useState<TargetTab>("overview");
  const [selectedAgent, setSelectedAgent] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [linkFilter, setLinkFilter] = useState<"all" | "internal" | "external">("all");
  const [linkSearch, setLinkSearch] = useState<string>("");

  useEffect(() => {
    setLoading(true);
    getBatchTargetReport(batchId, targetId)
      .then((data) => setTarget(data))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load the URL report."))
      .finally(() => setLoading(false));
  }, [batchId, targetId]);

  // Extract all findings with parsed evidence
  const allFindings: FindingItem[] = useMemo(() => {
    if (!target) return [];
    const items: FindingItem[] = [];
    for (const run of target.agent_runs) {
      const findingsList = Array.isArray(run.result_json?.findings)
        ? (run.result_json.findings as Array<Record<string, unknown>>)
        : [];
      for (const f of findingsList) {
        const ev = (f.evidence ?? {}) as Record<string, unknown>;
        let snippetData: FindingItem["snippet_data"] = null;
        if (typeof ev.snippet === "string") {
          try {
            snippetData = JSON.parse(ev.snippet) as FindingItem["snippet_data"];
          } catch {
            // ignore JSON parse error on snippet
          }
        }
        items.push({
          id: String(f.id ?? f.check_id ?? Math.random()),
          check_id: String(f.check_id ?? ""),
          agent_id: run.agent_id,
          title: String(f.title ?? "Finding"),
          status: String(f.status ?? "unknown"),
          severity: String(f.severity ?? "low"),
          weight: Number(f.weight ?? 0),
          points_earned: typeof f.points_earned === "number" ? f.points_earned : null,
          observed: String(ev.observed ?? ""),
          expected: String(ev.expected ?? ""),
          selector: typeof ev.selector === "string" ? ev.selector : null,
          snippet_data: snippetData,
          why_it_matters: String(f.why_it_matters ?? ""),
          recommendation: String(f.recommendation ?? "No recommendation recorded."),
          confidence: Number(f.confidence ?? 1.0),
        });
      }
    }
    return items;
  }, [target]);

  const visibleFindings = useMemo(() => {
    return allFindings.filter((item) => {
      if (selectedAgent !== "all" && item.agent_id !== selectedAgent) return false;
      if (statusFilter === "issues" && item.status !== "fail" && item.status !== "warn") return false;
      if (statusFilter === "pass" && item.status !== "pass") return false;
      if (statusFilter === "unknown" && item.status !== "unknown" && item.status !== "not_applicable") return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = item.title.toLowerCase().includes(q);
        const matchRec = item.recommendation.toLowerCase().includes(q);
        const matchObs = item.observed.toLowerCase().includes(q);
        if (!matchTitle && !matchRec && !matchObs) return false;
      }
      return true;
    });
  }, [allFindings, selectedAgent, statusFilter, searchQuery]);

  // Executive summary grouping
  const passedFindings = useMemo(() => allFindings.filter((f) => f.status === "pass"), [allFindings]);
  const criticalFindings = useMemo(
    () => allFindings.filter((f) => f.severity === "critical" && (f.status === "fail" || f.status === "warn")),
    [allFindings],
  );
  const highFindings = useMemo(
    () => allFindings.filter((f) => f.severity === "high" && (f.status === "fail" || f.status === "warn")),
    [allFindings],
  );

  if (loading) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] p-8 text-slate-500">
        <div className="mx-auto flex max-w-5xl items-center gap-3">
          <Loader2 className="animate-spin text-indigo-600" size={20} />
          <span>Loading URL report…</span>
        </div>
      </main>
    );
  }

  if (error || !target) {
    return (
      <main className="min-h-screen bg-[#f7f8fa] p-8">
        <div className="mx-auto max-w-5xl">
          <Link href={`/batches/${batchId}`} className="text-sm font-semibold text-indigo-600 hover:text-indigo-800">
            <ArrowLeft className="mr-1 inline" size={15} /> Back to Batch
          </Link>
          <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-red-700">
            <AlertCircle className="mr-2 inline" size={18} />
            {error || "URL report not found."}
          </div>
        </div>
      </main>
    );
  }

  const evidence = (target.evidence ?? {}) as Record<string, unknown>;
  const rawLinks = Array.isArray(evidence.links) ? (evidence.links as Array<Record<string, unknown>>) : [];
  const rawImages = Array.isArray(evidence.images) ? (evidence.images as Array<Record<string, unknown>>) : [];
  const rawHeadings = Array.isArray(evidence.headings) ? (evidence.headings as Array<Record<string, unknown>>) : [];
  const rawForms = Array.isArray(evidence.forms) ? (evidence.forms as Array<Record<string, unknown>>) : [];
  const classification = evidence.page_classification as Record<string, unknown> | undefined;

  // Filtered links
  const visibleLinks = rawLinks.filter((l) => {
    const isInternal = Boolean(l.internal);
    if (linkFilter === "internal" && !isInternal) return false;
    if (linkFilter === "external" && isInternal) return false;
    if (linkSearch.trim()) {
      const q = linkSearch.toLowerCase();
      const hrefMatch = String(l.href ?? "").toLowerCase().includes(q);
      const textMatch = String(l.text ?? "").toLowerCase().includes(q);
      if (!hrefMatch && !textMatch) return false;
    }
    return true;
  });

  const unavailable = "Unavailable: metric not collected";

  return (
    <main className="min-h-screen bg-[#f8fafc] px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
          <Link href="/" className="hover:text-indigo-600">
            Home
          </Link>
          <span>/</span>
          <Link href={`/batches/${batchId}`} className="hover:text-indigo-600">
            Batch {batchId.slice(0, 8)}…
          </Link>
          <span>/</span>
          <span className="font-semibold text-slate-800">Target #{target.position + 1}</span>
        </div>

        {/* Header Hero Card */}
        <header className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-600">
                  URL Intelligence Report
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">
                  Target #{target.position + 1}
                </span>
              </div>
              <h1 className="mt-2 break-all text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
                {target.submitted_url}
              </h1>
              {target.normalized_url && target.normalized_url !== target.submitted_url && (
                <p className="mt-1 text-xs text-slate-500">
                  ↳ Normalized: <span className="font-mono">{target.normalized_url}</span>
                </p>
              )}
              {target.final_url && target.final_url !== target.submitted_url && (
                <p className="mt-1 text-xs text-amber-700">
                  ↳ Redirected to: <span className="font-mono">{target.final_url}</span>
                </p>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span>
                  HTTP Status:{" "}
                  <strong className={target.response_status === 200 ? "text-emerald-700" : "text-amber-700"}>
                    {target.response_status ?? "Error"}
                  </strong>
                </span>
                <span>•</span>
                <span>Content-Type: {target.content_type || (target.html ? "text/html" : "non-html")}</span>
                <span>•</span>
                <span>
                  Fetch Timing:{" "}
                  {target.timing_ms !== null && target.timing_ms !== undefined
                    ? `${Math.round(target.timing_ms)}ms`
                    : "—"}
                </span>
                <span>•</span>
                <span>HTML Size: {evidence.raw_html_size ? `${Math.round(Number(evidence.raw_html_size) / 1024)} KB` : "—"}</span>
                <span>•</span>
                <span>Attempts: <strong className="text-slate-700">{target.attempts ?? 1}</strong></span>
                <span>•</span>
                <span>
                  Broken Links:{" "}
                  <strong className={(target.broken_link_count ?? 0) > 0 ? "text-red-600 font-semibold" : "text-slate-700"}>
                    {target.broken_link_count ?? 0}
                  </strong>
                </span>
                {target.started_at && (
                  <>
                    <span>•</span>
                    <span>Started: {formatDate(target.started_at)}</span>
                  </>
                )}
                {target.completed_at && (
                  <>
                    <span>•</span>
                    <span>Completed: {formatDate(target.completed_at)}</span>
                  </>
                )}
              </div>
              {target.error && (
                <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800 flex items-start gap-2 shadow-2xs">
                  <ShieldAlert size={16} className="shrink-0 text-red-600 mt-0.5" />
                  <div>
                    <strong className="font-semibold">Target Processing Error:</strong>{" "}
                    <span className="font-mono text-[11px] break-all">{target.error}</span>
                  </div>
                </div>
              )}
            </div>

            <div className="flex flex-col items-end gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusBadgeClass(
                    target.status,
                  )}`}
                >
                  Crawl: {target.status}
                </span>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusBadgeClass(
                    target.analysis_status,
                  )}`}
                >
                  Analysis: {target.analysis_status}
                </span>
              </div>
              <a
                href={target.final_url || target.submitted_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
              >
                Visit Audited URL <ArrowUpRight size={13} />
              </a>
            </div>
          </div>
        </header>

        {/* Tab Navigation */}
        <nav className="mt-6 flex overflow-x-auto border-b border-slate-200 text-sm font-semibold text-slate-500">
          {[
            { id: "overview", label: "Executive Summary", icon: Sparkles },
            { id: "links", label: `Parsed HTML Links (${rawLinks.length})`, icon: Link2 },
            { id: "onpage", label: "On-Page SEO", icon: FileText },
            { id: "technical", label: "Technical SEO", icon: CheckCircle2 },
            { id: "images", label: `Images (${rawImages.length})`, icon: ImageIcon },
            { id: "ib_content", label: "Content Insights", icon: BookOpen },
            { id: "conversion", label: "Conversion (CRO)", icon: Zap },
            { id: "visibility", label: "Search & Backlinks", icon: TrendingUp },
            { id: "findings", label: `All Findings (${allFindings.length})`, icon: ShieldAlert },
            { id: "html", label: "HTML Source", icon: Code },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id as TargetTab)}
              className={`flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 transition ${
                activeTab === id
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"
              }`}
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        {/* TAB 1: EXECUTIVE SUMMARY */}
        {activeTab === "overview" && (
          <div className="mt-6 space-y-6">
            {/* Quick Metrics Bar */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Discovered HTML Links</p>
                <p className="mt-2 text-2xl font-bold text-slate-900">{rawLinks.length}</p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {target.internal_link_count} internal · {target.external_link_count} external
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Visible Word Count</p>
                <p className="mt-2 text-2xl font-bold text-slate-900">
                  {typeof evidence.visible_text_word_count === "number" ? evidence.visible_text_word_count : "—"}
                </p>
                <p className="mt-0.5 text-xs text-slate-400">body copy depth</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Critical & High Issues</p>
                <p className="mt-2 text-2xl font-bold text-red-600">
                  {criticalFindings.length + highFindings.length}
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {criticalFindings.length} critical · {highFindings.length} high
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-medium text-slate-500">Passed Checks</p>
                <p className="mt-2 text-2xl font-bold text-emerald-600">{passedFindings.length}</p>
                <p className="mt-0.5 text-xs text-slate-400">confirmed compliant rules</p>
              </div>
            </div>

            {/* 4 Agent Score Cards */}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                SEO Evaluation Agent Scores
              </h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {target.agent_runs.map((run: BatchAgentRun) => {
                  const res = (run.result_json ?? {}) as Record<string, unknown>;
                  const scoreObj = (res.score ?? {}) as Record<string, unknown>;
                  const percent = typeof scoreObj.percent === "number" ? scoreObj.percent : null;
                  const coverage = typeof scoreObj.coverage_percent === "number" ? scoreObj.coverage_percent : null;
                  const earned = typeof scoreObj.earned === "number" ? scoreObj.earned : null;
                  const applicable = typeof scoreObj.applicable_weight === "number" ? scoreObj.applicable_weight : null;

                  return (
                    <div key={run.agent_id} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-bold text-slate-800">
                          {AGENT_LABELS[run.agent_id] ?? run.agent_id}
                        </p>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize ${statusBadgeClass(
                            run.status,
                          )}`}
                        >
                          {run.status}
                        </span>
                      </div>
                      <div className="mt-3 flex items-baseline gap-2">
                        <span className={`text-3xl font-extrabold ${scoreColor(percent)}`}>
                          {percent !== null ? `${Math.round(percent)}%` : "—"}
                        </span>
                        {earned !== null && applicable !== null && (
                          <span className="text-xs text-slate-400">
                            ({earned.toFixed(1)} / {applicable.toFixed(1)} pts)
                          </span>
                        )}
                      </div>
                      <div className="mt-2 space-y-1 text-xs text-slate-500">
                        <p>Coverage: {coverage !== null ? `${Math.round(coverage)}%` : "—"} applicable</p>
                        <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400">
                          <span>Attempt: {run.attempt ?? 1}</span>
                          <span>{run.finding_keys?.length ?? 0} rules</span>
                        </div>
                        {run.started_at && (
                          <p className="text-[10px] text-slate-400">Started: {formatDate(run.started_at)}</p>
                        )}
                        {run.finished_at && (
                          <p className="text-[10px] text-slate-400">Finished: {formatDate(run.finished_at)}</p>
                        )}
                      </div>
                      {run.error && (
                        <div className="mt-2 rounded bg-red-50 p-2 text-[11px] text-red-700 border border-red-100">
                          <strong>Error:</strong> {run.error}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            {/* What's Working Well vs Critical Gaps */}
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Working Well */}
              <section className="rounded-2xl border border-emerald-100 bg-emerald-50/40 p-6 shadow-sm">
                <div className="flex items-center gap-2 text-emerald-800">
                  <CheckCircle2 size={18} />
                  <h3 className="font-bold">What Is Working Well ({passedFindings.length} checks)</h3>
                </div>
                <p className="mt-1 text-xs text-emerald-950/70">
                  Evidence-backed strengths observed on this page by the crawl and agent rules.
                </p>
                <div className="mt-4 space-y-2.5">
                  {passedFindings.slice(0, 6).map((item) => (
                    <div key={item.id} className="rounded-xl border border-emerald-200/60 bg-white p-3 text-xs">
                      <p className="font-semibold text-slate-900">{item.title}</p>
                      {item.observed && (
                        <p className="mt-1 text-slate-500">
                          <strong className="text-emerald-700">Observed:</strong> {item.observed}
                        </p>
                      )}
                    </div>
                  ))}
                  {passedFindings.length === 0 && (
                    <p className="text-xs text-slate-500">No passing checks observed yet.</p>
                  )}
                </div>
              </section>

              {/* Critical & High Issues */}
              <section className="rounded-2xl border border-red-100 bg-red-50/40 p-6 shadow-sm">
                <div className="flex items-center gap-2 text-red-800">
                  <ShieldAlert size={18} />
                  <h3 className="font-bold">
                    Highest Priority Problems ({criticalFindings.length + highFindings.length} issues)
                  </h3>
                </div>
                <p className="mt-1 text-xs text-red-950/70">
                  Actionable defects requiring immediate engineering or editorial intervention.
                </p>
                <div className="mt-4 space-y-2.5">
                  {[...criticalFindings, ...highFindings].slice(0, 6).map((item) => (
                    <div key={item.id} className="rounded-xl border border-red-200/70 bg-white p-3 text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${severityBadgeClass(
                            item.severity,
                          )}`}
                        >
                          {item.severity}
                        </span>
                        <p className="font-semibold text-slate-900">{item.title}</p>
                      </div>
                      {item.why_it_matters && (
                        <p className="mt-1 text-slate-600">
                          <strong className="text-slate-800">Why it matters:</strong> {item.why_it_matters}
                        </p>
                      )}
                      {item.recommendation && (
                        <p className="mt-1 text-indigo-700">
                          <strong>Action:</strong> {item.recommendation}
                        </p>
                      )}
                    </div>
                  ))}
                  {criticalFindings.length + highFindings.length === 0 && (
                    <p className="text-xs text-emerald-700">No critical or high issues found on this page!</p>
                  )}
                </div>
              </section>
            </div>
          </div>
        )}

        {/* TAB 2: PARSED HTML LINKS */}
        {activeTab === "links" && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Parsed HTML Anchor Links ({rawLinks.length} total)
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  Links extracted from the page DOM using the HTML parser. Used to map site hierarchy and internal link flow.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search link URL or anchor text…"
                    value={linkSearch}
                    onChange={(e) => setLinkSearch(e.target.value)}
                    className="h-8 rounded-lg border border-slate-200 bg-slate-50 pl-7 pr-3 text-xs outline-none focus:border-indigo-500 focus:bg-white"
                  />
                </div>
                <div className="flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs font-semibold">
                  <button
                    onClick={() => setLinkFilter("all")}
                    className={`rounded-md px-2.5 py-1 ${
                      linkFilter === "all" ? "bg-white text-indigo-600 shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    All ({rawLinks.length})
                  </button>
                  <button
                    onClick={() => setLinkFilter("internal")}
                    className={`rounded-md px-2.5 py-1 ${
                      linkFilter === "internal" ? "bg-white text-indigo-600 shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    Internal ({target.internal_link_count})
                  </button>
                  <button
                    onClick={() => setLinkFilter("external")}
                    className={`rounded-md px-2.5 py-1 ${
                      linkFilter === "external" ? "bg-white text-indigo-600 shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    External ({target.external_link_count})
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5">Destination URL (href)</th>
                    <th className="px-4 py-2.5">Anchor Text</th>
                    <th className="px-3 py-2.5">Scope</th>
                    <th className="px-3 py-2.5">Rel</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {visibleLinks.map((link, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/70">
                      <td className="max-w-md break-all px-4 py-2.5 font-mono text-slate-800">
                        <a
                          href={String(link.href ?? "")}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:text-indigo-600 hover:underline"
                        >
                          {String(link.href ?? "")}
                        </a>
                      </td>
                      <td className="px-4 py-2.5 font-medium text-slate-700">
                        {String(link.text ?? "").trim() || <span className="italic text-slate-400">&lt;empty&gt;</span>}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            link.internal
                              ? "bg-indigo-50 text-indigo-700"
                              : "bg-amber-50 text-amber-700"
                          }`}
                        >
                          {link.internal ? "Internal" : "External"}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-slate-500">
                        {String(link.rel ?? "") || "—"}
                      </td>
                    </tr>
                  ))}
                  {visibleLinks.length === 0 && (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-slate-400">
                        No links match this filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* TAB 3: ON-PAGE SEO */}
        {activeTab === "onpage" && (
          <div className="mt-6 space-y-6">
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-base font-bold text-slate-900">On-Page Metadata & Content Structure</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Core indexability signals, metadata lengths, canonical declaration, and heading hierarchy.
              </p>

              <div className="mt-6 divide-y divide-slate-100">
                {/* Title */}
                <div className="py-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Page Title</span>
                    <span className="text-xs text-slate-400">
                      {String(evidence.parsed_title ?? "").length} characters (recommended: 30–65)
                    </span>
                  </div>
                  <p className="mt-1 font-semibold text-slate-900">
                    {String(evidence.parsed_title ?? unavailable)}
                  </p>
                </div>

                {/* Canonical */}
                <div className="py-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Canonical Tag</span>
                    <span className="text-xs text-slate-400">Self-referential check</span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-slate-800">
                    {String(evidence.canonical ?? "No canonical tag found")}
                  </p>
                </div>

                {/* Headings Hierarchy */}
                <div className="py-4">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Headings Distribution ({rawHeadings.length} found)
                  </span>
                  <div className="mt-3 space-y-2">
                    {rawHeadings.map((h, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-xs">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono font-bold text-slate-700">
                          {String(h.level ?? "H").toUpperCase()}
                        </span>
                        <span className="text-slate-800">{String(h.text ?? "")}</span>
                      </div>
                    ))}
                    {rawHeadings.length === 0 && (
                      <p className="text-xs text-amber-600">No heading tags (H1–H6) detected in page HTML.</p>
                    )}
                  </div>
                </div>

                {/* Meta Tags */}
                <div className="py-4">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Key Meta Directives
                  </span>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2 text-xs">
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="font-bold text-slate-600">Viewport:</span>{" "}
                      <span className="font-mono text-slate-800">{String(evidence.viewport ?? "Not declared")}</span>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="font-bold text-slate-600">Language:</span>{" "}
                      <span className="font-mono text-slate-800">{String(evidence.lang ?? "Not declared")}</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}

        {/* TAB 4: TECHNICAL SEO */}
        {activeTab === "technical" && (
          <div className="mt-6 space-y-6">
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-base font-bold text-slate-900">Technical SEO & Server Diagnostics</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl bg-slate-50 p-4">
                  <span className="text-xs font-medium text-slate-500">Response Code</span>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{target.response_status ?? "Error"}</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <span className="text-xs font-medium text-slate-500">Fetch Timing</span>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {target.timing_ms !== null && target.timing_ms !== undefined
                      ? `${Math.round(target.timing_ms)}ms`
                      : "—"}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <span className="text-xs font-medium text-slate-500">Raw HTML Payload</span>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {evidence.raw_html_size ? `${Math.round(Number(evidence.raw_html_size) / 1024)} KB` : "—"}
                  </p>
                </div>
              </div>

              {/* Redirect Chain */}
              <div className="mt-6 border-t border-slate-100 pt-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Redirect Chain</h3>
                {Array.isArray(evidence.redirect_chain) && evidence.redirect_chain.length > 0 ? (
                  <ul className="mt-2 space-y-1 font-mono text-xs text-slate-700">
                    {evidence.redirect_chain.map((hop, idx) => (
                      <li key={idx} className="flex items-center gap-2">
                        <span className="text-slate-400">#{idx + 1}</span>
                        <span>{String(hop)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">Direct response (0 redirects).</p>
                )}
              </div>
            </section>
          </div>
        )}

        {/* TAB 5: IMAGES */}
        {activeTab === "images" && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900">Parsed Images & Alt Attributes ({rawImages.length})</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Evaluates accessibility, image SEO, and missing descriptive alternative text.
            </p>

            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5">Image Source (src)</th>
                    <th className="px-4 py-2.5">Alt Attribute</th>
                    <th className="px-3 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rawImages.map((img, idx) => {
                    const hasAlt = Boolean(String(img.alt ?? "").trim());
                    return (
                      <tr key={idx} className="hover:bg-slate-50/70">
                        <td className="max-w-md break-all px-4 py-2.5 font-mono text-slate-800">
                          {String(img.src ?? "")}
                        </td>
                        <td className="px-4 py-2.5 text-slate-700">
                          {String(img.alt ?? "").trim() || <span className="italic text-slate-400">&lt;empty&gt;</span>}
                        </td>
                        <td className="px-3 py-2.5">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                              hasAlt ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                            }`}
                          >
                            {hasAlt ? "Alt present" : "Missing Alt"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {rawImages.length === 0 && (
                    <tr>
                      <td colSpan={3} className="p-8 text-center text-slate-400">
                        No images found in page HTML.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* TAB 6: IB CURRICULUM & CRO */}
        {activeTab === "ib_content" && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900">Content & Authority Alignment</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Evaluates page content, clarity, authority, and conversion signals recorded by the agents.
            </p>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs">
                <span className="font-bold text-slate-700">Detected Classification</span>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {classification?.label ? String(classification.label) : "Unclassified page"}
                </p>
                <p className="mt-0.5 text-slate-500">
                  Confidence: {classification?.confidence ? `${Math.round(Number(classification.confidence) * 100)}%` : "High"}
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs">
                <span className="font-bold text-slate-700">Target Location Specificity</span>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {target.submitted_url.match(/(?:cities|countries)\/([^/?#]+)/i)?.[1]?.replace(/-/g, " ") ?? "Global"}
                </p>
                <p className="mt-0.5 text-slate-500">Derived from URL slug and page content</p>
              </div>
            </div>

            {/* IB Agent Findings */}
            <div className="mt-6">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Content and subject-matter findings
              </h3>
              <div className="mt-3 space-y-3">
                {allFindings
                  .filter((f) => f.agent_id === "ib_conversion")
                  .map((finding) => (
                    <div key={finding.id} className="rounded-xl border border-slate-200 bg-white p-4 text-xs shadow-2xs">
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${severityBadgeClass(
                            finding.severity,
                          )}`}
                        >
                          {finding.severity}
                        </span>
                        <h4 className="font-semibold text-slate-900">{finding.title}</h4>
                      </div>
                      {finding.observed && (
                        <p className="mt-2 text-slate-600">
                          <strong className="text-slate-800">Observed:</strong> {finding.observed}
                        </p>
                      )}
                      {finding.why_it_matters && (
                        <p className="mt-1 text-slate-600">
                          <strong className="text-slate-800">Why it matters:</strong> {finding.why_it_matters}
                        </p>
                      )}
                      {finding.recommendation && (
                        <p className="mt-1 text-indigo-700">
                          <strong>Action:</strong> {finding.recommendation}
                        </p>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          </section>
        )}

        {/* TAB 7: CONVERSION & SALES */}
        {activeTab === "conversion" && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900">Sales & Conversion Optimization (CRO)</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Evaluates conversion paths, call-to-actions, WhatsApp/phone links, and form presence.
            </p>

            <div className="mt-6 grid gap-4 sm:grid-cols-3 text-xs">
              <div className="rounded-xl bg-slate-50 p-4">
                <span className="font-medium text-slate-500">Lead Capture Forms</span>
                <p className="mt-1 text-2xl font-bold text-slate-900">{rawForms.length}</p>
                <p className="mt-0.5 text-slate-400">forms detected in HTML</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <span className="font-medium text-slate-500">Enquiry Links</span>
                <p className="mt-1 text-2xl font-bold text-slate-900">
                  {rawLinks.filter((l) => /whatsapp|contact|phone|tel:/i.test(String(l.href ?? ""))).length}
                </p>
                <p className="mt-0.5 text-slate-400">WhatsApp / call / contact links</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <span className="font-medium text-slate-500">Internal Conversion Paths</span>
                <p className="mt-1 text-2xl font-bold text-slate-900">{target.internal_link_count}</p>
                <p className="mt-0.5 text-slate-400">internal links to guide users</p>
              </div>
            </div>
          </section>
        )}

        {/* TAB 8: SEARCH VISIBILITY */}
        {activeTab === "visibility" && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900">Search Visibility & External Integrations</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Google Search Console (GSC), Google Analytics 4 (GA4), and Backlink provider metrics.
            </p>

            <div className="mt-6 space-y-4">
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-xs text-amber-900">
                <div className="flex items-center gap-1.5 font-bold">
                  <AlertTriangle size={15} /> External Integration Status Notice
                </div>
                <p className="mt-1 leading-relaxed">
                  External search and backlink metrics (GSC clicks, GA4 sessions, Majestic/Ahrefs backlinks) are only
                  rendered when live authorized credentials or datasets are connected. RankPilot strictly avoids
                  inventing mock or synthetic external traffic metrics.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-3 text-xs">
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <span className="font-bold text-slate-700">Google Search Console</span>
                  <p className="mt-2 text-slate-500">Status: Requires API credentials</p>
                  <p className="mt-0.5 text-slate-400">Clicks, impressions, CTR, average position</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <span className="font-bold text-slate-700">Google Analytics 4</span>
                  <p className="mt-2 text-slate-500">Status: Requires Property ID</p>
                  <p className="mt-0.5 text-slate-400">Sessions, engagement rate, conversions</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <span className="font-bold text-slate-700">Backlinks Provider</span>
                  <p className="mt-2 text-slate-500">Status: Requires API key</p>
                  <p className="mt-0.5 text-slate-400">Referring domains, backlinks, anchor text</p>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* TAB 9: ALL DIAGNOSTIC FINDINGS */}
        {activeTab === "findings" && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 border-b border-slate-200 pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Diagnostic Findings ({visibleFindings.length} of {allFindings.length})
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  Filter by agent profile, pass/fail status, or search for specific terms.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search findings…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-8 rounded-lg border border-slate-200 bg-slate-50 pl-7 pr-3 text-xs outline-none focus:border-indigo-500 focus:bg-white"
                  />
                </div>
                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-700 outline-none focus:border-indigo-500"
                >
                  <option value="all">All Agents</option>
                  <option value="onpage">On-Page SEO</option>
                  <option value="technical">Technical SEO</option>
                  <option value="ib_conversion">Content & Conversion</option>
                  <option value="visibility">Visibility</option>
                </select>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-700 outline-none focus:border-indigo-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="issues">Issues Only (Fail & Warn)</option>
                  <option value="pass">Passed Only</option>
                </select>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              {visibleFindings.map((finding) => (
                <div
                  key={finding.id}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded border px-2 py-0.5 text-xs font-bold uppercase ${severityBadgeClass(
                            finding.severity,
                          )}`}
                        >
                          {finding.severity}
                        </span>
                        <span
                          className={`rounded border px-2 py-0.5 text-xs font-semibold capitalize ${statusBadgeClass(
                            finding.status,
                          )}`}
                        >
                          {finding.status}
                        </span>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                          {AGENT_LABELS[finding.agent_id] ?? finding.agent_id}
                        </span>
                        <h3 className="font-bold text-slate-900">{finding.title}</h3>
                      </div>
                    </div>
                    {finding.points_earned !== null && (
                      <span className="text-xs font-mono font-semibold text-slate-500">
                        {finding.points_earned.toFixed(1)} / {finding.weight.toFixed(1)} pts
                      </span>
                    )}
                  </div>

                  <div className="mt-3 grid gap-3 rounded-lg bg-slate-50 p-3 text-xs sm:grid-cols-2">
                    <div>
                      <span className="font-bold text-slate-700">Observed Evidence:</span>
                      <p className="mt-0.5 text-slate-600">{finding.observed || "No observation recorded."}</p>
                    </div>
                    <div>
                      <span className="font-bold text-slate-700">Expected Condition:</span>
                      <p className="mt-0.5 text-slate-600">{finding.expected || "Standard compliant condition."}</p>
                    </div>
                  </div>

                  {finding.selector && (
                    <p className="mt-2 text-xs font-mono text-slate-500">
                      DOM Selector: <span className="text-slate-700">{finding.selector}</span>
                    </p>
                  )}

                  {finding.why_it_matters && (
                    <p className="mt-2 text-xs text-slate-600">
                      <strong className="text-slate-800">Why it matters:</strong> {finding.why_it_matters}
                    </p>
                  )}

                  {finding.recommendation && (
                    <div className="mt-2 rounded-lg border border-indigo-100 bg-indigo-50/50 p-2.5 text-xs text-indigo-900">
                      <strong>Recommended Fix:</strong> {finding.recommendation}
                    </div>
                  )}
                </div>
              ))}
              {visibleFindings.length === 0 && (
                <div className="py-12 text-center text-sm text-slate-400">
                  No findings match the selected filters.
                </div>
              )}
            </div>
          </section>
        )}

        {/* TAB: HTML & DOCUMENT DETAILS */}
        {activeTab === "html" && (
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">Document Content & Crawl Capture</h2>
                <p className="text-xs text-slate-500">
                  Document observations recorded during the crawl{" "}
                  {evidence.raw_html_size
                    ? `(${Math.round(Number(evidence.raw_html_size) / 1024)} KB, ${Number(evidence.raw_html_size).toLocaleString()} bytes)`
                    : "(0 KB)"}.
                </p>
              </div>
              {Boolean(evidence.visible_text_preview) && (
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(String(evidence.visible_text_preview || ""));
                  }}
                  className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100"
                >
                  Copy Text Preview
                </button>
              )}
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs">
                <span className="font-semibold text-slate-500">HTML Format Detected:</span>
                <p className="mt-1 font-bold text-slate-800">{target.html ? "Yes (text/html)" : "No (non-html)"}</p>
              </div>
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs">
                <span className="font-semibold text-slate-500">Document Size:</span>
                <p className="mt-1 font-bold text-slate-800">
                  {evidence.raw_html_size ? `${Math.round(Number(evidence.raw_html_size) / 1024)} KB` : "—"}
                </p>
              </div>
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs">
                <span className="font-semibold text-slate-500">Extracted Word Count:</span>
                <p className="mt-1 font-bold text-slate-800">
                  {typeof evidence.visible_text_word_count === "number" ? `${evidence.visible_text_word_count} words` : "—"}
                </p>
              </div>
            </div>

            {evidence.visible_text_preview ? (
              <div className="mt-4">
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                  Visible Body Text Preview
                </h3>
                <div className="max-h-[500px] overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-200 shadow-inner">
                  <pre className="whitespace-pre-wrap break-all leading-relaxed">
                    {String(evidence.visible_text_preview)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="mt-4 py-8 text-center text-sm text-slate-400">
                No visible text preview recorded for this target.
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
