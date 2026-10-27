import type {
  Agent,
  AgentRunStarted,
  AuditCreated,
  AuditBatch,
  AuditReportData,
  AuditStatusResponse,
  BusinessReport,
  CrawlStatus,
  CrawlURL,
  BatchReport,
  BatchTargetReport,
  InvestigationResponse,
  InvestigationStarted,
  ProviderStatus,
  ResourceGraph,
  ConsolidatedWebsiteReport,
  PageAuditReport,
  LiveEventsPollResponse,
  LandingPageReport,
  MarketingRun,
} from "@/types/api";


const API_BASE = "/backend-api";

async function parseError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "error" in body) {
      const error = (body as { error: unknown }).error;
      if (typeof error === "string" && error.trim()) {
        return error;
      }
    }
  } catch {
    // Fall through to the status-based message.
  }
  return `Request failed (${response.status})`;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json() as Promise<T>;
}

export interface CreateAuditOptions {
  mode?: "standard" | "agentic" | string;
  audit_type?: "page" | "website" | string;
  max_crawl_pages?: number;
  max_crawl_depth?: number;
  same_domain_only?: boolean;
  objective?: string;
}

export async function createAudit(
  url: string,
  options?: CreateAuditOptions,
): Promise<AuditCreated> {
  return api("/audits/", {
    method: "POST",
    body: JSON.stringify({ url, ...(options ?? {}) }),
  });
}

export async function createBatch(
  urls: string[],
  idempotencyKey: string,
  allowInternalDiscovery = false,
): Promise<AuditBatch> {
  return api("/batches/", {
    method: "POST",
    body: JSON.stringify({
      urls,
      idempotency_key: idempotencyKey,
      allow_internal_discovery: allowInternalDiscovery,
    }),
  });
}

export async function listBatches(): Promise<AuditBatch[]> {
  return api("/batches/");
}

export async function getBatch(batchId: string): Promise<AuditBatch> {
  return api(`/batches/${batchId}/`);
}

export async function getBatchReport(batchId: string): Promise<BatchReport> {
  return api(`/batches/${encodeURIComponent(batchId)}/report/`);
}

export function getBatchExportUrl(
  batchId: string,
  type: "targets" | "findings" = "targets",
  format: "csv" | "json" | string = "csv",
): string {
  return `${API_BASE}/batches/${encodeURIComponent(batchId)}/export/?type=${type}&format=${format}`;
}

export async function getBatchTargetReport(
  batchId: string,
  targetId: number,
): Promise<BatchTargetReport> {
  return api(`/batches/${encodeURIComponent(batchId)}/targets/${targetId}/report/`);
}

export async function resumeBatch(batchId: string): Promise<{ id: string; status: string }> {
  return api(`/batches/${batchId}/resume/`, { method: "POST" });
}

export async function retryBatch(batchId: string): Promise<{ id: string; status: string }> {
  return api(`/batches/${batchId}/retry/`, { method: "POST" });
}

export async function cancelBatch(batchId: string): Promise<{ id: string; status: string }> {
  return api(`/batches/${batchId}/cancel/`, { method: "POST" });
}

export async function getAuditStatus(auditId: string): Promise<AuditStatusResponse> {
  return api(`/audits/${auditId}/`);
}

export async function getCrawlURLs(
  auditId: string,
  status?: CrawlStatus,
): Promise<CrawlURL[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return api(`/audits/${auditId}/urls/${query}`);
}

export async function getAgents(): Promise<Agent[]> {
  return api("/agents/");
}

export async function getProviderStatus(): Promise<ProviderStatus> {
  return api("/providers/status/");
}

export async function runAgent(
  auditId: string,
  agentId: string,
): Promise<AgentRunStarted> {
  return api(`/audits/${auditId}/agents/${agentId}/run/`, { method: "POST" });
}

export async function getAuditReport(
  auditId: string,
  agentId?: string,
): Promise<AuditReportData> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  return api(`/audits/${auditId}/report/${query}`);
}

export function getAuditReportCsvUrl(auditId: string, agentId?: string): string {
  const agentQuery = agentId ? `&agent_id=${encodeURIComponent(agentId)}` : "";
  return `${API_BASE}/audits/${encodeURIComponent(auditId)}/report/?format=csv${agentQuery}`;
}

export async function getConsolidatedWebsiteReport(
  auditId: string,
): Promise<ConsolidatedWebsiteReport> {
  return api(`/audits/${encodeURIComponent(auditId)}/report/?type=website`);
}

export async function getAuditPages(
  auditId: string,
  q?: string,
): Promise<{ audit_id: string; total_pages: number; pages: PageAuditReport[] }> {
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  return api(`/audits/${encodeURIComponent(auditId)}/pages/${query}`);
}

export async function getAuditPage(
  auditId: string,
  pageId: number,
): Promise<PageAuditReport> {
  return api(`/audits/${encodeURIComponent(auditId)}/pages/${pageId}/`);
}

export async function getAuditPageByUrl(
  auditId: string,
  url: string,
): Promise<PageAuditReport> {
  return api(`/audits/${encodeURIComponent(auditId)}/report/?url=${encodeURIComponent(url)}`);
}

