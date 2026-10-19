export type AuditStatus =
  | "pending"
  | "collecting"
  | "collected"
  | "running"
  | "completed"
  | "failed";

export type CrawlStatus = "pending" | "fetching" | "fetched" | "failed" | "skipped";
export type CrawlResourceType = "page" | "media";

export type DiscoverySource = "submitted" | "internal_link" | "sitemap";

export interface AuditCreated {
  id: string;
  status: AuditStatus;
}

export interface StageEvent {
  stage: string;
  status: string;
  message: string;
  created_at: string;
}

export interface AuditStatusResponse {
  id: string;
  url: string;
  status: AuditStatus;
  current_stage: string;
  created_at: string;
  stage_events: StageEvent[];
}

export interface CrawlURL {
  id: number;
  url: string;
  status: CrawlStatus;
  resource_type: CrawlResourceType;
  depth: number;
  response_status: number | null;
  discovery_source: DiscoverySource;
  discovery_source_url: string;
  discovered_from: number | null;
  final_url: string;
  error: string;
  created_at: string;
  updated_at: string;
}
