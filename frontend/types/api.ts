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
export type BatchStatus = "pending" | "running" | "completed" | "partial" | "failed" | "cancelled";
export type BatchTargetStatus = "pending" | "running" | "retryable" | "completed" | "failed" | "skipped";
export type AnalysisStatus = "pending" | "running" | "completed" | "partial" | "failed";
export type AgentId = "onpage" | "technical" | "visibility" | "ib_conversion";

export interface AuditCreated {
  id: string;
  status: AuditStatus;
}

export interface BatchTarget {
  id: number;
  position: number;
  submitted_url: string;
  normalized_url: string;
  status: BatchTargetStatus;
  analysis_status: AnalysisStatus;
  final_url: string;
  response_status: number | null;
  content_type: string;
  timing_ms: number | null;
  html: boolean;
  image_count: number;
  internal_link_count: number;
  external_link_count: number;
  broken_link_count: number;
  evidence: Record<string, unknown>;
  error: string;
  attempts: number;
  started_at: string | null;
  completed_at: string | null;
  scores?: Record<string, number | null>;
}

export interface BatchAgentRun {
  agent_id: string;
  attempt: number;
  status: string;
  result_json: Record<string, unknown>;
  error: string;
  finding_keys: string[];
  started_at: string;
  finished_at: string | null;
}

export interface BatchTargetReport extends BatchTarget {
  batch: string;
  agent_runs: BatchAgentRun[];
}

export interface BatchTopIssue {
  check_id: string;
  title: string;
  severity: string;
  agent_id: string;
  status: string;
  recommendation: string;
  why_it_matters: string;
  affected_count: number;
  affected_urls: string[];
}

export interface BatchSummary {
  total_targets: number;
  crawled_count: number;
  failed_count: number;
  skipped_count: number;
  overall_score: number | null;
  agent_averages: Record<string, number | null>;
  severity_counts: Record<string, number>;
  status_counts: Record<string, number>;
  top_issues: BatchTopIssue[];
}

export interface BatchReport {
  batch: AuditBatch;
  targets: BatchTargetReport[];
  findings: Array<Record<string, unknown> & {
    agent_id: string;
    target_id: number;
    url: string;
  }>;
  summary?: BatchSummary;
  limitations: string[];
}

