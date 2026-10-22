"use client";

import { useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ExternalLink,
  Eye,
  FileCode,
  FileText,
  Filter,
  Globe2,
  Image as ImageIcon,
  Layers,
  LayoutGrid,
  Link2,
  Network,
  Play,
  RotateCcw,
  Search,
  Sparkles,
  Video,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { ResourceGraph, ResourceGraphNode } from "@/types/api";

interface ResourceGraphProps {
  graph: ResourceGraph;
  selectedNodeId: string | null;
  onSelectNode: (node: ResourceGraphNode) => void;
  onAuditUrl: (url: string) => void;
}

type FilterCategory = "all" | "internal" | "external" | "images" | "scripts_css" | "issues";
type ViewMode = "graph" | "cards";

export function ResourceGraphView({
  graph,
  selectedNodeId,
  onSelectNode,
  onAuditUrl,
}: ResourceGraphProps) {
  const [filter, setFilter] = useState<FilterCategory>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [zoomLevel, setZoomLevel] = useState(1);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // Identify primary node
  const primaryNode = useMemo(() => {
    return (
      graph.nodes.find((n) => n.deeply_audited || n.node_type === "primary_page") ||
      graph.nodes[0]
    );
  }, [graph.nodes]);

  // Filter nodes based on category and search query
  const filteredNodes = useMemo(() => {
    let list = graph.nodes;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((n) => n.url.toLowerCase().includes(q) || n.label.toLowerCase().includes(q));
    }

    if (filter === "internal") {
      list = list.filter((n) => n.is_internal && n.node_type === "linked_page");
    } else if (filter === "external") {
      list = list.filter((n) => !n.is_internal && n.node_type === "linked_page");
    } else if (filter === "images") {
      list = list.filter((n) => n.node_type === "image" || n.node_type === "media");
    } else if (filter === "scripts_css") {
      list = list.filter((n) => n.node_type === "script" || n.node_type === "stylesheet");
    } else if (filter === "issues") {
      list = list.filter(
        (n) =>
          n.status === "client_error" ||
          n.status === "server_error" ||
          n.status === "redirects" ||
          (n.issues && n.issues.length > 0)
      );
    }

    return list;
  }, [graph.nodes, filter, searchQuery]);

  // Counts for pills
  const counts = useMemo(() => {
    const nodes = graph.nodes;
    return {
      all: nodes.length,
      internal: nodes.filter((n) => n.is_internal && n.node_type === "linked_page").length,
      external: nodes.filter((n) => !n.is_internal && n.node_type === "linked_page").length,
      images: nodes.filter((n) => n.node_type === "image" || n.node_type === "media").length,
      scripts_css: nodes.filter((n) => n.node_type === "script" || n.node_type === "stylesheet").length,
      issues: nodes.filter(
        (n) =>
          n.status === "client_error" ||
          n.status === "server_error" ||
          n.status === "redirects" ||
          (n.issues && n.issues.length > 0)
      ).length,
    };
  }, [graph.nodes]);

  // Layout calculation for SVG visualization
  // Primary node at center (480, 290)
  const svgLayout = useMemo(() => {
    const centerX = 480;
    const centerY = 290;

    // Separate other nodes (excluding primary)
    const otherNodes = filteredNodes.filter((n) => n.id !== primaryNode?.id);

    // Group other nodes into quadrants:
    // Q1: Internal Links (top left)
    // Q2: External Links (bottom left)
    // Q3: Images & Media (top right)
    // Q4: Scripts & Stylesheets (bottom right)
    const internalNodes: ResourceGraphNode[] = [];
    const externalNodes: ResourceGraphNode[] = [];
    const mediaNodes: ResourceGraphNode[] = [];
    const codeNodes: ResourceGraphNode[] = [];
    const otherMiscNodes: ResourceGraphNode[] = [];

    for (const node of otherNodes) {
      if (node.node_type === "linked_page") {
        if (node.is_internal) internalNodes.push(node);
        else externalNodes.push(node);
      } else if (node.node_type === "image" || node.node_type === "media") {
        mediaNodes.push(node);
      } else if (node.node_type === "script" || node.node_type === "stylesheet") {
        codeNodes.push(node);
      } else {
        otherMiscNodes.push(node);
      }
    }

    interface LayoutPosition {
      node: ResourceGraphNode;
      x: number;
      y: number;
    }

    const positions: LayoutPosition[] = [];

    function positionArc(
      nodes: ResourceGraphNode[],
      startAngleDeg: number,
      endAngleDeg: number,
      baseRadius: number
    ) {
      if (nodes.length === 0) return;
      // Cap visible nodes in SVG to prevent clutter, up to 16 per quadrant
      const visible = nodes.slice(0, 16);
      const angleStep = visible.length > 1 ? (endAngleDeg - startAngleDeg) / (visible.length - 1) : 0;
      const initialAngle = visible.length === 1 ? (startAngleDeg + endAngleDeg) / 2 : startAngleDeg;

      visible.forEach((node, idx) => {
        const deg = visible.length === 1 ? initialAngle : startAngleDeg + idx * angleStep;
        const rad = (deg * Math.PI) / 180;
        // Alternating radius for better stagger
        const r = baseRadius + (idx % 2 === 0 ? 0 : 35);
        const x = centerX + r * Math.cos(rad);
        const y = centerY + r * Math.sin(rad);
        positions.push({ node, x, y });
      });
    }

    // Top-left: Internal Links (-165 to -105 deg)
    positionArc(internalNodes, -165, -105, 200);
    // Bottom-left: External Links (105 to 165 deg)
    positionArc(externalNodes, 105, 165, 210);
    // Top-right: Images & Media (-75 to -15 deg)
    positionArc(mediaNodes, -75, -15, 200);
    // Bottom-right: Scripts & Styles (15 to 75 deg)
    positionArc(codeNodes, 15, 75, 210);
    // Bottom-center: Other misc (80 to 100 deg)
    positionArc(otherMiscNodes, 80, 100, 220);

    return { centerX, centerY, positions };
  }, [filteredNodes, primaryNode]);

  function getNodeColor(status: string) {
    switch (status) {
      case "available":
        return { stroke: "#10b981", fill: "#ecfdf5", text: "#065f46" };
      case "redirects":
        return { stroke: "#f59e0b", fill: "#fffbeb", text: "#92400e" };
      case "client_error":
        return { stroke: "#ef4444", fill: "#fef2f2", text: "#991b1b" };
      case "server_error":
        return { stroke: "#e11d48", fill: "#fff1f2", text: "#881337" };
      default:
        return { stroke: "#94a3b8", fill: "#f8fafc", text: "#334155" };
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Top Banner: Single-URL Scope Explanation */}
      <div className="border-b border-indigo-100 bg-gradient-to-r from-indigo-50/60 via-purple-50/40 to-slate-50 p-4 sm:px-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-lg bg-indigo-600 text-white shadow-xs">
              <Network size={16} />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-900">
                  Page-Centred Resource Graph
                </h3>
                <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold text-indigo-800 uppercase">
                  1 Primary Deep Node
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                Single-URL Audit isolates <strong>{primaryNode?.url}</strong> as the primary audit node. Connected links and resources undergo safe, lightweight shallow checks without recursive crawling.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-center">
            <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-2xs">
              <button
                onClick={() => setViewMode("graph")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition ${
                  viewMode === "graph"
                    ? "bg-indigo-600 text-white shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Network size={13} /> Visual Graph
              </button>
              <button
                onClick={() => setViewMode("cards")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition ${
                  viewMode === "cards"
                    ? "bg-indigo-600 text-white shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <LayoutGrid size={13} /> Cluster Grid
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="border-b border-slate-100 p-4 sm:px-6 flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-white">
        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <button
            onClick={() => setFilter("all")}
            className={`rounded-lg px-3 py-1.5 font-medium transition ${
              filter === "all"
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Resources ({counts.all})
          </button>
          <button
            onClick={() => setFilter("internal")}
            className={`rounded-lg px-3 py-1.5 font-medium transition ${
              filter === "internal"
                ? "bg-indigo-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Internal Links ({counts.internal})
          </button>
          <button
            onClick={() => setFilter("external")}
            className={`rounded-lg px-3 py-1.5 font-medium transition ${
              filter === "external"
                ? "bg-cyan-700 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            External Links ({counts.external})
          </button>
          <button
            onClick={() => setFilter("images")}
            className={`rounded-lg px-3 py-1.5 font-medium transition ${
              filter === "images"
                ? "bg-emerald-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Images & Media ({counts.images})
          </button>
          <button
            onClick={() => setFilter("scripts_css")}
            className={`rounded-lg px-3 py-1.5 font-medium transition ${
              filter === "scripts_css"
                ? "bg-violet-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Styles & Scripts ({counts.scripts_css})
          </button>
          <button
            onClick={() => setFilter("issues")}
            className={`rounded-lg px-3 py-1.5 font-medium transition ${
              filter === "issues"
                ? "bg-rose-600 text-white"
                : "bg-rose-50 text-rose-700 hover:bg-rose-100"
            }`}
          >
            Issues & Redirects ({counts.issues})
          </button>
        </div>

        {/* Search Input */}
        <div className="relative min-w-[220px]">
          <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Filter by path or URL…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-3 text-xs outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
          />
        </div>
      </div>

      {/* Graph or Grid Body */}
      {viewMode === "graph" ? (
        <div className="relative bg-slate-50/50 min-h-[560px] overflow-hidden select-none">
          {/* Zoom controls */}
          <div className="absolute bottom-4 right-4 z-10 flex flex-col rounded-lg border border-slate-200 bg-white shadow-md">
            <button
              onClick={() => setZoomLevel((z) => Math.min(z + 0.15, 1.6))}
              className="p-2 text-slate-600 hover:bg-slate-50 transition"
              title="Zoom In"
            >
              <ZoomIn size={15} />
            </button>
            <button
              onClick={() => setZoomLevel((z) => Math.max(z - 0.15, 0.7))}
              className="p-2 text-slate-600 hover:bg-slate-50 border-t border-slate-100 transition"
              title="Zoom Out"
            >
              <ZoomOut size={15} />
            </button>
            <button
              onClick={() => setZoomLevel(1)}
              className="p-2 text-slate-600 hover:bg-slate-50 border-t border-slate-100 transition"
              title="Reset Zoom"
            >
              <RotateCcw size={14} />
            </button>
          </div>

          {/* Graph Legend */}
          <div className="absolute top-4 left-4 z-10 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200/80 bg-white/90 px-3 py-1.5 text-[11px] shadow-xs backdrop-blur-xs">
            <span className="flex items-center gap-1 text-slate-600">
              <span className="size-2 rounded-full bg-emerald-500" /> Available (200)
            </span>
            <span className="flex items-center gap-1 text-slate-600">
              <span className="size-2 rounded-full bg-amber-500" /> Redirects (3xx)
            </span>
            <span className="flex items-center gap-1 text-slate-600">
              <span className="size-2 rounded-full bg-red-500" /> Error (4xx/5xx)
            </span>
            <span className="flex items-center gap-1 text-slate-600">
              <span className="size-2 rounded-full bg-slate-400" /> Unverified
            </span>
          </div>

          {/* SVG Canvas */}
          <div className="w-full overflow-auto flex items-center justify-center p-4">
            <svg
              viewBox="0 0 960 580"
              className="w-full max-w-5xl h-auto transition-transform duration-200"
              style={{ transform: `scale(${zoomLevel})` }}
            >
              <defs>
                <linearGradient id="primaryGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#4f46e5" />
                  <stop offset="100%" stopColor="#7c3aed" />
                </linearGradient>
                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              {/* Connecting Edges */}
              <g className="edges">
                {svgLayout.positions.map(({ node, x, y }) => {
                  const isHovered = hoveredNodeId === node.id;
                  const isSelected = selectedNodeId === node.id;
                  const colors = getNodeColor(node.status);

                  return (
                    <line
                      key={`edge-${node.id}`}
                      x1={svgLayout.centerX}
                      y1={svgLayout.centerY}
                      x2={x}
                      y2={y}
                      stroke={colors.stroke}
                      strokeWidth={isSelected ? 2.5 : isHovered ? 2 : 1.2}
                      strokeDasharray={node.is_internal ? undefined : "4 3"}
                      opacity={isSelected || isHovered ? 1 : 0.45}
                      className="transition-all duration-150"
                    />
                  );
                })}
              </g>

              {/* Connected Satellite Nodes */}
              <g className="satellites">
                {svgLayout.positions.map(({ node, x, y }) => {
                  const isHovered = hoveredNodeId === node.id;
                  const isSelected = selectedNodeId === node.id;
                  const colors = getNodeColor(node.status);
                  const radius = isSelected ? 18 : isHovered ? 16 : 14;

                  return (
                    <g
                      key={`node-${node.id}`}
                      transform={`translate(${x}, ${y})`}
                      className="cursor-pointer transition-transform"
                      onClick={() => onSelectNode(node)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      {/* Selection / Hover ring */}
                      {(isSelected || isHovered) && (
                        <circle
                          r={radius + 6}
                          fill="none"
                          stroke={colors.stroke}
                          strokeWidth="2"
                          opacity="0.6"
                          filter="url(#glow)"
                        />
                      )}

                      {/* Main node circle */}
                      <circle
                        r={radius}
                        fill={colors.fill}
                        stroke={colors.stroke}
                        strokeWidth={isSelected ? "2.5" : "1.5"}
                        className="transition-all"
                      />

                      {/* Status indicator dot */}
                      <circle
                        cx={radius - 2}
                        cy={-radius + 2}
                        r="3.5"
                        fill={colors.stroke}
                      />

                      {/* Inner Icon representation */}
                      <text
                        textAnchor="middle"
                        dy="4"
                        fontSize="10"
                        fontWeight="bold"
                        fill={colors.text}
                      >
                        {node.node_type === "image"
                          ? "IMG"
                          : node.node_type === "script"
                          ? "JS"
                          : node.node_type === "stylesheet"
                          ? "CSS"
                          : node.is_internal
                          ? "INT"
                          : "EXT"}
                      </text>

                      {/* Label below node */}
                      <text
                        y={radius + 12}
                        textAnchor="middle"
                        fontSize="9"
                        fontWeight={isSelected ? "bold" : "normal"}
                        fill="#334155"
                        className="pointer-events-none"
                      >
                        {node.label.length > 20
                          ? `${node.label.slice(0, 18)}…`
                          : node.label}
                      </text>
                    </g>
                  );
                })}
              </g>

              {/* Primary Node at Center */}
              {primaryNode && (
                <g
                  transform={`translate(${svgLayout.centerX}, ${svgLayout.centerY})`}
                  className="cursor-pointer"
                  onClick={() => onSelectNode(primaryNode)}
                >
                  {/* Outer pulsating ring */}
                  <circle
                    r="48"
                    fill="none"
                    stroke="#818cf8"
                    strokeWidth="1.5"
                    strokeDasharray="4 2"
                    opacity="0.8"
                  />
                  <circle
                    r="40"
                    fill="url(#primaryGrad)"
                    stroke="#4338ca"
                    strokeWidth="3"
                    filter="url(#glow)"
                  />
                  <text
                    textAnchor="middle"
                    dy="-8"
                    fontSize="11"
                    fontWeight="800"
                    fill="#ffffff"
                    letterSpacing="0.5"
                  >
                    PRIMARY AUDIT
                  </text>
                  <text
                    textAnchor="middle"
                    dy="8"
                    fontSize="9"
                    fontWeight="600"
                    fill="#e0e7ff"
                  >
                    DEEP 4-AGENT
                  </text>
                  <text
                    textAnchor="middle"
                    dy="22"
                    fontSize="8"
                    fill="#c7d2fe"
                  >
                    1 Page Crawled
                  </text>
                </g>
              )}
            </svg>
          </div>

          <div className="p-3 text-center text-xs text-slate-400 border-t border-slate-100 bg-white">
            Click any node to inspect shallow check headers, metadata, alt attributes, and redirect chains.
          </div>
        </div>
      ) : (
        /* Cluster Cards Grid View */
        <div className="p-5 sm:p-6 space-y-6">
          {filteredNodes.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500">
              No resources match the selected filter.
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {filteredNodes.map((node) => {
                const isPrimary = node.id === primaryNode?.id;
                const isSelected = selectedNodeId === node.id;
                const colors = getNodeColor(node.status);

                return (
                  <div
                    key={node.id}
                    onClick={() => onSelectNode(node)}
                    className={`cursor-pointer rounded-xl border p-4 transition-all hover:shadow-md ${
                      isSelected
                        ? "border-indigo-600 bg-indigo-50/40 ring-2 ring-indigo-200"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`size-2.5 rounded-full ${
                            node.status === "available"
                              ? "bg-emerald-500"
                              : node.status === "redirects"
                              ? "bg-amber-500"
                              : node.status === "client_error" || node.status === "server_error"
                              ? "bg-red-500"
                              : "bg-slate-400"
                          }`}
                        />
                        <span className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                          {isPrimary
                            ? "⭐ Primary Node"
                            : node.node_type.replace(/_/g, " ")}
                        </span>
                      </div>
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                        style={{ backgroundColor: colors.fill, color: colors.text }}
                      >
                        {node.http_status ?? node.status}
                      </span>
                    </div>

                    <p className="mt-2.5 font-mono text-xs font-semibold text-slate-900 break-all line-clamp-2">
                      {node.url}
                    </p>

                    {node.issues && node.issues.length > 0 && (
                      <div className="mt-2.5 flex items-center gap-1.5 text-[11px] font-medium text-rose-600">
                        <AlertCircle size={13} />
                        <span>{node.issues.length} issue(s) detected</span>
                      </div>
                    )}

                    <div className="mt-3.5 flex items-center justify-between border-t border-slate-100 pt-2.5 text-xs">
                      <span className="text-[11px] text-slate-400">
                        {node.is_internal ? "Internal" : "External"}
                      </span>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectNode(node);
                          }}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-700"
                        >
                          <Eye size={12} /> Inspect
                        </button>
                        {!isPrimary && node.node_type === "linked_page" && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onAuditUrl(node.url);
                            }}
                            className="inline-flex items-center gap-1 rounded bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700 hover:bg-indigo-100"
                          >
                            <Play size={10} /> Deep Audit
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
