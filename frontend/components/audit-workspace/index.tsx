"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Columns,
  Compass,
  ExternalLink,
  Eye,
  FileCode,
  FileText,
  Globe,
  HelpCircle,
  Layers,
  LayoutGrid,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  StopCircle,
  Terminal,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";

import {
  cancelAudit,
  getAuditLiveEvents,
  getAuditLiveStreamUrl,
  getAuditPage,
  getAuditPageByUrl,
  getAuditPages,
  getAuditReportCsvUrl,
  getAuditStatus,
  getConsolidatedWebsiteReport,
  getCrawlURLs,
} from "@/lib/api";
import type {
  AuditLiveEvent,
  AuditStatus,
  AuditStatusResponse,
  BrowserObservationData,
  ConsolidatedWebsiteReport,
  CrawlURL,
  PageAuditFinding,
  PageAuditReport,
} from "@/types/api";
import { LiveBrowserPanel } from "./live-browser-panel";
import { LiveReportPanel } from "./live-report-panel";
import type { DeviceViewport, ViewLayoutMode } from "./types";

interface LiveAuditWorkspaceProps {
  auditId: string;
}

export function LiveAuditWorkspace({ auditId }: LiveAuditWorkspaceProps) {
  const router = useRouter();

  // Audit state
  const [audit, setAudit] = useState<AuditStatusResponse | null>(null);
  const [targetUrl, setTargetUrl] = useState<string>("");
  const [activeUrl, setActiveUrl] = useState<string>("");
  const [autoFollowCrawler, setAutoFollowCrawler] = useState<boolean>(true);

  // Data collections
  const [crawlUrls, setCrawlUrls] = useState<CrawlURL[]>([]);
  const [pageReports, setPageReports] = useState<PageAuditReport[]>([]);
  const [findings, setFindings] = useState<PageAuditFinding[]>([]);
  const [consolidatedReport, setConsolidatedReport] = useState<ConsolidatedWebsiteReport | null>(null);
  const [liveObservation, setLiveObservation] = useState<BrowserObservationData | null>(null);
  const [activePageReport, setActivePageReport] = useState<PageAuditReport | null>(null);
  const [pageReportError, setPageReportError] = useState<string | null>(null);

  // Synchronization status
  const [connectionMode, setConnectionMode] = useState<"sse" | "polling" | "connected" | "closed">("sse");
  const [lastEventId, setLastEventId] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Responsive Layout Mode
  const [layoutMode, setLayoutMode] = useState<ViewLayoutMode>("split");
  const [mobileTab, setMobileTab] = useState<"report" | "browser">("report");

  // Keep track of processed event IDs to avoid duplicate findings
  const processedEventIdsRef = useRef<Set<number>>(new Set());
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollingTimerRef = useRef<number | null>(null);

  const isCrawlRunning = audit?.status === "running" || audit?.status === "collecting" || audit?.status === "pending" || audit?.status === "queued";

  // Initial Data Fetch
  const loadInitialData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusData, urlsData, pagesData] = await Promise.all([
        getAuditStatus(auditId),
        getCrawlURLs(auditId),
        getAuditPages(auditId).catch(() => ({ audit_id: auditId, total_pages: 0, pages: [] })),
      ]);

      setAudit(statusData);
      setTargetUrl(statusData.url);
      setCrawlUrls(urlsData);
      setPageReports(pagesData.pages);

      // Collect initial findings from all loaded page reports
      const initialFindings: PageAuditFinding[] = [];
      for (const pr of pagesData.pages) {
        if (pr.report_json?.findings) {
          for (const f of pr.report_json.findings) {
            initialFindings.push({
              ...f,
              page_url: pr.url,
              page_title: pr.title,
            });
          }
        }
      }
      setFindings(initialFindings);

      // Set active URL
      const initialActive = urlsData.find((u) => u.deeply_audited)?.url || statusData.url;
      setActiveUrl(initialActive);

      // If already completed, fetch the consolidated website report
      if (statusData.status === "completed") {
        try {
          const report = await getConsolidatedWebsiteReport(auditId);
          setConsolidatedReport(report);
        } catch {
          // Non-critical if consolidated report is still being finalized
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load audit workspace data.");
    } finally {
      setLoading(false);
    }
  }, [auditId]);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Update active page report when activeUrl or pageReports change
  useEffect(() => {
    if (!activeUrl) return;
    const norm = activeUrl.toLowerCase();
    const found = pageReports.find(
      (pr) => pr.url.toLowerCase() === norm || pr.normalized_url.toLowerCase() === norm
    );
    if (found) {
      setActivePageReport(found);
    }
  }, [activeUrl, pageReports]);

  // Helper to handle live event safely
  const handleLiveEvent = useCallback(
    (ev: AuditLiveEvent) => {
      if (processedEventIdsRef.current.has(ev.id)) {
        return;
      }
      processedEventIdsRef.current.add(ev.id);
      setLastEventId((prev) => Math.max(prev, ev.id));

      const payload = ev.data || {};

      switch (ev.event_type) {
        case "audit.status":
          if (payload.status) {
            setAudit((prev) => (prev ? { ...prev, status: payload.status } : null));
          }
          break;

        case "url.discovered":
          if (ev.url) {
            setCrawlUrls((prev) => {
              if (prev.some((u) => u.url.toLowerCase() === ev.url.toLowerCase())) {
                return prev;
              }
              const newCrawlItem: CrawlURL = {
                id: ev.id,
                url: ev.url,
                status: "pending",
                resource_type: "page",
                depth: payload.depth ?? 1,
                response_status: null,
                discovery_source: payload.source ?? "internal_link",
                discovery_source_url: payload.parent_url ?? "",
                discovered_from: null,
                final_url: ev.url,
                error: "",
                created_at: ev.created_at,
                updated_at: ev.created_at,
              };
              return [...prev, newCrawlItem];
            });
          }
          break;

        case "navigation.start":
          if (ev.url) {
            if (autoFollowCrawler) {
              setActiveUrl(ev.url);
            }
            setCrawlUrls((prev) =>
              prev.map((u) =>
                u.url.toLowerCase() === ev.url.toLowerCase() ? { ...u, status: "fetching" } : u
              )
            );
          }
          break;

        case "browser.observation":
          if (ev.url) {
            const obsData: BrowserObservationData = {
              url: ev.url,
              final_url: payload.final_url || ev.url,
              status_code: payload.status_code,
              timing_ms: payload.timing_ms,
              browser_engine: payload.browser_engine,
              page_title: payload.title,
              rendered_dom_available: payload.rendered_dom_available,
              empty_html_shell: payload.empty_html_shell,
            };
            setLiveObservation(obsData);

            if (autoFollowCrawler) {
              setActiveUrl(ev.url);
            }

            setCrawlUrls((prev) =>
              prev.map((u) =>
                u.url.toLowerCase() === ev.url.toLowerCase()
                  ? {
                      ...u,
                      response_status: payload.status_code,
                      page_title: payload.title,
                      timing_ms: payload.timing_ms,
                      final_url: payload.final_url || u.url,
                    }
                  : u
              )
            );
          }
          break;

        case "page.screenshot":
          if (payload.screenshot_id || payload.screenshot) {
            setLiveObservation((prev) => ({
              ...prev,
              url: ev.url || prev?.url || "",
              screenshot_id: payload.screenshot_id || (prev as any)?.screenshot_id,
              screenshot_data: payload.screenshot || prev?.screenshot_data || "",
            }));
          }
          break;

        case "finding.emitted":
          if (payload.check_id && payload.title) {
            const newFinding: PageAuditFinding = {
              id: payload.finding_id || `finding-${ev.id}`,
              check_id: payload.check_id,
              title: payload.title,
              status: payload.status || "fail",
              severity: payload.severity || "medium",
              evidence: {
                observed: payload.observed,
                expected: payload.expected,
                selector: payload.selector,
              },
              recommendation: payload.recommendation,
              why_it_matters: payload.why_it_matters,
              page_url: ev.url,
            };
            setFindings((prev) => {
              if (prev.some((f) => f.id === newFinding.id)) return prev;
              return [newFinding, ...prev];
            });
          }
          break;

        case "report.update":
          if (payload.page_report_id) {
            // Re-fetch pages to obtain full PageAuditReport
            getAuditPages(auditId)
              .then((res) => {
                setPageReports(res.pages);
              })
              .catch(() => {});
          }
          break;

        case "navigation.complete":
          if (ev.url) {
            setCrawlUrls((prev) =>
              prev.map((u) =>
                u.url.toLowerCase() === ev.url.toLowerCase()
                  ? {
                      ...u,
                      status: payload.status === "failed" ? "failed" : "fetched",
                      deeply_audited: payload.status !== "failed",
                      error: payload.error || "",
                    }
                  : u
              )
            );
          }
          break;

        case "audit.completed":
          setAudit((prev) => (prev ? { ...prev, status: "completed" } : null));
          getConsolidatedWebsiteReport(auditId)
            .then(setConsolidatedReport)
            .catch(() => {});
          getAuditPages(auditId)
            .then((res) => setPageReports(res.pages))
            .catch(() => {});
          break;

        case "audit.failed":
          setAudit((prev) => (prev ? { ...prev, status: "failed" } : null));
          setError(payload.error || "The live website audit failed.");
          break;
      }
    },
    [auditId, autoFollowCrawler]
  );

  // Setup SSE Stream with Fallback to Polling
  useEffect(() => {
    if (!audit || audit.status === "completed" || audit.status === "failed" || audit.status === "cancelled") {
      return;
    }

    let isSubscribed = true;

    // Start SSE stream
    const streamUrl = getAuditLiveStreamUrl(auditId, lastEventId);
    let es: EventSource | null = null;

    try {
      es = new EventSource(streamUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        if (!isSubscribed) return;
        setConnectionMode("sse");
      };

      const eventNames = [
        "audit.status",
        "url.discovered",
        "navigation.start",
        "navigation.complete",
        "browser.observation",
        "agent.start",
        "agent.complete",
        "agent.failure",
        "finding.emitted",
        "report.update",
        "audit.completed",
        "audit.failed",
      ];

      for (const evName of eventNames) {
        es.addEventListener(evName, (e: MessageEvent) => {
          if (!isSubscribed) return;
          try {
            const data = JSON.parse(e.data);
            handleLiveEvent(data);
          } catch {
            // Ignore parse errors on individual frames
          }
        });
      }

      es.addEventListener("close", () => {
        if (!isSubscribed) return;
        setConnectionMode("closed");
        es?.close();
      });

      es.onerror = () => {
        if (!isSubscribed) return;
        // Switch to polling fallback
        setConnectionMode("polling");
        es?.close();
        startPolling();
      };
    } catch {
      startPolling();
    }

    function startPolling() {
      if (pollingTimerRef.current) return;
      pollingTimerRef.current = window.setInterval(async () => {
        if (!isSubscribed) return;
        try {
          const pollRes = await getAuditLiveEvents(auditId, lastEventId);
          if (pollRes.events && pollRes.events.length > 0) {
            for (const ev of pollRes.events) {
              handleLiveEvent(ev);
            }
          }
          if (pollRes.completed) {
            if (pollingTimerRef.current) {
              clearInterval(pollingTimerRef.current);
              pollingTimerRef.current = null;
            }
            setConnectionMode("closed");
          }
        } catch {
          // Poll attempt failed; will retry next interval
        }
      }, 2000);
    }

    return () => {
      isSubscribed = false;
      if (es) {
        es.close();
      }
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, [audit?.status, auditId, handleLiveEvent, lastEventId]);

  // Handle Cancel Audit
  async function handleCancel() {
    if (!confirm("Are you sure you want to stop the live audit crawl?")) return;
    setCancelling(true);
    try {
      await cancelAudit(auditId);
      setAudit((prev) => (prev ? { ...prev, status: "cancelled" } : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel audit.");
    } finally {
      setCancelling(false);
    }
  }

  // Handle URL Selection from Report or Explorer
  const handleSelectUrl = useCallback(
    (url: string, pageReport?: PageAuditReport) => {
      setAutoFollowCrawler(false);
      setActiveUrl(url);

      if (pageReport) {
        setActivePageReport(pageReport);
        setPageReportError(null);
        if (pageReport.browser_data) {
          setLiveObservation(pageReport.browser_data);
        }
      } else {
        // Find in loaded page reports
        const found = pageReports.find(
          (pr) => pr.url.toLowerCase() === url.toLowerCase() || pr.normalized_url.toLowerCase() === url.toLowerCase()
        );
        if (found) {
          setActivePageReport(found);
          setPageReportError(null);
          if (found.browser_data) {
            setLiveObservation(found.browser_data);
          }
        } else {
          // Fetch on demand from backend
          setPageReportError(null);
          getAuditPageByUrl(auditId, url)
            .then((pr) => {
              setActivePageReport(pr);
              setPageReportError(null);
              if (pr.browser_data) setLiveObservation(pr.browser_data);
            })
            .catch((err) => {
              setActivePageReport(null);
              setPageReportError(err instanceof Error ? err.message : "No report found for this page.");
            });
        }
      }
    },
    [auditId, pageReports]
  );

  // Layout Width Calculation
  const splitWidthClasses = {
    split: { left: "lg:w-1/2", right: "lg:w-1/2" },
    "report-focus": { left: "lg:w-[65%]", right: "lg:w-[35%]" },
    "browser-focus": { left: "lg:w-[35%]", right: "lg:w-[65%]" },
    "report-only": { left: "w-full", right: "hidden" },
    "browser-only": { left: "hidden", right: "w-full" },
  }[layoutMode];

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans">
      {/* Top Main Workspace Navigation Bar */}
      <header className="h-14 bg-slate-950 border-b border-slate-800 px-3 sm:px-4 flex items-center justify-between gap-3 shrink-0 z-20">
        {/* Left: Branding & Back link */}
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>

          <div className="flex items-center gap-2 min-w-0">
            <span className="font-bold text-sm text-slate-100 tracking-tight hidden sm:inline">
              RankPilot Live
            </span>
            <span className="text-slate-600 hidden sm:inline">/</span>
            <span className="font-mono text-xs text-blue-400 font-semibold truncate max-w-[200px] sm:max-w-[320px]">
              {targetUrl || auditId}
            </span>
          </div>

          {/* Real-time Status Badge */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-900 border border-slate-800">
            {isCrawlRunning ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span className="text-emerald-400 font-semibold uppercase tracking-wider text-[10px]">
                  Crawling Live
                </span>
              </>
            ) : audit?.status === "completed" ? (
              <>
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span className="text-emerald-400 font-semibold text-[10px]">COMPLETED</span>
              </>
            ) : audit?.status === "failed" ? (
              <>
                <XCircle className="w-3 h-3 text-red-400" />
                <span className="text-red-400 font-semibold text-[10px]">FAILED</span>
              </>
            ) : (
              <span className="text-slate-400 text-[10px] uppercase font-mono">
                {audit?.status || "QUEUED"}
              </span>
            )}
          </div>
        </div>

        {/* Center: Live Sync & Real Counts */}
        <div className="hidden xl:flex items-center gap-4 text-xs font-mono text-slate-400">
          <div className="flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5 text-blue-400" />
            <span>Discovered:</span>
            <span className="text-slate-200 font-bold">{crawlUrls.length}</span>
          </div>

          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Deeply Audited:</span>
            <span className="text-emerald-400 font-bold">
              {crawlUrls.filter((u) => u.deeply_audited).length}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>In Queue:</span>
            <span className="text-slate-200 font-bold">
              {crawlUrls.filter((u) => u.status === "queued" || u.status === "pending").length}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-purple-400" />
            <span>Sync Mode:</span>
            <span className="text-slate-300 font-semibold uppercase text-[10px]">
              {connectionMode}
            </span>
          </div>
        </div>

        {/* Right: Controls & View Layout Presets */}
        <div className="flex items-center gap-2">
          {/* Cancel Audit Button */}
          {isCrawlRunning && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="px-2.5 py-1 rounded bg-red-950/80 hover:bg-red-900 border border-red-800 text-red-300 text-xs font-medium transition flex items-center gap-1.5"
              title="Stop live crawl"
            >
              <StopCircle className="w-3.5 h-3.5" />
              <span>{cancelling ? "Stopping..." : "Stop Audit"}</span>
            </button>
          )}

          {/* Desktop Layout Preset Selectors */}
          <div className="hidden lg:flex items-center gap-0.5 bg-slate-900 border border-slate-800 rounded p-0.5 text-xs">
            <button
              onClick={() => setLayoutMode("split")}
              title="Split 50 / 50"
              className={`p-1.5 rounded transition ${
                layoutMode === "split" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Columns className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setLayoutMode("report-focus")}
              title="Report Focus 65 / 35"
              className={`p-1.5 rounded text-[11px] font-mono transition ${
                layoutMode === "report-focus" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              65:35
            </button>
            <button
              onClick={() => setLayoutMode("browser-focus")}
              title="Browser Focus 35 / 65"
              className={`p-1.5 rounded text-[11px] font-mono transition ${
                layoutMode === "browser-focus" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              35:65
            </button>
            <button
              onClick={() => setLayoutMode("report-only")}
              title="Report Only"
              className={`p-1.5 rounded transition ${
                layoutMode === "report-only" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setLayoutMode("browser-only")}
              title="Browser Only"
              className={`p-1.5 rounded transition ${
                layoutMode === "browser-only" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Mobile Screen Tab Toggle */}
          <div className="flex lg:hidden items-center bg-slate-900 border border-slate-800 rounded p-0.5 text-xs">
            <button
              onClick={() => setMobileTab("report")}
              className={`px-2 py-1 rounded text-xs font-medium transition ${
                mobileTab === "report" ? "bg-blue-600 text-white" : "text-slate-400"
              }`}
            >
              Report
            </button>
            <button
              onClick={() => setMobileTab("browser")}
              className={`px-2 py-1 rounded text-xs font-medium transition ${
                mobileTab === "browser" ? "bg-blue-600 text-white" : "text-slate-400"
              }`}
            >
              Observation
            </button>
          </div>
        </div>
      </header>

      {/* Error Ribbon */}
      {error && (
        <div className="bg-red-950/80 border-b border-red-900 px-4 py-2 text-red-200 text-xs flex items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-red-400 hover:text-red-200 font-bold px-1"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Split-Screen Workspace Container */}
      <main className="flex-1 flex overflow-hidden relative">
        {/* Left Panel: Dynamic Report & Findings Panel */}
        <section
          className={`h-full flex flex-col overflow-hidden transition-all duration-150 ${splitWidthClasses.left} ${
            mobileTab === "report" ? "flex" : "hidden lg:flex"
          }`}
        >
          <LiveReportPanel
            auditId={auditId}
            targetUrl={targetUrl}
            isCrawlRunning={isCrawlRunning}
            activeUrl={activeUrl}
            activePageReport={activePageReport}
            pageReportError={pageReportError}
            consolidatedReport={consolidatedReport}
            findings={findings}
            crawlUrls={crawlUrls}
            pageReports={pageReports}
            onSelectUrl={handleSelectUrl}
            onFollowLiveCrawler={() => {
              setAutoFollowCrawler(true);
            }}
            isFollowingCrawler={autoFollowCrawler}
          />
        </section>

        {/* Right Panel: Live Browser & Page Observation Panel */}
        <section
          className={`h-full flex flex-col overflow-hidden transition-all duration-150 ${splitWidthClasses.right} ${
            mobileTab === "browser" ? "flex" : "hidden lg:flex"
          }`}
        >
          <LiveBrowserPanel
            activeUrl={activeUrl}
            auditId={auditId}
            observation={liveObservation}
            activePageReport={activePageReport}
            isCrawlRunning={isCrawlRunning}
            onRefresh={() => {
              if (activeUrl) {
                getAuditPageByUrl(auditId, activeUrl)
                  .then((pr) => {
                    setActivePageReport(pr);
                    if (pr.browser_data) setLiveObservation(pr.browser_data);
                  })
                  .catch(() => {});
              }
            }}
          />
        </section>
      </main>
    </div>
  );
}
