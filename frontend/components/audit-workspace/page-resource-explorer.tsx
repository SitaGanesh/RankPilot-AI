"use client";

import { useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Compass,
  ExternalLink,
  Eye,
  FileCode,
  FileText,
  Filter,
  Globe,
  Image as ImageIcon,
  Layers,
  Link2,
  List,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";

import type { CrawlURL, PageAuditReport } from "@/types/api";

interface PageResourceExplorerProps {
  auditId: string;
  crawlUrls: CrawlURL[];
  pageReports: PageAuditReport[];
  activeUrl: string;
  onSelectUrl: (url: string, pageReport?: PageAuditReport) => void;
}

export function PageResourceExplorer({
  auditId,
  crawlUrls,
  pageReports,
  activeUrl,
  onSelectUrl,
}: PageResourceExplorerProps) {
  const [activeTab, setActiveTab] = useState<"pages" | "resources">("pages");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Map page reports by normalized URL or regular URL for instant lookup
  const pageReportsMap = useMemo(() => {
    const map = new Map<string, PageAuditReport>();
    for (const pr of pageReports) {
      if (pr.url) map.set(pr.url.toLowerCase(), pr);
      if (pr.normalized_url) map.set(pr.normalized_url.toLowerCase(), pr);
    }
    return map;
  }, [pageReports]);

  // Derived counts based on real data
  const counts = useMemo(() => {
    const pages = crawlUrls.filter((u) => u.resource_type === "page");
    const resources = crawlUrls.filter((u) => u.resource_type !== "page");
    const deeplyAudited = pages.filter((u) => u.deeply_audited || pageReportsMap.has(u.url.toLowerCase())).length;
    const queued = pages.filter((u) => u.status === "queued" || u.status === "pending").length;
    const completed = pages.filter((u) => u.status === "completed" || u.status === "fetched").length;
    const failed = pages.filter((u) => u.status === "failed").length;

    return {
      totalDiscovered: crawlUrls.length,
      totalPages: pages.length,
      totalResources: resources.length,
      deeplyAudited,
      queued,
      completed,
      failed,
    };
  }, [crawlUrls, pageReportsMap]);

  // Filtered lists
  const filteredPages = useMemo(() => {
    return crawlUrls
      .filter((u) => u.resource_type === "page")
      .filter((u) => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
          u.url.toLowerCase().includes(q) ||
          (u.page_title && u.page_title.toLowerCase().includes(q))
        );
      })
      .filter((u) => {
        if (statusFilter === "all") return true;
        if (statusFilter === "deeply_audited") {
          return u.deeply_audited || pageReportsMap.has(u.url.toLowerCase());
        }
        if (statusFilter === "queued") return u.status === "queued" || u.status === "pending";
        if (statusFilter === "failed") return u.status === "failed";
        if (statusFilter === "completed") return u.status === "completed" || u.status === "fetched";
        return true;
      });
  }, [crawlUrls, searchQuery, statusFilter, pageReportsMap]);

  const filteredResources = useMemo(() => {
    return crawlUrls
      .filter((u) => u.resource_type !== "page")
      .filter((u) => {
        if (!searchQuery) return true;
        return u.url.toLowerCase().includes(searchQuery.toLowerCase());
      })
      .filter((u) => {
        if (statusFilter === "all") return true;
        if (statusFilter === "failed") return u.status === "failed" || (u.response_status && u.response_status >= 400);
        if (statusFilter === "completed") return u.status === "fetched" || u.status === "completed";
        return true;
      });
  }, [crawlUrls, searchQuery, statusFilter]);

  return (
    <div className="flex flex-col h-full bg-white text-slate-800">
      {/* Real Counts Header Grid */}
      <div className="p-3 bg-slate-50 border-b border-slate-200 grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
        <div className="p-2 rounded bg-white border border-slate-200">
          <span className="text-slate-500 block text-[11px]">Discovered URLs</span>
          <span className="text-base font-bold text-slate-900 font-mono mt-0.5 block">
            {counts.totalDiscovered}
          </span>
        </div>

        <div className="p-2 rounded bg-white border border-slate-200">
          <span className="text-slate-500 block text-[11px]">Deeply Audited</span>
          <span className="text-base font-bold text-emerald-600 font-mono mt-0.5 block">
            {counts.deeplyAudited}
          </span>
        </div>

        <div className="p-2 rounded bg-white border border-slate-200">
          <span className="text-slate-500 block text-[11px]">In Queue</span>
          <span className="text-base font-bold text-blue-600 font-mono mt-0.5 block">
            {counts.queued}
          </span>
        </div>

        <div className="p-2 rounded bg-white border border-slate-200">
          <span className="text-slate-500 block text-[11px]">Completed / Fetched</span>
          <span className="text-base font-bold text-slate-700 font-mono mt-0.5 block">
            {counts.completed}
          </span>
        </div>

        <div className="p-2 rounded bg-white border border-slate-200">
          <span className="text-slate-500 block text-[11px]">Failed / Errors</span>
          <span className="text-base font-bold text-red-600 font-mono mt-0.5 block">
            {counts.failed}
          </span>
        </div>
      </div>

      {/* Explorer Controls: Search & Tabs */}
      <div className="p-3 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Tab Toggle: Pages vs Linked Resources */}
        <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-xs">
          <button
            onClick={() => setActiveTab("pages")}
            className={`px-3 py-1.5 rounded-md font-medium transition flex items-center gap-1.5 ${
              activeTab === "pages"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-blue-600" />
            <span>Discovered Pages ({counts.totalPages})</span>
          </button>

          <button
            onClick={() => setActiveTab("resources")}
            className={`px-3 py-1.5 rounded-md font-medium transition flex items-center gap-1.5 ${
              activeTab === "resources"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-purple-600" />
            <span>Linked Resources ({counts.totalResources})</span>
          </button>
        </div>

        {/* Search & Filter */}
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder={activeTab === "pages" ? "Search pages by URL or title..." : "Search resources..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-md bg-slate-50 border border-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-md bg-slate-50 border border-slate-200 text-xs text-slate-700 focus:outline-none"
          >
            <option value="all">All Statuses</option>
            {activeTab === "pages" && <option value="deeply_audited">Deeply Audited</option>}
            <option value="completed">Completed</option>
            <option value="queued">Queued</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {/* List Container */}
      <div className="flex-1 overflow-auto divide-y divide-slate-100">
        {activeTab === "pages" ? (
          filteredPages.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-xs">
              No discovered pages match the current filters.
            </div>
          ) : (
            filteredPages.map((page) => {
              const report = pageReportsMap.get(page.url.toLowerCase());
              const isSelected = activeUrl.toLowerCase() === page.url.toLowerCase();
              const isDeep = Boolean(page.deeply_audited || report);

              return (
                <div
                  key={page.id}
                  onClick={(event) => {
                    // Completed pages open their persisted report in a new tab without rerunning the crawl
                    if (isDeep && report) {
                      event.stopPropagation();
                      window.open(
                        `/audits/${encodeURIComponent(auditId)}/pages/${report.id}`,
                        "_blank",
                        "noopener,noreferrer"
                      );
                      return;
                    }
                    onSelectUrl(page.url, report);
                  }}
                  className={`p-3 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs hover:bg-blue-50/50 ${
                    isSelected ? "bg-blue-50/80 border-l-4 border-l-blue-600" : ""
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {isDeep ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <ShieldCheck className="w-3 h-3 text-emerald-600" />
                          Deeply Audited
                        </span>
                      ) : page.status === "queued" || page.status === "pending" ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200">
                          <Clock className="w-3 h-3 text-blue-500 animate-spin" />
                          Queued
                        </span>
                      ) : page.status === "failed" ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-700 border border-red-200">
                          <AlertTriangle className="w-3 h-3 text-red-500" />
                          Failed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                          Shallow Check
                        </span>
                      )}

                      {page.response_status && (
                        <span
                          className={`font-mono text-[10px] font-semibold px-1 py-0.2 rounded ${
                            page.response_status >= 200 && page.response_status < 300
                              ? "text-emerald-700 bg-emerald-50"
                              : "text-amber-700 bg-amber-50"
                          }`}
                        >
                          HTTP {page.response_status}
                        </span>
                      )}

                      <span className="text-[10px] text-slate-400 font-mono">
                        Depth {page.depth} • Source: {page.discovery_source}
                      </span>
                    </div>

                    <div className="font-semibold text-slate-900 truncate">
                      {page.page_title || report?.title || "Untitled Page"}
                    </div>

                    <div className="text-slate-500 font-mono text-[11px] truncate mt-0.5">
                      {page.url}
                    </div>

                    {page.error && (
                      <div className="text-red-600 text-[11px] mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3 shrink-0" />
                        <span>{page.error}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex sm:flex-col items-center sm:items-end justify-between shrink-0 gap-1">
                    {report?.score_percent !== undefined && report.score_percent !== null && (
                      <span
                        className={`font-bold font-mono text-xs px-2 py-0.5 rounded border ${
                          report.score_percent >= 80
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : report.score_percent >= 50
                            ? "bg-amber-50 text-amber-700 border-amber-200"
                            : "bg-red-50 text-red-700 border-red-200"
                        }`}
                      >
                        {report.score_percent.toFixed(0)}%
                      </span>
                    )}

                    <span className="text-[11px] text-blue-600 font-medium hover:underline flex items-center gap-1">
                      <span>{isDeep && report ? "Open report" : "Inspect"}</span>
                      <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              );
            })
          )
        ) : (
          /* Resources Tab */
          filteredResources.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-xs">
              No linked media or asset subresources recorded.
            </div>
          ) : (
            filteredResources.map((res) => (
              <div
                key={res.id}
                className="p-3 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-slate-50 transition"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                      <ImageIcon className="w-3 h-3" />
                      {res.resource_type}
                    </span>

                    {res.response_status && (
                      <span
                        className={`font-mono text-[10px] font-semibold px-1 py-0.2 rounded ${
                          res.response_status >= 200 && res.response_status < 300
                            ? "text-emerald-700 bg-emerald-50"
                            : "text-red-700 bg-red-50"
                        }`}
                      >
                        HTTP {res.response_status}
                      </span>
                    )}

                    <span className="text-[10px] text-slate-400">
                      Shallow Asset Check (Availability Verified)
                    </span>
                  </div>

                  <div className="font-mono text-slate-800 break-all text-[11px]">
                    {res.url}
                  </div>

                  {res.error && (
                    <div className="text-red-600 text-[11px] mt-1 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3 shrink-0" />
                      <span>{res.error}</span>
                    </div>
                  )}
                </div>

                <div className="shrink-0 text-right">
                  <a
                    href={res.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-800"
                  >
                    <span>Open Asset</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            ))
          )
        )}
      </div>
    </div>
  );
}
