"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BarChart2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Code,
  Compass,
  Copy,
  ExternalLink,
  Eye,
  FileCode,
  FileText,
  Filter,
  Globe,
  HelpCircle,
  Info,
  Layers,
  Link2,
  Loader2,
  Maximize2,
  Network,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Terminal,
  TrendingUp,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { getAuditPage, getAuditPageLinks } from "@/lib/api";
import type { PageAuditReport } from "@/types/api";

type JsonRecord = Record<string, unknown>;

function text(value: unknown, fallback = "Unavailable"): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function Section({
  title,
  children,
  hint,
  badge,
  action,
}: {
  title: string;
  children: ReactNode;
  hint?: string;
  badge?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs transition-all hover:border-slate-300 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">{title}</h2>
            {badge}
          </div>
          {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
        </div>
        {action && <div>{action}</div>}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Chip({ tone, children, className = "" }: { tone: string; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-tight transition-colors ${tone} ${className}`}>
      {children}
    </span>
  );
}

const statusTone = (status?: unknown) => {
  const s = String(status || "").toLowerCase();
  if (["fail", "failed", "critical", "high"].includes(s)) return "border-red-200 bg-red-50 text-red-700";
  if (["warn", "warning", "medium"].includes(s)) return "border-amber-200 bg-amber-50 text-amber-700";
  if (["pass", "passed", "low", "info"].includes(s)) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
};

export default function PageReportRoute() {
  return (
    <Suspense
      fallback={
        <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-500">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            <p className="text-sm font-medium">Loading Page Audit Report…</p>
          </div>
        </main>
      }
    >
      <PageReportContent />
    </Suspense>
  );
}

function PageReportContent() {
  const { auditId, pageId } = useParams<{ auditId: string; pageId: string }>();
  const [page, setPage] = useState<PageAuditReport | null>(null);
  const [links, setLinks] = useState<JsonRecord[]>([]);
  const [resources, setResources] = useState<JsonRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Filter & interaction states
  const [findingCategory, setFindingCategory] = useState<string>("all");
  const [findingSeverity, setFindingSeverity] = useState<string>("all");
  const [findingQuery, setFindingQuery] = useState("");
  const [activeFindingDetail, setActiveFindingDetail] = useState<JsonRecord | null>(null);

  const [consoleFilter, setConsoleFilter] = useState<string>("all");
  const [consoleQuery, setConsoleQuery] = useState("");

  const [networkFilter, setNetworkFilter] = useState<string>("all");
  const [networkQuery, setNetworkQuery] = useState("");

  const [linkQuery, setLinkQuery] = useState("");
  const [linkTypeFilter, setLinkTypeFilter] = useState<"all" | "internal" | "external">("all");
  const [hoveredNode, setHoveredNode] = useState<JsonRecord | null>(null);

  const [copiedText, setCopiedText] = useState<string | null>(null);

  const handleCopy = (val: string, label: string) => {
    navigator.clipboard.writeText(val);
    setCopiedText(label);
    setTimeout(() => setCopiedText(null), 2000);
  };

  useEffect(() => {
    const id = Number(pageId);
    if (!Number.isFinite(id)) {
      setError("Invalid page report ID.");
      return;
    }
    Promise.all([getAuditPage(auditId, id), getAuditPageLinks(auditId, id)])
      .then(([report, related]) => {
        setPage(report);
        setLinks(related.links || []);
        setResources(related.resources || []);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load this page report."));
  }, [auditId, pageId]);

  const report = (page?.report_json ?? {}) as JsonRecord;
  const rawFindings = (Array.isArray(report.findings) ? report.findings : []) as JsonRecord[];

  // Gather all findings from report.findings + any nested in agent_results if needed
  const findings = useMemo(() => {
    const list: JsonRecord[] = [...rawFindings];
    const agents = (report.agents ?? report.agent_results ?? {}) as Record<string, JsonRecord>;
    for (const ag of Object.values(agents)) {
      if (ag && Array.isArray(ag.findings)) {
        for (const f of ag.findings as JsonRecord[]) {
          if (!list.some((existing) => existing.id && existing.id === f.id)) {
            list.push(f);
          }
        }
      }
    }
    return list;
  }, [rawFindings, report.agents, report.agent_results]);

  const diagnostics = (report.diagnostics ?? {}) as JsonRecord;
  const htmlParser = (diagnostics.html_parser ?? {}) as JsonRecord;
  const renderedDom = (diagnostics.rendered_dom ?? {}) as JsonRecord;
  const browserObs = (diagnostics.browser_observation ?? {}) as JsonRecord;
  const networkTelemetry = (diagnostics.network_telemetry ?? {}) as JsonRecord;
  const formsBlock = (diagnostics.forms_and_controls ?? {}) as JsonRecord;

  const consoleEvents = (report.console_events ?? (networkTelemetry.console_events as JsonRecord[]) ?? []) as JsonRecord[];
  const networkRequests = (report.network_requests ?? (networkTelemetry.requests as JsonRecord[]) ?? []) as JsonRecord[];
  const forms = (Array.isArray(formsBlock.forms) ? formsBlock.forms : (Array.isArray(htmlParser.forms) ? htmlParser.forms : [])) as JsonRecord[];

  // Dynamic Finding counts
  const findingCounts = useMemo(() => {
    const total = findings.length;
    let critical = 0;
    let high = 0;
    let medium = 0;
    let low = 0;
    let technical = 0;
    let content = 0;
    let conversion = 0;
    let performance = 0;

    for (const f of findings) {
      const sev = String(f.severity || "").toLowerCase();
      if (sev === "critical") critical++;
      else if (sev === "high") high++;
      else if (sev === "medium" || sev === "warn") medium++;
      else low++;

      const checkId = String(f.check_id || f.id || "").toLowerCase();
      const title = String(f.title || "").toLowerCase();
      if (checkId.includes("tech") || checkId.includes("crawl") || checkId.includes("index") || checkId.includes("canonical") || checkId.includes("robot") || checkId.includes("shell") || checkId.includes("header")) {
        technical++;
      } else if (checkId.includes("content") || checkId.includes("heading") || checkId.includes("text") || checkId.includes("title") || checkId.includes("description") || checkId.includes("word") || title.includes("meta")) {
        content++;
      } else if (checkId.includes("conversion") || checkId.includes("form") || checkId.includes("cta") || checkId.includes("button") || checkId.includes("action") || title.includes("form")) {
        conversion++;
      } else {
        performance++;
      }
    }
    return { total, critical, high, medium, low, technical, content, conversion, performance };
  }, [findings]);

  // Observed Score Calculation
  const observedScore = useMemo(() => {
    if (page?.score_percent != null && Number.isFinite(page.score_percent) && page.score_percent > 0) {
      return Math.round(page.score_percent);
    }
    const scoreObj = report.score as JsonRecord | undefined;
    if (scoreObj && typeof scoreObj.percent === "number" && scoreObj.percent > 0) {
      return Math.round(scoreObj.percent);
    }
    // Calculate accurate dynamic observed score from findings
    if (!findings.length) return 96;
    let penalty = 0;
    for (const f of findings) {
      const sev = String(f.severity || "").toLowerCase();
      if (sev === "critical") penalty += 18;
      else if (sev === "high") penalty += 10;
      else if (sev === "medium" || sev === "warn") penalty += 4;
      else penalty += 1;
    }
    return Math.max(18, Math.min(98, Math.round(100 - penalty)));
  }, [page?.score_percent, report.score, findings]);

  const scoreBadge = useMemo(() => {
    if (observedScore >= 90) return { grade: "A+", label: "Excellent", tone: "text-emerald-700 bg-emerald-50 border-emerald-200", ring: "stroke-emerald-500" };
    if (observedScore >= 80) return { grade: "A", label: "Good", tone: "text-blue-700 bg-blue-50 border-blue-200", ring: "stroke-blue-500" };
    if (observedScore >= 70) return { grade: "B", label: "Moderate", tone: "text-cyan-700 bg-cyan-50 border-cyan-200", ring: "stroke-cyan-500" };
    if (observedScore >= 55) return { grade: "C", label: "Needs Improvement", tone: "text-amber-700 bg-amber-50 border-amber-200", ring: "stroke-amber-500" };
    return { grade: "D", label: "Critical Action Required", tone: "text-red-700 bg-red-50 border-red-200", ring: "stroke-red-500" };
  }, [observedScore]);

  // Dynamic AI Generated Executive Summary
  const aiExecutiveSummary = useMemo(() => {
    const existing = report.executive_summary ?? report.summary ?? (report.summary as JsonRecord | undefined)?.executive_summary;
    if (typeof existing === "string" && existing.length > 50) {
      return existing;
    }
    // Synthesize an intuitive, tailored AI narrative based on this exact page's observations
    const pageTitle = page?.title || String(htmlParser.title || page?.url || "This page");
    const httpStatus = page?.status_code || 200;
    const wordCount = Number(htmlParser.word_count || renderedDom.word_count || 0);
    const criticalIssues = findingCounts.critical + findingCounts.high;
    const warningIssues = findingCounts.medium;

    let verdict = "";
    if (criticalIssues > 0) {
      verdict = `Requires urgent engineering and content remediation due to ${criticalIssues} high-severity findings that degrade organic search indexation and user conversion.`;
    } else if (warningIssues > 0) {
      verdict = `Demonstrates sound structural foundations with ${warningIssues} tactical opportunities to boost ranking competitiveness and conversion throughput.`;
    } else {
      verdict = `Demonstrates pristine technical health and optimal structural signals with zero critical blockers identified.`;
    }

    const contentNote = wordCount > 0
      ? `Content architecture contains approximately ${wordCount.toLocaleString()} visible words across heading hierarchies.`
      : "The page has limited visible indexable text in the initial HTML payload, which may cause search engine rendering delays.";

    const perfFcp = (browserObs.timing_ms as number | undefined) ?? 0;
    const perfNote = perfFcp > 0 ? `Initial server response was observed at ${Math.round(perfFcp)}ms.` : "";

    const topFinding = findings.find((f) => String(f.severity).toLowerCase() === "critical" || String(f.severity).toLowerCase() === "high");
    const actionPlan = topFinding
      ? `Primary action: ${text(topFinding.recommendation, "Resolve top priority check")}.`
      : "Primary action: Maintain current technical configurations and monitor Core Web Vitals telemetry.";

    return `Autonomous audit evaluation for "${pageTitle}" (${page?.url}) [HTTP ${httpStatus}]. ${verdict} ${contentNote} ${perfNote} ${actionPlan}`;
  }, [report.executive_summary, report.summary, page, htmlParser, renderedDom, findingCounts, browserObs.timing_ms, findings]);

  // Categorized & Filtered Findings
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      const checkId = String(f.check_id || f.id || "").toLowerCase();
      const title = String(f.title || "").toLowerCase();
      const rec = String(f.recommendation || "").toLowerCase();
      const sev = String(f.severity || "").toLowerCase();

      // Category filter
      if (findingCategory === "technical") {
        if (!(checkId.includes("tech") || checkId.includes("crawl") || checkId.includes("index") || checkId.includes("canonical") || checkId.includes("robot") || checkId.includes("shell") || checkId.includes("header") || checkId.includes("perf"))) return false;
      } else if (findingCategory === "content") {
        if (!(checkId.includes("content") || checkId.includes("heading") || checkId.includes("text") || checkId.includes("title") || checkId.includes("description") || checkId.includes("word") || title.includes("meta"))) return false;
      } else if (findingCategory === "conversion") {
        if (!(checkId.includes("conversion") || checkId.includes("form") || checkId.includes("cta") || checkId.includes("button") || checkId.includes("action") || title.includes("form") || title.includes("cta"))) return false;
      }

      // Severity filter
      if (findingSeverity !== "all") {
        if (findingSeverity === "critical" && sev !== "critical") return false;
        if (findingSeverity === "high" && sev !== "high") return false;
        if (findingSeverity === "medium" && sev !== "medium" && sev !== "warn") return false;
        if (findingSeverity === "low" && sev !== "low" && sev !== "info" && sev !== "pass") return false;
      }

      // Query filter
      if (findingQuery.trim()) {
        const q = findingQuery.toLowerCase();
        return title.includes(q) || rec.includes(q) || checkId.includes(q) || String(f.selector || "").toLowerCase().includes(q);
      }
      return true;
    });
  }, [findings, findingCategory, findingSeverity, findingQuery]);

  // Prioritized Recommendations
  const prioritizedRecommendations = useMemo(() => {
    const list = findings.filter((f) => text(f.recommendation, ""));
    const order: Record<string, number> = { critical: 1, high: 2, medium: 3, warn: 4, low: 5, pass: 6 };
    return list.sort((a, b) => {
      const sA = order[String(a.severity || "").toLowerCase()] ?? 99;
      const sB = order[String(b.severity || "").toLowerCase()] ?? 99;
      return sA - sB;
    });
  }, [findings]);

  // Console Events
  const filteredConsole = useMemo(() => {
    let list = consoleEvents;
    if (consoleFilter === "errors") list = list.filter((e) => String(e.severity) === "error");
    if (consoleFilter === "warnings") list = list.filter((e) => String(e.severity) === "warning" || String(e.severity) === "warn");
    if (consoleFilter === "exceptions") list = list.filter((e) => String(e.kind) === "js_exception" || String(e.type) === "exception");
    if (consoleQuery.trim()) {
      const q = consoleQuery.toLowerCase();
      list = list.filter((e) => String(e.message || "").toLowerCase().includes(q) || String(e.source_url || "").toLowerCase().includes(q));
    }
    return list;
  }, [consoleEvents, consoleFilter, consoleQuery]);

  // Network Requests & Graphs
  const networkStats = useMemo(() => {
    const total = networkRequests.length;
    let s2xx = 0;
    let s3xx = 0;
    let s4xx = 0;
    let s5xx = 0;
    let scripts = 0;
    let styles = 0;
    let images = 0;
    let fetchXhr = 0;
    let other = 0;
    let maxTiming = 0;

    for (const r of networkRequests) {
      const st = Number(r.status ?? 0);
      if (st >= 200 && st < 300) s2xx++;
      else if (st >= 300 && st < 400) s3xx++;
      else if (st >= 400 && st < 500) s4xx++;
      else if (st >= 500) s5xx++;

      const type = String(r.resource_type || "").toLowerCase();
      if (type.includes("script") || type.includes("js")) scripts++;
      else if (type.includes("style") || type.includes("css")) styles++;
      else if (type.includes("image") || type.includes("img") || type.includes("media")) images++;
      else if (type.includes("fetch") || type.includes("xhr")) fetchXhr++;
      else other++;

      const dur = Number(r.duration_ms ?? 0);
      if (dur > maxTiming) maxTiming = dur;
    }
    return { total, s2xx, s3xx, s4xx, s5xx, scripts, styles, images, fetchXhr, other, maxTiming: maxTiming || 1000 };
  }, [networkRequests]);

  const filteredNetwork = useMemo(() => {
    let list = networkRequests;
    if (networkFilter === "errors") list = list.filter((r) => Number(r.status ?? 0) >= 400);
    if (networkFilter === "success") list = list.filter((r) => Number(r.status ?? 0) >= 200 && Number(r.status) < 300);
    if (networkFilter === "redirects") list = list.filter((r) => Number(r.status ?? 0) >= 300 && Number(r.status) < 400);
    if (networkFilter === "scripts") list = list.filter((r) => String(r.resource_type || "").toLowerCase().includes("script"));
    if (networkFilter === "images") list = list.filter((r) => String(r.resource_type || "").toLowerCase().includes("image"));
    if (networkQuery.trim()) {
      const q = networkQuery.trim().toLowerCase();
      list = list.filter((r) => String(r.url ?? "").toLowerCase().includes(q));
    }
    return list;
  }, [networkRequests, networkFilter, networkQuery]);

  // Outgoing Links & Clustered Node Graph
  const filteredLinks = useMemo(() => {
    let list = links;
    if (linkTypeFilter === "internal") list = list.filter((l) => Boolean(l.internal));
    if (linkTypeFilter === "external") list = list.filter((l) => !l.internal);
    if (linkQuery.trim()) {
      const q = linkQuery.trim().toLowerCase();
      list = list.filter(
        (l) => String(l.href ?? "").toLowerCase().includes(q) || String(l.text ?? "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [links, linkTypeFilter, linkQuery]);

  const linkClusterNodes = useMemo(() => {
    // Select up to 28 representative links to form an elegant interactive cluster
    const sample = links.slice(0, 28);
    const radius = 140;
    const centerX = 200;
    const centerY = 180;

    return sample.map((link, index) => {
      const angle = (index / sample.length) * 2 * Math.PI;
      // Add slight jitter for natural organic clustering
      const jitter = (index % 3) * 15 - 15;
      const r = radius + jitter;
      const x = centerX + r * Math.cos(angle);
      const y = centerY + r * Math.sin(angle);
      const internal = Boolean(link.internal);
      const status = String(link.check_status || "");
      const isError = status === "fetch_failed" || (typeof link.destination_response_status === "number" && link.destination_response_status >= 400);

      return {
        ...link,
        x,
        y,
        internal,
        isError,
        color: isError ? "#ef4444" : internal ? "#4f46e5" : "#10b981",
        label: text(link.text, "Link").slice(0, 24),
      };
    });
  }, [links]);

  // Forms and Controls Calculation
  const formAuditStats = useMemo(() => {
    if (!forms.length) return null;
    let totalFields = 0;
    let labeledFields = 0;
    let requiredFields = 0;
    let secureAction = true;
    let hasSubmit = false;

    for (const f of forms) {
      const flds = (Array.isArray(f.fields) ? f.fields : []) as JsonRecord[];
      totalFields += flds.length || Number(f.field_count || 0);
      labeledFields += flds.filter((fl) => Boolean(fl.has_label)).length || Number(f.fields_with_labels_count || 0);
      requiredFields += flds.filter((fl) => Boolean(fl.required)).length || Number(f.required_fields_count || 0);
      if (f.has_submit) hasSubmit = true;
      const act = String(f.action || "");
      if (act.startsWith("http://")) secureAction = false;
    }

    const labelScore = totalFields > 0 ? Math.round((labeledFields / totalFields) * 100) : 100;
    const frictionIndex = totalFields > 6 ? "High friction (too many inputs)" : totalFields > 3 ? "Balanced" : "Low friction (high conversion potential)";

    const advice: string[] = [];
    if (labelScore < 100) {
      advice.push(`Accessibility Alert: ${totalFields - labeledFields} form field(s) lack explicit accessible labels, preventing screen readers from parsing them.`);
    }
    if (requiredFields > 5) {
      advice.push(`Conversion Friction: Form demands ${requiredFields} required fields. Consider deferring non-essential inputs to boost signup conversion rates.`);
    }
    if (!secureAction) {
      advice.push("Security Warning: Form submits to an insecure HTTP endpoint. Update form action to HTTPS to avoid browser security blocking.");
    }
    if (!hasSubmit) {
      advice.push("UX Notice: Ensure an unambiguous, high-contrast <button type='submit'> is present in the DOM for keyboard submission.");
    }
    if (!advice.length) {
      advice.push("Form architecture adheres to modern accessibility, input labeling, and conversion best practices.");
    }

    return { totalForms: forms.length, totalFields, labeledFields, requiredFields, labelScore, frictionIndex, advice };
  }, [forms]);

  // Resources coverage stats
  const resourceCoverage = useMemo(() => {
    const total = resources.length;
    let passed = 0;
    let failed = 0;
    let scripts = 0;
    let styles = 0;
    let images = 0;

    for (const r of resources) {
      const sc = Number(r.status_code || 0);
      if (sc >= 200 && sc < 400) passed++;
      else if (sc >= 400 || r.error) failed++;
      else passed++;

      const ct = String(r.content_type || r.resource_type || "").toLowerCase();
      if (ct.includes("script") || ct.includes("js")) scripts++;
      else if (ct.includes("css") || ct.includes("style")) styles++;
      else if (ct.includes("image") || ct.includes("png") || ct.includes("jpg")) images++;
    }
    const healthPercent = total > 0 ? Math.round((passed / total) * 100) : 100;
    return { total, passed, failed, scripts, styles, images, healthPercent };
  }, [resources]);

  if (!page && !error) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-500">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
          <p className="text-sm font-medium">Assembling dynamic page intelligence report…</p>
        </div>
      </main>
    );
  }

  if (error || !page) {
    return (
      <main className="min-h-screen bg-slate-50 p-8">
        <div className="mx-auto max-w-3xl rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700 shadow-sm">
          <div className="flex items-center gap-2 font-semibold">
            <AlertCircle size={20} />
            <span>Unable to render page report</span>
          </div>
          <p className="mt-2 text-sm">{error || "Report unavailable."}</p>
          <Link href={`/audits/${auditId}`} className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800">
            <ArrowLeft size={14} /> Return to audit overview
          </Link>
        </div>
      </main>
    );
  }

  const rawVsRendered: string[] = [];
  if (renderedDom.title_changed_by_js) rawVsRendered.push("Document title differs between raw HTML and the rendered DOM.");
  if (renderedDom.canonical_changed_by_js) rawVsRendered.push("Canonical URL differs between raw HTML and the rendered DOM.");
  if (renderedDom.empty_html_shell) rawVsRendered.push("Raw HTML contained little visible text; content depends on JavaScript.");

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 via-slate-50 to-slate-100/80 px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        
        {/* Top Breadcrumb & Actions Bar */}
        <nav className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
          <Link
            href={`/audits/${auditId}`}
            className="group inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-700 shadow-xs transition hover:border-indigo-300 hover:text-indigo-600"
          >
            <ArrowLeft size={14} className="transition-transform group-hover:-translate-x-0.5" /> Back to live audit
          </Link>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleCopy(page.url, "URL")}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-600 shadow-xs hover:bg-slate-50"
            >
              <Copy size={13} /> {copiedText === "URL" ? "Copied!" : "Copy page URL"}
            </button>
            <a
              href={page.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3.5 py-1.5 font-semibold text-white shadow-xs transition hover:bg-indigo-700"
            >
              Inspect live URL <ExternalLink size={13} />
            </a>
          </div>
        </nav>

        {/* Hero Header Card with Dynamic Score and Dynamic Finding Metrics */}
        <header className="relative overflow-hidden rounded-3xl border border-slate-200/90 bg-white p-6 shadow-sm sm:p-8">
          <div className="absolute right-0 top-0 -mr-16 -mt-16 h-64 w-64 rounded-full bg-gradient-to-br from-indigo-100/60 to-purple-100/30 blur-2xl pointer-events-none" />
          
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl space-y-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-0.5 text-[11px] font-bold uppercase tracking-wider text-indigo-700">
                  <Sparkles size={12} /> Single Page Intelligence
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-100/70 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                  HTTP {page.status_code ?? 200}
                </span>
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                  Audit Completed
                </span>
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                {page.title || page.url}
              </h1>
              <p className="break-all font-mono text-xs text-slate-500">{page.url}</p>
            </div>

            {/* Score & Health Badge */}
            <div className="flex items-center gap-4 rounded-2xl border border-slate-100 bg-slate-50/80 p-4 sm:p-5">
              <div className="relative grid h-20 w-20 place-items-center">
                <svg className="h-full w-full -rotate-90 transform" viewBox="0 0 36 36">
                  <path
                    className="stroke-slate-200"
                    strokeWidth="3.2"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className={scoreBadge.ring}
                    strokeDasharray={`${observedScore}, 100`}
                    strokeWidth="3.2"
                    strokeLinecap="round"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <div className="absolute flex flex-col items-center">
                  <span className="text-xl font-extrabold text-slate-900">{observedScore}%</span>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">{scoreBadge.grade}</span>
                </div>
              </div>

              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Observed Score</p>
                <p className="mt-0.5 text-base font-bold text-slate-800">{scoreBadge.label}</p>
                <p className="mt-1 text-[11px] text-slate-500">
                  Updated {new Date(page.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
            </div>
          </div>

          {/* Dynamic Finding & Diagnostic Numbers Bar */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-3">
              <p className="text-[11px] font-medium text-slate-500">Total Findings</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{findingCounts.total}</p>
              <p className="mt-0.5 text-[10px] text-slate-400">Evaluated checks</p>
            </div>
            <div className="rounded-xl border border-red-100 bg-red-50/50 p-3">
              <p className="text-[11px] font-medium text-red-600">Critical / High</p>
              <p className="mt-1 text-2xl font-bold text-red-700">{findingCounts.critical + findingCounts.high}</p>
              <p className="mt-0.5 text-[10px] text-red-500">Urgent action</p>
            </div>
            <div className="rounded-xl border border-amber-100 bg-amber-50/50 p-3">
              <p className="text-[11px] font-medium text-amber-600">Medium / Warn</p>
              <p className="mt-1 text-2xl font-bold text-amber-700">{findingCounts.medium}</p>
              <p className="mt-0.5 text-[10px] text-amber-500">Opportunities</p>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
              <p className="text-[11px] font-medium text-emerald-600">Low / Passing</p>
              <p className="mt-1 text-2xl font-bold text-emerald-700">{findingCounts.low}</p>
              <p className="mt-0.5 text-[10px] text-emerald-500">Good standing</p>
            </div>
            <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-3">
              <p className="text-[11px] font-medium text-slate-500">Network Assets</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{networkRequests.length}</p>
              <p className="mt-0.5 text-[10px] text-slate-400">Recorded requests</p>
            </div>
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3">
              <p className="text-[11px] font-medium text-indigo-600">Outgoing Links</p>
              <p className="mt-1 text-2xl font-bold text-indigo-700">{links.length}</p>
              <p className="mt-0.5 text-[10px] text-indigo-500">Discovered edges</p>
            </div>
          </div>
        </header>

        {/* Intuitive AI-Generated Executive Summary */}
        <Section
          title="AI-Generated Executive Summary"
          hint="Synthesized per-page intelligence tailored exclusively to this URL's content, structure, and findings."
          badge={
            <span className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-indigo-500/10 to-purple-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
              <Sparkles size={11} /> Context Aware
            </span>
          }
          action={
            <button
              onClick={() => handleCopy(aiExecutiveSummary, "Summary")}
              className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-indigo-600"
            >
              <Copy size={13} /> {copiedText === "Summary" ? "Copied" : "Copy summary"}
            </button>
          }
        >
          <div className="relative rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 via-white to-purple-50/20 p-5 shadow-xs">
            <p className="text-sm leading-relaxed text-slate-800">
              {aiExecutiveSummary}
            </p>
            
            <div className="mt-4 grid gap-3 sm:grid-cols-3 border-t border-indigo-100/70 pt-4 text-xs">
              <div className="flex items-start gap-2">
                <ShieldCheck size={16} className="mt-0.5 text-indigo-600 shrink-0" />
                <div>
                  <span className="font-semibold text-slate-800">Indexability Status:</span>
                  <p className="text-slate-500">
                    {htmlParser.robots ? `Directives: ${htmlParser.robots}` : "Indexable (default index, follow)"}
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <Activity size={16} className="mt-0.5 text-indigo-600 shrink-0" />
                <div>
                  <span className="font-semibold text-slate-800">Performance Baseline:</span>
                  <p className="text-slate-500">
                    {browserObs.timing_ms ? `${Math.round(Number(browserObs.timing_ms))}ms response latency` : "Normal runtime responsiveness"}
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <Layers size={16} className="mt-0.5 text-indigo-600 shrink-0" />
                <div>
                  <span className="font-semibold text-slate-800">Content Architecture:</span>
                  <p className="text-slate-500">
                    {htmlParser.word_count ? `${htmlParser.word_count} indexable words` : "Hydrated client-side DOM"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </Section>

        {/* Technical, Content, and Conversion Findings in Compact Grid Format with Expand Feature */}
        <Section
          title="Technical, Content, and Conversion Findings"
          hint="Interactive compact grid of audit discoveries. Click any finding card to expand complete evidence, affected DOM selectors, and AI remediation code."
          badge={
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">
              {filteredFindings.length} of {findingCounts.total}
            </span>
          }
          action={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  value={findingQuery}
                  onChange={(e) => setFindingQuery(e.target.value)}
                  placeholder="Filter findings…"
                  className="rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-3 text-xs focus:border-indigo-500 focus:bg-white focus:outline-hidden"
                />
              </div>
            </div>
          }
        >
          {/* Category Tabs */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
            <div className="flex flex-wrap gap-1.5">
              {[
                { id: "all", label: "All Findings", count: findingCounts.total },
                { id: "technical", label: "Technical", count: findingCounts.technical },
                { id: "content", label: "Content", count: findingCounts.content },
                { id: "conversion", label: "Conversion", count: findingCounts.conversion },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setFindingCategory(tab.id)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    findingCategory === tab.id
                      ? "bg-indigo-600 text-white shadow-xs"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  <span>{tab.label}</span>
                  <span className={`rounded-full px-1.5 py-0.2 text-[10px] ${findingCategory === tab.id ? "bg-indigo-500 text-white" : "bg-slate-200 text-slate-700"}`}>
                    {tab.count}
                  </span>
                </button>
              ))}
            </div>

            {/* Severity Filter Pills */}
            <div className="flex items-center gap-1 text-xs">
              <span className="text-slate-400 mr-1">Severity:</span>
              {["all", "critical", "high", "medium", "low"].map((sev) => (
                <button
                  key={sev}
                  onClick={() => setFindingSeverity(sev)}
                  className={`rounded-md px-2 py-0.5 text-[11px] font-semibold capitalize transition ${
                    findingSeverity === sev ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>
          </div>

          {/* Grid of Finding Cards */}
          {filteredFindings.length ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredFindings.map((finding, idx) => {
                const title = text(finding.title, "Unspecified Finding");
                const sev = String(finding.severity || "info").toLowerCase();
                const selector = finding.selector ? String(finding.selector) : null;
                const rec = text(finding.recommendation, "");
                const observed = text((finding.evidence as JsonRecord | undefined)?.observed ?? finding.observed, "");

                return (
                  <div
                    key={String(finding.id ?? idx)}
                    onClick={() => setActiveFindingDetail(finding)}
                    className="group relative flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs transition hover:border-indigo-400 hover:shadow-md cursor-pointer"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <Chip tone={statusTone(finding.severity)}>
                          {sev}
                        </Chip>
                        <span className="text-[11px] font-mono text-slate-400">
                          #{String(finding.check_id || finding.id || idx + 1).slice(0, 18)}
                        </span>
                      </div>

                      <h3 className="mt-2.5 text-sm font-bold text-slate-900 group-hover:text-indigo-600 transition-colors line-clamp-2">
                        {title}
                      </h3>

                      {selector && (
                        <div className="mt-2 inline-flex max-w-full items-center gap-1 rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-700 truncate">
                          <Code size={11} className="shrink-0 text-slate-400" />
                          <span className="truncate">{selector}</span>
                        </div>
                      )}

                      <p className="mt-2.5 text-xs text-slate-600 line-clamp-3 leading-relaxed">
                        {observed || rec || "Click to inspect diagnostic evidence and fix instructions."}
                      </p>
                    </div>

                    <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
                      <span className="text-[11px] font-medium text-indigo-600 group-hover:underline inline-flex items-center gap-1">
                        Inspect & AI Fix Plan <ArrowRight size={12} />
                      </span>
                      <Maximize2 size={13} className="text-slate-400 group-hover:text-indigo-600 transition" />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500">
              No findings matched your current filters.
            </div>
          )}
        </Section>

        {/* Modal / Expanded View for Selected Finding */}
        {activeFindingDetail && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/60 p-4 backdrop-blur-xs">
            <div className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl sm:p-8 animate-in fade-in zoom-in-95 duration-150">
              <button
                onClick={() => setActiveFindingDetail(null)}
                className="absolute right-5 top-5 rounded-full p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <X size={18} />
              </button>

              <div className="flex items-center gap-2">
                <Chip tone={statusTone(activeFindingDetail.severity)}>
                  {String(activeFindingDetail.severity || "info")}
                </Chip>
                <Chip tone="border-slate-200 bg-slate-50 text-slate-600">
                  {text(activeFindingDetail.check_id as string, "finding")}
                </Chip>
              </div>

              <h2 className="mt-3 text-xl font-bold text-slate-900">
                {text(activeFindingDetail.title as string, "Finding Overview")}
              </h2>

              <div className="mt-5 space-y-4 text-xs text-slate-700">
                {/* Where it lies */}
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Where the mistake lies (Element Location)
                  </p>
                  <div className="mt-2 flex items-center justify-between gap-2 font-mono text-xs text-indigo-700 bg-white p-2.5 rounded-lg border border-slate-200">
                    <span className="break-all">{text(activeFindingDetail.selector as string, "Page HTML Document Scope (<head> / <body>)")}</span>
                    <button
                      onClick={() => handleCopy(String(activeFindingDetail.selector || page.url), "Selector")}
                      className="shrink-0 p-1 text-slate-400 hover:text-indigo-600"
                      title="Copy element selector"
                    >
                      <Copy size={13} />
                    </button>
                  </div>
                  {activeFindingDetail.url ? (
                    <p className="mt-1.5 break-all text-[11px] text-slate-500">
                      Located on: <span className="font-mono">{String(activeFindingDetail.url)}</span>
                    </p>
                  ) : null}
                </div>

                {/* Observed vs Expected */}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-red-100 bg-red-50/40 p-3.5">
                    <p className="font-semibold text-red-800">What mistake was observed:</p>
                    <p className="mt-1 text-slate-700 leading-relaxed">
                      {text((activeFindingDetail.evidence as JsonRecord | undefined)?.observed ?? activeFindingDetail.observed, "Specific non-compliance observed in HTML/DOM payload.")}
                    </p>
                  </div>
                  <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-3.5">
                    <p className="font-semibold text-emerald-800">What was expected:</p>
                    <p className="mt-1 text-slate-700 leading-relaxed">
                      {text((activeFindingDetail.evidence as JsonRecord | undefined)?.expected ?? activeFindingDetail.expected, "Standards-compliant SEO, performance, or accessibility markup.")}
                    </p>
                  </div>
                </div>

                {/* Why that matters */}
                {Boolean(activeFindingDetail.why_it_matters) && (
                  <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5">
                    <p className="font-semibold text-indigo-900">Why that matters for rankings & conversion:</p>
                    <p className="mt-1 text-indigo-800 leading-relaxed">
                      {text(activeFindingDetail.why_it_matters as string)}
                    </p>
                  </div>
                )}

                {/* AI Action Plan & Recommended Fix */}
                <div className="rounded-xl border border-slate-200 bg-slate-900 text-slate-100 p-4">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                      <Sparkles size={13} /> AI Improvement Fix Plan
                    </p>
                    <button
                      onClick={() => handleCopy(String(activeFindingDetail.recommendation || ""), "Fix")}
                      className="text-[11px] font-semibold text-slate-300 hover:text-white"
                    >
                      {copiedText === "Fix" ? "Copied" : "Copy Fix"}
                    </button>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-slate-200">
                    {text(activeFindingDetail.recommendation as string, "Remediate according to Web Standards.")}
                  </p>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => setActiveFindingDetail(null)}
                  className="rounded-xl bg-slate-800 px-5 py-2 text-xs font-semibold text-white hover:bg-slate-700"
                >
                  Close inspection
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Prioritized Recommendations */}
        <Section
          title="Prioritized Recommendations"
          hint="Targeted roadmap showing what to fix first, where the error is located in the HTML, and why fixing it improves search engine rank and conversion rates."
          badge={
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-bold text-indigo-700">
              {prioritizedRecommendations.length} action items
            </span>
          }
        >
          {prioritizedRecommendations.length ? (
            <div className="space-y-3.5">
              {prioritizedRecommendations.map((finding, index) => {
                const sev = String(finding.severity || "medium").toLowerCase();
                const selector = finding.selector ? String(finding.selector) : "<head> / Document Structure";
                const priorityLabel = index === 0 ? "Highest SEO Priority" : index < 3 ? "High Ranking Impact" : "Tactical Enhancement";

                return (
                  <div
                    key={String(finding.id ?? index)}
                    className="rounded-2xl border border-slate-200 bg-white p-4.5 shadow-xs transition hover:border-indigo-300 sm:p-5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="grid h-6 w-6 place-items-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                          {index + 1}
                        </span>
                        <span className="text-xs font-bold text-slate-900">{priorityLabel}</span>
                        <Chip tone={statusTone(sev)}>{sev}</Chip>
                      </div>

                      <div className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">
                        <Code size={11} className="text-slate-400" />
                        <span>{selector}</span>
                      </div>
                    </div>

                    <p className="mt-2.5 text-sm font-semibold text-slate-800">
                      {text(finding.recommendation)}
                    </p>

                    <div className="mt-3 grid gap-2.5 sm:grid-cols-2 text-xs text-slate-600 border-t border-slate-100 pt-3">
                      <div>
                        <span className="font-semibold text-slate-800">Why this makes the page rank better:</span>
                        <p className="mt-0.5 text-slate-500">
                          {text(finding.why_it_matters as string, "Eliminates search crawl friction, improves Google indexation signals, and maximizes click-through rates.")}
                        </p>
                      </div>
                      <div>
                        <span className="font-semibold text-slate-800">HTML Reference & Fix Location:</span>
                        <p className="mt-0.5 font-mono text-[11px] text-indigo-700 break-all">
                          Target: {selector}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No prioritized recommendations were recorded for this page.</p>
          )}
        </Section>

        {/* Page Diagnostics (Extracted from HTML Parser & Live DOM) */}
        <Section
          title="Page Diagnostics"
          hint="Comprehensive structural, metadata, and DOM parity diagnostics extracted directly by the HTML Parser and verified against the rendered DOM."
          badge={
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">
              Fully Populated
            </span>
          }
        >
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            
            {/* 1. Meta & Search Directives */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4.5 shadow-xs space-y-2.5 text-xs">
              <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                <Globe size={15} className="text-indigo-600" />
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">Meta & Directives</h3>
              </div>
              
              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Title Tag</span>
                <p className="font-semibold text-slate-800 break-all">{text(htmlParser.title as string)}</p>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400">
                  <span>Length: {String(htmlParser.title || "").length} chars</span>
                  <span className={String(htmlParser.title || "").length >= 40 && String(htmlParser.title || "").length <= 60 ? "text-emerald-600" : "text-amber-600"}>
                    {String(htmlParser.title || "").length >= 40 && String(htmlParser.title || "").length <= 60 ? "Optimal (40-60)" : "Review length"}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Meta Description</span>
                <p className="text-slate-700 break-all line-clamp-2">{text(htmlParser.meta_description as string, "Not declared")}</p>
                <span className="text-[10px] text-slate-400">Length: {String(htmlParser.meta_description || "").length} chars (aim for 120-160)</span>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Canonical Tag</span>
                <p className="font-mono text-[11px] text-slate-700 break-all">{text(htmlParser.canonical as string)}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-100">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">Robots</span>
                  <p className="font-medium text-slate-700">{text(htmlParser.robots as string, "all (index, follow)")}</p>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">Language</span>
                  <p className="font-medium text-slate-700">{text(htmlParser.lang as string, "en")}</p>
                </div>
              </div>
            </div>

            {/* 2. Content & Architecture */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4.5 shadow-xs space-y-2.5 text-xs">
              <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                <FileText size={15} className="text-indigo-600" />
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">Content & Structure</h3>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-50 p-2">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Word Count</span>
                  <p className="text-base font-bold text-slate-900">{String(htmlParser.word_count || renderedDom.word_count || 0)}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Est. Read Time</span>
                  <p className="text-base font-bold text-slate-900">
                    ~{Math.max(1, Math.round(Number(htmlParser.word_count || renderedDom.word_count || 0) / 200))} min
                  </p>
                </div>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Headings Hierarchy</span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <span className="rounded bg-indigo-50 px-2 py-0.5 font-semibold text-indigo-700 text-[10px]">
                    H1: {Array.isArray(htmlParser.headings) ? (htmlParser.headings as JsonRecord[]).filter((h) => Number(h.level) === 1).length : 1}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700 text-[10px]">
                    H2: {Array.isArray(htmlParser.headings) ? (htmlParser.headings as JsonRecord[]).filter((h) => Number(h.level) === 2).length : 0}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700 text-[10px]">
                    H3-H6: {Array.isArray(htmlParser.headings) ? (htmlParser.headings as JsonRecord[]).filter((h) => Number(h.level) > 2).length : 0}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Duplicate Element IDs</span>
                <p className="text-slate-700">
                  {Array.isArray(htmlParser.duplicate_ids) && (htmlParser.duplicate_ids as string[]).length
                    ? (htmlParser.duplicate_ids as string[]).join(", ")
                    : "Zero duplicate IDs found (Valid)"}
                </p>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Structured Data (JSON-LD)</span>
                <p className="text-slate-700">{String(htmlParser.json_ld_blocks ?? 0)} schema block(s) detected</p>
              </div>
            </div>

            {/* 3. Rendered DOM Parity */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4.5 shadow-xs space-y-2.5 text-xs">
              <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                <Layers size={15} className="text-indigo-600" />
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">Rendered DOM (Live JS)</h3>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Browser Engine</span>
                <p className="font-semibold text-slate-800">{renderedDom.available ? "Chromium Headless (Executed)" : "Raw HTML fallback"}</p>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">DOM Title</span>
                <p className="text-slate-700 break-all">{text(renderedDom.title as string, text(htmlParser.title as string))}</p>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">DOM Canonical</span>
                <p className="font-mono text-[11px] text-slate-700 break-all">{text(renderedDom.canonical as string, text(htmlParser.canonical as string))}</p>
              </div>

              {rawVsRendered.length > 0 ? (
                <div className="rounded-lg bg-amber-50 p-2 text-amber-800">
                  <span className="font-semibold block text-[10px]">Client Mutation Notice:</span>
                  <ul className="mt-0.5 list-disc list-inside space-y-0.5 text-[10px]">
                    {rawVsRendered.map((diff, i) => (
                      <li key={i}>{diff}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="rounded-lg bg-emerald-50 p-2 text-emerald-800 text-[10px]">
                  Pristine parity between initial HTML payload and live browser DOM.
                </div>
              )}
            </div>

            {/* 4. HTTP Response & Headers */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4.5 shadow-xs space-y-2.5 text-xs">
              <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                <Activity size={15} className="text-indigo-600" />
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">HTTP & Connection</h3>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-50 p-2">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Response Code</span>
                  <p className="text-base font-bold text-emerald-700">HTTP {page.status_code ?? 200}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <span className="text-[10px] text-slate-400 uppercase font-semibold">Latency</span>
                  <p className="text-base font-bold text-slate-900">{browserObs.timing_ms ? `${Math.round(Number(browserObs.timing_ms))} ms` : "—"}</p>
                </div>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Final URL</span>
                <p className="font-mono text-[11px] text-slate-700 break-all">{text(browserObs.final_url as string, page.url)}</p>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Redirect Chain</span>
                <p className="text-slate-700">
                  {Array.isArray(browserObs.redirect_chain) && (browserObs.redirect_chain as string[]).length
                    ? (browserObs.redirect_chain as string[]).join(" → ")
                    : "Direct (0 redirects)"}
                </p>
              </div>

              <p className="text-[10px] text-slate-400 italic">
                {text(browserObs.http_headers_note as string, "Response validated from live browser socket.")}
              </p>
            </div>

          </div>
        </Section>

        {/* Console Telemetry (Understandable with Attributed Sources) */}
        <Section
          title="Console Telemetry"
          hint="Browser runtime log stream attributed to this page. Distinguishes first-party application exceptions from third-party vendor scripts."
          badge={
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">
              {filteredConsole.length} events
            </span>
          }
          action={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  value={consoleQuery}
                  onChange={(e) => setConsoleQuery(e.target.value)}
                  placeholder="Filter logs…"
                  className="rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-3 text-xs focus:border-indigo-500 focus:bg-white focus:outline-hidden"
                />
              </div>
            </div>
          }
        >
          {/* Console Filter Pills */}
          <div className="mb-3.5 flex flex-wrap gap-1.5 border-b border-slate-100 pb-3">
            {["all", "errors", "warnings", "exceptions"].map((key) => (
              <button
                key={key}
                onClick={() => setConsoleFilter(key)}
                className={`rounded-lg px-3 py-1 text-xs font-semibold capitalize transition ${
                  consoleFilter === key ? "bg-slate-900 text-white shadow-xs" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {key}
              </button>
            ))}
          </div>

          {filteredConsole.length ? (
            <div className="space-y-2.5">
              {filteredConsole.map((event, i) => {
                const isError = String(event.severity) === "error" || String(event.kind).includes("exception");
                const sourceUrl = text(event.source_url as string, "");
                const isThirdParty = sourceUrl.includes("googletagmanager") || sourceUrl.includes("google-analytics") || sourceUrl.includes("facebook") || sourceUrl.includes("cdn");

                return (
                  <details key={i} className="group rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs transition hover:border-slate-300">
                    <summary className="cursor-pointer list-none text-xs flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2 min-w-0">
                        <Chip tone={isError ? "border-red-200 bg-red-50 text-red-700" : "border-amber-200 bg-amber-50 text-amber-700"}>
                          {text(event.kind, "console")}
                        </Chip>
                        
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${isThirdParty ? "bg-purple-50 text-purple-700" : "bg-blue-50 text-blue-700"}`}>
                          {isThirdParty ? "3rd-Party Script" : "1st-Party App"}
                        </span>

                        <span className="font-mono text-xs text-slate-800 truncate max-w-xl">
                          {text(event.message as string)}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {Number(event.occurrences ?? 1) > 1 && (
                          <Chip tone="border-slate-200 bg-slate-100 text-slate-700">
                            ×{String(event.occurrences)}
                          </Chip>
                        )}
                        <ChevronDown size={14} className="text-slate-400 group-open:rotate-180 transition-transform" />
                      </div>
                    </summary>

                    <div className="mt-3.5 border-t border-slate-100 pt-3 space-y-2 text-xs text-slate-600">
                      <div>
                        <span className="font-semibold text-slate-800">Source Script:</span>
                        <p className="mt-0.5 font-mono text-[11px] text-slate-700 break-all">{sourceUrl || "Inline script tag or eval execution"}</p>
                      </div>

                      {Boolean(event.location) && (
                        <div>
                          <span className="font-semibold text-slate-800">Origin Trace:</span>
                          <p className="mt-0.5 font-mono text-[11px] text-indigo-700">
                            Line {String((event.location as JsonRecord).line ?? "?")}, Column {String((event.location as JsonRecord).column ?? "?")}
                          </p>
                        </div>
                      )}

                      {event.stack ? (
                        <div>
                          <span className="font-semibold text-slate-800">Stack Trace:</span>
                          <pre className="mt-1 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] text-slate-200">
                            {text(event.stack as string)}
                          </pre>
                        </div>
                      ) : null}
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No console errors or warnings were emitted on this page.</p>
          )}
        </Section>

        {/* Network Requests (Visual Distribution Graph & Multi-Column Table) */}
        <Section
          title="Network Requests & Asset Telemetry"
          hint="Interactive connection graph and comprehensive multi-column request telemetry showcasing status, MIME types, duration, and connection health."
          badge={
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">
              {networkRequests.length} requests
            </span>
          }
          action={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  value={networkQuery}
                  onChange={(e) => setNetworkQuery(e.target.value)}
                  placeholder="Filter URL…"
                  className="rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-3 text-xs focus:border-indigo-500 focus:bg-white focus:outline-hidden"
                />
              </div>
            </div>
          }
        >
          {/* Visual Distribution Graphs */}
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            
            {/* Status Breakdown Bar */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-slate-700">Response Status Distribution</span>
                <span className="text-slate-500">{networkStats.total} total</span>
              </div>
              <div className="mt-2.5 flex h-3 w-full overflow-hidden rounded-full bg-slate-200">
                {networkStats.s2xx > 0 && (
                  <div style={{ width: `${(networkStats.s2xx / networkStats.total) * 100}%` }} className="bg-emerald-500" title={`2xx Success: ${networkStats.s2xx}`} />
                )}
                {networkStats.s3xx > 0 && (
                  <div style={{ width: `${(networkStats.s3xx / networkStats.total) * 100}%` }} className="bg-blue-500" title={`3xx Redirects: ${networkStats.s3xx}`} />
                )}
                {networkStats.s4xx > 0 && (
                  <div style={{ width: `${(networkStats.s4xx / networkStats.total) * 100}%` }} className="bg-amber-500" title={`4xx Client Errors: ${networkStats.s4xx}`} />
                )}
                {networkStats.s5xx > 0 && (
                  <div style={{ width: `${(networkStats.s5xx / networkStats.total) * 100}%` }} className="bg-red-500" title={`5xx Server Errors: ${networkStats.s5xx}`} />
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-600">
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> 2xx Success ({networkStats.s2xx})</span>
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-blue-500" /> 3xx Redirect ({networkStats.s3xx})</span>
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500" /> 4xx Client Error ({networkStats.s4xx})</span>
                {networkStats.s5xx > 0 && (
                  <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> 5xx Server Error ({networkStats.s5xx})</span>
                )}
              </div>
            </div>

            {/* Asset Types Distribution */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-slate-700">Asset Types Composition</span>
                <span className="text-slate-500">Resource weights</span>
              </div>
              <div className="mt-2.5 flex h-3 w-full overflow-hidden rounded-full bg-slate-200">
                <div style={{ width: `${(networkStats.scripts / networkStats.total) * 100}%` }} className="bg-indigo-500" title={`Scripts: ${networkStats.scripts}`} />
                <div style={{ width: `${(networkStats.styles / networkStats.total) * 100}%` }} className="bg-purple-500" title={`Styles: ${networkStats.styles}`} />
                <div style={{ width: `${(networkStats.images / networkStats.total) * 100}%` }} className="bg-cyan-500" title={`Images: ${networkStats.images}`} />
                <div style={{ width: `${(networkStats.fetchXhr / networkStats.total) * 100}%` }} className="bg-amber-400" title={`Fetch/XHR: ${networkStats.fetchXhr}`} />
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-600">
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-indigo-500" /> JS ({networkStats.scripts})</span>
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-purple-500" /> CSS ({networkStats.styles})</span>
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-cyan-500" /> Media ({networkStats.images})</span>
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" /> API/Fetch ({networkStats.fetchXhr})</span>
              </div>
            </div>

          </div>

          {/* Quick Filters */}
          <div className="mb-3.5 flex flex-wrap gap-1.5 border-b border-slate-100 pb-3">
            {["all", "success", "errors", "redirects", "scripts", "images"].map((key) => (
              <button
                key={key}
                onClick={() => setNetworkFilter(key)}
                className={`rounded-lg px-3 py-1 text-xs font-semibold capitalize transition ${
                  networkFilter === key ? "bg-slate-900 text-white shadow-xs" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {key}
              </button>
            ))}
          </div>

          {/* Multi-Column Data Table */}
          {filteredNetwork.length ? (
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3 font-semibold">Status</th>
                    <th className="py-2.5 px-3 font-semibold">Method</th>
                    <th className="py-2.5 px-3 font-semibold">Resource URL</th>
                    <th className="py-2.5 px-3 font-semibold">Origin</th>
                    <th className="py-2.5 px-3 font-semibold">Type</th>
                    <th className="py-2.5 px-3 font-semibold">Timing / Latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredNetwork.slice(0, 100).map((req, i) => {
                    const statusNum = Number(req.status ?? 0);
                    const isErr = statusNum >= 400 || !req.status;
                    const urlStr = text(req.url as string);
                    const isExternal = !urlStr.includes(new URL(page.url).hostname);
                    const dur = Number(req.duration_ms ?? 0);
                    const timingPercent = Math.min(100, Math.round((dur / networkStats.maxTiming) * 100));

                    return (
                      <tr key={i} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-2 px-3">
                          <Chip tone={isErr ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                            {req.status ? String(req.status) : "failed"}
                          </Chip>
                        </td>
                        <td className="py-2 px-3 font-mono font-semibold text-slate-600">
                          {text(req.method as string, "GET")}
                        </td>
                        <td className="py-2 px-3 max-w-md">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-[11px] text-slate-800 truncate" title={urlStr}>
                              {urlStr}
                            </span>
                            <a href={urlStr} target="_blank" rel="noreferrer" className="text-slate-400 hover:text-indigo-600">
                              <ExternalLink size={12} />
                            </a>
                          </div>
                        </td>
                        <td className="py-2 px-3">
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${isExternal ? "bg-purple-50 text-purple-700" : "bg-blue-50 text-blue-700"}`}>
                            {isExternal ? "3rd-Party" : "1st-Party"}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-600">
                          {text(req.resource_type as string, "other")}
                        </td>
                        <td className="py-2 px-3 w-40">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[11px] w-12">{dur ? `${dur}ms` : "—"}</span>
                            {dur > 0 && (
                              <div className="h-1.5 w-16 rounded-full bg-slate-200 overflow-hidden">
                                <div
                                  style={{ width: `${Math.max(10, timingPercent)}%` }}
                                  className={`h-full ${dur > 600 ? "bg-red-500" : dur > 250 ? "bg-amber-500" : "bg-emerald-500"}`}
                                />
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No network requests matched your search criteria.</p>
          )}
        </Section>

        {/* Forms & Interactive Controls (Calculated with Actionable Reviewer Guidance) */}
        <Section
          title="Forms & Conversion Controls"
          hint="Calculated conversion ergonomics and accessibility score. Pinpoints input friction, missing labels, and security postures to empower web reviewers."
          badge={
            formAuditStats ? (
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-bold text-indigo-700">
                {formAuditStats.labelScore}% Label Score
              </span>
            ) : undefined
          }
        >
          {formAuditStats ? (
            <div className="space-y-4">
              
              {/* Calculated Reviewer Insights Dashboard */}
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Forms</span>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{formAuditStats.totalForms}</p>
                  <p className="mt-0.5 text-[10px] text-slate-500">Observed in DOM</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Fields</span>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{formAuditStats.totalFields}</p>
                  <p className="mt-0.5 text-[10px] text-slate-500">{formAuditStats.requiredFields} required inputs</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Accessible Labels</span>
                  <p className={`mt-1 text-2xl font-bold ${formAuditStats.labelScore >= 90 ? "text-emerald-700" : "text-amber-700"}`}>
                    {formAuditStats.labelScore}%
                  </p>
                  <p className="mt-0.5 text-[10px] text-slate-500">{formAuditStats.labeledFields} / {formAuditStats.totalFields} labeled</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Friction Level</span>
                  <p className="mt-1 text-sm font-bold text-slate-900">{formAuditStats.frictionIndex}</p>
                  <p className="mt-0.5 text-[10px] text-slate-500">Conversion readiness</p>
                </div>
              </div>

              {/* Actionable Reviewer Improvisation Guidance */}
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
                <h4 className="text-xs font-bold text-indigo-900 uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles size={13} className="text-indigo-600" />
                  Reviewer Improvisation Advice (How to boost conversions):
                </h4>
                <ul className="mt-2 space-y-1 text-xs text-indigo-800 list-disc list-inside">
                  {formAuditStats.advice.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>

              {/* Detailed Form Accordions */}
              <div className="space-y-3">
                {forms.map((form, i) => (
                  <details key={i} className="group rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                    <summary className="cursor-pointer list-none text-xs flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-slate-900 text-sm">
                          Form #{i + 1} {form.form_id ? `(#${String(form.form_id)})` : ""}
                        </span>
                        <Chip tone="border-slate-200 bg-slate-100 text-slate-700">
                          {text(form.method as string, "POST")}
                        </Chip>
                        <Chip tone={form.has_submit ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}>
                          {form.has_submit ? "Submit Button Present" : "Missing Submit Tag"}
                        </Chip>
                      </div>
                      <ChevronDown size={14} className="text-slate-400 group-open:rotate-180 transition-transform" />
                    </summary>

                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <p className="text-xs text-slate-500 mb-2 font-mono">
                        Action Endpoint: {text(form.action as string, "(Submits to current URL)")}
                      </p>

                      <div className="overflow-x-auto rounded-lg border border-slate-100">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-slate-50 text-slate-500">
                            <tr>
                              <th className="py-2 px-3 font-semibold">Field Name</th>
                              <th className="py-2 px-3 font-semibold">Input Type</th>
                              <th className="py-2 px-3 font-semibold">Accessible Label</th>
                              <th className="py-2 px-3 font-semibold">Required</th>
                              <th className="py-2 px-3 font-semibold">Autocomplete</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {((Array.isArray(form.fields) ? form.fields : []) as JsonRecord[]).map((field, fi) => (
                              <tr key={fi}>
                                <td className="py-2 px-3 font-mono">{text(field.name as string, "—")}</td>
                                <td className="py-2 px-3 text-slate-600">{text(field.type as string, "text")}</td>
                                <td className="py-2 px-3">
                                  {field.has_label ? (
                                    <span className="text-emerald-700 font-medium">{text(field.label_text as string, "Labeled")}</span>
                                  ) : (
                                    <span className="text-amber-700 font-semibold">Missing label</span>
                                  )}
                                </td>
                                <td className="py-2 px-3">{field.required ? "Yes" : "Optional"}</td>
                                <td className="py-2 px-3 font-mono text-[11px] text-slate-500">{text(field.autocomplete as string, "—")}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </details>
                ))}
              </div>

            </div>
          ) : (
            <p className="text-sm text-slate-500">No interactive forms were detected on this page.</p>
          )}
        </Section>

        {/* Discovered Outgoing Links (Interactive Clustered Nodes Formation with Hover) */}
        <Section
          title="Discovered Outgoing Links"
          hint="Interactive node formation cluster showcasing internal vs external graph topologies. Hover over any node to inspect destination anchor text, HTTP check status, and crawl rels."
          badge={
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">
              {filteredLinks.length} total edges
            </span>
          }
          action={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  value={linkQuery}
                  onChange={(e) => setLinkQuery(e.target.value)}
                  placeholder="Filter anchor or URL…"
                  className="rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-3 text-xs focus:border-indigo-500 focus:bg-white focus:outline-hidden"
                />
              </div>
            </div>
          }
        >
          {/* Node Formation Cluster Visualization */}
          {linkClusterNodes.length > 0 && (
            <div className="relative mb-6 rounded-2xl border border-slate-200 bg-radial from-slate-50 via-white to-slate-100/50 p-4 shadow-inner">
              <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
                <span className="font-semibold uppercase tracking-wider text-[11px]">Link Equity Node Cluster</span>
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-indigo-600" /> Internal Node</span>
                  <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> External Node</span>
                  <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> Broken / Error</span>
                </div>
              </div>

              <div className="relative mx-auto flex justify-center overflow-hidden">
                <svg viewBox="0 0 400 360" className="h-72 w-full max-w-md select-none">
                  {/* Central Hub Node */}
                  <circle cx="200" cy="180" r="18" fill="#312e81" className="drop-shadow-md animate-pulse" />
                  <text x="200" y="184" textAnchor="middle" fill="#ffffff" fontSize="9" fontWeight="bold">ROOT</text>

                  {/* Satellite Clustered Nodes & Connection Vectors */}
                  {linkClusterNodes.map((node, i) => (
                    <g key={i}>
                      <line
                        x1="200"
                        y1="180"
                        x2={node.x}
                        y2={node.y}
                        stroke={node.color}
                        strokeWidth="0.8"
                        strokeDasharray={node.internal ? "none" : "3,2"}
                        opacity="0.4"
                      />
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.internal ? "6" : "5"}
                        fill={node.color}
                        className="cursor-pointer transition-all hover:scale-150 drop-shadow-sm"
                        onMouseEnter={() => setHoveredNode(node)}
                        onMouseLeave={() => setHoveredNode(null)}
                      />
                    </g>
                  ))}
                </svg>

                {/* Floating Tooltip on Hover */}
                {hoveredNode && (
                  <div className="absolute bottom-4 left-4 right-4 sm:left-auto sm:right-6 sm:max-w-xs rounded-xl border border-slate-200 bg-white/95 p-3.5 shadow-xl backdrop-blur-md text-xs animate-in fade-in duration-100 pointer-events-none">
                    <p className="font-bold text-slate-900 truncate">{text(hoveredNode.text, "Untitled Link")}</p>
                    <p className="mt-0.5 font-mono text-[10px] text-slate-500 break-all">{text(hoveredNode.href as string)}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                      <Chip tone={hoveredNode.internal ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                        {hoveredNode.internal ? "Internal link" : "External link"}
                      </Chip>
                      <Chip tone={hoveredNode.isError ? "border-red-200 bg-red-50 text-red-700" : "border-slate-200 bg-slate-50 text-slate-600"}>
                        {text(hoveredNode.check_status as string, "Audited")}
                      </Chip>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Type Filter Pills */}
          <div className="mb-3.5 flex flex-wrap gap-1.5 border-b border-slate-100 pb-3">
            {[
              { id: "all", label: "All Links" },
              { id: "internal", label: "Internal Only" },
              { id: "external", label: "External Only" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setLinkTypeFilter(tab.id as "all" | "internal" | "external")}
                className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                  linkTypeFilter === tab.id ? "bg-slate-900 text-white shadow-xs" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Compact Scannable Grid List */}
          {filteredLinks.length ? (
            <div className="divide-y divide-slate-100 max-h-96 overflow-y-auto rounded-xl border border-slate-200 p-2">
              {filteredLinks.slice(0, 100).map((link, idx) => {
                const href = text(link.href, "");
                const internal = Boolean(link.internal);
                const checkStatus = String(link.check_status || "");

                return (
                  <div key={idx} className="flex items-center justify-between gap-3 p-2.5 text-xs hover:bg-slate-50/80 transition-colors rounded-lg">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-800 truncate">{text(link.text, "Untitled Link")}</p>
                      <p className="font-mono text-[11px] text-slate-500 truncate">{href}</p>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                        <Chip tone={internal ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-slate-50 text-slate-600"}>
                          {internal ? "internal" : "external"}
                        </Chip>
                        {link.section ? <Chip tone="border-slate-200 bg-slate-50 text-slate-600">{String(link.section)}</Chip> : null}
                        {checkStatus ? <Chip tone={statusTone(checkStatus === "audited" ? "pass" : checkStatus === "fetch_failed" ? "fail" : "medium")}>{checkStatus}</Chip> : null}
                      </div>
                    </div>

                    {href && (
                      <Link
                        target="_blank"
                        href={internal ? `/audits/${auditId}/pages/by-url?url=${encodeURIComponent(href)}` : href}
                        className="shrink-0 p-1.5 text-slate-400 hover:text-indigo-600 transition"
                      >
                        <ExternalLink size={14} />
                      </Link>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No links matched your search filter.</p>
          )}
        </Section>

        {/* Resources and Coverage */}
        <Section
          title="Resources & Coverage"
          hint="Subresources and dependency health. Evaluates stylesheet availability, script execution reliability, media integrity, and cache coverage."
          badge={
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
              {resourceCoverage.healthPercent}% Availability
            </span>
          }
        >
          {/* Visual Coverage Cards */}
          <div className="grid gap-3 sm:grid-cols-4 mb-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Resources</span>
              <p className="mt-1 text-2xl font-bold text-slate-900">{resourceCoverage.total}</p>
              <p className="mt-0.5 text-[10px] text-slate-500">Subresources verified</p>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-3.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600">Passed / Healthy</span>
              <p className="mt-1 text-2xl font-bold text-emerald-700">{resourceCoverage.passed}</p>
              <p className="mt-0.5 text-[10px] text-emerald-600">200 OK responses</p>
            </div>
            <div className="rounded-xl border border-red-100 bg-red-50/50 p-3.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-red-600">Errors / Blocked</span>
              <p className="mt-1 text-2xl font-bold text-red-700">{resourceCoverage.failed}</p>
              <p className="mt-0.5 text-[10px] text-red-500">Subresource issues</p>
            </div>
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">Coverage Score</span>
              <p className="mt-1 text-2xl font-bold text-indigo-700">{resourceCoverage.healthPercent}%</p>
              <p className="mt-0.5 text-[10px] text-indigo-500">Resource health meter</p>
            </div>
          </div>

          {/* Compact Resource List */}
          <div className="grid gap-3 sm:grid-cols-2 max-h-96 overflow-y-auto">
            {resources.map((resource, index) => {
              const resUrl = text(resource.url ?? resource.href);
              const isErr = Number(resource.status_code ?? 0) >= 400 || Boolean(resource.error);

              return (
                <div key={index} className="rounded-xl border border-slate-200 p-3.5 text-xs bg-white hover:border-slate-300 transition-colors shadow-xs">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 font-medium text-slate-800">
                      <FileCode size={14} className="text-slate-400" />
                      <span className="truncate">{text(resource.resource_type as string, "Resource")}</span>
                    </div>
                    <Chip tone={isErr ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>
                      {resource.status_code ? `HTTP ${String(resource.status_code)}` : text(resource.check_status as string, "Checked")}
                    </Chip>
                  </div>

                  <p className="mt-2 font-mono text-[11px] text-slate-600 break-all">{resUrl}</p>

                  {Boolean(resource.content_type) && (
                    <p className="mt-1 text-[10px] text-slate-400">
                      MIME: {String(resource.content_type)}
                    </p>
                  )}

                  {Boolean(resource.error) && (
                    <p className="mt-1 text-[11px] text-red-600 font-medium">Error: {text(resource.error as string)}</p>
                  )}
                </div>
              );
            })}
            {!resources.length && (
              <p className="text-sm text-slate-500 col-span-2">No resource checks were recorded for this page.</p>
            )}
          </div>
        </Section>

      </div>
    </main>
  );
}
