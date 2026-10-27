"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Award,
  BarChart3,
  BookOpen,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  Compass,
  ExternalLink,
  Eye,
  FileCode,
  FileText,
  Filter,
  Flame,
  Globe,
  Layers,
  Lightbulb,
  Link2,
  ListOrdered,
  Megaphone,
  PieChart,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Workflow,
  Zap,
} from "lucide-react";

import {
  getMarketingRun,
  getMarketingRunForAudit,
  startMarketingRun,
} from "@/lib/api";
import type {
  MarketingActionItem,
  MarketingCriterion,
  MarketingPageReport,
  MarketingPriority,
  MarketingRun,
} from "@/types/api";

interface MarketingIntelligencePanelProps {
  auditId: string;
  targetUrl: string;
  activeUrl: string;
  onSelectUrl?: (url: string) => void;
}

const CRITERION_LABELS: Record<MarketingCriterion, { label: string; icon: typeof Target; desc: string }> = {
  audience_intent: {
    label: "Audience & Search Intent",
    icon: Compass,
    desc: "Alignment between visitor queries, knowledge level, and content relevance",
  },
  value_proposition: {
    label: "Value Proposition & Moat",
    icon: Zap,
    desc: "Immediate clarity of the offering, unique benefits, and competitive moat",
  },
  content_quality: {
    label: "Content Depth & Authority",
    icon: FileText,
    desc: "Messaging clarity, information hierarchy, and evidence-backed claims",
  },
  visitor_journey: {
    label: "Visitor Journey & CTAs",
    icon: Workflow,
    desc: "Conversion ladder, frictionless next steps, and guidance through the funnel",
  },
  brand_positioning: {
    label: "Brand Positioning & Trust",
    icon: Award,
    desc: "Market positioning, proof elements, accreditations, and schema entity validation",
  },
};

