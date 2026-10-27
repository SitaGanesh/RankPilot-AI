"use client";

import { useMemo } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCode,
  FileText,
  Globe2,
  HelpCircle,
  Image as ImageIcon,
  Layers,
  Link2,
  Play,
  ShieldAlert,
  Sparkles,
  Video,
  X,
  Zap,
} from "lucide-react";
import type { ResourceGraphNode } from "@/types/api";

interface NodeInspectorProps {
  node: ResourceGraphNode | null;
  primaryUrl: string;
  onClose: () => void;
  onAuditUrl: (url: string) => void;
}

export function NodeInspector({
  node,
  primaryUrl,
  onClose,
  onAuditUrl,
}: NodeInspectorProps) {
  if (!node) return null;

  const isPrimary = node.deeply_audited || node.node_type === "primary_page" || node.url === primaryUrl;
  const isHtmlPage = node.node_type === "linked_page" || node.node_type === "primary_page";

  const statusTone = useMemo(() => {
    switch (node.status) {
      case "available":
        return {
          bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
          dot: "bg-emerald-500",
          label: `${node.http_status ?? 200} OK · Available`,
        };
      case "redirects":
        return {
          bg: "bg-amber-50 text-amber-700 border-amber-200",
          dot: "bg-amber-500",
          label: `${node.http_status ?? 301} · Redirects`,
        };
      case "client_error":
        return {
          bg: "bg-red-50 text-red-700 border-red-200",
          dot: "bg-red-500",
          label: `${node.http_status ?? 404} · Client Error`,
        };
      case "server_error":
        return {
          bg: "bg-rose-50 text-rose-700 border-rose-200",
          dot: "bg-rose-500",
          label: `${node.http_status ?? 500} · Server Error`,
        };
      case "could_not_be_checked":
        return {
          bg: "bg-slate-100 text-slate-700 border-slate-300",
          dot: "bg-slate-400",
          label: "Unverified / Protected",
        };
      default:
        return {
          bg: "bg-rose-50 text-rose-700 border-rose-200",
          dot: "bg-rose-500",
          label: node.status,
        };
    }
  }, [node.status, node.http_status]);

  const typeIcon = useMemo(() => {
    switch (node.node_type) {
      case "primary_page":
        return <Sparkles size={16} className="text-indigo-600" />;
      case "linked_page":
        return node.is_internal ? (
          <Link2 size={16} className="text-blue-600" />
        ) : (
          <Globe2 size={16} className="text-cyan-600" />
        );
      case "image":
        return <ImageIcon size={16} className="text-emerald-600" />;
      case "media":
        return <Video size={16} className="text-teal-600" />;
      case "stylesheet":
      case "script":
        return <FileCode size={16} className="text-violet-600" />;
      case "failed_resource":
        return <AlertTriangle size={16} className="text-red-600" />;
      default:
        return <FileText size={16} className="text-slate-600" />;
    }
  }, [node.node_type, node.is_internal]);

  return (
    <aside
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform animate-in slide-in-from-right duration-200"
      aria-label="Node Details"
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="grid size-8 place-items-center rounded-lg bg-slate-100">
            {typeIcon}
          </div>
          <div>
            <h3 className="text-sm font-bold capitalize text-slate-900">
              {node.node_type.replace(/_/g, " ")} Details
            </h3>
            <p className="text-xs text-slate-500">Resource Inspector</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="grid size-8 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
          aria-label="Close panel"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
        {/* Provenance & Audit Scope Banner */}
        {isPrimary ? (
          <div className="rounded-xl border border-indigo-200 bg-gradient-to-r from-indigo-50 to-purple-50 p-4">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-600 px-2.5 py-0.5 text-xs font-bold text-white shadow-xs">
                <Sparkles size={12} /> Primary Audited Page
              </span>
              <span className="text-xs font-semibold text-indigo-900">Deep Multi-Agent Analysis</span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-indigo-950">
              This is the audit root. Full DOM evidence, headers, navigation structure, forms, subresources, and SEO/connectivity signals were comprehensively analyzed.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-semibold text-slate-800">
                Connected Resource
              </span>
              <span className="text-[11px] font-medium text-slate-500">
                {node.deeply_audited ? "Deeply Audited" : "Lightweight Shallow Check"}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-600">
              {node.deeply_audited
                ? "This page was deeply crawled and audited with full multi-agent evidence."
                : "Discovered during crawl. Verified via bounded HTTP checks without recursive crawling to respect rate limits and crawl bounds."}
            </p>
          </div>
        )}

        {/* Potential Orphan Alert if applicable */}
        {node.is_orphan && !isPrimary && isHtmlPage && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-600 px-2.5 py-0.5 text-xs font-bold text-white">
                <AlertTriangle size={12} /> Potential Orphan Page
              </span>
              <span className="text-xs font-medium text-amber-900">0 Inbound Links in Crawl</span>
            </div>
            <p className="mt-2 text-xs text-amber-800 leading-relaxed">
              No internal links discovered pointing to this page within the configured crawl depth. Note: Orphan status is bounded by crawl depth and limits; verify external discovery channels and sitemaps.
            </p>
          </div>
        )}

        {/* Connectivity & Discovery Metadata */}
        {(node.in_degree !== undefined || node.out_degree !== undefined || node.discovery_source) && (
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Connectivity & Discovery Architecture
            </h4>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg border border-slate-200 p-2.5 bg-slate-50/50">
                <span className="text-[10px] uppercase font-bold text-slate-400">Inbound Links</span>
                <p className="mt-1 text-sm font-bold text-slate-900">
                  {node.in_degree ?? 0}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 p-2.5 bg-slate-50/50">
                <span className="text-[10px] uppercase font-bold text-slate-400">Outbound Links</span>
                <p className="mt-1 text-sm font-bold text-slate-900">
                  {node.out_degree ?? 0}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 p-2.5 bg-slate-50/50">
                <span className="text-[10px] uppercase font-bold text-slate-400">Discovery</span>
                <p className="mt-1 font-semibold text-slate-800 capitalize truncate" title={node.discovery_source || "crawl"}>
                  {node.discovery_source || "crawl"}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* URL Box & Deep Audit Action */}
        <div className="space-y-3">
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Target URL
            </label>
            <div className="mt-1 flex items-start justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50/70 p-3 text-xs">
              <span className="break-all font-mono font-medium text-slate-900">
                {node.url}
              </span>
              <a
                href={node.url}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-slate-400 hover:text-indigo-600 transition"
                title="Open in new tab"
              >
                <ExternalLink size={15} />
              </a>
            </div>
          </div>

          {/* If it is a linked HTML page and not the current primary, allow on-demand exploration */}
          {!isPrimary && isHtmlPage && !node.deeply_audited && (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold text-slate-900">Deep Audit This Page</p>
                <p className="text-[11px] text-slate-500">
                  Launch a full multi-agent single-URL audit with this page as the primary node.
                </p>
              </div>
              <button
                onClick={() => onAuditUrl(node.url)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition"
              >
                <Play size={13} /> Audit Now
              </button>
            </div>
          )}
        </div>

        {/* Network & HTTP Check Results */}
        <div className="space-y-3">
          <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Shallow Check Response
          </h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg border border-slate-200 p-3">
              <span className="text-[10px] uppercase font-bold text-slate-400">Status</span>
              <div className="mt-1 flex items-center gap-1.5">
                <span className={`size-2 rounded-full ${statusTone.dot}`} />
                <span className="font-semibold text-slate-900">
                  {statusTone.label}
                </span>
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 p-3">
              <span className="text-[10px] uppercase font-bold text-slate-400">Content Type</span>
              <p className="mt-1 truncate font-mono font-medium text-slate-800">
                {node.content_type || "text/html"}
              </p>
            </div>
            {node.details?.timing_ms !== undefined && (
              <div className="rounded-lg border border-slate-200 p-3">
                <span className="text-[10px] uppercase font-bold text-slate-400">Response Timing</span>
                <p className="mt-1 font-mono font-medium text-slate-800">
                  {node.details.timing_ms} ms
                </p>
              </div>
            )}
            <div className="rounded-lg border border-slate-200 p-3">
              <span className="text-[10px] uppercase font-bold text-slate-400">Link Scope</span>
              <p className="mt-1 font-medium text-slate-800">
                {node.is_internal ? "Internal (Same Domain)" : "External"}
              </p>
            </div>
          </div>
        </div>

        {/* Redirect Chain Visualization */}
        {node.redirect_chain && node.redirect_chain.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-amber-700">
              <AlertTriangle size={14} />
              <span>Redirect Chain ({node.redirect_chain.length} Hops)</span>
            </div>
            <div className="rounded-xl border border-amber-200 bg-amber-50/40 p-3.5 space-y-2 text-xs">
              <div className="font-mono text-slate-600 break-all">{node.url}</div>
              {node.redirect_chain.map((hop, idx) => (
                <div key={idx} className="flex items-center gap-2 pl-3 border-l-2 border-amber-300">
                  <ArrowRight size={13} className="text-amber-600 shrink-0" />
                  <span className="font-mono break-all text-slate-800">{hop}</span>
                </div>
              ))}
              <div className="pt-1 text-[11px] font-medium text-amber-900">
                Final Target: <span className="font-mono">{node.final_url}</span>
              </div>
            </div>
          </div>
        )}

        {/* Specific Metadata Inspector */}
        {node.node_type === "image" && (
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Image SEO Metadata
            </h4>
            <div className="rounded-xl border border-slate-200 p-4 space-y-3 text-xs">
              <div>
                <span className="text-[10px] font-bold uppercase text-slate-400">Alt Text</span>
                {node.details.alt ? (
                  <p className="mt-1 font-medium text-slate-900 bg-slate-50 p-2 rounded border border-slate-100 flex items-center gap-1.5">
                    <CheckCircle2 size={14} className="text-emerald-600 shrink-0" />
                    <span>&ldquo;{node.details.alt}&rdquo;</span>
                  </p>
                ) : node.details.has_alt || node.details.alt === "" ? (
                  <p className="mt-1 font-medium text-slate-700 bg-slate-50 p-2 rounded border border-slate-200 flex items-center gap-1.5">
                    <CheckCircle2 size={14} className="text-slate-400 shrink-0" />
                    <span>alt=&quot;&quot; (Explicit decorative image)</span>
                  </p>
                ) : node.details.aria_label ? (
                  <p className="mt-1 font-medium text-teal-800 bg-teal-50 p-2 rounded border border-teal-200 flex items-center gap-1.5">
                    <CheckCircle2 size={14} className="text-teal-600 shrink-0" />
                    <span>aria-label: &ldquo;{node.details.aria_label}&rdquo;</span>
                  </p>
                ) : (
                  <p className="mt-1 font-medium text-red-600 bg-red-50 p-2 rounded border border-red-100 flex items-center gap-1.5">
                    <AlertCircle size={14} className="shrink-0" /> Missing Alt Attribute (Accessibility & SEO issue)
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Dimensions</span>
                  <p className="mt-0.5 font-mono text-slate-700">
                    {node.details.width && node.details.height
                      ? `${node.details.width} × ${node.details.height}${!String(node.details.width).includes('px') && !String(node.details.width).includes('%') ? ' px' : ''}`
                      : node.details.width
                        ? `${node.details.width} × auto`
                        : node.details.height
                          ? `auto × ${node.details.height}`
                          : "Not specified (CLS risk)"}
                  </p>
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Loading Strategy</span>
                  <p className="mt-0.5 capitalize text-slate-700">
                    {node.details.loading ? node.details.loading : "Default (eager)"}
                  </p>
                </div>
              </div>

              {node.details.section && (
                <div className="pt-1">
                  <span className="text-[10px] font-bold uppercase text-slate-400">DOM Placement</span>
                  <p className="mt-0.5 capitalize text-slate-700">
                    {node.details.section} section
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Link Specific Metadata */}
        {isHtmlPage && !isPrimary && (
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Anchor & Link Attributes
            </h4>
            <div className="rounded-xl border border-slate-200 p-4 space-y-3 text-xs">
              {node.details.anchor_text ? (
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Anchor Text</span>
                  <p className="mt-1 font-medium text-slate-900 bg-slate-50 p-2 rounded border border-slate-100">
                    &ldquo;{node.details.anchor_text}&rdquo;
                  </p>
                </div>
              ) : node.details.aria_label ? (
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Accessible Name (aria-label)</span>
                  <p className="mt-1 font-medium text-slate-900 bg-slate-50 p-2 rounded border border-slate-100">
                    &ldquo;{node.details.aria_label}&rdquo;
                  </p>
                </div>
              ) : null}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Rel Attribute</span>
                  <p className="mt-0.5 font-mono text-slate-700">
                    {(() => {
                      const relList = Array.isArray(node.details.rel)
                        ? node.details.rel
                        : typeof node.details.rel === "string"
                          ? (node.details.rel as string).split(/\s+/).filter(Boolean)
                          : [];
                      return relList.length > 0 ? relList.join(", ") : "None";
                    })()}
                  </p>
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Target</span>
                  <p className="mt-0.5 font-mono text-slate-700">
                    {node.details.target || "_self"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Scripts / Stylesheet Specific Metadata */}
        {(node.node_type === "script" || node.node_type === "stylesheet") && (
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Resource Attributes
            </h4>
            <div className="rounded-xl border border-slate-200 p-4 space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Async</span>
                  <p className="mt-0.5 font-mono text-slate-700">{node.details.async ? "Yes" : "No"}</p>
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase text-slate-400">Defer</span>
                  <p className="mt-0.5 font-mono text-slate-700">{node.details.defer ? "Yes" : "No"}</p>
                </div>
              </div>
              {!node.details.async && !node.details.defer && node.node_type === "script" && (
                <p className="text-[11px] text-amber-700 bg-amber-50 p-2 rounded border border-amber-200 mt-2">
                  ⚠️ Synchronous script may be render-blocking.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Issues & Recommendations */}
        {node.issues && node.issues.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-rose-700">
              <ShieldAlert size={14} />
              <span>Detected Issues ({node.issues.length})</span>
            </div>
            <div className="space-y-2">
              {node.issues.map((iss, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 space-y-1.5 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-rose-900">{iss.issue}</span>
                    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-800">
                      {iss.severity}
                    </span>
                  </div>
                  {iss.evidence && (
                    <p className="text-slate-600 font-mono text-[11px]">
                      Evidence: {iss.evidence}
                    </p>
                  )}
                  {iss.impact && (
                    <p className="text-slate-600">
                      <strong>Impact:</strong> {iss.impact}
                    </p>
                  )}
                  <p className="text-rose-950 font-medium pt-1">
                    👉 {iss.recommendation}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Drawer Footer */}
      <div className="border-t border-slate-100 p-4 bg-slate-50/50 flex items-center justify-end">
        <button
          onClick={onClose}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
        >
          Close Inspector
        </button>
      </div>
    </aside>
  );
}