export interface PageReportAvailability {
  status: "pending" | "processing" | "completed" | "failed" | "skipped" | "unavailable" | string;
  availability: string;
  page: PageAuditReport | null;
  crawl_url: CrawlURL | null;
  request_audit?: {
    method: string;
    path: string;
    body: { url: string; audit_type: string };
    label: string;
  };
}

export async function getAuditPageReportByUrl(
  auditId: string,
  url: string,
): Promise<PageReportAvailability> {
  return api(
    `/audits/${encodeURIComponent(auditId)}/pages/report/?url=${encodeURIComponent(url)}`,
  );
}

export interface PageLinksResponse {
  audit_id: string;
  page_id: number;
  url: string;
  links: Array<Record<string, unknown>>;
  resources: Array<Record<string, unknown>>;
  link_count?: number;
  resource_count?: number;
}

export async function getAuditPageLinks(
  auditId: string,
  pageId: number,
): Promise<PageLinksResponse> {
  return api(`/audits/${encodeURIComponent(auditId)}/pages/${pageId}/links/`);
}

export async function cancelAudit(
  auditId: string,
): Promise<{ id: string; status: string }> {
  return api(`/audits/${encodeURIComponent(auditId)}/cancel/`, { method: "POST" });
}

export async function getAuditLiveEvents(
  auditId: string,
  afterId = 0,
): Promise<LiveEventsPollResponse> {
  return api(`/audits/${encodeURIComponent(auditId)}/events/?format=json&poll=1&after=${afterId}`);
}

export function getAuditLiveStreamUrl(auditId: string, afterId = 0): string {
  const afterParam = afterId > 0 ? `?after=${afterId}` : "";
  return `${API_BASE}/audits/${encodeURIComponent(auditId)}/stream/${afterParam}`;
}

export async function getBusinessReport(auditId: string): Promise<BusinessReport> {
  return api(`/audits/${auditId}/business-report/`);
}

export async function getEvaluationReport(auditId: string): Promise<BusinessReport> {
  return api(`/audits/${auditId}/evaluation/`);
}

export async function getResourceGraph(auditId: string): Promise<ResourceGraph> {
  return api(`/audits/${encodeURIComponent(auditId)}/graph/`);
}

export async function getInvestigation(
  auditId: string,
): Promise<InvestigationResponse> {
  return api(`/audits/${encodeURIComponent(auditId)}/investigation/`);
}

export async function startInvestigation(
  auditId: string,
  objective?: string,
): Promise<InvestigationStarted> {
  return api(`/audits/${encodeURIComponent(auditId)}/investigation/`, {
    method: "POST",
    body: JSON.stringify(objective ? { objective } : {}),
  });
}

export async function resumeInvestigation(
  auditId: string,
): Promise<{ status: string; execution_backend?: string }> {
  return api(`/audits/${encodeURIComponent(auditId)}/investigation/resume/`, {
    method: "POST",
  });
}

export async function cancelInvestigation(
  auditId: string,
): Promise<{ id: string; status: string }> {
  return api(`/audits/${encodeURIComponent(auditId)}/investigation/cancel/`, {
    method: "POST",
  });
}

export async function decideProposal(
  auditId: string,
  proposalId: number,
  decision: "approve" | "reject",
  note = "",
): Promise<{ status?: string; message?: string }> {
  return api(
    `/audits/${encodeURIComponent(auditId)}/proposals/${proposalId}/decision/`,
    {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    },
  );
}

export async function verifyProposal(
  auditId: string,
  proposalId: number,
): Promise<{ status: string; execution_backend?: string }> {
  return api(
    `/audits/${encodeURIComponent(auditId)}/proposals/${proposalId}/verify/`,
    { method: "POST" },
  );
}

export async function getLandingPageReport(
  auditId: string,
  options?: { url?: string; pageId?: number; refresh?: boolean },
): Promise<LandingPageReport> {
  const query = new URLSearchParams();
  if (options?.url) query.set("url", options.url);
  if (options?.pageId) query.set("page_id", String(options.pageId));
  if (options?.refresh) query.set("refresh", "1");
  const qs = query.toString() ? `?${query.toString()}` : "";
  return api(`/audits/${encodeURIComponent(auditId)}/landing-report/${qs}`);
}

/* ================================================================== */
/* Marketing Intelligence Agent API                                    */
/* ================================================================== */

async function marketingFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/marketing-api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json() as Promise<T>;
}

export async function startMarketingRun(
  auditId: string,
  url: string,
  maxPages = 5,
): Promise<MarketingRun> {
  return marketingFetch<MarketingRun>("/runs/", {
    method: "POST",
    body: JSON.stringify({ audit_id: auditId, url, max_pages: maxPages }),
  });
}

export async function getMarketingRun(runId: number): Promise<MarketingRun> {
  return marketingFetch<MarketingRun>(`/runs/${runId}/`);
}

export async function getMarketingRunForAudit(auditId: string): Promise<MarketingRun | null> {
  try {
    return await marketingFetch<MarketingRun>(`/audit/${encodeURIComponent(auditId)}/`);
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes("404")) {
      return null;
    }
    return null;
  }
}