const PRIORITY_COLORS: Record<MarketingPriority, { bg: string; text: string; border: string; badge: string }> = {
  Critical: { bg: "bg-red-500/10", text: "text-red-600 dark:text-red-400", border: "border-red-500/30", badge: "bg-red-600 text-white" },
  High: { bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/30", badge: "bg-amber-600 text-white" },
  Medium: { bg: "bg-blue-500/10", text: "text-blue-600 dark:text-blue-400", border: "border-blue-500/30", badge: "bg-blue-600 text-white" },
  Low: { bg: "bg-slate-500/10", text: "text-slate-600 dark:text-slate-400", border: "border-slate-500/30", badge: "bg-slate-600 text-white" },
};

export function MarketingIntelligencePanel({
  auditId,
  targetUrl,
  activeUrl,
  onSelectUrl,
}: MarketingIntelligencePanelProps) {
  const [run, setRun] = useState<MarketingRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingRun, setStartingRun] = useState(false);
  const [maxPages, setMaxPages] = useState(5);
  const [viewMode, setViewMode] = useState<"stories" | "roadmap" | "radar" | "dossier">("stories");
  const [selectedCriterion, setSelectedCriterion] = useState<string>("all");
  const [selectedPriority, setSelectedPriority] = useState<string>("all");
  const [selectedPageUrl, setSelectedPageUrl] = useState<string>("all");
  const [expandedItemId, setExpandedItemId] = useState<number | null>(0);
  const [showHtmlSignals, setShowHtmlSignals] = useState(true);

  // Poll for latest run
  useEffect(() => {
    let mounted = true;
    let timer: NodeJS.Timeout | null = null;

    async function loadData() {
      try {
        const latest = await getMarketingRunForAudit(auditId);
        if (mounted) {
          setRun(latest);
          setLoading(false);

          if (latest && (latest.status === "queued" || latest.status === "running")) {
            timer = setTimeout(loadData, 3000);
          }
        }
      } catch {
        if (mounted) setLoading(false);
      }
    }

    loadData();

    return () => {
      mounted = false;
      if (timer) clearTimeout(timer);
    };
  }, [auditId]);

  const handleStartRun = async () => {
    setStartingRun(true);
    try {
      const newRun = await startMarketingRun(auditId, targetUrl || activeUrl, maxPages);
      setRun(newRun);
      // Poll until done
      const interval = setInterval(async () => {
        try {
          const updated = await getMarketingRun(newRun.id);
          setRun(updated);
          if (updated.status === "done" || updated.status === "failed") {
            clearInterval(interval);
            setStartingRun(false);
          }
        } catch {
          clearInterval(interval);
          setStartingRun(false);
        }
      }, 3000);
    } catch {
      setStartingRun(false);
    }
  };

  const synthesis = run?.result?.site;
  const pages = run?.result?.pages || [];
  const roadmap = run?.result?.roadmap || [];
  const brief = run?.research_brief;

  // Filter roadmap action items
  const filteredItems = useMemo(() => {
    return roadmap.filter((item) => {
      if (selectedCriterion !== "all" && item.criterion !== selectedCriterion) return false;
      if (selectedPriority !== "all" && item.priority !== selectedPriority) return false;
      if (selectedPageUrl !== "all" && item.page_url !== selectedPageUrl) return false;
      return true;
    });
  }, [roadmap, selectedCriterion, selectedPriority, selectedPageUrl]);

  // Aggregate criteria scores
  const criteriaScores = useMemo(() => {
    const scores: Record<MarketingCriterion, { total: number; count: number }> = {
      audience_intent: { total: 0, count: 0 },
      value_proposition: { total: 0, count: 0 },
      content_quality: { total: 0, count: 0 },
      visitor_journey: { total: 0, count: 0 },
      brand_positioning: { total: 0, count: 0 },
    };

    for (const page of pages) {
      for (const c of page.criteria || []) {
        if (c.criterion in scores) {
          scores[c.criterion].total += c.score;
          scores[c.criterion].count += 1;
        }
      }
    }

    return Object.entries(scores).map(([k, v]) => ({
      criterion: k as MarketingCriterion,
      score: v.count > 0 ? Number((v.total / v.count).toFixed(1)) : 6.0,
      label: CRITERION_LABELS[k as MarketingCriterion]?.label || k,
    }));
  }, [pages]);

  const overallScore = synthesis?.overall_marketing_score ?? (
    criteriaScores.length > 0
      ? Number((criteriaScores.reduce((acc, c) => acc + c.score, 0) / criteriaScores.length).toFixed(1))
      : 7.0
  );

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-slate-900/40 text-slate-100 p-4 sm:p-6 space-y-6">
      {/* ── HEADER BANNER ────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl bg-gradient-to-r from-blue-950/60 via-indigo-950/40 to-purple-950/60 border border-blue-500/20 shadow-xl backdrop-blur-md">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400 shrink-0">
            <BrainCircuit className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-white tracking-tight">
                Marketing Intelligence Agent
              </h2>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                Holistic Multi-Phase Report
              </span>
              {run?.status === "running" && (
                <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
                  <Activity className="w-3 h-3 animate-spin" />
                  Synthesizing Insights...
                </span>
              )}
            </div>
            <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-2xl leading-relaxed">
              Autonomous agent auditing value proposition, audience intent, and visitor journeys grounded in live HTML parser evidence — telling the complete story from finding to future business impact.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3 shrink-0 self-end md:self-center">
          <button
            onClick={handleStartRun}
            disabled={startingRun || run?.status === "running"}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-500/20 disabled:opacity-50 transition active:scale-95"
          >
            <RefreshCw className={`w-4 h-4 ${startingRun || run?.status === "running" ? "animate-spin" : ""}`} />
            <span>{run ? "Re-Run Marketing Audit" : "Launch Marketing Agent"}</span>
          </button>
        </div>
      </div>

      {/* ── LOADING / RUNNING STATE ──────────────────────────────── */}
      {loading && !run && (
        <div className="flex flex-col items-center justify-center p-12 rounded-2xl bg-slate-800/40 border border-slate-700/50 text-slate-400">
          <Activity className="w-8 h-8 animate-spin text-blue-400 mb-3" />
          <p className="text-sm font-medium">Checking marketing agent intelligence runs...</p>
        </div>
      )}

      {/* ── NO RUN YET HEROCARD ──────────────────────────────────── */}
      {!loading && !run && (
        <div className="p-8 rounded-2xl bg-slate-800/40 border border-slate-700/60 text-center max-w-xl mx-auto space-y-4">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <Sparkles className="w-7 h-7" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">No Marketing Agent Audit Yet</h3>
            <p className="text-xs sm:text-sm text-slate-400 mt-1">
              Run the autonomous agent to crawl <b>{targetUrl || activeUrl}</b>, extract deep HTML parser signals (headings, CTAs, meta descriptions, word counts), evaluate competitors, and formulate a story-driven roadmap.
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={handleStartRun}
              disabled={startingRun}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/30 transition"
            >
              <Bot className="w-4 h-4" />
              <span>{startingRun ? "Starting Agent..." : "Run Marketing Audit"}</span>
            </button>
          </div>
        </div>
      )}

      {/* ── MAIN DASHBOARD (RUN AVAILABLE) ───────────────────────── */}
      {run && (
        <>
          {/* 1. TOP METRICS & PLOT GRID */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Overall Score Dial */}
            <div className="lg:col-span-4 p-5 rounded-2xl bg-slate-800/50 border border-slate-700/60 flex flex-col justify-between shadow-lg">
              <div>
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  Holistic Marketing Health
                </span>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-4xl font-extrabold text-white tracking-tight">
                    {overallScore}
                  </span>
                  <span className="text-base font-semibold text-slate-400">/ 10</span>
                  <span
                    className={`ml-auto px-2.5 py-1 rounded-full text-xs font-semibold ${
                      overallScore >= 8
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : overallScore >= 6
                        ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                        : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                    }`}
                  >
                    {overallScore >= 8 ? "Optimal" : overallScore >= 6 ? "Competitive" : "Needs Lift"}
                  </span>
                </div>
              </div>

              {/* Circular Progress SVG Gauge */}
              <div className="my-4 flex items-center justify-center">
                <div className="relative w-36 h-36 flex items-center justify-center">
                  <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                    <circle
                      cx="50"
                      cy="50"
                      r="40"
                      className="stroke-slate-700/50"
                      strokeWidth="8"
                      fill="transparent"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="40"
                      className="stroke-blue-500 transition-all duration-1000 ease-out"
                      strokeWidth="8"
                      strokeDasharray={251.2}
                      strokeDashoffset={251.2 - (251.2 * (overallScore * 10)) / 100}
                      strokeLinecap="round"
                      fill="transparent"
                    />
                  </svg>
                  <div className="absolute flex flex-col items-center">
                    <span className="text-xl font-black text-white font-mono">
                      {(overallScore * 10).toFixed(0)}%
                    </span>
                    <span className="text-[10px] text-slate-400 uppercase font-medium">Index</span>
                  </div>
                </div>
              </div>

              <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed bg-slate-900/40 p-2.5 rounded-lg border border-slate-700/40">
                {synthesis?.executive_summary || "Synthesized evaluation of target audience intent, messaging hierarchy, and friction points."}
              </p>
            </div>

            {/* Criteria Score Bars & Interactive Radar Visual */}
            <div className="lg:col-span-8 p-5 rounded-2xl bg-slate-800/50 border border-slate-700/60 flex flex-col justify-between shadow-lg">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                  Core Marketing Dimensions (1–10)
                </span>
                <span className="text-xs text-blue-400 font-medium flex items-center gap-1">
                  <Sparkles className="w-3.5 h-3.5" />
                  Grounded in HTML Parser
                </span>
              </div>

              <div className="space-y-3 my-1">
                {criteriaScores.map((c) => {
                  const meta = CRITERION_LABELS[c.criterion];
                  const Icon = meta.icon;
                  const pct = (c.score / 10) * 100;
                  return (
                    <div key={c.criterion} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-1.5 font-medium text-slate-200">
                          <Icon className="w-3.5 h-3.5 text-blue-400" />
                          <span>{c.label}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-white">{c.score}</span>
                          <span className="text-[11px] text-slate-400">/ 10</span>
                        </div>
                      </div>
                      <div className="h-2 w-full bg-slate-700/40 rounded-full overflow-hidden flex">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${
                            c.score >= 8
                              ? "bg-emerald-500"
                              : c.score >= 6
                              ? "bg-blue-500"
                              : "bg-amber-500"
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Quick Summary Pill Bar */}
              <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-700/50 text-[11px] text-slate-400 flex-wrap">
                <span className="text-slate-300 font-medium">Pages evaluated:</span>
                <span className="font-mono text-white bg-slate-900/60 px-2 py-0.5 rounded border border-slate-700/60">
                  {pages.length} URLs
                </span>
                <span className="text-slate-300 font-medium ml-2">Total Action Items:</span>
                <span className="font-mono text-white bg-slate-900/60 px-2 py-0.5 rounded border border-slate-700/60">
                  {roadmap.length} items
                </span>
                <span className="text-slate-300 font-medium ml-2">Sequencing:</span>
                <span className="text-slate-300 italic truncate max-w-xs">
                  {synthesis?.sequencing_rationale ? synthesis.sequencing_rationale.slice(0, 60) + "..." : "Prioritized by impact vs effort"}
                </span>
              </div>
            </div>
          </div>

          {/* 2. SUB-VIEW NAVIGATION TABS */}
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2 overflow-x-auto text-xs sm:text-sm">
            <button
              onClick={() => setViewMode("stories")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
                viewMode === "stories"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <Lightbulb className="w-4 h-4 text-amber-300" />
              <span>Action Stories ({roadmap.length})</span>
            </button>

            <button
              onClick={() => setViewMode("roadmap")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
                viewMode === "roadmap"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <ListOrdered className="w-4 h-4 text-indigo-300" />
              <span>Prioritized Roadmap</span>
            </button>

            <button
              onClick={() => setViewMode("radar")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
                viewMode === "radar"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <Layers className="w-4 h-4 text-emerald-300" />
              <span>Page Matrix & HTML Signals</span>
            </button>

            <button
              onClick={() => setViewMode("dossier")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition ${
                viewMode === "dossier"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <BookOpen className="w-4 h-4 text-purple-300" />
              <span>Research Dossier & Moat</span>
            </button>
          </div>

          {/* 3. STORIES & ROADMAP VIEW */}
          {(viewMode === "stories" || viewMode === "roadmap") && (
            <div className="space-y-4">
              {/* Filter Strip */}
              <div className="flex flex-wrap items-center gap-2 p-3 rounded-xl bg-slate-800/40 border border-slate-700/50 text-xs">
                <span className="text-slate-400 font-medium flex items-center gap-1 mr-1">
                  <Filter className="w-3.5 h-3.5" />
                  Filter by:
                </span>

                {/* Priority */}
                <select
                  value={selectedPriority}
                  onChange={(e) => setSelectedPriority(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 focus:outline-none focus:border-blue-500"
                >
                  <option value="all">All Priorities</option>
                  <option value="Critical">Critical</option>
                  <option value="High">High</option>
                  <option value="Medium">Medium</option>
                  <option value="Low">Low</option>
                </select>

                {/* Criterion */}
                <select
                  value={selectedCriterion}
                  onChange={(e) => setSelectedCriterion(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 focus:outline-none focus:border-blue-500"
                >
                  <option value="all">All Dimensions</option>
                  {Object.entries(CRITERION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v.label}
                    </option>
                  ))}
                </select>

                {/* Page URL */}
                <select
                  value={selectedPageUrl}
                  onChange={(e) => setSelectedPageUrl(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 max-w-xs truncate focus:outline-none focus:border-blue-500"
                >
                  <option value="all">All Pages ({pages.length})</option>
                  {pages.map((p) => (
                    <option key={p.url} value={p.url}>
                      {p.url}
                    </option>
                  ))}
                </select>

                <div className="ml-auto text-slate-400 font-medium">
                  Showing <b>{filteredItems.length}</b> of {roadmap.length} items
                </div>
              </div>

              {/* Action Item Story Cards */}
              <div className="space-y-4">
                {filteredItems.map((item, index) => {
                  const isExpanded = expandedItemId === index;
                  const prio = PRIORITY_COLORS[item.priority] || PRIORITY_COLORS.Medium;
                  const crit = CRITERION_LABELS[item.criterion];
                  const Icon = crit?.icon || Lightbulb;

                  return (
                    <div
                      key={index}
                      className={`rounded-2xl border transition-all duration-300 overflow-hidden shadow-lg ${
                        isExpanded
                          ? "bg-slate-800/80 border-blue-500/40 ring-1 ring-blue-500/20"
                          : "bg-slate-800/40 border-slate-700/60 hover:border-slate-600"
                      }`}
                    >
                      {/* Card Header Accordion Trigger */}
                      <button
                        onClick={() => setExpandedItemId(isExpanded ? null : index)}
                        className="w-full p-4 sm:p-5 flex items-start sm:items-center justify-between text-left gap-4"
                      >
                        <div className="flex items-start sm:items-center gap-3 min-w-0">
                          {/* Rank Badge */}
                          <div className="w-7 h-7 rounded-lg bg-slate-900 border border-slate-700 flex items-center justify-center font-mono font-bold text-xs text-blue-400 shrink-0">
                            #{item.rank ?? index + 1}
                          </div>

                          <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${prio.badge}`}>
                                {item.priority}
                              </span>
                              <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-700 text-slate-300">
                                {crit?.label}
                              </span>
                              <span className="text-[11px] text-slate-400">
                                Effort: <b>{item.complexity}</b>
                              </span>
                              <span className="text-[11px] text-slate-400">
                                Impact: <b>{item.impact_level}</b>
                              </span>
                            </div>
                            <h3 className="text-sm sm:text-base font-bold text-white tracking-tight truncate">
                              {item.title}
                            </h3>
                            {item.page_url && (
                              <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-1 truncate">
                                <Globe className="w-3 h-3 text-slate-500 shrink-0" />
                                <span className="truncate">{item.page_url}</span>
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="p-1 rounded-lg bg-slate-900/40 text-slate-400 shrink-0">
                          <ChevronDown
                            className={`w-5 h-5 transition-transform duration-200 ${
                              isExpanded ? "transform rotate-180 text-blue-400" : ""
                            }`}
                          />
                        </div>
                      </button>

                      {/* Expanded Narrative Story Chapters */}
                      {isExpanded && (
                        <div className="p-5 pt-0 border-t border-slate-700/50 space-y-5 text-xs sm:text-sm mt-2">
                          {/* Narrative Grid: 4 Chapters */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Chapter 1: The Finding (What was observed) */}
                            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-700/60 space-y-2">
                              <div className="flex items-center gap-2 text-rose-400 font-bold uppercase tracking-wider text-[11px]">
                                <Eye className="w-3.5 h-3.5" />
                                <span>1. The Finding & Current State</span>
                              </div>
                              <p className="text-slate-300 leading-relaxed font-normal">
                                {item.current_situation}
                              </p>
                              {item.evidence && item.evidence.length > 0 && (
                                <div className="mt-2 pt-2 border-t border-slate-800 space-y-1">
                                  <span className="text-[10px] text-slate-400 uppercase font-semibold block">
                                    HTML Parser Grounding:
                                  </span>
                                  {item.evidence.map((ev, i) => (
                                    <div
                                      key={i}
                                      className="font-mono text-[11px] text-blue-300/90 bg-slate-950/60 p-1.5 rounded border border-slate-800 break-words"
                                    >
                                      {ev}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* Chapter 2: The Reason (Why it matters) */}
                            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-700/60 space-y-2">
                              <div className="flex items-center gap-2 text-amber-400 font-bold uppercase tracking-wider text-[11px]">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                <span>2. Why This Matters (The Friction)</span>
                              </div>
                              <p className="text-slate-300 leading-relaxed font-normal">
                                {item.reason}
                              </p>
                            </div>

                            {/* Chapter 3: The Action (By doing this...) */}
                            <div className="p-4 rounded-xl bg-blue-950/40 border border-blue-500/30 space-y-2">
                              <div className="flex items-center gap-2 text-blue-400 font-bold uppercase tracking-wider text-[11px]">
                                <Sparkles className="w-3.5 h-3.5" />
                                <span>3. The Prescribed Action</span>
                              </div>
                              <p className="text-blue-100 font-medium leading-relaxed">
                                {item.recommended_change}
                              </p>
                            </div>

                            {/* Chapter 4: The Future Transformation */}
                            <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/30 space-y-2">
                              <div className="flex items-center gap-2 text-emerald-400 font-bold uppercase tracking-wider text-[11px]">
                                <TrendingUp className="w-3.5 h-3.5" />
                                <span>4. What Happens in Future & Why Better</span>
                              </div>
                              <p className="text-emerald-100 font-medium leading-relaxed">
                                {item.expected_outcome}
                              </p>
                              <div className="text-xs text-emerald-200/90 bg-emerald-900/30 p-2 rounded border border-emerald-500/20 mt-1">
                                <b>Why this is superior:</b> {item.why_better}
                              </div>
                            </div>
                          </div>

                          {/* Impact Metrics Movement Grid */}
                          {item.nature_of_impact && item.nature_of_impact.length > 0 && (
                            <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-700/60 space-y-2">
                              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
                                Projected KPI Trajectory
                              </span>
                              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                                {item.nature_of_impact.map((eff, i) => (
                                  <div
                                    key={i}
                                    className="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800 space-y-1"
                                  >
                                    <div className="flex items-center justify-between text-xs">
                                      <span className="font-semibold text-slate-200 capitalize">
                                        {eff.metric.replace("_", " ")}
                                      </span>
                                      <span
                                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                          eff.direction === "increase"
                                            ? "bg-emerald-500/20 text-emerald-300"
                                            : eff.direction === "decrease"
                                            ? "bg-blue-500/20 text-blue-300"
                                            : "bg-slate-700 text-slate-300"
                                        }`}
                                      >
                                        {eff.direction === "increase" ? "↑ Increase" : eff.direction === "decrease" ? "↓ Decrease" : "→ Neutral"} ({eff.magnitude})
                                      </span>
                                    </div>
                                    <p className="text-[11px] text-slate-400 leading-snug">
                                      {eff.explanation}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Success Metric & Verification */}
                          <div className="flex items-center justify-between gap-4 p-3 rounded-lg bg-slate-900/40 border border-slate-800 text-xs">
                            <div className="flex items-center gap-2">
                              <Target className="w-4 h-4 text-blue-400" />
                              <span className="text-slate-400">Success KPI to Measure:</span>
                              <span className="text-slate-200 font-semibold">{item.success_metric}</span>
                            </div>
                            <div className="text-slate-400">
                              Confidence: <b className="text-white">{item.confidence}</b>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 4. PAGE MATRIX & DIRECT HTML SIGNALS VIEW */}
          {viewMode === "radar" && (
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    Audited Pages & Deep HTML Signals
                  </h3>
                  <p className="text-xs text-slate-400">
                    Concrete signals extracted by collector.parser for each page in the marketing audit.
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                {pages.map((p, idx) => (
                  <div
                    key={idx}
                    className="p-5 rounded-2xl bg-slate-800/50 border border-slate-700/60 space-y-4 shadow-lg"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-700/60 pb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-600/30 text-blue-300 border border-blue-500/30">
                            {p.page_type || "page"}
                          </span>
                          <span className="text-sm font-bold text-white truncate max-w-md">
                            {p.url}
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 mt-1">{p.summary}</p>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        {p.audience_fit && (
                          <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                            Intent Match: {p.audience_fit.intent_match}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* HTML Parser Signals Strip */}
                    {p.html_signals && (
                      <div className="p-3.5 rounded-xl bg-slate-900/70 border border-slate-700/60 space-y-3">
                        <div className="flex items-center justify-between text-xs font-bold text-blue-400">
                          <span className="flex items-center gap-1.5">
                            <Code2 className="w-3.5 h-3.5" />
                            HTML Parser Evidence (collector.parser)
                          </span>
                          <span className="text-slate-400 font-normal">
                            Word count: <b>{p.html_signals.word_count}</b> | Missing Alt: <b>{p.html_signals.images_missing_alt}</b>
                          </span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                          {/* Title & Meta */}
                          <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800 space-y-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400 block">
                              &lt;title&gt; Tag
                            </span>
                            <div className="font-mono text-slate-200">
                              {p.html_signals.title || "(Missing)"}
                            </div>
                            <span className="text-[10px] uppercase font-bold text-slate-400 block mt-2">
                              &lt;meta name="description"&gt;
                            </span>
                            <div className="font-mono text-slate-300 text-[11px] line-clamp-2">
                              {p.html_signals.meta_description || "(Missing / Empty)"}
                            </div>
                          </div>

                          {/* Headings & CTAs */}
                          <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800 space-y-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400 block">
                              Parsed Headings ({p.html_signals.headings?.length || 0} sample)
                            </span>
                            <div className="space-y-0.5 max-h-20 overflow-y-auto font-mono text-[11px]">
                              {p.html_signals.headings?.map((h: any, i: number) => (
                                <div key={i} className="text-slate-300 truncate">
                                  <span className="text-indigo-400 font-bold">{h.tag}:</span> {h.text}
                                </div>
                              ))}
                            </div>
                            <span className="text-[10px] uppercase font-bold text-slate-400 block mt-2">
                              Detected Calls to Action ({p.html_signals.calls_to_action?.length || 0})
                            </span>
                            <div className="space-y-0.5 max-h-16 overflow-y-auto font-mono text-[11px]">
                              {p.html_signals.calls_to_action?.map((c: any, i: number) => (
                                <div key={i} className="text-emerald-300 truncate">
                                  [CTA] {c.text}
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Criteria Scores for this page */}
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                      {p.criteria?.map((c, i) => (
                        <div key={i} className="p-2.5 rounded-xl bg-slate-900/50 border border-slate-800 text-center">
                          <span className="text-[10px] text-slate-400 block truncate font-medium">
                            {CRITERION_LABELS[c.criterion]?.label.split(" ")[0]}
                          </span>
                          <span
                            className={`text-base font-extrabold font-mono mt-0.5 block ${
                              c.score >= 8 ? "text-emerald-400" : c.score >= 6 ? "text-blue-400" : "text-amber-400"
                            }`}
                          >
                            {c.score}/10
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 5. RESEARCH DOSSIER & STRATEGIC MOAT VIEW */}
          {viewMode === "dossier" && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Brief Summary */}
                <div className="p-5 rounded-2xl bg-slate-800/50 border border-slate-700/60 space-y-3 shadow-lg">
                  <div className="flex items-center gap-2 text-xs font-bold text-blue-400 uppercase tracking-wider">
                    <Compass className="w-4 h-4" />
                    <span>Business & Market Context</span>
                  </div>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed font-normal">
                    {brief?.business_summary || "Automated synthesis of the site's primary market role and offerings."}
                  </p>
                  {brief?.likely_audiences && (
                    <div className="space-y-1 pt-2">
                      <span className="text-xs font-semibold text-slate-400">Target Audiences:</span>
                      <div className="flex flex-wrap gap-1.5">
                        {brief.likely_audiences.map((aud, i) => (
                          <span key={i} className="px-2 py-0.5 rounded text-xs bg-slate-900 text-slate-300 border border-slate-700">
                            {aud}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Competitors & Reputation */}
                <div className="p-5 rounded-2xl bg-slate-800/50 border border-slate-700/60 space-y-3 shadow-lg">
                  <div className="flex items-center gap-2 text-xs font-bold text-purple-400 uppercase tracking-wider">
                    <Target className="w-4 h-4" />
                    <span>Competitive Landscape & Moat</span>
                  </div>
                  {brief?.competitors && brief.competitors.length > 0 ? (
                    <div className="space-y-1">
                      <span className="text-xs font-semibold text-slate-400">Identified Competitors:</span>
                      <div className="flex flex-wrap gap-1.5">
                        {brief.competitors.map((comp, i) => (
                          <span key={i} className="px-2 py-0.5 rounded text-xs bg-purple-950/50 text-purple-300 border border-purple-800/50">
                            {comp}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">No direct competitors discovered in search phase.</p>
                  )}
                  <p className="text-xs text-slate-300 leading-relaxed pt-2">
                    {brief?.external_reputation_notes || "Reputation signals synthesized from web search & brand presence."}
                  </p>
                </div>
              </div>

              {/* Cross-page Inconsistencies & Strategic Positioning Gaps */}
              {synthesis && (
                <div className="p-5 rounded-2xl bg-slate-800/50 border border-slate-700/60 space-y-4 shadow-lg">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    Site-Level Consistency & Moat Gaps
                  </h3>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-700/60 space-y-2">
                      <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block">
                        Cross-Page Inconsistencies
                      </span>
                      <ul className="space-y-1.5 text-xs text-slate-300">
                        {synthesis.cross_page_inconsistencies?.map((inc, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-amber-400 shrink-0 mt-0.5">•</span>
                            <span>{inc}</span>
                          </li>
                        )) || <li className="text-slate-500 italic">None detected.</li>}
                      </ul>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-700/60 space-y-2">
                      <span className="text-xs font-bold text-rose-400 uppercase tracking-wider block">
                        Strategic Positioning Gaps
                      </span>
                      <ul className="space-y-1.5 text-xs text-slate-300">
                        {synthesis.strategic_positioning_gaps?.map((gap, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-rose-400 shrink-0 mt-0.5">•</span>
                            <span>{gap}</span>
                          </li>
                        )) || <li className="text-slate-500 italic">None detected.</li>}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
