import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Compass,
  Download,
  ExternalLink,
  Eye,
  FileCode,
  FileSpreadsheet,
  FileText,
  Filter,
  Globe,
  HelpCircle,
  Image as ImageIcon,
  Layers,
  Link2,
  ListFilter,
  Network,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";

import { getAuditReportCsvUrl, getLandingPageReport } from "@/lib/api";
import type {
  ConsolidatedWebsiteReport,
  CrawlURL,
  LandingPageReport,
  PageAuditFinding,
  PageAuditReport,
} from "@/types/api";
import {
  FINDING_CATEGORIES,
  FindingCategory,
  categorizeFinding,
} from "./types";
import { PageResourceExplorer } from "./page-resource-explorer";
import { MarketingIntelligencePanel } from "./marketing-intelligence-panel";


interface LiveReportPanelProps {
  auditId: string;
  targetUrl: string;
  isCrawlRunning: boolean;
  activeUrl: string;
  activePageReport: PageAuditReport | null;
  pageReportError?: string | null;
  consolidatedReport: ConsolidatedWebsiteReport | null;
  findings: PageAuditFinding[];
  crawlUrls: CrawlURL[];
  pageReports: PageAuditReport[];
  onSelectUrl: (url: string, pageReport?: PageAuditReport) => void;
  onFollowLiveCrawler?: () => void;
  isFollowingCrawler?: boolean;
}

