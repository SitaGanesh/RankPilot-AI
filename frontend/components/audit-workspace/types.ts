import type {
  AuditLiveEvent,
  AuditStatus,
  BrowserObservationData,
  ConsolidatedWebsiteReport,
  CrawlURL,
  PageAuditFinding,
  PageAuditReport,
} from "@/types/api";

export type FindingCategory =
  | "executive_summary"
  | "technical_seo_ai"
  | "content_quality"
  | "marketing_conversion"
  | "website_functionality"
  | "connectivity"
  | "links_redirects"
  | "images_media"
  | "accessibility_structure";

export interface FindingCategoryMeta {
  key: FindingCategory;
  label: string;
  description: string;
  badgeColor: string;
}

export const FINDING_CATEGORIES: FindingCategoryMeta[] = [
  {
    key: "technical_seo_ai",
    label: "Technical SEO & AI Visibility",
    description: "Crawlability, canonicals, robots directives, schema markup, and AI search discoverability.",
    badgeColor: "bg-indigo-50 text-indigo-700 border-indigo-200",
  },
  {
    key: "content_quality",
    label: "Subject-Matter Content",
    description: "Heading depth, readability, text volume, and content quality.",
    badgeColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  {
    key: "marketing_conversion",
    label: "Marketing & Conversion",
    description: "OpenGraph tags, Twitter Cards, calls to action, and conversion paths.",
    badgeColor: "bg-purple-50 text-purple-700 border-purple-200",
  },
  {
    key: "website_functionality",
    label: "Website Functionality",
    description: "Real browser runtime JavaScript console exceptions and failed script/CSS assets.",
    badgeColor: "bg-rose-50 text-rose-700 border-rose-200",
  },
  {
    key: "connectivity",
    label: "Connectivity & Latency",
    description: "Server TTFB latency, HTTP responses, SSL certificates, and network health.",
    badgeColor: "bg-blue-50 text-blue-700 border-blue-200",
  },
  {
    key: "links_redirects",
    label: "Links & Redirects",
    description: "Internal and external hyperlinking health, redirect hops, and anchor tags.",
    badgeColor: "bg-cyan-50 text-cyan-700 border-cyan-200",
  },
  {
    key: "images_media",
    label: "Images & Media",
    description: "Image accessibility alt attributes, dimensions, format, and media responsiveness.",
    badgeColor: "bg-amber-50 text-amber-700 border-amber-200",
  },
  {
    key: "accessibility_structure",
    label: "Accessibility & Structure",
    description: "H1 hierarchy, document lang, responsive viewport, and semantic landmark tags.",
    badgeColor: "bg-teal-50 text-teal-700 border-teal-200",
  },
];

export function categorizeFinding(
  checkId: string,
  title: string,
  category?: string,
  agentId?: string,
): FindingCategory {
  const cid = (checkId || "").toLowerCase();
  const t = (title || "").toLowerCase();
  const cat = (category || "").toLowerCase();
  const ag = (agentId || "").toLowerCase();

  if (
    cid.includes("image") ||
    t.includes("image") ||
    cid.includes("media") ||
    cid.includes("alt_text") ||
    t.includes("alt text")
  ) {
    return "images_media";
  }

  if (
    cid.includes("heading") ||
    cid.includes("h1") ||
    t.includes("heading") ||
    t.includes("h1") ||
    cid.includes("accessibility") ||
    cid.includes("aria") ||
    cid.includes("viewport") ||
    cid.includes("html_lang") ||
    cid.includes("semantic")
  ) {
    return "accessibility_structure";
  }

  if (
    cid.includes("link") ||
    cid.includes("redirect") ||
    t.includes("redirect") ||
    t.includes("broken link") ||
    cid.includes("anchor")
  ) {
    return "links_redirects";
  }

  if (
    cid.includes("connectivity") ||
    cid.includes("response_time") ||
    cid.includes("ttfb") ||
    t.includes("response time") ||
    t.includes("ttfb") ||
    cid.includes("latency") ||
    cid.includes("ssl") ||
    cid.includes("dns")
  ) {
    return "connectivity";
  }

  if (
    cid.includes("functionality") ||
    cid.includes("console") ||
    cid.includes("subresource") ||
    cid.includes("javascript") ||
    t.includes("console") ||
    t.includes("javascript") ||
    t.includes("subresource") ||
    cid.includes("empty_html_shell")
  ) {
    return "website_functionality";
  }

  if (
    ag === "ib_conversion" ||
    cat.includes("marketing") ||
    cat.includes("conversion") ||
    cid.includes("cta") ||
    cid.includes("conversion") ||
    cid.includes("opengraph") ||
    cid.includes("twitter") ||
    cid.includes("social")
  ) {
    return "marketing_conversion";
  }

  if (
    ag === "onpage" &&
    (cid.includes("content") ||
      cid.includes("word_count") ||
      cid.includes("readability") ||
      cid.includes("thin") ||
      t.includes("content"))
  ) {
    return "content_quality";
  }

  return "technical_seo_ai";
}

export interface WorkspaceState {
  auditId: string;
  targetUrl: string;
  auditStatus: AuditStatus;
  currentStage: string;
  activeUrl: string;
  autoFollowCrawler: boolean;
  activePageReport: PageAuditReport | null;
  consolidatedReport: ConsolidatedWebsiteReport | null;
  liveObservation: BrowserObservationData | null;
  crawlUrls: CrawlURL[];
  pageReports: PageAuditReport[];
  findings: PageAuditFinding[];
  liveEvents: AuditLiveEvent[];
  connectionMode: "sse" | "polling" | "connected" | "disconnected" | "closed";
  lastEventId: number;
  error: string | null;
}

export type ViewLayoutMode = "split" | "report-focus" | "browser-focus" | "report-only" | "browser-only";
export type DeviceViewport = "desktop" | "tablet" | "mobile" | "fit";