export interface AuditBatch {
  id: string;
  idempotency_key: string;
  status: BatchStatus;
  analysis_status?: AnalysisStatus;
  total_count: number;
  completed_count: number;
  failed_count: number;
  skipped_count: number;
  allow_internal_discovery: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  targets: BatchTarget[];
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
  metrics?: ResourceGraphMetrics;
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

export interface CategoryScore {
  category: "technical_seo" | "marketing_seo" | "conversion" | "ib_content" | string;
  label: string;
  score_percent: number | null;
  earned: number;
  applicable_weight: number;
  total_weight: number;
  coverage_percent: number;
  rule_count: number;
  pass_count: number;
  issue_count: number;
  warning_count: number;
  na_count: number;
  insufficient_count: number;
}

export interface PriorityItem {
  rule_id: string;
  title: string;
  category: string;
  severity: string;
  priority_score: number;
  confidence: number;
  page_type: string;
  recommendation: string;
  observed: string;
  expected: string;
  basis?: string;
}

export interface EvaluationSummary {
  total_rules: number;
  pass: number;
  issues: number;
  warnings: number;
  not_applicable: number;
  insufficient_evidence: number;
}

export interface BusinessFinding {
  id: string;
  rule_id?: string;
  title: string;
  name?: string;
  category?: string;
  subcategory?: string;
  description?: string;
  status: "pass" | "warn" | "fail" | "unknown" | "not_applicable";
  severity: "critical" | "high" | "medium" | "low" | "info" | string;
  weight?: number;
  points_earned?: number | null;
  evidence: { observed: string; expected: string };
  observed?: string;
  expected?: string;
  why_it_matters?: string;
  recommendation: string;
  confidence: number;
  source?: string;
  selector?: string | null;
  snippet?: string | null;
  rule_version?: string;
  url: string;
  page_type: string;
  business_priority?: number;
}

export interface BusinessReport {
  url: string;
  evaluated_at?: string;
  scoring_version?: string;
  page_classification: { label: string; confidence: number; evidence: string[] } | null;
  categories?: CategoryScore[];
  findings: BusinessFinding[];
  priority_items?: PriorityItem[];
  summary?: EvaluationSummary;
  disclaimer?: string;
  finding_count: number;
  by_rule: Record<string, number>;
  heuristic_priority: string;
}

export interface Agent {
  id: string;
  name: string;
  version: string;
  scope: string;
}

export interface ProviderStatus {
  search_console: {
    status: string;
    reason: string;
  };
  analytics?: {
    status: string;
    reason?: string;
    imported_events_count?: number;
    active_users_30d?: number | null;
  };
  backlinks: {
    status: string;
    reason: string;
  };
}

export interface AuditReportFinding {
  id: string;
  check_id: string;
  title: string;
  status: string;
  severity: string;
  weight: number;
  points_earned: number | null;
  evidence: {
    observed: string;
    expected: string;
    selector?: string | null;
  };
  why_it_matters: string;
  recommendation: string;
  confidence: number;
  source?: string;
}

export interface AuditReportAgent {
  agent_id: string;
  agent_version: string;
  rule_version: string;
  scope: string;
  status: string;
  score: {
    earned: number;
    applicable_weight: number;
    total_weight: number;
    percent: number;
    coverage_percent: number;
  };
  findings: AuditReportFinding[];
}

export interface AuditReportData {
  audit_id: string;
  url: string;
  generated_at: string;
  rule_version: string;
  agents: AuditReportAgent[];
  findings?: AuditReportFinding[];
  score: {
    earned: number;
    applicable_weight: number;
    total_weight: number;
    percent: number;
    coverage_percent: number;
  };
  coverage: number;
  final_audit?: {
    executive_summary: string;
    strengths: string[];
    weaknesses: string[];
    quick_wins: string[];
    prioritized_actions: Array<{
      action: string;
      rationale: string;
      finding_ids: string[];
    }>;
    explanation_for_beginners: string;
    llm_fallback?: boolean;
  };
  charts?: Record<string, unknown>;
  stages?: StageEvent[];
  errors?: string[];
  resource_graph?: ResourceGraph;
}

export interface AuditReportItem {
  agent_id: string;
  report_json: AuditReportData | Record<string, unknown>;
  created_at: string;
}

export interface AgentRunStarted {
  status: string;
  agent_id: string;
}

export type ResourceNodeType =
  | "primary_page"
  | "linked_page"
  | "image"
  | "media"
  | "stylesheet"
  | "script"
  | "other_resource"
  | "failed_resource";

export type ResourceCheckStatus =
  | "available"
  | "redirects"
  | "client_error"
  | "server_error"
  | "error"
  | "could_not_be_checked"
  | "inconclusive";

export interface ResourceGraphIssue {
  issue: string;
  evidence: string;
  impact: string;
  recommendation: string;
  severity: string;
  affected_resource?: string;
  verification?: string;
}

export interface ResourceNodeDetails {
  title?: string;
  word_count?: number;
  headings_count?: number;
  canonical?: string;
  timing_ms?: number;
  alt?: string | null;
  has_alt?: boolean;
  aria_label?: string | null;
  width?: string | null;
  height?: string | null;
  loading?: string | null;
  section?: string | null;
  note?: string;
  anchor_text?: string;
  rel?: string[] | string;
  target?: string | null;
  async?: boolean;
  defer?: boolean;
  type?: string;
  media?: string;
  media_tag?: string;
  media_type?: string;
  resource_type?: string;
  error?: string;
  [key: string]: any;
}

export interface ResourceGraphNode {
  id: string;
  url: string;
  label: string;
  node_type: ResourceNodeType;
  status: ResourceCheckStatus;
  http_status: number | null;
  final_url: string;
  redirect_chain: string[];
  content_type: string;
  is_internal: boolean;
  deeply_audited: boolean;
  details: ResourceNodeDetails;
  issues: ResourceGraphIssue[];
  recommendations: string[];
}

export interface ResourceGraphEdge {
  id: string;
  source: string;
  target: string;
  relationship:
    | "outgoing_internal_link"
    | "outgoing_external_link"
    | "image"
    | "stylesheet"
    | "script"
    | "media"
    | "other_resource";
  discovery_source: string;
  check_status: ResourceCheckStatus;
  attributes: Record<string, unknown>;
}

export interface ResourceGraphMetrics {
  deep_pages_crawled: number;
  discovered_html_links: number;
  internal_links_count: number;
  external_links_count: number;
  unique_resource_urls: number;
  images_count: number;
  scripts_count: number;
  stylesheets_count: number;
  media_count: number;
  link_check_attempts: number;
  successfully_checked_resources: number;
  failed_resources_count: number;
  redirect_count: number;
}

export interface ResourceGraph {
  primary_url: string;
  nodes: ResourceGraphNode[];
  edges: ResourceGraphEdge[];
  metrics: ResourceGraphMetrics;
}