export function LiveReportPanel({
  auditId,
  targetUrl,
  isCrawlRunning,
  activeUrl,
  activePageReport,
  pageReportError,
  consolidatedReport,
  findings,
  crawlUrls,
  pageReports,
  onSelectUrl,
  onFollowLiveCrawler,
  isFollowingCrawler,
}: LiveReportPanelProps) {
  // Navigation sub-tabs on the left report panel
  const [panelTab, setPanelTab] = useState<"landing" | "marketing" | "findings" | "technical_functionality" | "executive" | "explorer">("landing");
  const [activeTaskDAgent, setActiveTaskDAgent] = useState<"all" | "functionality" | "technical" | "connectivity">("all");

  // Landing Page Holistic Analysis States (Task B)
  const [landingReport, setLandingReport] = useState<LandingPageReport | null>(
    activePageReport?.report_json?.landing_page_analysis || null
  );
  const [landingLoading, setLandingLoading] = useState(false);
  const [landingPerspectiveTab, setLandingPerspectiveTab] = useState<"marketing" | "sales" | "subject_matter" | "seo_functionality">("marketing");
  const [activeGapTab, setActiveGapTab] = useState<"missing" | "objections" | "trust" | "messaging" | "opportunities">("missing");
  const [expandedLandingFindingId, setExpandedLandingFindingId] = useState<string | null>(null);

  // Synchronize or fetch landing page report when active page or audit changes
  useEffect(() => {
    if (activePageReport?.report_json?.landing_page_analysis) {
      setLandingReport(activePageReport.report_json.landing_page_analysis);
      return;
    }

    let isMounted = true;
    setLandingLoading(true);
    getLandingPageReport(auditId, { url: activeUrl, pageId: activePageReport?.id })
      .then((rep) => {
        if (isMounted) {
          setLandingReport(rep);
        }
      })
      .catch(() => {
        // Fallback gracefully without throwing
      })
      .finally(() => {
        if (isMounted) setLandingLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [activePageReport, activeUrl, auditId]);

  const handleRefreshLanding = useCallback(async () => {
    setLandingLoading(true);
    try {
      const rep = await getLandingPageReport(auditId, {
        url: activeUrl,
        pageId: activePageReport?.id,
        refresh: true,
      });
      setLandingReport(rep);
    } catch {
      // Ignored
    } finally {
      setLandingLoading(false);
    }
  }, [activePageReport?.id, activeUrl, auditId]);

  // Filtering & Search states
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<FindingCategory | "all">("all");
  const [selectedSeverity, setSelectedSeverity] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(null);


  // Group findings into categories
  const findingsByCategory = useMemo(() => {
    const map = new Map<FindingCategory, PageAuditFinding[]>();
    for (const cat of FINDING_CATEGORIES) {
      map.set(cat.key, []);
    }

    for (const f of findings) {
      const cat = categorizeFinding(f.check_id, f.title, f.category, f.agent_id);
      const list = map.get(cat) || [];
      list.push(f);
      map.set(cat, list);
    }
    return map;
  }, [findings]);

  // Filtered findings list
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      // 1. Category filter
      if (selectedCategory !== "all") {
        const cat = categorizeFinding(f.check_id, f.title, f.category, f.agent_id);
        if (cat !== selectedCategory) return false;
      }

      // 2. Severity filter
      if (selectedSeverity !== "all") {
        if ((f.severity || "").toLowerCase() !== selectedSeverity.toLowerCase()) {
          return false;
        }
      }

      // 3. Status filter
      if (selectedStatus !== "all") {
        const st = (f.status || "").toLowerCase();
        if (selectedStatus === "fail" && st !== "fail" && st !== "failed") return false;
        if (selectedStatus === "warn" && st !== "warn" && st !== "warning") return false;
        if (selectedStatus === "pass" && st !== "pass" && st !== "passed") return false;
        if (selectedStatus === "skipped" && st !== "skipped" && st !== "skip") return false;
        if (selectedStatus === "inconclusive" && st !== "inconclusive" && st !== "unknown" && st !== "unavailable") {
          return false;
        }
      }

      // 4. Search query
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          f.title.toLowerCase().includes(q) ||
          f.check_id.toLowerCase().includes(q) ||
          (f.recommendation && f.recommendation.toLowerCase().includes(q)) ||
          (f.page_url && f.page_url.toLowerCase().includes(q))
        );
      }

      return true;
    });
  }, [findings, selectedCategory, selectedSeverity, selectedStatus, searchQuery]);

  // Real severity counts
  const severityCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0, info: 0, fail: 0, warn: 0, pass: 0 };
    for (const f of findings) {
      const sev = (f.severity || "").toLowerCase();
      if (sev in counts) {
        counts[sev as keyof typeof counts]++;
      }
      const st = (f.status || "").toLowerCase();
      if (st === "fail" || st === "failed") counts.fail++;
      if (st === "warn" || st === "warning") counts.warn++;
      if (st === "pass" || st === "passed") counts.pass++;
    }
    return counts;
  }, [findings]);

  // Overall score
  const overallScore = consolidatedReport?.score?.percent ?? activePageReport?.score_percent ?? null;

  return (
    <div className="flex flex-col h-full bg-slate-50 border-r border-slate-200 text-slate-800 overflow-hidden">
      {/* Top Header / Summary Bar */}
      <div className="p-3 bg-white border-b border-slate-200 shadow-sm shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-bold text-sm text-slate-900 tracking-tight">Audit Intelligence Report</span>
            {isCrawlRunning ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-200">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                </span>
                <span>Streaming Findings...</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                <Check className="w-3 h-3" />
                <span>Audit Complete</span>
              </span>
            )}
          </div>

          {/* CSV Export & Actions */}
          <div className="flex items-center gap-1.5">
            {onFollowLiveCrawler && isCrawlRunning && (
              <button
                onClick={onFollowLiveCrawler}
                className={`px-2 py-1 rounded text-xs font-medium transition flex items-center gap-1 ${
                  isFollowingCrawler
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-slate-100 text-slate-600 hover:text-slate-900"
                }`}
                title="Follow the active crawl URL automatically"
              >
                <Compass className="w-3 h-3" />
                <span>Auto-follow</span>
              </button>
            )}

            <a
              href={getAuditReportCsvUrl(auditId)}
              target="_blank"
              rel="noopener noreferrer"
              className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition flex items-center gap-1"
              title="Download consolidated findings as CSV"
            >
              <Download className="w-3 h-3" />
              <span>Export CSV</span>
            </a>
          </div>
        </div>

        {/* Quick Stats Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Domain Health Score</span>
            <span
              className={`text-base font-bold font-mono mt-0.5 block ${
                overallScore === null
                  ? "text-slate-400"
                  : overallScore >= 80
                  ? "text-emerald-600"
                  : overallScore >= 50
                  ? "text-amber-600"
                  : "text-red-600"
              }`}
            >
              {overallScore !== null ? `${overallScore.toFixed(0)}%` : isCrawlRunning ? "Calculating..." : "—"}
            </span>
          </div>

          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Total Findings</span>
            <span className="text-base font-bold text-slate-900 font-mono mt-0.5 block">
              {findings.length}
            </span>
          </div>

          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Confirmed Issues</span>
            <span className="text-base font-bold text-red-600 font-mono mt-0.5 block">
              {severityCounts.fail}
            </span>
          </div>

          <div className="p-2 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Warnings & Passed</span>
            <span className="text-base font-bold text-slate-700 font-mono mt-0.5 block">
              {severityCounts.warn} <span className="text-slate-400 font-normal">/ {severityCounts.pass}</span>
            </span>
          </div>
        </div>

        {/* Panel View Tabs */}
        <div className="flex items-center gap-1 mt-3 border-t border-slate-100 pt-2 text-xs overflow-x-auto">
          <button
            onClick={() => setPanelTab("landing")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
              panelTab === "landing"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            <span>Landing Page Analysis</span>
          </button>

          <button
            onClick={() => setPanelTab("marketing")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
              panelTab === "marketing"
                ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-sm font-semibold"
                : "text-slate-700 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <BrainCircuit className="w-3.5 h-3.5 text-purple-400" />
            <span>Marketing Intelligence Agent</span>
          </button>

          <button
            onClick={() => setPanelTab("findings")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
              panelTab === "findings"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Findings Stream ({findings.length})</span>
          </button>

          <button
            onClick={() => setPanelTab("technical_functionality")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
              panelTab === "technical_functionality"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-indigo-300" />
            <span>Technical & Functionality</span>
          </button>

          <button
            onClick={() => setPanelTab("executive")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
              panelTab === "executive"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Executive Dimensions</span>
          </button>

          <button
            onClick={() => setPanelTab("explorer")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
              panelTab === "explorer"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <Compass className="w-3.5 h-3.5" />
            <span>Page & Resource Explorer ({crawlUrls.length})</span>
          </button>
        </div>
      </div>


      {/* Main Left Content Area */}
      <div className="flex-1 overflow-auto">
        {pageReportError && !activePageReport && (
          <div className="p-4 mx-3 my-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-sm">No report available for this page</div>
              <div className="text-amber-700 mt-1">
                A page audit report is not available for <span className="font-mono bg-amber-100/60 px-1 py-0.5 rounded">{activeUrl}</span>.
              </div>
            </div>
          </div>
        )}

        {/* Marketing Intelligence Agent Tab */}
        {panelTab === "marketing" && (
          <MarketingIntelligencePanel
            auditId={auditId}
            targetUrl={targetUrl}
            activeUrl={activeUrl}
            onSelectUrl={onSelectUrl}
          />
        )}

        {/* TASK B: Landing Page Holistic Analysis Tab */}
        {panelTab === "landing" && (
          <div className="p-3 sm:p-4 space-y-4 text-xs">
            {/* Top Page Context Bar */}
            <div className="p-3.5 rounded-lg bg-white border border-slate-200 shadow-sm space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-bold text-slate-900 text-xs sm:text-sm truncate">
                    {landingReport?.page_title || activePageReport?.title || "Landing Page Analysis"}
                  </span>
                  <a
                    href={activeUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-400 hover:text-blue-600 transition shrink-0"
                    title="Open live URL"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={handleRefreshLanding}
                    disabled={landingLoading}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-medium transition disabled:opacity-50"
                    title="Run fresh AI agent analysis for this landing page"
                  >
                    <RefreshCw className={`w-3 h-3 ${landingLoading ? "animate-spin" : ""}`} />
                    <span>{landingLoading ? "Analyzing..." : "Re-analyze Page"}</span>
                  </button>

                  <span
                    className={`font-mono font-bold text-xs px-2.5 py-1 rounded border ${
                      (landingReport?.overall_score ?? 0) >= 80
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : (landingReport?.overall_score ?? 0) >= 50
                        ? "bg-amber-50 text-amber-700 border-amber-200"
                        : "bg-red-50 text-red-700 border-red-200"
                    }`}
                  >
                    {landingReport?.overall_score ?? (activePageReport?.score_percent ? Math.round(activePageReport.score_percent) : 75)}% Health
                  </span>
                </div>
              </div>

              {/* URL & Purpose Strip */}
              <div className="flex flex-wrap items-center gap-2 text-[11px] pt-1 border-t border-slate-100">
                <span className="text-slate-400 font-mono truncate max-w-[280px] sm:max-w-md">
                  {activeUrl}
                </span>
                <span className="text-slate-300">·</span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px]">
                  <Zap className="w-3 h-3 text-indigo-500" />
                  <span>{landingReport?.landing_page_purpose || "Purpose not observed"}</span>
                </span>
                {landingReport?.ib_context?.is_ib_page && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-amber-50 text-amber-800 border border-amber-200 text-[10px]">
                    <BookOpen className="w-3 h-3 text-amber-600" />
                    <span>IB Curriculum Verified</span>
                  </span>
                )}
              </div>
            </div>

            {/* AI Holistic Executive Summary Card */}
            {landingReport?.executive_summary && (
              <div className="p-4 rounded-lg bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 text-white shadow-md border border-slate-800 space-y-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-indigo-900/60 pb-2.5">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-amber-400" />
                    <span className="font-bold text-sm tracking-tight text-white">
                      Landing Page Executive Synthesis
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      Marketing · Sales · Subject Expertise · SEO
                    </span>
                  </div>

                  <span className="text-indigo-300 font-mono text-[11px]">
                    Band: {landingReport.score_band || "not scored"}
                  </span>
                </div>

                <p className="text-slate-200 text-xs leading-relaxed font-sans">
                  {landingReport.executive_summary}
                </p>

                {/* Audience & Commercial Offer Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-2 border-t border-indigo-900/40 text-[11px]">
                  {/* Intended Audience Profile */}
                  <div className="p-2.5 rounded bg-white/5 border border-white/10 space-y-1.5">
                    <span className="font-semibold text-indigo-300 flex items-center gap-1.5">
                      <Eye className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Intended Audience Profile</span>
                    </span>
                    <div className="space-y-1 text-slate-300 text-[11px]">
                      {landingReport.intended_audience?.target_profiles && (
                        <p><span className="text-slate-400">Target Personas:</span> {landingReport.intended_audience.target_profiles.join("; ")}</p>
                      )}
                      {landingReport.intended_audience?.primary_needs && (
                        <p><span className="text-slate-400">Core Needs:</span> {landingReport.intended_audience.primary_needs.join("; ")}</p>
                      )}
                      <p className="font-mono text-[10px] text-indigo-200">
                        Intent: {landingReport.intended_audience?.search_intent || "Not observed"} · Stage: {landingReport.intended_audience?.journey_stage || "Not observed"}
                      </p>
                    </div>
                  </div>

                  {/* Commercial Offer Profile */}
                  <div className="p-2.5 rounded bg-white/5 border border-white/10 space-y-1.5">
                    <span className="font-semibold text-emerald-300 flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Commercial Offer & Positioning</span>
                    </span>
                    <div className="space-y-1 text-slate-300 text-[11px]">
                      <p><span className="text-slate-400">Value Proposition:</span> {landingReport.commercial_offer?.value_proposition || "Not observed"}</p>
                      <p><span className="text-slate-400">Positioning:</span> {landingReport.commercial_offer?.positioning || "Not observed"}</p>
                      <p className="font-mono text-[10px] text-emerald-200">
                        Pricing Transparency: {landingReport.commercial_offer?.pricing_clarity || "Not observed"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Key Strengths & Critical Blockers */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1 text-[11px]">
                  {landingReport.top_strengths && landingReport.top_strengths.length > 0 && (
                    <div className="p-2.5 rounded bg-emerald-950/30 border border-emerald-500/20 space-y-1">
                      <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Core Page Strengths</span>
                      </span>
                      <ul className="space-y-1 text-slate-300 list-disc list-inside">
                        {landingReport.top_strengths.map((str, i) => (
                          <li key={i} className="leading-snug">{str}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {landingReport.critical_blockers && landingReport.critical_blockers.length > 0 && (
                    <div className="p-2.5 rounded bg-rose-950/30 border border-rose-500/20 space-y-1">
                      <span className="font-semibold text-rose-400 flex items-center gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>High-Impact Friction Points</span>
                      </span>
                      <ul className="space-y-1 text-slate-300 list-disc list-inside">
                        {landingReport.critical_blockers.map((blk, i) => (
                          <li key={i} className="leading-snug">{blk}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 4 Specialized Perspectives Navigation & Cards */}
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2 border-b border-slate-200 pb-2">
                <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-600" />
                  <span>Specialized Analytical Perspectives</span>
                </h4>
                <span className="text-slate-400 text-[11px]">Click perspective to view findings</span>
              </div>

              {/* Perspective Subtabs */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  {
                    key: "marketing" as const,
                    label: "Marketing & Positioning",
                    data: landingReport?.perspectives?.marketing,
                  },
                  {
                    key: "sales" as const,
                    label: "Sales & Conversion",
                    data: landingReport?.perspectives?.sales,
                  },
                  {
                    key: "subject_matter" as const,
                    label: "Subject Expertise",
                    data: landingReport?.perspectives?.subject_matter,
                  },
                  {
                    key: "seo_functionality" as const,
                    label: "SEO & Runtime",
                    data: landingReport?.perspectives?.seo_functionality,
                  },
                ].map((p) => {
                  const isSelected = landingPerspectiveTab === p.key;
                  const score = p.data?.health_score ?? null;
                  return (
                    <button
                      key={p.key}
                      onClick={() => setLandingPerspectiveTab(p.key)}
                      className={`p-2.5 rounded-lg border text-left transition flex flex-col justify-between ${
                        isSelected
                          ? "bg-blue-50 border-blue-500 ring-1 ring-blue-500 shadow-xs"
                          : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <span className={`font-semibold text-xs leading-tight block ${isSelected ? "text-blue-900" : "text-slate-800"}`}>
                        {p.label}
                      </span>
                      <div className="flex items-center justify-between gap-1 mt-2 font-mono text-[11px]">
                        <span className="text-slate-400">Score:</span>
                        <span
                          className={`font-bold ${
                            score === null
                              ? "text-slate-400"
                              : score >= 80
                              ? "text-emerald-600"
                              : score >= 60
                              ? "text-amber-600"
                              : "text-rose-600"
                          }`}
                        >
                          {score === null ? "—" : `${score}%`}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Active Perspective Detailed Findings & Summary */}
              {landingReport?.perspectives && (
                (() => {
                  const activePersp = landingReport.perspectives[landingPerspectiveTab];
                  if (!activePersp) return null;

                  return (
                    <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-sm space-y-3.5">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                        <div>
                          <h4 className="font-bold text-slate-900 text-xs sm:text-sm">
                            {activePersp.title}
                          </h4>
                          <p className="text-slate-500 text-[11px] mt-0.5">
                            {activePersp.summary}
                          </p>
                        </div>

                        <span
                          className={`font-mono font-bold text-xs px-2.5 py-0.5 rounded border ${
                            activePersp.health_score == null
                              ? "bg-slate-50 text-slate-500 border-slate-200"
                              : activePersp.health_score >= 80
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                              : activePersp.health_score >= 60
                              ? "bg-amber-50 text-amber-700 border-amber-200"
                              : "bg-rose-50 text-rose-700 border-rose-200"
                          }`}
                        >
                          {activePersp.health_score == null
                            ? "Findings only (no score)"
                            : `${activePersp.health_score}%${activePersp.score_band ? ` (${activePersp.score_band})` : ""}`}
                        </span>
                      </div>

                      {/* Perspective Strengths and Weaknesses */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                        {activePersp.strengths && activePersp.strengths.length > 0 && (
                          <div className="p-2.5 rounded bg-emerald-50/60 border border-emerald-200 space-y-1">
                            <span className="font-semibold text-emerald-900 block text-[10px] uppercase tracking-wider font-mono">
                              Observed Strengths
                            </span>
                            <ul className="space-y-0.5 text-emerald-800 list-disc list-inside">
                              {activePersp.strengths.map((s, si) => (
                                <li key={si}>{s}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {activePersp.key_weaknesses && activePersp.key_weaknesses.length > 0 && (
                          <div className="p-2.5 rounded bg-rose-50/60 border border-rose-200 space-y-1">
                            <span className="font-semibold text-rose-900 block text-[10px] uppercase tracking-wider font-mono">
                              Attention Areas
                            </span>
                            <ul className="space-y-0.5 text-rose-800 list-disc list-inside">
                              {activePersp.key_weaknesses.map((w, wi) => (
                                <li key={wi}>{w}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      {/* Finding Cards */}
                      <div className="space-y-2.5 pt-1">
                        <span className="font-bold text-slate-800 text-[11px] block">
                          Detailed Evidence-Based Findings ({activePersp.findings?.length || 0})
                        </span>

                        {activePersp.findings && activePersp.findings.length > 0 ? (
                          activePersp.findings.map((f, fi) => {
                            const isExpanded = expandedLandingFindingId === f.id || fi === 0;
                            return (
                              <div
                                key={f.id || fi}
                                className="rounded-lg border border-slate-200 bg-white overflow-hidden shadow-xs hover:border-slate-300 transition"
                              >
                                <div
                                  onClick={() => setExpandedLandingFindingId(isExpanded && expandedLandingFindingId === f.id ? null : f.id)}
                                  className="p-3 cursor-pointer flex items-start justify-between gap-3 bg-slate-50/60 hover:bg-slate-50 transition"
                                >
                                  <div className="space-y-1 min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-1.5 font-mono text-[10px]">
                                      <span
                                        className={`px-1.5 py-0.2 rounded font-semibold uppercase ${
                                          f.status === "fail"
                                            ? "bg-rose-100 text-rose-800 border border-rose-200"
                                            : f.status === "warn"
                                            ? "bg-amber-100 text-amber-800 border border-amber-200"
                                            : "bg-emerald-100 text-emerald-800 border border-emerald-200"
                                        }`}
                                      >
                                        {f.status}
                                      </span>

                                      <span
                                        className={`px-1.5 py-0.2 rounded border capitalize ${
                                          f.severity === "critical"
                                            ? "bg-rose-50 text-rose-700 border-rose-200 font-bold"
                                            : f.severity === "high"
                                            ? "bg-amber-50 text-amber-700 border-amber-200 font-semibold"
                                            : "bg-slate-100 text-slate-600 border-slate-200"
                                        }`}
                                      >
                                        {f.severity}
                                      </span>

                                      <span className="px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                                        {f.category}
                                      </span>

                                      {f.section_or_element && (
                                        <span className="px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 border border-slate-200">
                                          {f.section_or_element}
                                        </span>
                                      )}

                                      {f.assessment && (
                                        <span
                                          className={`px-1.5 py-0.2 rounded uppercase font-bold ${
                                            f.assessment === "supported"
                                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                              : f.assessment === "outdated"
                                              ? "bg-amber-100 text-amber-900 border border-amber-300"
                                              : "bg-rose-100 text-rose-900 border border-rose-300"
                                          }`}
                                        >
                                          {f.assessment.replace("_", " ")}
                                        </span>
                                      )}
                                    </div>

                                    <h5 className="font-semibold text-slate-900 text-xs sm:text-sm">
                                      {f.title}
                                    </h5>
                                  </div>

                                  <div className="shrink-0 text-slate-400 mt-1">
                                    {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                                  </div>
                                </div>

                                {isExpanded && (
                                  <div className="p-3.5 border-t border-slate-100 bg-slate-50/50 space-y-3 text-xs">
                                    {/* Quote / Specific Claim */}
                                    {f.specific_claim_or_passage && (
                                      <div className="p-2.5 rounded bg-slate-100/90 border border-slate-200 space-y-1">
                                        <span className="font-semibold text-slate-800 text-[10px] uppercase font-mono block">
                                          Specific Claim or Passage Under Evaluation
                                        </span>
                                        <p className="text-slate-800 text-[11px] italic leading-relaxed">
                                          &ldquo;{f.specific_claim_or_passage}&rdquo;
                                        </p>
                                      </div>
                                    )}

                                    {/* Observed vs Expected */}
                                    <div className="p-2.5 rounded bg-white border border-slate-200 space-y-2">
                                      <div>
                                        <span className="text-slate-500 text-[10px] uppercase font-mono block">Directly Observed Evidence:</span>
                                        <p className="text-slate-800 text-[11px] font-mono mt-0.5 bg-slate-50 p-2 rounded border border-slate-100 break-words">
                                          {f.observed}
                                        </p>
                                      </div>

                                      {f.expected && (
                                        <div>
                                          <span className="text-slate-500 text-[10px] uppercase font-mono block">Expected Standard / Baseline:</span>
                                          <p className="text-slate-700 text-[11px] font-mono mt-0.5 bg-slate-50 p-2 rounded border border-slate-100 break-words">
                                            {f.expected}
                                          </p>
                                        </div>
                                      )}
                                    </div>

                                    {/* Audience Context */}
                                    {f.intended_audience_context && (
                                      <div className="text-[11px] text-slate-700">
                                        <span className="font-semibold text-slate-800">Audience Impact: </span>
                                        <span>{f.intended_audience_context}</span>
                                      </div>
                                    )}

                                    {/* Why it matters */}
                                    {f.why_it_matters && (
                                      <div className="text-[11px] text-slate-700">
                                        <span className="font-semibold text-slate-800">Why It Matters: </span>
                                        <span>{f.why_it_matters}</span>
                                      </div>
                                    )}

                                    {/* Actionable Recommendation */}
                                    {f.recommendation && (
                                      <div className="p-2.5 rounded bg-blue-50/80 border border-blue-200">
                                        <span className="font-semibold text-blue-900 block text-[11px]">
                                          Actionable Recommendation:
                                        </span>
                                        <p className="text-blue-800 mt-0.5 leading-relaxed">
                                          {f.recommendation}
                                        </p>
                                        {f.priority_rationale && (
                                          <p className="text-blue-700/80 text-[10px] mt-1 italic">
                                            Priority Rationale ({f.priority}): {f.priority_rationale}
                                          </p>
                                        )}
                                      </div>
                                    )}

                                    {/* IB Authoritative Reference */}
                                    {f.authoritative_source && (
                                      <div className="p-2 rounded bg-indigo-50/80 border border-indigo-200 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                                        <div>
                                          <span className="font-semibold text-indigo-950">Official Reference: </span>
                                          <span className="text-indigo-800 font-mono text-[10px] break-all">{f.authoritative_source}</span>
                                        </div>
                                        {f.authoritative_source.startsWith("http") && (
                                          <a
                                            href={f.authoritative_source}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center gap-1 text-indigo-700 hover:text-indigo-900 font-semibold text-[10px] underline"
                                          >
                                            <span>Official IBO Link</span>
                                            <ExternalLink className="w-3 h-3" />
                                          </a>
                                        )}
                                      </div>
                                    )}

                                    {/* Educational Implications */}
                                    {f.educational_implications && (
                                      <div className="p-2 rounded bg-amber-50/70 border border-amber-200 text-[11px] text-amber-900">
                                        <span className="font-semibold text-amber-950">Curriculum & Exam Implication: </span>
                                        <span>{f.educational_implications}</span>
                                      </div>
                                    )}

                                    {/* Suggested Verification & Limitations */}
                                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-200 text-[10px] text-slate-500 font-mono">
                                      {f.suggested_verification && (
                                        <span>Verification: {f.suggested_verification}</span>
                                      )}
                                      {f.confidence && (
                                        <span>Confidence: {Math.round(f.confidence * 100)}%</span>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })
                        ) : (
                          <p className="text-slate-500 text-xs py-2">No critical findings observed for this perspective.</p>
                        )}
                      </div>
                    </div>
                  );
                })()
              )}
            </div>

            {/* 5 Strategic Gap Analysis Diagnostics */}
            {landingReport?.gap_analysis && (
              <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                  <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                    <span>Strategic Friction & Gap Diagnosis</span>
                  </h4>
                  <span className="text-slate-400 text-[11px]">Unanswered objections & trust gaps</span>
                </div>

                {/* Gap Diagnostic Sub-tabs */}
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  {[
                    { key: "missing" as const, label: "Missing Information", count: landingReport.gap_analysis?.missing_information?.length || 0 },
                    { key: "objections" as const, label: "Unanswered Objections", count: landingReport.gap_analysis?.unanswered_objections?.length || 0 },
                    { key: "trust" as const, label: "Trust Gaps", count: landingReport.gap_analysis?.trust_gaps?.length || 0 },
                    { key: "messaging" as const, label: "Messaging Problems", count: landingReport.gap_analysis?.messaging_problems?.length || 0 },
                    { key: "opportunities" as const, label: "Conversion Opportunities", count: landingReport.gap_analysis?.conversion_opportunities?.length || 0 },
                  ].map((g) => (
                    <button
                      key={g.key}
                      onClick={() => setActiveGapTab(g.key)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 ${
                        activeGapTab === g.key
                          ? "bg-slate-900 text-white shadow-xs"
                          : "bg-slate-100 text-slate-600 hover:text-slate-900 hover:bg-slate-200"
                      }`}
                    >
                      <span>{g.label}</span>
                      <span className="px-1.5 py-0.2 rounded-full bg-white/20 text-[10px] font-mono">
                        {g.count}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Diagnostic Items List */}
                <div className="p-3 rounded-md bg-slate-50 border border-slate-200 space-y-2">
                  {activeGapTab === "missing" && (
                    <ul className="space-y-1.5 text-slate-700 text-xs">
                      {(landingReport.gap_analysis?.missing_information || []).length > 0 ? (
                        landingReport.gap_analysis.missing_information.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-amber-500 font-bold shrink-0">•</span>
                            <span className="leading-relaxed">{item}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-slate-400 italic">No missing information points identified.</li>
                      )}
                    </ul>
                  )}

                  {activeGapTab === "objections" && (
                    <ul className="space-y-1.5 text-slate-700 text-xs">
                      {(landingReport.gap_analysis?.unanswered_objections || []).length > 0 ? (
                        landingReport.gap_analysis.unanswered_objections.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-rose-500 font-bold shrink-0">•</span>
                            <span className="leading-relaxed">{item}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-slate-400 italic">No unanswered customer objections detected.</li>
                      )}
                    </ul>
                  )}

                  {activeGapTab === "trust" && (
                    <ul className="space-y-1.5 text-slate-700 text-xs">
                      {(landingReport.gap_analysis?.trust_gaps || []).length > 0 ? (
                        landingReport.gap_analysis.trust_gaps.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-indigo-500 font-bold shrink-0">•</span>
                            <span className="leading-relaxed">{item}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-slate-400 italic">No credibility or trust gaps identified.</li>
                      )}
                    </ul>
                  )}

                  {activeGapTab === "messaging" && (
                    <ul className="space-y-1.5 text-slate-700 text-xs">
                      {(landingReport.gap_analysis?.messaging_problems || []).length > 0 ? (
                        landingReport.gap_analysis.messaging_problems.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-orange-500 font-bold shrink-0">•</span>
                            <span className="leading-relaxed">{item}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-slate-400 italic">No messaging friction issues identified.</li>
                      )}
                    </ul>
                  )}

                  {activeGapTab === "opportunities" && (
                    <ul className="space-y-1.5 text-slate-700 text-xs">
                      {(landingReport.gap_analysis?.conversion_opportunities || []).length > 0 ? (
                        landingReport.gap_analysis.conversion_opportunities.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-emerald-500 font-bold shrink-0">•</span>
                            <span className="leading-relaxed font-medium text-emerald-900">{item}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-slate-400 italic">No additional conversion opportunities found.</li>
                      )}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {/* Prioritized Recommendations Action Roadmap */}
            {landingReport?.prioritized_recommendations && landingReport.prioritized_recommendations.length > 0 && (
              <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                  <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Prioritized Landing Page Action Roadmap</span>
                  </h4>
                  <span className="text-slate-400 text-[11px]">Ranked by impact & feasibility</span>
                </div>

                <div className="space-y-2">
                  {landingReport.prioritized_recommendations.map((rec) => (
                    <div key={rec.rank} className="p-3 rounded-md bg-slate-50 border border-slate-200 flex items-start gap-3">
                      <div className="w-6 h-6 rounded-full bg-slate-900 text-white flex items-center justify-center font-mono font-bold text-xs shrink-0 mt-0.5">
                        {rec.rank}
                      </div>

                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-bold text-slate-900 text-xs">{rec.title}</span>
                          <div className="flex items-center gap-1.5 font-mono text-[10px]">
                            <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 capitalize">
                              {rec.perspective}
                            </span>
                            <span
                              className={`px-1.5 py-0.5 rounded border capitalize ${
                                rec.priority === "critical"
                                  ? "bg-rose-50 text-rose-700 border-rose-200 font-bold"
                                  : rec.priority === "high"
                                  ? "bg-amber-50 text-amber-700 border-amber-200 font-semibold"
                                  : "bg-slate-100 text-slate-700 border-slate-200"
                              }`}
                            >
                              {rec.priority || "high"}
                            </span>
                            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                              {(rec.effort || "moderate").replace("_", " ")}
                            </span>
                          </div>
                        </div>

                        <p className="text-slate-700 text-[11px] leading-relaxed">
                          <span className="font-medium text-slate-800">Direction:</span> {rec.implementation_direction}
                        </p>
                        <p className="text-slate-500 text-[10px]">
                          <span className="font-medium text-slate-600">Expected Benefit:</span> {rec.expected_benefit}
                        </p>
                        <p className="text-emerald-700 text-[10px]">
                          <span className="font-medium text-emerald-800">Verification:</span> {rec.verification_step}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Coverage Indicators & Declared Boundaries */}
            {landingReport && (
              <div className="p-3.5 rounded-lg bg-slate-100/80 border border-slate-200 text-slate-600 text-[11px] space-y-2">
                <span className="font-bold text-slate-800 flex items-center gap-1 text-xs">
                  <Terminal className="w-3.5 h-3.5 text-blue-600" />
                  <span>Coverage & Grounding Boundaries</span>
                </span>

                {landingReport.coverage_indicators && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[10px]">
                    <div className="p-1.5 rounded bg-white border border-slate-200">
                      <span className="text-slate-400 block">Rendered DOM:</span>
                      <span className="font-bold text-slate-700">{landingReport.coverage_indicators.rendered_dom_utilized ? "Rendered (live browser)" : "HTML snapshot"}</span>
                    </div>
                    <div className="p-1.5 rounded bg-white border border-slate-200">
                      <span className="text-slate-400 block">Console Errors:</span>
                      <span className={`font-bold ${landingReport.coverage_indicators.console_errors_count > 0 ? "text-rose-600" : "text-emerald-600"}`}>
                        {landingReport.coverage_indicators.console_errors_count}
                      </span>
                    </div>
                    <div className="p-1.5 rounded bg-white border border-slate-200">
                      <span className="text-slate-400 block">Failed Subresources:</span>
                      <span className={`font-bold ${landingReport.coverage_indicators.failed_network_requests > 0 ? "text-amber-600" : "text-emerald-600"}`}>
                        {landingReport.coverage_indicators.failed_network_requests}
                      </span>
                    </div>
                    <div className="p-1.5 rounded bg-white border border-slate-200">
                      <span className="text-slate-400 block">Page Word Count:</span>
                      <span className="font-bold text-slate-700">{landingReport.coverage_indicators.word_count || 0} words</span>
                    </div>
                  </div>
                )}

                {landingReport.unavailable_data_indicators && landingReport.unavailable_data_indicators.length > 0 && (
                  <div className="pt-1">
                    <span className="font-semibold text-slate-700 block text-[10px] uppercase font-mono">Declared Data Boundaries:</span>
                    <ul className="space-y-0.5 list-disc list-inside text-[10px] text-slate-500 mt-0.5">
                      {landingReport.unavailable_data_indicators.map((u, ui) => (
                        <li key={ui}>{u}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {panelTab === "findings" && (
          <div className="p-3 sm:p-4 space-y-4">
            {/* Filter Bar */}
            <div className="p-3 rounded-lg bg-white border border-slate-200 shadow-sm space-y-3">
              {/* Search & Severity Pills */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">

                <div className="relative flex-1 max-w-sm">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search findings by issue, check ID, recommendation..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 rounded-md bg-slate-50 border border-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div className="flex items-center gap-1 text-xs">
                  <span className="text-slate-500 font-medium text-[11px]">Severity:</span>
                  {["all", "critical", "high", "medium", "low"].map((sev) => (
                    <button
                      key={sev}
                      onClick={() => setSelectedSeverity(sev)}
                      className={`px-2 py-0.5 rounded text-[11px] font-medium capitalize transition ${
                        selectedSeverity === sev
                          ? "bg-slate-900 text-white"
                          : "text-slate-600 hover:bg-slate-100"
                      }`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>

              {/* Status Filter */}
              <div className="flex flex-wrap items-center gap-1.5 text-xs pt-1 border-t border-slate-100">
                <span className="text-slate-500 font-medium text-[11px] mr-1">Status:</span>
                {[
                  { key: "all", label: "All Checks" },
                  { key: "fail", label: "Confirmed Failures" },
                  { key: "warn", label: "Warnings" },
                  { key: "pass", label: "Passed" },
                  { key: "skipped", label: "Skipped" },
                  { key: "inconclusive", label: "Inconclusive / N/A" },
                ].map((st) => (
                  <button
                    key={st.key}
                    onClick={() => setSelectedStatus(st.key)}
                    className={`px-2 py-0.5 rounded text-[11px] transition ${
                      selectedStatus === st.key
                        ? "bg-blue-50 text-blue-700 border border-blue-200 font-semibold"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {st.label}
                  </button>
                ))}
              </div>

              {/* Category Pills */}
              <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-slate-100">
                <button
                  onClick={() => setSelectedCategory("all")}
                  className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
                    selectedCategory === "all"
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  All Categories ({findings.length})
                </button>

                {FINDING_CATEGORIES.map((cat) => {
                  const count = (findingsByCategory.get(cat.key) || []).length;
                  return (
                    <button
                      key={cat.key}
                      onClick={() => setSelectedCategory(cat.key)}
                      className={`px-2 py-0.5 rounded text-[11px] transition ${
                        selectedCategory === cat.key
                          ? "bg-slate-900 text-white font-medium"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {cat.label} ({count})
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Findings List */}
            {filteredFindings.length === 0 ? (
              <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs">
                <ShieldCheck className="w-10 h-10 mx-auto text-slate-300 mb-2" />
                <p className="font-medium text-slate-700">No findings match the selected filters</p>
                <p className="text-slate-400 mt-1">
                  Adjust severity, status, or category filters to inspect all findings.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredFindings.map((finding) => {
                  const isExpanded = expandedFindingId === finding.id;
                  const cat = categorizeFinding(
                    finding.check_id,
                    finding.title,
                    finding.category,
                    finding.agent_id
                  );
                  const catMeta = FINDING_CATEGORIES.find((c) => c.key === cat);
                  const st = (finding.status || "").toLowerCase();
                  const sev = (finding.severity || "medium").toLowerCase();

                  return (
                    <div
                      key={finding.id}
                      className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden transition hover:border-slate-300"
                    >
                      {/* Card Header */}
                      <div
                        onClick={() => setExpandedFindingId(isExpanded ? null : finding.id)}
                        className="p-3.5 cursor-pointer flex items-start gap-3 select-none"
                      >
                        <div className="mt-0.5 shrink-0">
                          {st === "fail" || st === "failed" ? (
                            <XCircle className="w-4 h-4 text-red-600" />
                          ) : st === "warn" || st === "warning" ? (
                            <AlertTriangle className="w-4 h-4 text-amber-500" />
                          ) : st === "pass" || st === "passed" ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          ) : (
                            <HelpCircle className="w-4 h-4 text-slate-400" />
                          )}
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1 text-[11px]">
                            {/* Severity Badge */}
                            <span
                              className={`px-1.5 py-0.2 rounded font-semibold font-mono uppercase text-[10px] ${
                                sev === "critical"
                                  ? "bg-red-100 text-red-800 border border-red-200"
                                  : sev === "high"
                                  ? "bg-orange-100 text-orange-800 border border-orange-200"
                                  : sev === "medium"
                                  ? "bg-amber-100 text-amber-800 border border-amber-200"
                                  : "bg-blue-100 text-blue-800 border border-blue-200"
                              }`}
                            >
                              {sev}
                            </span>

                            {/* Status Badge */}
                            <span
                              className={`px-1.5 py-0.2 rounded text-[10px] font-medium ${
                                st === "fail" || st === "failed"
                                  ? "bg-red-50 text-red-700"
                                  : st === "warn" || st === "warning"
                                  ? "bg-amber-50 text-amber-700"
                                  : st === "pass" || st === "passed"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-slate-100 text-slate-600"
                              }`}
                            >
                              {st === "fail" || st === "failed"
                                ? "Confirmed Issue"
                                : st === "warn" || st === "warning"
                                ? "Warning"
                                : st === "pass" || st === "passed"
                                ? "Passed Check"
                                : st.toUpperCase()}
                            </span>

                            {/* Category Badge */}
                            {catMeta && (
                              <span
                                className={`px-1.5 py-0.2 rounded text-[10px] font-medium border ${catMeta.badgeColor}`}
                              >
                                {catMeta.label}
                              </span>
                            )}

                            {(finding.perspective || finding.agent_id) && (
                              <span className="px-1.5 py-0.2 rounded text-[10px] font-medium font-mono uppercase bg-indigo-50 text-indigo-700 border border-indigo-200">
                                {finding.perspective || finding.agent_id}
                              </span>
                            )}

                            {finding.assessment && (
                              <span
                                className={`px-1.5 py-0.2 rounded text-[10px] font-semibold font-mono uppercase ${
                                  finding.assessment === "supported"
                                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                    : finding.assessment === "outdated"
                                    ? "bg-amber-100 text-amber-800 border border-amber-300"
                                    : finding.assessment === "potentially_inaccurate"
                                    ? "bg-rose-100 text-rose-800 border border-rose-300"
                                    : finding.assessment === "incomplete"
                                    ? "bg-orange-50 text-orange-700 border border-orange-200"
                                    : "bg-purple-50 text-purple-700 border border-purple-200"
                                }`}
                              >
                                {finding.assessment.replace("_", " ")}
                              </span>
                            )}

                            {finding.affected_urls && finding.affected_urls.length > 1 && (
                              <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-amber-50 text-amber-800 border border-amber-200">
                                {finding.affected_urls.length} pages
                              </span>
                            )}

                            <span className="text-[10px] text-slate-400 font-mono">
                              {finding.check_id}
                            </span>
                          </div>

                          <h4 className="text-xs sm:text-sm font-semibold text-slate-900 leading-snug">
                            {finding.title}
                          </h4>

                          {finding.page_url && (
                            <div className="text-[11px] text-slate-500 font-mono truncate mt-0.5">
                              URL: {finding.page_url}
                            </div>
                          )}
                        </div>

                        <div className="shrink-0 text-slate-400 mt-1">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </div>
                      </div>

                      {/* Expandable Details Body */}
                      {isExpanded && (
                        <div className="p-3.5 bg-slate-50/80 border-t border-slate-100 text-xs space-y-3">
                          {/* Claim / Content Passage Under Review */}
                          {finding.specific_claim_or_passage && (
                            <div className="p-2.5 rounded bg-slate-100/80 border border-slate-200 space-y-1">
                              <span className="font-semibold text-slate-800 block text-[11px] uppercase tracking-wider font-mono">
                                Claim / Content Passage Under Review
                              </span>
                              <p className="text-slate-800 text-[11px] italic leading-relaxed">
                                &ldquo;{finding.specific_claim_or_passage}&rdquo;
                              </p>
                            </div>
                          )}

                          {/* Evidence Comparison */}
                          {finding.evidence && (
                            <div className="p-2.5 rounded bg-white border border-slate-200 space-y-2">
                              <span className="font-semibold text-slate-700 block text-[11px] uppercase tracking-wider font-mono">
                                Technical Evidence
                              </span>

                              {finding.evidence.observed && (
                                <div>
                                  <span className="text-slate-500 text-[11px] block">Observed:</span>
                                  <div className="font-mono text-slate-800 text-[11px] bg-slate-50 p-2 rounded border border-slate-100 break-words mt-0.5">
                                    {finding.evidence.observed}
                                  </div>
                                </div>
                              )}

                              {finding.evidence.expected && (
                                <div>
                                  <span className="text-slate-500 text-[11px] block">Expected Standard:</span>
                                  <div className="font-mono text-slate-800 text-[11px] bg-slate-50 p-2 rounded border border-slate-100 break-words mt-0.5">
                                    {finding.evidence.expected}
                                  </div>
                                </div>
                              )}

                              {finding.evidence.selector && (
                                <div className="text-[11px] text-slate-500 font-mono">
                                  Selector / Element:{" "}
                                  <span className="text-slate-800 font-semibold">{finding.evidence.selector}</span>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Educational & Curriculum Implications */}
                          {finding.educational_implications && (
                            <div className="p-2.5 rounded bg-amber-50/70 border border-amber-200">
                              <span className="font-semibold text-amber-950 block text-[11px]">
                                Educational & Assessment Implications:
                              </span>
                              <p className="text-amber-900 mt-0.5 leading-relaxed">
                                {finding.educational_implications}
                              </p>
                            </div>
                          )}

                          {/* Business & SEO Impact */}
                          {finding.why_it_matters && (
                            <div>
                              <span className="font-semibold text-slate-800 block text-[11px]">
                                Business & Search Impact:
                              </span>
                              <p className="text-slate-600 mt-0.5 leading-relaxed">
                                {finding.why_it_matters}
                              </p>
                            </div>
                          )}

                          {/* Actionable Recommendation */}
                          {finding.recommendation && (
                            <div className="p-2.5 rounded bg-blue-50/70 border border-blue-200">
                              <span className="font-semibold text-blue-900 block text-[11px]">
                                Recommended Remediation:
                              </span>
                              <p className="text-blue-800 mt-0.5 leading-relaxed">
                                {finding.recommendation}
                              </p>
                            </div>
                          )}

                          {/* Authoritative Source / IBO Reference */}
                          {finding.authoritative_source && (
                            <div className="p-2 rounded bg-indigo-50/70 border border-indigo-200 text-[11px] flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <span className="font-semibold text-indigo-950">Authoritative Standard: </span>
                                <span className="text-indigo-800 font-mono text-[10px] break-all">{finding.authoritative_source}</span>
                              </div>
                              {finding.authoritative_source.startsWith("http") && (
                                <a
                                  href={finding.authoritative_source}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="inline-flex items-center gap-1 text-indigo-700 hover:text-indigo-900 font-medium text-[10px] underline shrink-0"
                                >
                                  <span>View IBO Source</span>
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                            </div>
                          )}

                          {/* Verification Guidance & Limitations */}
                          {finding.verification_guidance && (
                            <div className="text-slate-600 text-[11px]">
                              <span className="font-semibold text-slate-700">Verification Steps: </span>
                              <span>{finding.verification_guidance}</span>
                            </div>
                          )}
                          {finding.verification_limitations && (
                            <div className="text-slate-500 text-[10px] italic">
                              <span className="font-semibold text-slate-600">Verification Boundary: </span>
                              <span>{finding.verification_limitations}</span>
                            </div>
                          )}

                          {/* Open this finding's page report in a new tab (no crawl rerun) */}
                          {finding.page_url && (
                            <div className="pt-2 border-t border-slate-200 flex justify-end">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  window.open(
                                    `/audits/${encodeURIComponent(auditId)}/pages/by-url?url=${encodeURIComponent(finding.page_url!)}`,
                                    "_blank",
                                    "noopener,noreferrer"
                                  );
                                }}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-white hover:bg-slate-100 border border-slate-200 text-blue-600 text-[11px] font-medium transition"
                              >
                                <span>Open Page Report</span>
                                <ArrowRight className="w-3 h-3" />
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Technical SEO, Website Functionality & Connectivity Tab */}
        {panelTab === "technical_functionality" && (
          <div className="p-3 sm:p-4 space-y-4 text-xs">
            {/* Top Overview & Agent Selector */}
            <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white shadow-md border border-slate-800 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-indigo-600/30 border border-indigo-500/40">
                    <Layers className="w-4 h-4 text-indigo-300" />
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-white">
                      Technical, Functionality & Connectivity Analysis
                    </h3>
                    <p className="text-[11px] text-indigo-200">
                      Contextual AI analysis backed by real browser runtime, DOM parity, subresource network telemetry, and crawl graph.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 bg-slate-950/60 p-1 rounded-lg border border-slate-800 text-[11px]">
                  <button
                    onClick={() => setActiveTaskDAgent("all")}
                    className={`px-2.5 py-1 rounded font-medium transition ${
                      activeTaskDAgent === "all" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    All Agents
                  </button>
                  <button
                    onClick={() => setActiveTaskDAgent("functionality")}
                    className={`px-2.5 py-1 rounded font-medium transition ${
                      activeTaskDAgent === "functionality" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Functionality
                  </button>
                  <button
                    onClick={() => setActiveTaskDAgent("technical")}
                    className={`px-2.5 py-1 rounded font-medium transition ${
                      activeTaskDAgent === "technical" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Technical SEO & AI
                  </button>
                  <button
                    onClick={() => setActiveTaskDAgent("connectivity")}
                    className={`px-2.5 py-1 rounded font-medium transition ${
                      activeTaskDAgent === "connectivity" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Connectivity
                  </button>
                </div>
              </div>
            </div>

            {/* Agent 1: Website Functionality Agent */}
            {(activeTaskDAgent === "all" || activeTaskDAgent === "functionality") && (
              <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-50 text-rose-600 border border-rose-200">
                      <Zap className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-slate-900 text-sm">A. Website Functionality Agent</h4>
                      <p className="text-[11px] text-slate-500">
                        Browser runtime exceptions, subresource 4xx/5xx failures, form accessibility & labels, and mobile overflow.
                      </p>
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-100 text-slate-700">
                    Safe Read-Only Telemetry
                  </span>
                </div>

                {/* Functionality Findings List */}
                {(() => {
                  const agentFindings = findings.filter(
                    (f) => f.agent_id === "functionality" || (f.check_id && f.check_id.startsWith("functionality."))
                  );
                  if (agentFindings.length === 0) {
                    return (
                      <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-slate-500 text-center text-xs">
                        No functionality issues detected or checks still evaluating.
                      </div>
                    );
                  }
                  return (
                    <div className="space-y-3">
                      {agentFindings.map((f, idx) => (
                        <div
                          key={f.id || idx}
                          className={`p-3.5 rounded-lg border text-xs space-y-2 ${
                            f.status === "fail"
                              ? "bg-rose-50/50 border-rose-200"
                              : f.status === "warn"
                              ? "bg-amber-50/50 border-amber-200"
                              : "bg-emerald-50/50 border-emerald-200"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-bold text-slate-900">{f.title}</span>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                                  f.status === "fail"
                                    ? "bg-rose-100 text-rose-800"
                                    : f.status === "warn"
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-emerald-100 text-emerald-800"
                                }`}
                              >
                                {f.status}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono bg-white border border-slate-200 text-slate-600">
                                {f.severity}
                              </span>
                            </div>
                          </div>
                          {f.observed_evidence && (
                            <div className="p-2 rounded bg-white/80 border border-slate-200/80 font-mono text-[11px] text-slate-700 break-words">
                              <span className="font-sans font-semibold text-slate-500">Observed Evidence: </span>
                              {f.observed_evidence}
                            </div>
                          )}
                          {f.why_it_matters && (
                            <p className="text-slate-600 leading-relaxed">
                              <strong>Why It Matters: </strong>
                              {f.why_it_matters}
                            </p>
                          )}
                          {f.actionable_recommendations && (
                            <p className="font-medium text-slate-800 leading-relaxed">
                              👉 <strong>Recommendation: </strong>
                              {f.actionable_recommendations}
                            </p>
                          )}
                          {f.verification_guidance && (
                            <div className="text-slate-500 text-[11px]">
                              <span className="font-semibold text-slate-600">Verification Steps: </span>
                              {f.verification_guidance}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Agent 2: Technical SEO and AI-Readability Agent */}
            {(activeTaskDAgent === "all" || activeTaskDAgent === "technical") && (
              <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-200">
                      <ShieldCheck className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-slate-900 text-sm">B. Technical SEO and AI-Readability Agent</h4>
                      <p className="text-[11px] text-slate-500">
                        Status codes, canonicals, robots directives, structured data, DOM parity, and LLM/RAG machine comprehension.
                      </p>
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                    Google Search Essentials Grounded
                  </span>
                </div>

                {/* Technical SEO Findings List */}
                {(() => {
                  const agentFindings = findings.filter(
                    (f) => f.agent_id === "technical" || (f.check_id && f.check_id.startsWith("technical."))
                  );
                  if (agentFindings.length === 0) {
                    return (
                      <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-slate-500 text-center text-xs">
                        No technical SEO issues detected or checks still evaluating.
                      </div>
                    );
                  }
                  return (
                    <div className="space-y-3">
                      {agentFindings.map((f, idx) => (
                        <div
                          key={f.id || idx}
                          className={`p-3.5 rounded-lg border text-xs space-y-2 ${
                            f.status === "fail"
                              ? "bg-rose-50/50 border-rose-200"
                              : f.status === "warn"
                              ? "bg-amber-50/50 border-amber-200"
                              : "bg-emerald-50/50 border-emerald-200"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-bold text-slate-900">{f.title}</span>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                                  f.status === "fail"
                                    ? "bg-rose-100 text-rose-800"
                                    : f.status === "warn"
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-emerald-100 text-emerald-800"
                                }`}
                              >
                                {f.status}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono bg-white border border-slate-200 text-slate-600">
                                {f.severity}
                              </span>
                            </div>
                          </div>
                          {f.observed_evidence && (
                            <div className="p-2 rounded bg-white/80 border border-slate-200/80 font-mono text-[11px] text-slate-700 break-words">
                              <span className="font-sans font-semibold text-slate-500">Observed Evidence: </span>
                              {f.observed_evidence}
                            </div>
                          )}
                          {f.why_it_matters && (
                            <p className="text-slate-600 leading-relaxed">
                              <strong>Why It Matters: </strong>
                              {f.why_it_matters}
                            </p>
                          )}
                          {f.actionable_recommendations && (
                            <p className="font-medium text-slate-800 leading-relaxed">
                              👉 <strong>Recommendation: </strong>
                              {f.actionable_recommendations}
                            </p>
                          )}
                          {f.verification_guidance && (
                            <div className="text-slate-500 text-[11px]">
                              <span className="font-semibold text-slate-600">Verification Steps: </span>
                              {f.verification_guidance}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Agent 3: Website Connectivity Agent */}
            {(activeTaskDAgent === "all" || activeTaskDAgent === "connectivity") && (
              <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-cyan-50 text-cyan-600 border border-cyan-200">
                      <Network className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-slate-900 text-sm">C. Website Connectivity Agent</h4>
                      <p className="text-[11px] text-slate-500">
                        Internal and external link structures, anchor text quality, broken destinations, redirect loops, and crawl discovery.
                      </p>
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200">
                    Multi-Page Link Graph
                  </span>
                </div>

                {/* Connectivity Findings List */}
                {(() => {
                  const agentFindings = findings.filter(
                    (f) => f.agent_id === "connectivity" || (f.check_id && f.check_id.startsWith("connectivity."))
                  );
                  if (agentFindings.length === 0) {
                    return (
                      <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-slate-500 text-center text-xs">
                        No connectivity issues detected or checks still evaluating.
                      </div>
                    );
                  }
                  return (
                    <div className="space-y-3">
                      {agentFindings.map((f, idx) => (
                        <div
                          key={f.id || idx}
                          className={`p-3.5 rounded-lg border text-xs space-y-2 ${
                            f.status === "fail"
                              ? "bg-rose-50/50 border-rose-200"
                              : f.status === "warn"
                              ? "bg-amber-50/50 border-amber-200"
                              : "bg-emerald-50/50 border-emerald-200"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-bold text-slate-900">{f.title}</span>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                                  f.status === "fail"
                                    ? "bg-rose-100 text-rose-800"
                                    : f.status === "warn"
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-emerald-100 text-emerald-800"
                                }`}
                              >
                                {f.status}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono bg-white border border-slate-200 text-slate-600">
                                {f.severity}
                              </span>
                            </div>
                          </div>
                          {f.observed_evidence && (
                            <div className="p-2 rounded bg-white/80 border border-slate-200/80 font-mono text-[11px] text-slate-700 break-words">
                              <span className="font-sans font-semibold text-slate-500">Observed Evidence: </span>
                              {f.observed_evidence}
                            </div>
                          )}
                          {f.why_it_matters && (
                            <p className="text-slate-600 leading-relaxed">
                              <strong>Why It Matters: </strong>
                              {f.why_it_matters}
                            </p>
                          )}
                          {f.actionable_recommendations && (
                            <p className="font-medium text-slate-800 leading-relaxed">
                              👉 <strong>Recommendation: </strong>
                              {f.actionable_recommendations}
                            </p>
                          )}
                          {f.verification_guidance && (
                            <div className="text-slate-500 text-[11px]">
                              <span className="font-semibold text-slate-600">Verification Steps: </span>
                              {f.verification_guidance}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        )}

        {/* Executive Dimensions Tab */}
        {panelTab === "executive" && (
          <div className="p-3 sm:p-4 space-y-4 text-xs">
            {/* AI Holistic Executive Summary Card */}
            {consolidatedReport?.executive_summary && (
              <div className="p-4 rounded-lg bg-gradient-to-br from-slate-900 to-indigo-950 text-white shadow-md border border-slate-800 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-indigo-900/60 pb-3">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-amber-400" />
                    <span className="font-bold text-sm tracking-tight text-white">
                      AI Holistic Executive Synthesis
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      Multi-Agent Swarm
                    </span>
                  </div>

                  <div className="flex items-center gap-2 font-mono">
                    <span className="text-slate-400 text-xs">Domain Health:</span>
                    <span
                      className={`px-2.5 py-0.5 rounded font-bold text-sm border ${
                        consolidatedReport.score?.percent == null
                          ? "bg-white/10 text-slate-300 border-white/20"
                          : consolidatedReport.score.percent >= 80
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                          : consolidatedReport.score.percent >= 50
                          ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                          : "bg-rose-500/20 text-rose-300 border-rose-500/40"
                      }`}
                      title={consolidatedReport.score?.methodology || undefined}
                    >
                      {consolidatedReport.score?.percent == null
                        ? "Findings only (no score)"
                        : `${consolidatedReport.score.percent}%${
                            consolidatedReport.score.band ? ` (${consolidatedReport.score.band})` : ""
                          }`}
                    </span>
                  </div>
                </div>

                <p className="text-slate-200 text-xs leading-relaxed font-sans">
                  {consolidatedReport.executive_summary}
                </p>

                {/* Observed crawl coverage (real backend counters only) */}
                {consolidatedReport.crawl_coverage && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 pt-1 font-mono text-[10px]">
                    {[
                      ["Discovered", consolidatedReport.crawl_coverage.discovered_unique_urls],
                      ["Deeply analyzed", consolidatedReport.crawl_coverage.deeply_analyzed_pages],
                      ["Fetch attempts", consolidatedReport.crawl_coverage.attempted_fetches],
                      ["Failed pages", consolidatedReport.crawl_coverage.failed_pages],
                      ["Queued", consolidatedReport.crawl_coverage.queued_urls],
                      ["HTML fetched", consolidatedReport.crawl_coverage.fetched_html_pages],
                      ["Links checked", consolidatedReport.crawl_coverage.shallowly_checked_links],
                      ["Unique resources", consolidatedReport.crawl_coverage.unique_resources],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="px-2 py-1 rounded bg-white/5 border border-white/10">
                        <span className="text-indigo-300 block">{label}</span>
                        <span className="text-white font-bold">{value ?? 0}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Key Strengths & Critical Blockers Pills */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-2 border-t border-indigo-900/40 text-[11px]">
                  {consolidatedReport.top_strengths && consolidatedReport.top_strengths.length > 0 && (
                    <div className="p-2.5 rounded bg-white/5 border border-white/10 space-y-1">
                      <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Core Architectural Strengths</span>
                      </span>
                      <ul className="space-y-1 text-slate-300 list-disc list-inside">
                        {consolidatedReport.top_strengths.map((str, i) => (
                          <li key={i} className="leading-snug">{str}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {consolidatedReport.critical_blockers && consolidatedReport.critical_blockers.length > 0 && (
                    <div className="p-2.5 rounded bg-white/5 border border-white/10 space-y-1">
                      <span className="font-semibold text-rose-400 flex items-center gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>High-Impact Attention Points</span>
                      </span>
                      <ul className="space-y-1 text-slate-300 list-disc list-inside">
                        {consolidatedReport.critical_blockers.map((blk, i) => (
                          <li key={i} className="leading-snug">{blk}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Conflicting Recommendations Resolved */}
                {consolidatedReport.conflicting_recommendations_resolved && consolidatedReport.conflicting_recommendations_resolved.length > 0 && (
                  <div className="pt-2 text-[11px] text-slate-300">
                    <span className="font-semibold text-amber-300 block mb-1">
                      Cross-Perspective Synthesis & Conflict Resolution:
                    </span>
                    <ul className="space-y-1 list-disc list-inside text-slate-300">
                      {consolidatedReport.conflicting_recommendations_resolved.map((res, i) => (
                        <li key={i} className="leading-snug">{res}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* 4 Expert Perspectives Cards */}
            {consolidatedReport?.perspectives && (
              <div className="space-y-2">
                <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-blue-600" />
                  <span>Analytical Perspectives</span>
                </h4>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(consolidatedReport.perspectives).map(([pKey, pVal]: [string, any]) => {
                    if (!pVal) return null;
                    return (
                      <div
                        key={pKey}
                        className="p-3.5 rounded-lg bg-white border border-slate-200 shadow-sm space-y-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-slate-900 text-xs">
                            {pVal.title || pKey.toUpperCase()}
                          </span>
                          <span
                            className={`font-mono font-bold text-xs px-2 py-0.5 rounded border ${
                              pVal.health_score == null
                                ? "bg-slate-50 text-slate-500 border-slate-200"
                                : pVal.health_score >= 80
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                : pVal.health_score >= 50
                                ? "bg-amber-50 text-amber-700 border-amber-200"
                                : "bg-red-50 text-red-700 border-red-200"
                            }`}
                            title={pVal.score_methodology || undefined}
                          >
                            {pVal.health_score == null ? "Findings only" : `${pVal.health_score}%`}
                          </span>
                        </div>

                        <p className="text-slate-600 text-[11px] leading-relaxed">
                          {pVal.summary}
                        </p>

                        {pVal.findings && pVal.findings.length > 0 && (
                          <div className="pt-1.5 border-t border-slate-100 text-[11px] space-y-1">
                            <span className="font-semibold text-slate-700 block">Top Findings:</span>
                            {pVal.findings.slice(0, 2).map((fd: any, i: number) => (
                              <div key={i} className="p-1.5 rounded bg-slate-50 border border-slate-200 text-slate-700">
                                <span className="font-medium text-slate-900">{fd.title}</span>
                                {fd.recommendation && (
                                  <p className="text-[10px] text-blue-700 mt-0.5">{fd.recommendation}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Cross-Page / Site-Wide Issues */}
            {consolidatedReport?.cross_page_issues && consolidatedReport.cross_page_issues.length > 0 && (
              <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                  <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Cross-Page & Shared Template Root Causes</span>
                  </h4>
                  <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-mono text-[10px] border border-indigo-200">
                    {consolidatedReport.cross_page_issues.length} detected
                  </span>
                </div>

                <div className="space-y-2.5">
                  {consolidatedReport.cross_page_issues.map((cpi, i) => (
                    <div key={i} className="p-3 rounded-md bg-slate-50 border border-slate-200 space-y-1.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-slate-900 text-xs">{cpi.title}</span>
                        <span className="px-2 py-0.5 rounded bg-red-50 text-red-700 border border-red-200 font-mono text-[10px] uppercase">
                          {cpi.impact_level} impact ({cpi.affected_pages_count} pages)
                        </span>
                      </div>

                      <div className="text-[11px] text-slate-600 space-y-1">
                        <p><span className="font-medium text-slate-700">Root Cause:</span> {cpi.root_cause_diagnosis}</p>
                        <p className="text-blue-800"><span className="font-medium text-blue-900">Remediation:</span> {cpi.actionable_fix}</p>
                        <p className="text-slate-500 text-[10px]"><span className="font-medium text-slate-600">Verification:</span> {cpi.verification_method}</p>
                      </div>

                      {cpi.affected_urls && cpi.affected_urls.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-slate-200/60">
                          <span className="text-[10px] text-slate-400">Affected:</span>
                          {cpi.affected_urls.slice(0, 3).map((u, ui) => (
                            <button
                              key={ui}
                              onClick={() =>
                                window.open(
                                  `/audits/${encodeURIComponent(auditId)}/pages/by-url?url=${encodeURIComponent(u)}`,
                                  "_blank",
                                  "noopener,noreferrer"
                                )
                              }
                              className="px-1.5 py-0.5 rounded bg-white hover:bg-slate-100 border border-slate-200 font-mono text-[10px] text-blue-600 truncate max-w-[200px]"
                              title={u}
                            >
                              {u}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Prioritized Action Plan Roadmap */}
            {consolidatedReport?.prioritized_actions && consolidatedReport.prioritized_actions.length > 0 && (
              <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                  <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Prioritized Improvement Action Roadmap</span>
                  </h4>
                  <span className="text-slate-400 text-[11px]">Ranked by impact & feasibility</span>
                </div>

                <div className="space-y-2">
                  {consolidatedReport.prioritized_actions.map((act) => (
                    <div key={act.rank} className="p-3 rounded-md bg-slate-50 border border-slate-200 flex items-start gap-3">
                      <div className="w-6 h-6 rounded-full bg-slate-900 text-white flex items-center justify-center font-mono font-bold text-xs shrink-0 mt-0.5">
                        {act.rank}
                      </div>

                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-bold text-slate-900 text-xs">{act.title}</span>
                          <div className="flex items-center gap-1.5 font-mono text-[10px]">
                            <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                              {act.perspective}
                            </span>
                            <span
                              className={`px-1.5 py-0.5 rounded border capitalize ${
                                act.priority === "critical"
                                  ? "bg-rose-50 text-rose-700 border-rose-200"
                                  : act.priority === "high"
                                  ? "bg-amber-50 text-amber-700 border-amber-200"
                                  : "bg-slate-100 text-slate-700 border-slate-200"
                              }`}
                            >
                              {act.priority}
                            </span>
                            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                              {act.effort_estimate.replace("_", " ")}
                            </span>
                          </div>
                        </div>

                        <p className="text-slate-700 text-[11px] leading-relaxed">{act.action}</p>
                        <p className="text-slate-500 text-[10px] leading-snug"><span className="font-medium text-slate-600">Rationale:</span> {act.rationale}</p>
                        <p className="text-emerald-700 text-[10px]"><span className="font-medium text-emerald-800">Verification:</span> {act.verification_step}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Core Dimensions Cards (Technical, Content, Marketing, Functionality, Connectivity) */}
            {consolidatedReport?.dimensions && (
              <div className="space-y-2 pt-1">
                <h4 className="font-bold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-slate-600" />
                  <span>Technical & Performance Dimensions</span>
                </h4>

                <div className="space-y-3">
                  {["technical_seo_ai", "content_quality", "marketing_conversion", "website_functionality", "overall_connectivity"]
                    .map((dimKey) => {
                      const dim = consolidatedReport.dimensions[dimKey];
                      if (!dim) return null;
                      return (
                        <div
                          key={dimKey}
                          className="p-3.5 rounded-lg bg-white border border-slate-200 shadow-sm space-y-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <h4 className="font-bold text-slate-900 text-xs">{dim.name}</h4>
                            <span
                              className={`font-mono font-bold text-xs px-2 py-0.5 rounded border ${
                                dim.score == null
                                  ? "bg-slate-50 text-slate-500 border-slate-200"
                                  : dim.score >= 80
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : dim.score >= 50
                                  ? "bg-amber-50 text-amber-700 border-amber-200"
                                  : "bg-red-50 text-red-700 border-red-200"
                              }`}
                              title={dim.score_methodology || undefined}
                            >
                              {dim.score == null ? "Findings only" : `${dim.score}%`}
                            </span>
                          </div>

                          <p className="text-slate-600 text-[11px] leading-relaxed">
                            {dim.summary}
                          </p>

                          <div className="flex items-center gap-4 text-[10px] text-slate-500 pt-1 font-mono">
                            <span>Total Findings: {dim.total_findings}</span>
                            <span className="text-red-600 font-semibold">
                              Issues / Attention: {dim.issues_count}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {!consolidatedReport?.dimensions && (
              <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500">
                <Clock className="w-8 h-8 mx-auto text-slate-400 mb-2 animate-spin" />
                <p className="font-medium text-slate-700">Consolidating Website Dimensions</p>
                <p className="text-slate-400 text-xs mt-1">
                  The multi-agent swarm is currently auditing individual pages. Dimension scores will consolidate
                  upon crawl completion.
                </p>
              </div>
            )}

            {/* Browser Session Telemetry Summary */}
            {consolidatedReport?.browser_session_summary && (
              <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-sm space-y-2">
                <h4 className="font-bold text-slate-900 text-xs flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-blue-600" />
                  <span>Browser Session Telemetry</span>
                </h4>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-[11px]">
                  <div className="p-2 rounded bg-slate-50 border border-slate-200">
                    <span className="text-slate-500 font-sans block text-[10px]">Pages Inspected:</span>
                    <span className="font-bold text-slate-800 text-sm mt-0.5 block">
                      {consolidatedReport.browser_session_summary.pages_inspected}
                    </span>
                  </div>

                  <div className="p-2 rounded bg-slate-50 border border-slate-200">
                    <span className="text-slate-500 font-sans block text-[10px]">Console Error Events:</span>
                    <span className="font-bold text-red-600 text-sm mt-0.5 block">
                      {consolidatedReport.browser_session_summary.console_error_events ??
                        consolidatedReport.browser_session_summary.javascript_errors_detected ??
                        0}
                    </span>
                  </div>

                  <div className="p-2 rounded bg-slate-50 border border-slate-200">
                    <span className="text-slate-500 font-sans block text-[10px]">Failed Asset Requests:</span>
                    <span className="font-bold text-amber-600 text-sm mt-0.5 block">
                      {consolidatedReport.browser_session_summary.failed_network_requests}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Declared Limitations & Grounding Disclosure */}
            {consolidatedReport?.limitations && consolidatedReport.limitations.length > 0 && (
              <div className="p-3.5 rounded-lg bg-slate-100/80 border border-slate-200 text-slate-600 text-[11px] space-y-1.5">
                <span className="font-bold text-slate-800 flex items-center gap-1 text-xs">
                  <ShieldCheck className="w-3.5 h-3.5 text-slate-600" />
                  <span>Audit Evidence Boundaries & Limitations</span>
                </span>
                <ul className="space-y-1 list-disc list-inside text-slate-600 text-[10px]">
                  {consolidatedReport.limitations.map((lim, i) => (
                    <li key={i} className="leading-relaxed">{lim}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Page & Resource Explorer Tab */}
        {panelTab === "explorer" && (
          <PageResourceExplorer
            auditId={auditId}
            crawlUrls={crawlUrls}
            pageReports={pageReports}
            activeUrl={activeUrl}
            onSelectUrl={onSelectUrl}
          />
        )}
      </div>
    </div>
  );
}
