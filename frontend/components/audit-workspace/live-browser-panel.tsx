"use client";

import { useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Code2,
  Copy,
  ExternalLink,
  Eye,
  FileCode,
  Globe,
  Info,
  Laptop,
  Layers,
  Lock,
  Maximize2,
  Minimize2,
  RefreshCw,
  Search,
  Shield,
  Smartphone,
  Tablet,
  Terminal,
  Zap,
} from "lucide-react";

import type { DeviceViewport } from "./types";
import type { BrowserObservationData, PageAuditReport } from "@/types/api";

interface LiveBrowserPanelProps {
  activeUrl: string;
  auditId: string;
  observation: BrowserObservationData | null;
  activePageReport: PageAuditReport | null;
  isCrawlRunning: boolean;
  onRefresh?: () => void;
}

export function LiveBrowserPanel({
  activeUrl,
  auditId,
  observation,
  activePageReport,
  isCrawlRunning,
  onRefresh,
}: LiveBrowserPanelProps) {
  const [viewport, setViewport] = useState<DeviceViewport>("fit");
  const [activeTab, setActiveTab] = useState<"preview" | "dom" | "console" | "network" | "headers" | "functionality">("preview");
  const [previewMode, setPreviewMode] = useState<"screenshot" | "iframe">("screenshot");
  const [copied, setCopied] = useState(false);

  // Fallback to activePageReport browser_data if observation is missing
  const effectiveObservation: BrowserObservationData | null = useMemo(() => {
    if (observation && Object.keys(observation).length > 0) {
      return observation;
    }
    if (activePageReport?.browser_data && Object.keys(activePageReport.browser_data).length > 0) {
      return activePageReport.browser_data;
    }
    return null;
  }, [observation, activePageReport]);

  const consoleErrors = effectiveObservation?.console_errors ?? [];
  const failedRequests = effectiveObservation?.failed_requests ?? [];
  // User-facing rendering status (never exposes internal engine identifiers)
  const engine = (() => {
    const raw = effectiveObservation?.browser_engine || "";
    switch (raw) {
      case "headless_browser":
        return "Live browser (rendered DOM)";
      case "html_snapshot":
      case "emulated-http":
        return "HTML snapshot (no JS rendering)";
      case "fetch-error":
        return "Fetch failed";
      default:
        return raw ? raw.replace(/[_-]+/g, " ") : "Not observed yet";
    }
  })();
  const timingMs = effectiveObservation?.timing_ms ?? activePageReport?.browser_data?.timing_ms;
  const statusCode = effectiveObservation?.status_code ?? activePageReport?.status_code;
  const isHttps = activeUrl.startsWith("https://");

  // Determine screenshot URL (storage endpoint or legacy data URI)
  const screenshotId =
    (effectiveObservation as any)?.screenshot_id ||
    (effectiveObservation as any)?.screenshot_metadata?.screenshot_id;
  const screenshotUrl = screenshotId
    ? `/api/audits/${encodeURIComponent(auditId)}/screenshots/${encodeURIComponent(screenshotId)}/`
    : effectiveObservation?.screenshot_data || "";

  // Check if frame preview is blocked by target site's response headers (X-Frame-Options or CSP frame-ancestors)
  const isFrameBlocked = useMemo(() => {
    const headers = effectiveObservation?.headers || {};
    for (const [key, val] of Object.entries(headers)) {
      const k = key.toLowerCase();
      const v = String(val).toLowerCase();
      if (k === "x-frame-options" && (v.includes("deny") || v.includes("sameorigin"))) {
        return true;
      }
      if (k === "content-security-policy" && v.includes("frame-ancestors")) {
        return true;
      }
    }
    return false;
  }, [effectiveObservation?.headers]);

  function handleCopyUrl() {
    if (!activeUrl) return;
    navigator.clipboard.writeText(activeUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // Viewport container width styling
  const viewportWidthClass = {
    desktop: "max-w-[1280px] w-full",
    tablet: "max-w-[768px] w-full",
    mobile: "max-w-[375px] w-full",
    fit: "w-full",
  }[viewport];

  return (
    <div className="flex flex-col h-full bg-slate-900 border-l border-slate-800 text-slate-100 overflow-hidden select-none">
      {/* Top Header Bar: Synchronized Status & Engine */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-slate-950 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-blue-950/80 border border-blue-800/80 text-blue-300 font-medium">
            <span className="relative flex h-2 w-2">
              {isCrawlRunning ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </>
              ) : (
                <span className="inline-flex rounded-full h-2 w-2 bg-slate-400"></span>
              )}
            </span>
            <span>Live Observation</span>
          </div>

          <div className="hidden sm:flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            <Shield className="w-3 h-3 text-slate-400" />
            <span className="text-[11px] font-mono text-slate-300">Read-only observation</span>
          </div>

          <div className="hidden md:flex items-center gap-1 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-400 font-mono">
            <span>Rendering:</span>
            <span className="text-slate-200 font-semibold">{engine}</span>
          </div>
        </div>

        {/* Viewport Width Controls */}
        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded p-0.5">
          <button
            onClick={() => setViewport("fit")}
            title="Fit Width"
            className={`px-1.5 py-0.5 rounded text-[11px] flex items-center gap-1 transition ${
              viewport === "fit" ? "bg-blue-600 text-white font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Maximize2 className="w-3 h-3" />
            <span className="hidden xl:inline">Fit</span>
          </button>
          <button
            onClick={() => setViewport("desktop")}
            title="Desktop 1280px"
            className={`px-1.5 py-0.5 rounded text-[11px] flex items-center gap-1 transition ${
              viewport === "desktop" ? "bg-blue-600 text-white font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Laptop className="w-3 h-3" />
            <span className="hidden xl:inline">1280</span>
          </button>
          <button
            onClick={() => setViewport("tablet")}
            title="Tablet 768px"
            className={`px-1.5 py-0.5 rounded text-[11px] flex items-center gap-1 transition ${
              viewport === "tablet" ? "bg-blue-600 text-white font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Tablet className="w-3 h-3" />
            <span className="hidden xl:inline">768</span>
          </button>
          <button
            onClick={() => setViewport("mobile")}
            title="Mobile 375px"
            className={`px-1.5 py-0.5 rounded text-[11px] flex items-center gap-1 transition ${
              viewport === "mobile" ? "bg-blue-600 text-white font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Smartphone className="w-3 h-3" />
            <span className="hidden xl:inline">375</span>
          </button>
        </div>
      </div>

      {/* URL Address Bar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-900 border-b border-slate-800">
        <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-slate-950 border border-slate-800 text-xs font-mono min-w-0">
          {isHttps ? (
            <Lock className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          ) : (
            <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          )}

          <span className="text-slate-300 truncate select-text flex-1">
            {activeUrl || "Awaiting crawler navigation..."}
          </span>

          {statusCode && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-sans font-semibold shrink-0 ${
                statusCode >= 200 && statusCode < 300
                  ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                  : statusCode >= 300 && statusCode < 400
                  ? "bg-amber-950 text-amber-400 border border-amber-800"
                  : "bg-red-950 text-red-400 border border-red-800"
              }`}
            >
              HTTP {statusCode}
            </span>
          )}

          {typeof timingMs === "number" && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-slate-400 shrink-0">
              <Clock className="w-3 h-3 text-slate-500" />
              {timingMs.toFixed(0)}ms
            </span>
          )}
        </div>

        <button
          onClick={handleCopyUrl}
          title="Copy active URL"
          className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition shrink-0"
        >
          {copied ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
        </button>

        {activeUrl && (
          <a
            href={activeUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Open URL in new tab"
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition shrink-0"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}

        {onRefresh && (
          <button
            onClick={onRefresh}
            title="Refresh current page observation"
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition shrink-0"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Observation Sub-navigation Tabs */}
      <div className="flex items-center gap-1 px-3 py-1 bg-slate-950 border-b border-slate-800 overflow-x-auto text-xs">
        <button
          onClick={() => setActiveTab("preview")}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition whitespace-nowrap ${
            activeTab === "preview"
              ? "bg-blue-600/30 text-blue-300 border border-blue-500/50 font-medium"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Page Preview</span>
        </button>

        <button
          onClick={() => setActiveTab("dom")}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition whitespace-nowrap ${
            activeTab === "dom"
              ? "bg-blue-600/30 text-blue-300 border border-blue-500/50 font-medium"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Code2 className="w-3.5 h-3.5" />
          <span>DOM Diagnostics</span>
          {effectiveObservation?.rendered_dom_available && (
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("console")}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition whitespace-nowrap ${
            activeTab === "console"
              ? "bg-blue-600/30 text-blue-300 border border-blue-500/50 font-medium"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Terminal className="w-3.5 h-3.5" />
          <span>Console Telemetry</span>
          {consoleErrors.length > 0 && (
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-red-950 text-red-400 border border-red-800 font-mono font-bold">
              {consoleErrors.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("network")}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition whitespace-nowrap ${
            activeTab === "network"
              ? "bg-blue-600/30 text-blue-300 border border-blue-500/50 font-medium"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          <span>Subresources</span>
          {failedRequests.length > 0 && (
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-amber-950 text-amber-400 border border-amber-800 font-mono font-bold">
              {failedRequests.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("headers")}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition whitespace-nowrap ${
            activeTab === "headers"
              ? "bg-blue-600/30 text-blue-300 border border-blue-500/50 font-medium"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileCode className="w-3.5 h-3.5" />
          <span>Headers & Network</span>
        </button>

        <button
          onClick={() => setActiveTab("functionality")}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition whitespace-nowrap ${
            activeTab === "functionality"
              ? "bg-blue-600/30 text-blue-300 border border-blue-500/50 font-medium"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Forms & Controls</span>
        </button>
      </div>

      {/* Main Panel Viewport Area */}
      <div className="flex-1 bg-slate-950 p-2 sm:p-4 overflow-auto flex justify-center items-start">
        {activeTab === "preview" && (
          <div className={`flex flex-col h-full ${viewportWidthClass} transition-all duration-200`}>
            {/* Read-only preview note */}
            <div className="mb-2 p-2 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[11px] flex items-start gap-2 shadow-sm">
              <Info className="w-3.5 h-3.5 text-blue-400 mt-0.5 shrink-0" />
              <div className="leading-relaxed">
                <span className="font-semibold text-slate-200">Page preview:</span> a read-only view of the audited page.
                Console, DOM and network telemetry shown in the other tabs come from the actual audit run for this URL.
              </div>
            </div>

            {/* Browser Window Frame */}
            <div className="flex-1 flex flex-col bg-slate-900 rounded-lg border border-slate-800 overflow-hidden shadow-2xl min-h-[480px]">
              {/* Window Controls */}
              <div className="flex items-center justify-between px-3 py-1.5 bg-slate-950 border-b border-slate-800">
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500/80"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80"></div>
                </div>

                <div className="text-[11px] text-slate-400 font-mono truncate max-w-[360px]">
                  {effectiveObservation?.page_title || activePageReport?.title || activeUrl || "Waiting for crawl..."}
                </div>

                <div className="flex items-center gap-2">
                  {screenshotUrl && (
                    <button
                      onClick={() => setPreviewMode((m) => (m === "screenshot" ? "iframe" : "screenshot"))}
                      className="px-2 py-0.5 rounded text-[10px] bg-slate-800 hover:bg-slate-700 text-blue-300 font-medium transition"
                    >
                      {previewMode === "screenshot"
                        ? "Page preview"
                        : "Browser screenshot"}
                    </button>
                  )}
                  <div className="text-[10px] text-slate-500 font-mono">
                    {viewport.toUpperCase()}
                  </div>
                </div>
              </div>

              {/* Read-only page preview or browser screenshot */}
              <div className="flex-1 relative bg-slate-950 flex items-center justify-center overflow-auto">
                {activeUrl ? (
                  screenshotUrl && previewMode === "screenshot" ? (
                    <div className="w-full h-full flex items-start justify-center p-2 bg-slate-950 overflow-auto">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={screenshotUrl}
                        alt="Browser screenshot of the audited page"
                        className="max-w-full h-auto rounded shadow border border-slate-800 object-contain"
                      />
                    </div>
                  ) : isFrameBlocked ? (
                    <div className="h-full flex flex-col items-center justify-center p-6 text-center text-slate-400 bg-slate-900">
                      <Shield className="w-8 h-8 mb-2 text-amber-400" />
                      <p className="text-sm font-semibold text-slate-200">Safe Preview Disabled by Site Policy</p>
                      <p className="text-xs text-slate-400 max-w-md mt-1">
                        The target page restricts iframe embedding via X-Frame-Options or CSP frame-ancestors directives.
                        A browser screenshot captured during the audit is used instead.
                      </p>
                      {screenshotUrl && (
                        <button
                          onClick={() => setPreviewMode("screenshot")}
                          className="mt-3 px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded font-medium"
                        >
                          View Browser Screenshot
                        </button>
                      )}
                    </div>
                  ) : (
                    <iframe
                      src={activeUrl}
                      title="Read-only page preview"
                      sandbox=""
                      referrerPolicy="no-referrer"
                      className="w-full h-full border-0 bg-white"
                      loading="lazy"
                    />
                  )
                ) : (
                  <div className="h-full flex flex-col items-center justify-center p-8 text-center text-slate-500 bg-slate-900">
                    <Globe className="w-10 h-10 mb-3 text-slate-600 animate-pulse" />
                    <p className="text-sm font-medium text-slate-300">Awaiting live crawl navigation</p>
                    <p className="text-xs text-slate-500 mt-1">
                      The preview follows the active page as the audit progresses.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* DOM Diagnostics Tab */}
        {activeTab === "dom" && (
          <div className="w-full max-w-4xl space-y-4 select-text">
            {/* Title & Metadata Card */}
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
              <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
                <Code2 className="w-4 h-4 text-blue-400" />
                <span>Title & Canonical Structure Comparison</span>
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 mb-1 flex items-center justify-between font-sans">
                    <span>Raw HTML Title:</span>
                    {effectiveObservation?.title_changed && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800">
                        Modified by JS
                      </span>
                    )}
                  </div>
                  <div className="text-slate-200 break-words font-semibold">
                    {effectiveObservation?.raw_title || activePageReport?.title || "—"}
                  </div>
                </div>

                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 mb-1 font-sans">Rendered DOM Title:</div>
                  <div className="text-slate-200 break-words font-semibold">
                    {effectiveObservation?.rendered_title || effectiveObservation?.page_title || activePageReport?.title || "—"}
                  </div>
                </div>

                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 mb-1 flex items-center justify-between font-sans">
                    <span>Raw Canonical Tag:</span>
                    {effectiveObservation?.canonical_changed && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800">
                        Modified by JS
                      </span>
                    )}
                  </div>
                  <div className="text-slate-200 break-all">
                    {effectiveObservation?.raw_canonical || "Not defined in raw HTML"}
                  </div>
                </div>

                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400 mb-1 font-sans">Rendered Canonical:</div>
                  <div className="text-slate-200 break-all">
                    {effectiveObservation?.rendered_canonical || effectiveObservation?.canonical || "Not defined"}
                  </div>
                </div>
              </div>
            </div>

            {/* Client-Side Hydration & Word Count */}
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
              <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <span>Client-Side Hydration & Content Density</span>
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400">Raw Word Count</div>
                  <div className="text-xl font-bold text-slate-100 mt-1 font-mono">
                    {effectiveObservation?.raw_word_count ?? "—"}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5">Initial server HTML response</div>
                </div>

                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400">Rendered Word Count</div>
                  <div className="text-xl font-bold text-slate-100 mt-1 font-mono">
                    {effectiveObservation?.rendered_word_count ?? "—"}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5">After JavaScript execution</div>
                </div>

                <div className="p-3 rounded bg-slate-950 border border-slate-800">
                  <div className="text-slate-400">Empty HTML Shell</div>
                  <div className="mt-1">
                    {effectiveObservation?.empty_html_shell ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800">
                        <AlertTriangle className="w-3.5 h-3.5" /> Detected (SSR Risk)
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Clean (Content Present)
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">Evaluates initial crawlability</div>
                </div>
              </div>
            </div>

            {/* Semantic Structure & Accessibility */}
            {effectiveObservation?.accessibility_summary && (
              <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
                <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-emerald-400" />
                  <span>Semantic Headings & Accessibility Diagnostic</span>
                </h3>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                    <span className="text-slate-400">H1 Tag Count</span>
                    <div className="text-lg font-bold text-slate-100 mt-0.5 font-mono">
                      {effectiveObservation.accessibility_summary.h1_count ?? 0}
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                    <span className="text-slate-400">Total Headings</span>
                    <div className="text-lg font-bold text-slate-100 mt-0.5 font-mono">
                      {effectiveObservation.accessibility_summary.total_headings ?? 0}
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                    <span className="text-slate-400">Missing Alt Tags</span>
                    <div className="text-lg font-bold text-amber-400 mt-0.5 font-mono">
                      {effectiveObservation.accessibility_summary.missing_alt_count ?? 0}
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                    <span className="text-slate-400">Viewport & Lang</span>
                    <div className="text-xs font-medium text-slate-200 mt-1">
                      {effectiveObservation.accessibility_summary.has_viewport ? "Viewport: Yes" : "No Viewport"} •{" "}
                      {effectiveObservation.accessibility_summary.has_lang ? "Lang: Yes" : "No Lang"}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Console Telemetry Tab */}
        {activeTab === "console" && (
          <div className="w-full max-w-4xl space-y-3 select-text font-mono text-xs">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900 border border-slate-800">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-blue-400" />
                <span className="font-semibold text-slate-200">Runtime Console Output</span>
              </div>
              <span className="text-slate-400 text-[11px]">
                {consoleErrors.length} message(s) captured during the audit run
              </span>
            </div>

            {consoleErrors.length === 0 ? (
              <div className="p-8 rounded-lg bg-slate-900 border border-slate-800 text-center text-slate-400 font-sans">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
                <p className="font-medium text-slate-200">Clean Console Execution</p>
                <p className="text-xs text-slate-500 mt-1">
                  No unhandled JavaScript exceptions or console warnings were observed on this page.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {consoleErrors.map((msg: any, idx: number) => (
                  <div
                    key={idx}
                    className={`p-3 rounded border ${
                      (msg.severity || msg.type) === "error" || msg.kind === "js_exception"
                        ? "bg-red-950/60 border-red-900 text-red-200"
                        : "bg-amber-950/60 border-amber-900 text-amber-200"
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px] mb-1 font-bold">
                      <span className="uppercase tracking-wider">
                        [{msg.kind || msg.type || "ERROR"}]
                        {Number(msg.occurrences || 1) > 1 ? ` ×${msg.occurrences}` : ""}
                      </span>
                      <span className="text-slate-400 font-normal">
                        {(msg.location && typeof msg.location === "object" && (msg.location as { url?: string }).url) ||
                          msg.source_url ||
                          ""}
                        {msg.location && typeof msg.location === "object" && (msg.location as { line?: number; lineNumber?: number }).line != null
                          ? `:${(msg.location as { line?: number }).line}`
                          : msg.location && typeof msg.location === "object" && (msg.location as { lineNumber?: number }).lineNumber != null
                          ? `:${(msg.location as { lineNumber?: number }).lineNumber}`
                          : ""}
                      </span>
                    </div>
                    <div className="break-words leading-relaxed">{msg.message || msg.text}</div>
                    {msg.page_url && (
                      <div className="text-[10px] text-slate-500 mt-1">page: {msg.page_url}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Failed Subresources Tab */}
        {activeTab === "network" && (
          <div className="w-full max-w-4xl space-y-3 select-text text-xs">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900 border border-slate-800">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-400" />
                <span className="font-semibold text-slate-200">Observed Network Subresources</span>
              </div>
              <span className="text-slate-400 text-[11px]">
                {failedRequests.length} failed asset request(s)
              </span>
            </div>

            {failedRequests.length === 0 ? (
              <div className="p-8 rounded-lg bg-slate-900 border border-slate-800 text-center text-slate-400">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
                <p className="font-medium text-slate-200">All Checked Assets Loaded Successfully</p>
                <p className="text-xs text-slate-500 mt-1">
                  Stylesheets, scripts, and media resources returned valid HTTP responses.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {failedRequests.map((req: any, idx: number) => (
                  <div
                    key={idx}
                    className="p-3 rounded bg-slate-900 border border-red-900/60 text-slate-200 flex flex-col gap-1"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="px-1.5 py-0.5 rounded font-mono font-bold bg-red-950 text-red-400 border border-red-800">
                        {req.status ? `HTTP ${req.status}` : req.failure || req.error || "NETWORK_FAIL"}
                      </span>
                      <span className="text-slate-400 uppercase text-[10px] font-mono">
                        {req.kind || req.resource_type || req.method || "Asset"}
                      </span>
                    </div>
                    <div className="font-mono text-slate-300 break-all">{req.url}</div>
                    {req.error && req.error !== req.failure && <div className="text-[11px] text-red-400">{req.error}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Headers & Network Tab */}
        {activeTab === "headers" && (
          <div className="w-full max-w-4xl space-y-4 select-text text-xs">
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
              <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
                <FileCode className="w-4 h-4 text-blue-400" />
                <span>Response Summary</span>
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono">
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans">Status Code</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {statusCode ?? "—"}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans">Response Latency</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {timingMs ? `${timingMs.toFixed(1)} ms` : "—"}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans">Final Destination</span>
                  <div className="text-xs text-slate-300 truncate mt-1">
                    {effectiveObservation?.final_url || activeUrl || "—"}
                  </div>
                </div>
              </div>

              {effectiveObservation?.headers && Object.keys(effectiveObservation.headers).length > 0 && (
                <div className="mt-4">
                  <div className="text-xs font-semibold text-slate-300 mb-2">HTTP Response Headers:</div>
                  <div className="p-3 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] space-y-1 overflow-x-auto">
                    {Object.entries(effectiveObservation.headers).map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <span className="text-slate-400 font-medium shrink-0">{k}:</span>
                        <span className="text-slate-200 break-all">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Forms, Navigation & Interactive Controls Tab */}
        {activeTab === "functionality" && (
          <div className="w-full max-w-4xl space-y-4 select-text text-xs">
            {/* Safe Read-Only Policy Alert */}
            <div className="p-3.5 rounded-lg bg-indigo-950/60 border border-indigo-800/80 text-indigo-200 flex items-start gap-2.5 shadow-sm">
              <Shield className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="font-semibold text-indigo-100 flex items-center gap-1.5">
                  <Lock className="w-3 h-3 text-indigo-400" /> Safe Read-Only Interactive Telemetry
                </div>
                <p className="text-[11px] leading-relaxed text-indigo-300">
                  Controls, links, and forms are passively evaluated for visibility, accessibility attributes, required fields, and client-side validation rules. In strict adherence to safe auditing guidelines, form submissions, payment attempts, and account creations are non-destructive and withheld without explicit authorization.
                </p>
              </div>
            </div>

            {/* Forms Telemetry */}
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-blue-400" />
                  <span>Observed Forms & Inputs</span>
                </h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                  {effectiveObservation?.forms_summary?.total_forms ?? 0} Forms Detected
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono">
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Total Fields</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {effectiveObservation?.forms_summary?.inputs_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Required Fields</span>
                  <div className="text-base font-bold text-amber-300 mt-0.5">
                    {effectiveObservation?.forms_summary?.required_inputs_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Labeled Fields</span>
                  <div className="text-base font-bold text-emerald-300 mt-0.5">
                    {effectiveObservation?.forms_summary?.labeled_inputs_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Submit Buttons</span>
                  <div className="text-base font-bold text-indigo-300 mt-0.5">
                    {effectiveObservation?.forms_summary?.submit_buttons_count ?? 0}
                  </div>
                </div>
              </div>

              {effectiveObservation?.forms_summary?.forms_detail && effectiveObservation.forms_summary.forms_detail.length > 0 && (
                <div className="space-y-2 pt-1">
                  <span className="text-[11px] font-bold uppercase text-slate-400 tracking-wider">Form Declarations:</span>
                  {effectiveObservation.forms_summary.forms_detail.map((form: any, idx: number) => (
                    <div key={idx} className="p-3 rounded bg-slate-950 border border-slate-800 text-[11px] space-y-1">
                      <div className="flex items-center justify-between font-mono">
                        <span className="text-blue-400 font-semibold">Form #{form.form_index ?? idx + 1} ({form.method || "POST"})</span>
                        <span className="text-slate-400">Action: {form.action || "(Current URL)"}</span>
                      </div>
                      <div className="text-slate-300 text-xs">
                        Fields: {form.input_count ?? 0} ({form.required_count ?? 0} required, {form.labeled_count ?? 0} labeled)
                      </div>
                      <div className="text-amber-400 font-mono text-[10px]">
                        Status: Safely Inspected (Submission Untested)
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Navigation & Menu Architecture */}
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 space-y-3">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Globe className="w-4 h-4 text-cyan-400" />
                <span>Navigation & Menu Usability</span>
              </h3>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono">
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">&lt;nav&gt; Elements</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {effectiveObservation?.navigation_summary?.nav_elements_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Nav Menu Links</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {effectiveObservation?.navigation_summary?.menu_links_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Empty / Broken Hrefs</span>
                  <div className={`text-base font-bold mt-0.5 ${(effectiveObservation?.navigation_summary?.empty_hrefs_count ?? 0) > 0 ? "text-amber-300" : "text-slate-100"}`}>
                    {effectiveObservation?.navigation_summary?.empty_hrefs_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Mobile Toggles</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {effectiveObservation?.navigation_summary?.mobile_toggles_count ?? 0}
                  </div>
                </div>
              </div>

              {effectiveObservation?.navigation_summary?.sample_nav_labels && effectiveObservation.navigation_summary.sample_nav_labels.length > 0 && (
                <div className="text-[11px] text-slate-400">
                  <span className="font-semibold text-slate-300">Observed Nav Items: </span>
                  {effectiveObservation.navigation_summary.sample_nav_labels.join(" · ")}
                </div>
              )}
            </div>

            {/* Interactive Controls & Buttons */}
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 space-y-3">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-400" />
                <span>Interactive Controls & Layout</span>
              </h3>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 font-mono">
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Total Buttons</span>
                  <div className="text-base font-bold text-slate-100 mt-0.5">
                    {effectiveObservation?.interactive_controls_summary?.buttons_count ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Missing Accessible Name</span>
                  <div className={`text-base font-bold mt-0.5 ${(effectiveObservation?.interactive_controls_summary?.buttons_without_accessible_name ?? 0) > 0 ? "text-rose-400" : "text-emerald-400"}`}>
                    {effectiveObservation?.interactive_controls_summary?.buttons_without_accessible_name ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 font-sans text-[11px]">Horizontal Overflow</span>
                  <div className={`text-sm font-bold mt-0.5 ${effectiveObservation?.layout_summary?.has_horizontal_scroll_overflow ? "text-rose-400" : "text-emerald-400"}`}>
                    {effectiveObservation?.layout_summary?.has_horizontal_scroll_overflow ? "Detected (Scroll Risk)" : "Clean (No Overflow)"}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
