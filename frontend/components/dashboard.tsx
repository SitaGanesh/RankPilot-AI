"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  CircleHelp,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileCode,
  FileSpreadsheet,
  FileText,
  Filter,
  Globe2,
  HelpCircle,
  Image as ImageIcon,
  Layers,
  LayoutGrid,
  Link2,
  Loader2,
  Network,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Video,
  XCircle,
  Zap,
} from "lucide-react";

import {
  createAudit,
  createBatch,
  getAgents,
  getAuditReport,
  getAuditReportCsvUrl,
  getAuditStatus,
  getBusinessReport,
  getCrawlURLs,
  getEvaluationReport,
  getProviderStatus,
  getResourceGraph,
  runAgent,
} from "@/lib/api";
import type {
  Agent,
  AuditReportData,
  AuditStatusResponse,
  BusinessReport,
  CrawlStatus,
  CrawlURL,
  ProviderStatus,
  ResourceGraph,
  ResourceGraphMetrics,
  ResourceGraphNode,
  ResourceNodeDetails,
  ResourceCheckStatus,
} from "@/types/api";

import { StatusBadge } from "./status-badge";
import { ResourceGraphView } from "./resource-graph";
import { NodeInspector } from "./node-inspector";

const terminalStatuses = new Set(["completed", "failed"]);
const crawlFilters: Array<{ value: CrawlStatus | "all"; label: string }> = [
  { value: "all", label: "All URLs" },
  { value: "pending", label: "Pending" },
  { value: "fetching", label: "Fetching" },
  { value: "fetched", label: "Fetched" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function validateURL(value: string) {
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

export function Dashboard() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [audit, setAudit] = useState<AuditStatusResponse | null>(null);
  const [urls, setUrls] = useState<CrawlURL[]>([]);
  const [resourceGraph, setResourceGraph] = useState<ResourceGraph | null>(null);
  const [selectedNode, setSelectedNode] = useState<ResourceGraphNode | null>(null);

  const [businessReport, setBusinessReport] = useState<BusinessReport | null>(null);
  const [evaluationReport, setEvaluationReport] = useState<BusinessReport | null>(null);
  const [auditReport, setAuditReport] = useState<AuditReportData | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>("onpage");
  const [agentRunning, setAgentRunning] = useState(false);

  const [activeTab, setActiveTab] = useState<
    "graph" | "audit" | "links" | "resources" | "business" | "evaluation" | "crawl"
  >("graph");

  const [filter, setFilter] = useState<CrawlStatus | "all">("all");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [batchCreating, setBatchCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Load registered agents and provider status on mount
  useEffect(() => {
    getAgents().then(setAgents).catch(() => { });
    getProviderStatus().then(setProviderStatus).catch(() => { });
  }, []);

  const discoveredHtmlPages = useMemo(() => {
    return urls.filter((u) => u.resource_type === "page").map((u) => u.url);
  }, [urls]);

  async function handleBatchAuditDiscovered() {
    if (discoveredHtmlPages.length === 0) return;
    setBatchCreating(true);
    setError(null);
    try {
      const idempotencyKey = `batch-discovered-${Date.now()}`;
      const batch = await createBatch(discoveredHtmlPages, idempotencyKey, true);
      router.push(`/batches/${encodeURIComponent(batch.id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch batch audit on discovered links.");
      setBatchCreating(false);
    }
  }

  const refresh = useCallback(async (auditId: string) => {
    const [status, inventory] = await Promise.all([
      getAuditStatus(auditId),
      getCrawlURLs(auditId),
    ]);
    setAudit(status);
    setUrls(inventory);

    // Fetch resource graph
    try {
      const graph = await getResourceGraph(auditId);
      setResourceGraph(graph);
    } catch {
      // Graph might be building
    }

    if (status.status === "collected" || status.status === "completed" || status.status === "running") {
      try {
        setBusinessReport(await getBusinessReport(auditId));
      } catch {
        setBusinessReport(null);
      }
      try {
        setEvaluationReport(await getEvaluationReport(auditId));
      } catch {
        setEvaluationReport(null);
      }
      try {
        const report = await getAuditReport(auditId);
        setAuditReport(report);
        if (report.resource_graph) {
          setResourceGraph(report.resource_graph);
        }
      } catch {
        // Report not generated yet
      }
    }
    return status;
  }, []);

  useEffect(() => {
    if (!audit || terminalStatuses.has(audit.status)) return;
    const timer = window.setInterval(async () => {
      try {
        await refresh(audit.id);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Unable to refresh audit progress.");
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [audit, refresh]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = validateURL(input.trim());
    if (!normalized) {
      setValidationError("Enter a valid HTTP or HTTPS website URL.");
      return;
    }
    setValidationError(null);
    setError(null);
    setLoading(true);
    setSelectedNode(null);
    setResourceGraph(null);
    setAuditReport(null);
    setBusinessReport(null);
    setEvaluationReport(null);
    try {
      const created = await createAudit(normalized);
      await refresh(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start the audit.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAuditUrl(targetUrl: string) {
    const normalized = validateURL(targetUrl.trim());
    if (!normalized) return;
    setInput(normalized);
    setValidationError(null);
    setError(null);
    setLoading(true);
    setSelectedNode(null);
    setResourceGraph(null);
    setAuditReport(null);
    setBusinessReport(null);
    setEvaluationReport(null);
    try {
      const created = await createAudit(normalized);
      await refresh(created.id);
      setActiveTab("graph");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start deep audit on this page.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRefresh() {
    if (!audit) return;
    setRefreshing(true);
    setError(null);
    try {
      await refresh(audit.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to refresh audit progress.");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleRunAgent(agentId: string) {
    if (!audit) return;
    setAgentRunning(true);
    setError(null);
    try {
      await runAgent(audit.id, agentId);
      await refresh(audit.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to execute ${agentId} agent.`);
    } finally {
      setAgentRunning(false);
    }
  }

  // Explicit, disentangled metric counts
  const metrics = useMemo<ResourceGraphMetrics>(() => {
    if (resourceGraph?.metrics) {
      return resourceGraph.metrics;
    }
    if (audit?.metrics) {
      return audit.metrics;
    }
    const pages = urls.filter((u) => u.resource_type === "page");
    const internals = pages.filter((u) => u.discovery_source === "internal_link");
    const externals = pages.filter((u) => u.discovery_source !== "internal_link");
    const resources = urls.filter((u) => u.resource_type !== "page");
    return {
      deep_pages_crawled: audit?.status === "completed" || audit?.status === "collected" ? 1 : 0,
      discovered_html_links: pages.length,
      internal_links_count: internals.length,
      external_links_count: externals.length,
      unique_resource_urls: resources.length,
      images_count: resources.filter((r) => r.resource_type === "media").length,
      scripts_count: 0,
      stylesheets_count: 0,
      media_count: 0,
      link_check_attempts: Math.max(0, urls.length - 1),
      successfully_checked_resources: urls.filter((u) => u.status === "fetched").length,
      failed_resources_count: urls.filter((u) => u.status === "failed").length,
      redirect_count: 0,
    };
  }, [resourceGraph, audit, urls]);

  // Derived link nodes for the Links tab
  const linkNodes = useMemo<ResourceGraphNode[]>(() => {
    const graph = resourceGraph || auditReport?.resource_graph;
    if (graph?.nodes) {
      return graph.nodes.filter(
        (n) => n.node_type === "linked_page" && !n.deeply_audited
      );
    }
    return urls
      .filter((u) => u.resource_type === "page" && u.depth > 0)
      .map((u) => ({
        id: u.url,
        url: u.url,
        label: u.url,
        node_type: "linked_page" as const,
        status: (u.status === "fetched" ? "available" : u.status === "failed" ? "client_error" : "could_not_be_checked") as ResourceCheckStatus,
        http_status: u.response_status,
        final_url: u.final_url || u.url,
        redirect_chain: [],
        content_type: "text/html",
        is_internal: u.discovery_source === "internal_link",
        deeply_audited: false,
        details: {} as ResourceNodeDetails,
        issues: [],
        recommendations: [],
      }));
  }, [resourceGraph, auditReport, urls]);

  // Derived asset nodes for the Assets tab
  const imageNodes = useMemo<ResourceGraphNode[]>(() => {
    const graph = resourceGraph || auditReport?.resource_graph;
    if (graph?.nodes) {
      return graph.nodes.filter((n) => n.node_type === "image" || n.node_type === "media");
    }
    return urls
      .filter((u) => u.resource_type === "media")
      .map((u) => ({
        id: u.url,
        url: u.url,
        label: u.url,
        node_type: "image" as const,
        status: (u.status === "fetched" ? "available" : u.status === "failed" ? "client_error" : "could_not_be_checked") as ResourceCheckStatus,
        http_status: u.response_status,
        final_url: u.url,
        redirect_chain: [],
        content_type: "",
        is_internal: true,
        deeply_audited: false,
        details: {} as ResourceNodeDetails,
        issues: [],
        recommendations: [],
      }));
  }, [resourceGraph, auditReport, urls]);

  const scriptCssNodes = useMemo<ResourceGraphNode[]>(() => {
    if (resourceGraph?.nodes) {
      return resourceGraph.nodes.filter(
        (n) => n.node_type === "script" || n.node_type === "stylesheet"
      );
    }
    return [];
  }, [resourceGraph]);

  const visibleURLs = useMemo(
    () => (filter === "all" ? urls : urls.filter((item) => item.status === filter)),
    [filter, urls],
  );

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-950">
      {/* Node Inspector Drawer */}
      {selectedNode && (
        <NodeInspector
          node={selectedNode}
          primaryUrl={audit?.url || input}
          onClose={() => setSelectedNode(null)}
          onAuditUrl={handleAuditUrl}
        />
      )}

      {/* Sidebar Navigation */}
      <aside className="fixed inset-y-0 hidden w-64 border-r border-slate-200 bg-white px-5 py-7 lg:block">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <Sparkles size={18} />
          </div>
          <div>
            <p className="text-sm font-bold tracking-tight">RankPilot</p>
            <p className="text-xs text-slate-500">SEO Intelligence</p>
          </div>
        </div>

        <nav className="mt-12 space-y-1 text-sm">
          <a
            className="flex items-center gap-3 rounded-lg bg-indigo-50 px-3 py-2.5 font-semibold text-indigo-700"
            href="#dashboard"
          >
            <Globe2 size={17} /> Single-URL Audit
          </a>
          <Link
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-700 hover:bg-slate-50 font-medium transition"
            href="/batches"
          >
            <Layers size={17} className="text-indigo-600" /> Batch Audits
          </Link>
          <a
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-500 hover:bg-slate-50 transition"
            href="#graph-section"
          >
            <Network size={17} /> Resource Graph
          </a>
          <a
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-500 hover:bg-slate-50 transition"
            href="#audits"
          >
            <Search size={17} /> New Audit
          </a>
        </nav>

        <div className="absolute bottom-7 left-5 right-5 rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5 text-xs leading-5 text-indigo-950">
          <div className="mb-1 flex items-center gap-1.5 font-bold text-indigo-900">
            <ShieldCheck size={14} className="text-indigo-600" />
            Bounded Audit Scope
          </div>
          Single-URL Audit deeply crawls only the submitted primary page. Outgoing links & resources are checked via safe lightweight HEAD requests.
        </div>
      </aside>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:px-10">
          {/* Header */}
          <header id="dashboard" className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-indigo-600">
                Single-URL Audit & Resource Graph
              </p>
              <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
                SEO Deep Page Audit
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                Deep 4-agent SEO analysis for a single URL with an interactive page-centred resource graph and shallow check verification.
              </p>
            </div>
            {audit && (
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition"
              >
                <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> Refresh
              </button>
            )}
          </header>

          {/* Batch Audits Banner */}
          <div className="mb-6 flex flex-col items-start justify-between gap-4 rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-50 to-white p-5 shadow-sm sm:flex-row sm:items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-indigo-100/70 px-2.5 py-0.5 text-xs font-semibold text-indigo-800">
                <Sparkles size={13} /> Multi-URL Batch Auditing Ready
              </div>
              <h2 className="mt-2 text-base font-bold text-slate-900">
                Need to audit multiple pages across a domain?
              </h2>
              <p className="mt-0.5 text-xs text-slate-600">
                Launch batch audits across dozens of URLs or benchmark the 25 IB Tutoring Seed URLs.
              </p>
            </div>
            <Link
              href="/batches"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-700"
            >
              Open Batch Audits →
            </Link>
          </div>

          {/* Start Audit Input Section */}
          <section id="audits" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="mb-5 flex items-start gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
                <Globe2 size={19} />
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">Start a Single-URL Deep Audit</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Enter a target page URL to deeply inspect that page only (all 4 agents) and map connected page assets.
                </p>
              </div>
            </div>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
              <label className="sr-only" htmlFor="audit-url">
                Website URL
              </label>
              <input
                id="audit-url"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="https://tutors.tychr.com/ib-tutor/cities/bangalore"
                disabled={loading}
                className="h-12 min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-4 text-sm outline-none transition focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-100 disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={loading}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-6 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading && <Loader2 size={17} className="animate-spin" />}
                {loading ? "Auditing…" : "Start Deep Audit"}
              </button>
            </form>
            {validationError && <p className="mt-3 text-sm text-red-600">{validationError}</p>}
            {error && (
              <div
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
              >
                <AlertCircle size={17} className="mt-0.5 shrink-0" />
                {error}
              </div>
            )}
          </section>

          {audit ? (
            <>
              {/* Explicit Disentangled Metrics Cards */}
              <section className="mt-6 grid gap-4 grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                <Metric
                  label="Deep Pages Crawled"
                  value={metrics.deep_pages_crawled.toString()}
                  detail="Primary Audit Root Analyzed"
                  tone="indigo"
                />
                <Metric
                  label="Discovered HTML Links"
                  value={metrics.discovered_html_links.toString()}
                  detail={`${metrics.internal_links_count} internal · ${metrics.external_links_count} external`}
                />
                <Metric
                  label="Unique Page Resources"
                  value={metrics.unique_resource_urls.toString()}
                  detail={`${metrics.images_count} img · ${metrics.scripts_count} JS · ${metrics.stylesheets_count} CSS`}
                />
                <Metric
                  label="Shallow Link Checks"
                  value={`${metrics.successfully_checked_resources} / ${metrics.link_check_attempts}`}
                  detail="Safe bounded HEAD checks"
                />
                <Metric
                  label="Errors & Broken"
                  value={metrics.failed_resources_count.toString()}
                  detail="Client/Server or Fetch Errors"
                  tone={metrics.failed_resources_count > 0 ? "rose" : "slate"}
                />
                <Metric
                  label="Redirects"
                  value={metrics.redirect_count.toString()}
                  detail="Redirect chains tracked"
                  tone={metrics.redirect_count > 0 ? "amber" : "slate"}
                />
              </section>

              {/* Provider Status */}
              {providerStatus && (
                <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
                    <div>
                      <h2 className="text-sm font-bold tracking-tight text-slate-900">
                        External Provider Signals
                      </h2>
                      <p className="mt-0.5 text-xs text-slate-500">
                        Search Console, Backlink intelligence, and Analytics integrations.
                      </p>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">
                      GET /api/providers/status/
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-700">Google Search Console</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${providerStatus.search_console.status.includes("configured")
                              ? "bg-amber-100 text-amber-800"
                              : "bg-slate-200 text-slate-600"
                            }`}
                        >
                          {providerStatus.search_console.status.replace(/_/g, " ")}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-slate-500">
                        {providerStatus.search_console.reason || "Search performance dataset ready"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-700">Backlink Intelligence</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${providerStatus.backlinks.status.includes("configured")
                              ? "bg-amber-100 text-amber-800"
                              : "bg-slate-200 text-slate-600"
                            }`}
                        >
                          {providerStatus.backlinks.status.replace(/_/g, " ")}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-slate-500">
                        {providerStatus.backlinks.reason || "Backlink profile dataset ready"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-700">Web Analytics</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${providerStatus.analytics?.status === "active" ||
                              providerStatus.analytics?.status === "configured"
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-slate-200 text-slate-600"
                            }`}
                        >
                          {providerStatus.analytics?.status || "not configured"}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-slate-500">
                        {providerStatus.analytics?.imported_events_count
                          ? `${providerStatus.analytics.imported_events_count} events imported`
                          : providerStatus.analytics?.reason || "Event tracking feed"}
                      </p>
                    </div>
                  </div>
                </section>
              )}

              {/* Execution Progress & Stage Events */}
              <section className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="font-semibold text-slate-900">Single-URL Pipeline Status</h2>
                      <StatusBadge status={audit.status} />
                    </div>
                    <p className="mt-2 text-sm text-slate-500 break-all">
                      {audit.url} · {audit.current_stage || "Pipeline execution active"}
                    </p>
                  </div>
                  <div className="text-left text-xs text-slate-400 sm:text-right">
                    Started {formatDate(audit.created_at)}
                    <br />
                    Audit ID <span className="font-mono">{audit.id.slice(0, 8)}…</span>
                  </div>
                </div>

                <div className="grid gap-3 p-5 sm:grid-cols-3 sm:p-6">
                  <ProgressItem
                    label="1. Page Fetch & Discovery"
                    value={audit.status === "pending" ? "Queued" : "Single Page Fetched"}
                    active={!terminalStatuses.has(audit.status)}
                  />
                  <ProgressItem
                    label="2. Shallow Resource Checks"
                    value={`${metrics.successfully_checked_resources} of ${metrics.link_check_attempts} checked`}
                    active={metrics.successfully_checked_resources < metrics.link_check_attempts && audit.status !== "failed"}
                  />
                  <ProgressItem
                    label="3. 4-Agent Execution"
                    value={
                      auditReport
                        ? `${auditReport.agents.length} agent(s) completed`
                        : audit.status === "collected"
                          ? "Ready to run"
                          : audit.status === "running"
                            ? "Executing 4 agents…"
                            : "Waiting"
                    }
                    active={audit.status === "running"}
                  />
                </div>

                {audit.stage_events && audit.stage_events.length > 0 && (
                  <div className="border-t border-slate-100 bg-slate-50/50 p-5 sm:p-6">
                    <h3 className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                      Pipeline Execution Log
                    </h3>
                    <div className="space-y-2">
                      {audit.stage_events.map((evt, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-2xs"
                        >
                          <span
                            className={`mt-0.5 size-2 shrink-0 rounded-full ${evt.status === "done"
                                ? "bg-emerald-500"
                                : evt.status === "failed"
                                  ? "bg-red-500"
                                  : "bg-blue-500 animate-pulse"
                              }`}
                          />
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-bold uppercase text-slate-700">
                                {evt.stage}
                              </span>
                              <span className="text-slate-400">
                                {evt.created_at ? formatDate(evt.created_at) : ""}
                              </span>
                            </div>
                            <p className="mt-1 text-slate-600">{evt.message}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </section>

              {/* Agent Execution Trigger Bar */}
              {(audit.status === "collected" || audit.status === "completed" || audit.status === "running") && (
                <section className="mt-6 rounded-2xl border border-indigo-100 bg-indigo-50/40 p-5 shadow-sm sm:p-6">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <Sparkles size={16} className="text-indigo-600" />
                        <h2 className="font-bold text-slate-900">Run Specialized SEO Agent</h2>
                      </div>
                      <p className="mt-1 text-xs text-slate-600">
                        Execute deterministic and LLM-coordinated checks against collected HTML page evidence.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={selectedAgent}
                        onChange={(e) => setSelectedAgent(e.target.value)}
                        disabled={agentRunning || audit.status === "running"}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-800 shadow-2xs outline-none focus:border-indigo-500"
                      >
                        {agents.length > 0 ? (
                          agents.map((ag) => (
                            <option key={ag.id} value={ag.id}>
                              {ag.name} ({ag.id})
                            </option>
                          ))
                        ) : (
                          <>
                            <option value="onpage">On-Page SEO Agent</option>
                            <option value="technical">Technical SEO Agent</option>
                            <option value="visibility">Search Visibility Agent</option>
                            <option value="ib_conversion">IB Content & Conversion Agent</option>
                          </>
                        )}
                        <option value="all">Run All Agents</option>
                      </select>
                      <button
                        onClick={() => handleRunAgent(selectedAgent)}
                        disabled={agentRunning || audit.status === "running"}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition"
                      >
                        {agentRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                        {agentRunning ? "Launching…" : `Run ${selectedAgent} Agent`}
                      </button>
                    </div>
                  </div>
                </section>
              )}

              {/* Main Navigation Tabs */}
              <div id="graph-section" className="mt-8">
                <div className="flex overflow-x-auto border-b border-slate-200">
                  <button
                    onClick={() => setActiveTab("graph")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "graph"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <Network size={16} /> Resource Graph
                    {resourceGraph && (
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-bold text-indigo-700">
                        {resourceGraph.nodes.length}
                      </span>
                    )}
                  </button>
                  <button
                    onClick={() => setActiveTab("audit")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "audit"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <FileText size={16} /> 4-Agent SEO Report
                    {auditReport && (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-700">
                        {Math.round(auditReport.score.percent)}%
                      </span>
                    )}
                  </button>
                  <button
                    onClick={() => setActiveTab("links")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "links"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <Link2 size={16} /> Discovered Links ({metrics.discovered_html_links})
                  </button>
                  <button
                    onClick={() => setActiveTab("resources")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "resources"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <ImageIcon size={16} /> Page Assets ({metrics.unique_resource_urls})
                  </button>
                  <button
                    onClick={() => setActiveTab("business")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "business"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <Zap size={16} /> Business CRO
                  </button>
                  <button
                    onClick={() => setActiveTab("evaluation")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "evaluation"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <ShieldCheck size={16} /> Academic Evaluation
                  </button>
                  <button
                    onClick={() => setActiveTab("crawl")}
                    className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${activeTab === "crawl"
                        ? "border-indigo-600 text-indigo-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                  >
                    <Layers size={16} /> Crawl Records ({urls.length})
                  </button>
                </div>

                {/* TAB 1: RESOURCE GRAPH */}
                {activeTab === "graph" && (
                  <div className="mt-6">
                    {resourceGraph ? (
                      <ResourceGraphView
                        graph={resourceGraph}
                        selectedNodeId={selectedNode?.id ?? null}
                        onSelectNode={setSelectedNode}
                        onAuditUrl={handleAuditUrl}
                      />
                    ) : (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
                        <Loader2 size={24} className="mx-auto text-indigo-600 animate-spin" />
                        <h3 className="mt-3 text-sm font-semibold text-slate-800">
                          Constructing Page Resource Graph…
                        </h3>
                        <p className="mt-1 text-xs text-slate-500">
                          Extracting HTML links, image elements, stylesheets, and scripts, then performing lightweight shallow checks.
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 2: 4-AGENT SEO REPORT */}
                {activeTab === "audit" && (
                  <div className="mt-6">
                    {auditReport ? (
                      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="border-b border-slate-200 p-6">
                          <div className="flex flex-wrap items-start justify-between gap-4">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
                                  Rule Version: {auditReport.rule_version}
                                </span>
                                {auditReport.final_audit?.llm_fallback && (
                                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                                    Deterministic Narrative Fallback
                                  </span>
                                )}
                              </div>
                              <h2 className="mt-2 text-xl font-bold text-slate-900">
                                SEO Audit Report & Agent Findings
                              </h2>
                              <p className="mt-1 text-sm text-slate-500 break-all">
                                Generated {formatDate(auditReport.generated_at)} for {auditReport.url}
                              </p>
                            </div>
                            <div className="flex items-center gap-3">
                              <div className="text-right">
                                <p className="text-3xl font-extrabold text-indigo-600">
                                  {Math.round(auditReport.score.percent)}%
                                </p>
                                <p className="text-xs text-slate-400">
                                  {Math.round(auditReport.score.coverage_percent)}% check coverage
                                </p>
                              </div>
                              <a
                                href={getAuditReportCsvUrl(audit.id, selectedAgent)}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 transition"
                              >
                                <Download size={14} /> Export CSV
                              </a>
                            </div>
                          </div>
                        </div>

                        {/* Executive Summary */}
                        {auditReport.final_audit && (
                          <div className="border-b border-slate-100 bg-slate-50/50 p-6">
                            <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                              Executive Summary
                            </h3>
                            <p className="mt-2 text-sm leading-relaxed text-slate-700">
                              {auditReport.final_audit.executive_summary}
                            </p>
                            {auditReport.final_audit.explanation_for_beginners && (
                              <p className="mt-2 text-xs italic text-slate-500">
                                Note: {auditReport.final_audit.explanation_for_beginners}
                              </p>
                            )}

                            {/* Strengths & Weaknesses */}
                            <div className="mt-4 grid gap-4 sm:grid-cols-2">
                              {auditReport.final_audit.strengths.length > 0 && (
                                <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
                                  <h4 className="flex items-center gap-1.5 text-xs font-bold text-emerald-800">
                                    <CheckCircle2 size={14} /> Confirmed Strengths ({auditReport.final_audit.strengths.length})
                                  </h4>
                                  <ul className="mt-2 space-y-1 text-xs text-emerald-900">
                                    {auditReport.final_audit.strengths.slice(0, 5).map((s, i) => (
                                      <li key={i}>• {s}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {auditReport.final_audit.weaknesses.length > 0 && (
                                <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                                  <h4 className="flex items-center gap-1.5 text-xs font-bold text-amber-800">
                                    <AlertTriangle size={14} /> Improvement Areas ({auditReport.final_audit.weaknesses.length})
                                  </h4>
                                  <ul className="mt-2 space-y-1 text-xs text-amber-900">
                                    {auditReport.final_audit.weaknesses.slice(0, 5).map((w, i) => (
                                      <li key={i}>• {w}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Agents Execution Breakdown */}
                        <div className="p-6">
                          <h3 className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                            Agent Findings Breakdown
                          </h3>
                          <div className="space-y-6">
                            {auditReport.agents.map((agentItem) => (
                              <div key={agentItem.agent_id} className="rounded-xl border border-slate-200 p-5">
                                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                                  <div>
                                    <h4 className="font-bold text-slate-900 capitalize">
                                      {agentItem.agent_id.replace("_", " ")} Agent
                                    </h4>
                                    <p className="text-xs text-slate-500">{agentItem.scope}</p>
                                  </div>
                                  <div className="text-right">
                                    <span className="text-lg font-bold text-indigo-600">
                                      {Math.round(agentItem.score.percent)}%
                                    </span>
                                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold capitalize text-slate-600">
                                      {agentItem.status}
                                    </span>
                                  </div>
                                </div>
                                <div className="mt-4 divide-y divide-slate-100">
                                  {agentItem.findings.map((f) => (
                                    <div key={f.id} className="py-3 first:pt-0 last:pb-0">
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                          <span
                                            className={`size-2 rounded-full ${f.status === "pass"
                                                ? "bg-emerald-500"
                                                : f.status === "warn"
                                                  ? "bg-amber-500"
                                                  : "bg-red-500"
                                              }`}
                                          />
                                          <span className="text-xs font-bold text-slate-800">{f.title}</span>
                                          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-600">
                                            {f.check_id}
                                          </span>
                                        </div>
                                        <span
                                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${f.severity === "critical"
                                              ? "bg-red-100 text-red-700"
                                              : f.severity === "high"
                                                ? "bg-orange-100 text-orange-700"
                                                : "bg-slate-100 text-slate-600"
                                            }`}
                                        >
                                          {f.severity}
                                        </span>
                                      </div>
                                      <p className="mt-1 text-xs text-slate-500">
                                        <strong>Observed:</strong> {f.evidence.observed || "—"} ·{" "}
                                        <strong>Expected:</strong> {f.evidence.expected || "—"}
                                      </p>
                                      <p className="mt-1 text-xs text-slate-700">{f.recommendation}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </section>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
                        <FileText size={24} className="mx-auto text-slate-400" />
                        <h3 className="mt-2 text-sm font-semibold text-slate-800">No agent report generated yet</h3>
                        <p className="mt-1 text-xs text-slate-500">
                          {audit.status === "collected"
                            ? "Page collection is complete. Click 'Run Agent' above to generate findings and scores."
                            : "Waiting for page collection to finish."}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 3: DISCOVERED LINKS & EXPLORATION */}
                {activeTab === "links" && (
                  <div className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                    <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="font-semibold text-slate-900">
                            Discovered Outgoing Links ({linkNodes.length})
                          </h2>
                          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                            {metrics.internal_links_count} Internal · {metrics.external_links_count} External
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Outgoing HTML hyperlinks detected on the page. Click &ldquo;Inspect&rdquo; to view shallow check details or &ldquo;Deep Audit&rdquo; to launch an independent audit.
                        </p>
                      </div>
                      {discoveredHtmlPages.length > 0 && (
                        <button
                          onClick={handleBatchAuditDiscovered}
                          disabled={batchCreating}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition"
                        >
                          {batchCreating ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
                          {batchCreating ? "Queueing Batch…" : `Audit All in Batch (${discoveredHtmlPages.length})`}
                        </button>
                      )}
                    </div>

                    {linkNodes.length === 0 ? (
                      <div className="p-10 text-center text-sm text-slate-500">
                        No outgoing HTML links were discovered on this page.
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[760px] text-left text-sm">
                          <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-6 py-3">Link URL</th>
                              <th className="px-4 py-3">Scope</th>
                              <th className="px-4 py-3">Check Status</th>
                              <th className="px-4 py-3">HTTP Code</th>
                              <th className="px-4 py-3">Anchor / Rel</th>
                              <th className="px-6 py-3 text-right">Actions</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {linkNodes.map((item: ResourceGraphNode) => (
                              <tr key={item.id} className="align-top hover:bg-slate-50/70">
                                <td className="max-w-[320px] break-all px-6 py-4 font-medium text-slate-800">
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="hover:text-indigo-600 hover:underline inline-flex items-center gap-1"
                                  >
                                    {item.url}
                                    <ExternalLink size={12} className="text-slate-400 shrink-0" />
                                  </a>
                                  {item.issues && item.issues.length > 0 && (
                                    <div className="mt-1 flex items-center gap-1 text-[11px] text-rose-600">
                                      <AlertTriangle size={12} />
                                      <span>{item.issues[0].issue}</span>
                                    </div>
                                  )}
                                </td>
                                <td className="px-4 py-4">
                                  <span
                                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${item.is_internal
                                        ? "bg-indigo-50 text-indigo-700"
                                        : "bg-slate-100 text-slate-600"
                                      }`}
                                  >
                                    {item.is_internal ? "Internal" : "External"}
                                  </span>
                                </td>
                                <td className="px-4 py-4 text-xs font-semibold">
                                  <span
                                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${item.status === "available"
                                        ? "bg-emerald-50 text-emerald-700"
                                        : item.status === "redirects"
                                          ? "bg-amber-50 text-amber-700"
                                          : item.status === "client_error" || item.status === "server_error"
                                            ? "bg-red-50 text-red-700"
                                            : "bg-slate-100 text-slate-600"
                                      }`}
                                  >
                                    {item.status.replace("_", " ")}
                                  </span>
                                </td>
                                <td className="px-4 py-4 font-mono text-xs text-slate-600">
                                  {item.http_status ?? "—"}
                                </td>
                                <td className="px-4 py-4 text-xs text-slate-500 max-w-[220px]">
                                  <div className="truncate">
                                    {item.details?.anchor_text ? (
                                      <span className="font-medium text-slate-800" title={item.details.anchor_text}>
                                        &ldquo;{item.details.anchor_text}&rdquo;
                                      </span>
                                    ) : item.details?.aria_label ? (
                                      <span className="italic text-slate-400" title={`aria-label: ${item.details.aria_label}`}>
                                        aria: &ldquo;{item.details.aria_label}&rdquo;
                                      </span>
                                    ) : (
                                      <span className="text-slate-400">—</span>
                                    )}
                                  </div>
                                  {(() => {
                                    const relList = Array.isArray(item.details?.rel)
                                      ? item.details.rel
                                      : typeof item.details?.rel === "string"
                                        ? (item.details.rel as string).split(/\s+/).filter(Boolean)
                                        : [];
                                    return relList.length > 0 ? (
                                      <div className="mt-0.5 font-mono text-[10px] text-slate-400 truncate" title={`rel: ${relList.join(", ")}`}>
                                        rel: {relList.join(", ")}
                                      </div>
                                    ) : null;
                                  })()}
                                  {item.details?.target && item.details.target !== "_self" && (
                                    <div className="font-mono text-[10px] text-slate-400">
                                      target: {item.details.target}
                                    </div>
                                  )}
                                </td>
                                <td className="whitespace-nowrap px-6 py-4 text-right">
                                  <div className="inline-flex items-center gap-2">
                                    <button
                                      onClick={() => setSelectedNode(item)}
                                      className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                                    >
                                      Inspect
                                    </button>
                                    <button
                                      onClick={() => handleAuditUrl(item.url)}
                                      className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 transition"
                                    >
                                      <Play size={10} /> Deep Audit
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 4: PAGE ASSETS (IMAGES, CSS, SCRIPTS) */}
                {activeTab === "resources" && (
                  <div className="mt-6 space-y-6">
                    {/* Images Section */}
                    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                      <div className="border-b border-slate-200 p-5 sm:p-6">
                        <div className="flex items-center gap-2">
                          <ImageIcon size={18} className="text-emerald-600" />
                          <h3 className="font-semibold text-slate-900">
                            Page Images & Media ({imageNodes.length})
                          </h3>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Evaluated for accessibility alt text, CLS dimensions (width × height), and shallow check availability.
                        </p>
                      </div>

                      {imageNodes.length === 0 ? (
                        <div className="p-8 text-center text-sm text-slate-500">
                          No image or media tags were detected on this page.
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full min-w-[700px] text-left text-sm">
                            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                              <tr>
                                <th className="px-6 py-3">Resource URL</th>
                                <th className="px-4 py-3">Alt Text Status</th>
                                <th className="px-4 py-3">Dimensions (CLS)</th>
                                <th className="px-4 py-3">Loading</th>
                                <th className="px-4 py-3">Status</th>
                                <th className="px-6 py-3 text-right">Inspect</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {imageNodes.map((img: ResourceGraphNode) => (
                                <tr key={img.id} className="hover:bg-slate-50/70">
                                  <td className="max-w-[280px] break-all px-6 py-3.5 font-medium text-slate-800 text-xs">
                                    <span className="font-mono">{img.url}</span>
                                  </td>
                                  <td className="px-4 py-3.5 text-xs">
                                    {img.details?.alt ? (
                                      <span className="inline-flex items-center gap-1 text-emerald-700 font-medium" title={img.details.alt}>
                                        <CheckCircle2 size={13} /> &ldquo;{img.details.alt.slice(0, 30)}&rdquo;
                                      </span>
                                    ) : img.details?.has_alt || img.details?.alt === "" ? (
                                      <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600" title="Explicit empty alt attribute for decorative image">
                                        <CheckCircle2 size={11} className="text-slate-400" /> alt=&quot;&quot; (Decorative)
                                      </span>
                                    ) : img.details?.aria_label ? (
                                      <span className="inline-flex items-center gap-1 text-teal-700 font-medium text-[11px]" title={`aria: ${img.details.aria_label}`}>
                                        <CheckCircle2 size={13} /> aria: &ldquo;{String(img.details.aria_label).slice(0, 30)}&rdquo;
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 rounded bg-rose-50 px-2 py-0.5 text-[10px] font-bold text-rose-700">
                                        <AlertCircle size={11} /> Missing Alt
                                      </span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3.5 font-mono text-xs text-slate-600">
                                    {img.details?.width && img.details?.height ? (
                                      `${img.details.width} × ${img.details.height}${!String(img.details.width).includes('px') && !String(img.details.width).includes('%') ? ' px' : ''}`
                                    ) : img.details?.width ? (
                                      <span>{img.details.width} × <span className="text-slate-400 text-[10px]">auto</span></span>
                                    ) : img.details?.height ? (
                                      <span><span className="text-slate-400 text-[10px]">auto</span> × {img.details.height}</span>
                                    ) : (
                                      <span className="text-amber-600 text-[11px]">Unspecified</span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3.5 capitalize text-xs text-slate-600">
                                    {img.details?.loading ? (
                                      <span className={img.details.loading.includes("lazy") ? "text-emerald-700 font-medium" : "text-slate-700"}>
                                        {img.details.loading}
                                      </span>
                                    ) : (
                                      <span className="text-slate-400 text-[11px]">eager (default)</span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3.5 font-mono text-xs">
                                    {img.http_status ?? img.status}
                                  </td>
                                  <td className="px-6 py-3.5 text-right">
                                    <button
                                      onClick={() => setSelectedNode(img)}
                                      className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                                    >
                                      Inspect
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>

                    {/* Scripts & Stylesheets */}
                    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                      <div className="border-b border-slate-200 p-5 sm:p-6">
                        <div className="flex items-center gap-2">
                          <FileCode size={18} className="text-violet-600" />
                          <h3 className="font-semibold text-slate-900">
                            Stylesheets & Scripts ({scriptCssNodes.length})
                          </h3>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Inspect CSS and JS dependencies for render-blocking characteristics and safe delivery.
                        </p>
                      </div>

                      {scriptCssNodes.length === 0 ? (
                        <div className="p-8 text-center text-sm text-slate-500">
                          No external scripts or stylesheets were detected.
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full min-w-[700px] text-left text-sm">
                            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                              <tr>
                                <th className="px-6 py-3">Resource URL</th>
                                <th className="px-4 py-3">Type</th>
                                <th className="px-4 py-3">Attributes</th>
                                <th className="px-4 py-3">Render Impact</th>
                                <th className="px-4 py-3">Status</th>
                                <th className="px-6 py-3 text-right">Inspect</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {scriptCssNodes.map((res: ResourceGraphNode) => {
                                const isBlocking =
                                  res.node_type === "script" &&
                                  !res.details?.async &&
                                  !res.details?.defer;

                                return (
                                  <tr key={res.id} className="hover:bg-slate-50/70">
                                    <td className="max-w-[280px] break-all px-6 py-3.5 font-medium text-slate-800 text-xs font-mono">
                                      {res.url}
                                    </td>
                                    <td className="px-4 py-3.5 text-xs font-semibold uppercase text-slate-600">
                                      {res.node_type}
                                    </td>
                                    <td className="px-4 py-3.5 font-mono text-xs text-slate-500">
                                      {res.details?.async
                                        ? "async"
                                        : res.details?.defer
                                          ? "defer"
                                          : "sync"}
                                    </td>
                                    <td className="px-4 py-3.5 text-xs">
                                      {isBlocking ? (
                                        <span className="rounded bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                                          Render-Blocking
                                        </span>
                                      ) : (
                                        <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                                          Non-Blocking
                                        </span>
                                      )}
                                    </td>
                                    <td className="px-4 py-3.5 font-mono text-xs">
                                      {res.http_status ?? res.status}
                                    </td>
                                    <td className="px-6 py-3.5 text-right">
                                      <button
                                        onClick={() => setSelectedNode(res)}
                                        className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                                      >
                                        Inspect
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* TAB 5: BUSINESS SEO */}
                {activeTab === "business" && (
                  <div className="mt-6">
                    {businessReport ? (
                      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="border-b border-slate-200 p-5 sm:p-6">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <h2 className="font-semibold text-slate-900">
                                Business SEO Intelligence Report
                              </h2>
                              <p className="mt-1 text-sm text-slate-500">
                                Classified as{" "}
                                <span className="font-medium text-slate-700">
                                  {businessReport.page_classification?.label ?? "unknown"}
                                </span>
                                {" · "}confidence{" "}
                                {Math.round((businessReport.page_classification?.confidence ?? 0) * 100)}%
                              </p>
                            </div>
                            <a
                              className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                              href={businessReport.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open audited page <ArrowUpRight size={15} className="ml-1 inline" />
                            </a>
                          </div>
                        </div>
                        <div className="divide-y divide-slate-100">
                          {businessReport.findings
                            .filter((finding) => finding.status !== "pass")
                            .map((finding) => (
                              <div
                                key={finding.id}
                                className="grid gap-3 p-5 sm:grid-cols-[1fr_auto] sm:p-6"
                              >
                                <div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <h3 className="font-medium text-slate-800">{finding.title}</h3>
                                    <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold capitalize text-amber-700">
                                      {finding.severity}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-sm text-slate-500">
                                    Observed: {finding.evidence.observed}
                                  </p>
                                  <p className="mt-1 text-sm text-slate-700">{finding.recommendation}</p>
                                </div>
                                <span className="text-xs text-slate-400">
                                  Confidence {Math.round(finding.confidence * 100)}%
                                </span>
                              </div>
                            ))}
                          {businessReport.finding_count === 0 && (
                            <p className="p-6 text-sm text-emerald-700">
                              No business-focused opportunities were observed for this page.
                            </p>
                          )}
                        </div>
                        <p className="border-t border-slate-100 px-5 py-4 text-xs text-slate-400 sm:px-6">
                          {businessReport.heuristic_priority}
                        </p>
                      </section>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-xs text-slate-500">
                        Business report not available yet.
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 6: ACADEMIC EVALUATION */}
                {activeTab === "evaluation" && (
                  <div className="mt-6">
                    {evaluationReport ? (
                      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="border-b border-slate-200 p-5 sm:p-6">
                          <h2 className="font-semibold text-slate-900">
                            Academic Evaluation Report (IB Curriculum & Authority)
                          </h2>
                          <p className="mt-1 text-sm text-slate-500">
                            Evaluated across {evaluationReport.findings.length} academic and authority rules.
                          </p>
                        </div>
                        <div className="divide-y divide-slate-100">
                          {evaluationReport.findings.map((f) => (
                            <div key={f.id} className="p-5 sm:p-6">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <h3 className="font-medium text-slate-800">{f.title}</h3>
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${f.status === "pass"
                                        ? "bg-emerald-100 text-emerald-800"
                                        : f.status === "warn"
                                          ? "bg-amber-100 text-amber-800"
                                          : "bg-red-100 text-red-800"
                                      }`}
                                  >
                                    {f.status}
                                  </span>
                                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold capitalize text-slate-600">
                                    {f.severity}
                                  </span>
                                </div>
                              </div>
                              <p className="mt-2 text-xs text-slate-500">
                                <strong>Observed:</strong> {f.evidence.observed}
                              </p>
                              <p className="mt-1 text-xs text-slate-700">{f.recommendation}</p>
                            </div>
                          ))}
                        </div>
                      </section>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-xs text-slate-500">
                        Academic evaluation report not available yet.
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 7: RAW CRAWL INVENTORY */}
                {activeTab === "crawl" && (
                  <section id="urls" className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="font-semibold text-slate-900">
                            Raw Crawl Records ({urls.length} URLs)
                          </h2>
                          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                            {discoveredHtmlPages.length} HTML pages
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Underlying database records stored in the CrawlURL table for this audit.
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {discoveredHtmlPages.length > 0 && (
                          <button
                            onClick={handleBatchAuditDiscovered}
                            disabled={batchCreating}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition"
                          >
                            {batchCreating ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
                            {batchCreating ? "Queueing Batch…" : `Audit Discovered Links in Batch (${discoveredHtmlPages.length} Pages)`}
                          </button>
                        )}
                        <label className="sr-only" htmlFor="status-filter">
                          Filter URLs by status
                        </label>
                        <select
                          id="status-filter"
                          value={filter}
                          onChange={(event) => setFilter(event.target.value as CrawlStatus | "all")}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 outline-none focus:border-indigo-500"
                        >
                          {crawlFilters.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    {visibleURLs.length === 0 ? (
                      <div className="p-10 text-center text-sm text-slate-500">
                        {urls.length === 0
                          ? "No URLs have been persisted yet. Discovery may still be starting."
                          : "No URLs match this filter."}
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[760px] text-left text-sm">
                          <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-6 py-3">Discovered URL</th>
                              <th className="px-4 py-3">Status</th>
                              <th className="px-4 py-3">Resource Type</th>
                              <th className="px-4 py-3">Depth</th>
                              <th className="px-4 py-3">HTTP Code</th>
                              <th className="px-4 py-3">Discovery Source</th>
                              <th className="px-6 py-3">Updated</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {visibleURLs.map((item) => (
                              <tr key={item.id} className="align-top hover:bg-slate-50/70">
                                <td className="max-w-[320px] break-all px-6 py-4 font-medium text-slate-800">
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="hover:text-indigo-600 hover:underline"
                                  >
                                    {item.url}
                                  </a>
                                  {item.error && (
                                    <p className="mt-1 text-xs font-normal text-red-500">{item.error}</p>
                                  )}
                                </td>
                                <td className="px-4 py-4">
                                  <StatusBadge status={item.status} />
                                </td>
                                <td className="px-4 py-4 text-slate-600">
                                  {item.resource_type === "media" ? "Media" : "HTML Page"}
                                </td>
                                <td className="px-4 py-4 font-mono text-xs text-slate-600">{item.depth}</td>
                                <td className="px-4 py-4 font-mono text-xs text-slate-600">
                                  {item.response_status ?? "—"}
                                </td>
                                <td className="px-4 py-4 capitalize text-slate-600">
                                  {item.discovery_source.replace("_", " ")}
                                </td>
                                <td className="whitespace-nowrap px-6 py-4 text-xs text-slate-500">
                                  {formatDate(item.updated_at)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                )}
              </div>
            </>
          ) : (
            <section className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white/70 p-12 text-center">
              <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500">
                <Search size={21} />
              </div>
              <h2 className="mt-4 font-semibold text-slate-800">No audit active</h2>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
                Enter a target URL above to run a single-page deep audit, view the resource graph, and check connected assets.
              </p>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  muted = false,
  tone = "slate",
}: {
  label: string;
  value: string;
  detail: string;
  muted?: boolean;
  tone?: "slate" | "indigo" | "rose" | "amber" | "emerald";
}) {
  const borderTone =
    tone === "indigo"
      ? "border-indigo-200 bg-indigo-50/30"
      : tone === "rose"
        ? "border-rose-200 bg-rose-50/30"
        : tone === "amber"
          ? "border-amber-200 bg-amber-50/30"
          : "border-slate-200 bg-white";

  const textTone =
    muted
      ? "text-slate-400 text-lg"
      : tone === "indigo"
        ? "text-indigo-700"
        : tone === "rose"
          ? "text-rose-700"
          : tone === "amber"
            ? "text-amber-700"
            : "text-slate-950";

  return (
    <div className={`rounded-2xl border p-4 shadow-sm transition hover:shadow-md ${borderTone}`}>
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-extrabold tracking-tight ${textTone}`}>{value}</p>
      <p className="mt-1 text-[11px] text-slate-400 truncate" title={detail}>
        {detail}
      </p>
    </div>
  );
}

function ProgressItem({ label, value, active }: { label: string; value: string; active: boolean }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <span className={`size-2 rounded-full ${active ? "bg-blue-500 animate-pulse" : "bg-emerald-500"}`} />
      </div>
      <p className="mt-2 text-xs text-slate-500">{value}</p>
    </div>
  );
}
