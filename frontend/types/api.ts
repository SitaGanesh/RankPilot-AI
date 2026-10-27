export type AuditStatus =
  | "pending"
  | "queued"
  | "collecting"
  | "collected"
  | "running"
  | "waiting_for_access"
  | "waiting_for_approval"
  | "completed"
  | "completed_with_limitations"
  | "failed"
  | "cancelled";

export type CrawlStatus =
  | "pending"
  | "queued"
  | "fetching"
  | "fetched"
  | "processing"
  | "completed"
  | "discovered"
  | "failed"
  | "skipped";
export type CrawlResourceType = "page" | "media";

export type DiscoverySource = "submitted" | "internal_link" | "sitemap";
export type BatchStatus = "pending" | "running" | "completed" | "partial" | "failed" | "cancelled";
export type BatchTargetStatus = "pending" | "running" | "retryable" | "completed" | "failed" | "skipped";
export type AnalysisStatus = "pending" | "running" | "completed" | "partial" | "failed";
export type AgentId = "onpage" | "technical" | "functionality" | "connectivity" | "visibility" | string;

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
  mode?: "standard" | "agentic" | string;
  audit_type?: "page" | "website" | string;
  max_crawl_pages?: number;
  max_crawl_depth?: number;
  pages_crawled_count?: number;
  objective?: string;
  current_stage: string;
  execution_backend?: string;
  stop_reason?: string;
  created_at: string;
  stage_events: StageEvent[];
  metrics?: ResourceGraphMetrics;
  crawl_coverage?: CrawlCoverage | null;
  investigation?: InvestigationSummary | null;
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
  deeply_audited?: boolean;
  page_title?: string;
  timing_ms?: number;
  content_type?: string;
  browser_data?: Record<string, any>;
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
  in_degree?: number;
  out_degree?: number;
  is_orphan?: boolean;
  discovery_source?: string;
  score_percent?: number | null;
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
  orphan_pages_count?: number;
  crawl_coverage_limited?: boolean;
}

export interface ResourceGraph {
  primary_url: string;
  nodes: ResourceGraphNode[];
  edges: ResourceGraphEdge[];
  metrics: ResourceGraphMetrics;
}

/* ------------------------------------------------------------------ */
/* Agentic investigation                                              */
/* ------------------------------------------------------------------ */

export type InvestigationStatus =
  | "queued"
  | "running"
  | "waiting_for_access"
  | "waiting_for_approval"
  | "interrupted"
  | "completed"
  | "completed_with_limitations"
  | "failed"
  | "cancelled";

export interface InvestigationAction {
  sequence: number;
  decision_type: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  rationale: string;
  status: "running" | "succeeded" | "failed" | "rejected";
  result_json: Record<string, unknown> | null;
  observation: string;
  error: string;
  evidence_ref: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface InvestigationFinding {
  id: number;
  finding_ref: string;
  check_id: string;
  title: string;
  status: string;
  severity: string;
  confidence: number;
  affected_urls: string[];
  observed: string;
  expected: string;
  root_cause: string;
  recommendation: string;
  evidence_refs: string[];
  source_tool: string;
  verification_status: string;
  created_at: string;
  updated_at: string;
}

export interface InvestigationHypothesis {
  id: number;
  statement: string;
  status: string;
  confidence: number;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface RemediationProposal {
  id: number;
  finding_ref: string;
  status: string;
  change: string;
  scope: string[];
  expected_outcome: string;
  risk: string;
  verification_method: string;
  rollback: string;
  baseline: Record<string, unknown>;
  evidence_refs: string[];
  approval_note: string;
  approved_at: string | null;
  execution_status: string;
  execution_result: Record<string, unknown>;
  verification: Record<string, unknown>;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvestigationProgress {
  actions_completed: number;
  actions_rejected: number;
  iterations_used: number;
  iterations_max: number;
  tool_calls_used: number;
  tool_calls_max: number;
  requests_used: number;
  request_budget: number;
}

export interface InvestigationCurrentAction {
  sequence: number;
  decision_type: string;
  tool_name: string;
  status: string;
  observation: string;
}

export interface InvestigationSummary {
  id: string;
  objective: string;
  status: InvestigationStatus;
  stop_reason: string;
  iteration_count: number;
  max_iterations: number;
  tool_call_count: number;
  max_tool_calls: number;
  model_call_count: number;
  max_model_calls: number;
  requests_used: number;
  request_budget: number;
  current_action: InvestigationCurrentAction | null;
  progress: InvestigationProgress;
  started_at: string | null;
  finished_at: string | null;
  last_checkpoint_at: string | null;
}

export interface InvestigationDetail extends InvestigationSummary {
  audit_id: string;
  plan: Record<string, unknown>;
  next_action: Record<string, unknown>;
  time_budget_seconds: number;
  limitations: string[];
  actions: InvestigationAction[];
  findings: InvestigationFinding[];
  hypotheses: InvestigationHypothesis[];
  proposals: RemediationProposal[];
  coverage: Record<string, unknown>;
}

export interface InvestigationResponse {
  audit_id: string;
  mode: "standard" | "agentic" | string;
  objective: string;
  execution_backend: string;
  stop_reason: string;
  investigation: InvestigationDetail | null;
  report_available: boolean;
}

export interface InvestigationStarted {
  audit_id: string;
  investigation_id: string;
  status: string;
  execution_backend: string;
}

export interface AuditLiveEvent {
  id: number;
  audit_id: string;
  url: string;
  event_type: string;
  data: Record<string, any>;
  created_at: string;
}

export interface LiveEventsPollResponse {
  audit_id: string;
  status: AuditStatus;
  current_stage: string;
  pages_crawled_count: number;
  last_event_id: number;
  completed: boolean;
  events: AuditLiveEvent[];
}

export interface BrowserObservationData {
  url?: string;
  final_url?: string;
  status_code?: number;
  redirect_chain?: string[];
  headers?: Record<string, string>;
  timing_ms?: number;
  browser_engine?: string;
  raw_title?: string;
  rendered_title?: string;
  page_title?: string;
  title_changed?: boolean;
  raw_canonical?: string;
  rendered_canonical?: string;
  canonical?: string;
  canonical_changed?: boolean;
  raw_word_count?: number;
  rendered_word_count?: number;
  empty_html_shell?: boolean;
  rendered_dom_available?: boolean;
  console_errors?: Array<{
    kind?: string;
    type?: string;
    severity?: string;
    text?: string;
    message?: string;
    location?: Record<string, any>;
    page_url?: string;
    source_url?: string;
    stack?: string;
    timestamp?: string;
    occurrences?: number;
  }>;
  console_events?: Array<Record<string, unknown>>;
  network_requests?: Array<{
    url?: string;
    method?: string;
    resource_type?: string;
    status?: number;
    status_text?: string;
    content_type?: string;
    duration_ms?: number | null;
    redirected_from?: string;
    page_url?: string;
  }>;
  resource_checks?: Array<Record<string, unknown>>;
  failed_requests?: Array<{
    kind?: string;
    url?: string;
    method?: string;
    resource_type?: string;
    status?: number;
    status_text?: string;
    failure?: string;
    error?: string;
    content_type?: string;
    page_url?: string;
    timestamp?: string;
    occurrences?: number;
  }>;
  resource_summary?: {
    images_count?: number;
    scripts_count?: number;
    stylesheets_count?: number;
    checked_assets_count?: number;
    failed_assets_count?: number;
  };
  accessibility_summary?: {
    h1_count?: number;
    total_headings?: number;
    images_count?: number;
    missing_alt_count?: number;
    has_lang?: boolean;
    has_viewport?: boolean;
  };
  raw_internal_links?: Array<Record<string, any>>;
  internal_links?: Array<Record<string, any>>;
  external_links?: string[];
  screenshot_id?: string;
  screenshot_data?: string;
  screenshot_metadata?: {
    screenshot_id?: string;
    screenshot_path?: string;
    width?: number;
    height?: number;
    bytes?: number;
    captured_at?: string;
    viewport?: string;
  };
  performance_metrics?: Record<string, any>;
  navigation_summary?: {
    nav_elements_count?: number;
    menu_links_count?: number;
    empty_hrefs_count?: number;
    mobile_toggles_count?: number;
    sample_nav_labels?: string[];
  };
  forms_summary?: {
    total_forms?: number;
    visible_forms?: number;
    inputs_count?: number;
    required_inputs_count?: number;
    labeled_inputs_count?: number;
    submit_buttons_count?: number;
    forms_with_validation?: number;
    safe_status?: string;
    forms_detail?: Array<Record<string, any>>;
  };
  interactive_controls_summary?: {
    buttons_count?: number;
    buttons_without_accessible_name?: number;
    disabled_buttons_count?: number;
    sample_buttons?: Array<Record<string, any>>;
  };
  layout_summary?: {
    has_viewport_meta?: boolean;
    landmarks?: Record<string, any>;
    has_horizontal_scroll_overflow?: boolean;
  };
  error?: string;
}

export interface PageAuditFinding {
  id: string;
  check_id: string;
  title: string;
  status: "pass" | "warn" | "fail" | "skipped" | "unavailable" | "inconclusive" | string;
  severity: "critical" | "high" | "medium" | "low" | "info" | string;
  weight?: number;
  points_earned?: number;
  evidence?: {
    observed?: string;
    expected?: string;
    selector?: string;
  };
  observed?: string;
  expected?: string;
  observed_evidence?: string;
  actionable_recommendations?: string[] | string;
  section_or_element?: string;
  intended_audience_context?: string;
  suggested_verification?: string;
  why_it_matters?: string;
  recommendation?: string;
  verification_guidance?: string;
  confidence?: number;
  source?: string;
  category?: string;
  agent_id?: string;
  perspective?: string;
  affected_urls?: string[];
  priority?: string;
  priority_rationale?: string;
  specific_claim_or_passage?: string;
  assessment?: "supported" | "potentially_inaccurate" | "outdated" | "incomplete" | "ambiguous" | "unverifiable" | string;
  authoritative_source?: string;
  educational_implications?: string;
  verification_limitations?: string;
  page_url?: string;
  page_title?: string;
}

export interface PageAuditReport {
  id: number;
  audit_id: string;
  crawl_url_id: number | null;
  url: string;
  normalized_url: string;
  title: string;
  status_code: number | null;
  score_percent: number | null;
  report_json: {
    findings?: PageAuditFinding[];
    summary?: Record<string, any>;
    agent_results?: Record<string, any>;
    agents?: Record<string, any>;
    status?: string;
    error_reason?: string | null;
    url?: string;
    executive_summary?: string;
    score?: { percent: number; band?: string };
    diagnostics?: Record<string, any>;
    links?: Array<Record<string, unknown>>;
    resources?: Array<Record<string, unknown>>;
    console_events?: Array<Record<string, unknown>>;
    network_requests?: Array<Record<string, unknown>>;
    observation_sources?: Record<string, string>;
    browser_observation?: Record<string, any>;
    landing_page_analysis?: LandingPageReport;
    [key: string]: unknown;
  };
  browser_data: BrowserObservationData;
  created_at: string;
  updated_at: string;
}


export interface WebsiteDimensionSummary {
  name: string;
  score: number | null;
  score_methodology?: string;
  total_findings: number;
  issues_count: number;
  summary: string;
  top_issues: PageAuditFinding[];
  strengths?: string[];
  telemetry?: Record<string, unknown>;
}

export interface CrossPageIssueItem {
  issue_id: string;
  title: string;
  perspective: string;
  affected_pages_count: number;
  affected_urls: string[];
  root_cause_diagnosis: string;
  impact_level: "critical" | "high" | "medium" | "low" | string;
  actionable_fix: string;
  verification_method: string;
}

export interface PrioritizedActionPlanItem {
  rank: number;
  perspective: string;
  title: string;
  action: string;
  rationale: string;
  affected_urls: string[];
  priority: "critical" | "high" | "medium" | "low" | string;
  effort_estimate: "quick_win" | "moderate" | "substantial" | string;
  verification_step: string;
}

export interface CrawlCoverage {
  discovered_unique_urls: number;
  queued_urls: number;
  attempted_fetches: number;
  fetched_html_pages: number;
  deeply_analyzed_pages: number;
  failed_pages: number;
  skipped_urls: number;
  shallowly_checked_links: number;
  unique_resources: number;
  links_recorded: number;
  page_reports: number;
  status_breakdown?: Record<string, number>;
}

export interface ConsolidatedWebsiteReport {
  audit_id: string;
  target_url: string;
  normalized_url: string;
  audit_type: string;
  generated_at: string;
  pages_crawled_count: number;
  crawl_coverage?: CrawlCoverage;
  score: {
    percent: number | null;
    band: "excellent" | "good" | "needs_improvement" | "poor" | "not_scored" | string;
    methodology?: string;
  };
  executive_summary?: string;
  top_strengths?: string[];
  critical_blockers?: string[];
  perspectives?: {
    seo?: Record<string, unknown>;
    marketing?: Record<string, unknown>;
    sales?: Record<string, unknown>;
    subject_matter?: Record<string, unknown>;
    [key: string]: unknown;
  };
  cross_page_issues?: CrossPageIssueItem[];
  prioritized_actions?: PrioritizedActionPlanItem[];
  conflicting_recommendations_resolved?: string[];
  limitations?: string[];
  dimensions: {
    technical_seo_ai?: WebsiteDimensionSummary;
    content_quality?: WebsiteDimensionSummary;
    marketing_conversion?: WebsiteDimensionSummary;
    website_functionality?: WebsiteDimensionSummary;
    overall_connectivity?: WebsiteDimensionSummary;
    seo?: WebsiteDimensionSummary;
    marketing?: WebsiteDimensionSummary;
    sales?: WebsiteDimensionSummary;
    subject_matter?: WebsiteDimensionSummary;
    [key: string]: WebsiteDimensionSummary | undefined;
  };
  all_pages: Array<{
    id: number;
    url: string;
    title: string;
    status_code: number | null;
    score_percent: number | null;
    findings_count: number;
  }>;
  browser_session_summary: {
    pages_inspected: number;
    console_error_events?: number;
    javascript_errors_detected?: number;
    failed_network_requests: number;
    unique_resources_checked?: number;
    rendered_dom_utilized: boolean;
    average_page_timing_ms?: number;
  };
}

export interface LandingPerspectiveData {
  perspective: "marketing" | "sales" | "subject_matter" | "seo_functionality" | string;
  title: string;
  health_score?: number | null;
  score_band?: "excellent" | "good" | "needs_improvement" | "poor" | string | null;
  summary: string;
  strengths: string[];
  key_weaknesses: string[];
  findings: PageAuditFinding[];
}

export interface LandingGapAnalysisData {
  missing_information: string[];
  unanswered_objections: string[];
  trust_gaps: string[];
  messaging_problems: string[];
  conversion_opportunities: string[];
}

export interface LandingPrioritizedRecommendation {
  rank: number;
  perspective: string;
  title: string;
  expected_benefit: string;
  implementation_direction: string;
  priority: "critical" | "high" | "medium" | "low" | string;
  effort: "quick_win" | "moderate" | "substantial" | string;
  verification_step: string;
}

export interface LandingPageReport {
  page_url: string;
  page_title: string;
  landing_page_purpose: string;
  intended_audience: {
    target_profiles?: string[];
    primary_needs?: string[];
    search_intent?: string;
    journey_stage?: string;
  };
  commercial_offer: {
    offer_summary?: string;
    value_proposition?: string;
    positioning?: string;
    pricing_clarity?: string;
  };
  executive_summary: string;
  overall_score: number;
  score_band: "excellent" | "good" | "needs_improvement" | "poor" | string;
  top_strengths: string[];
  critical_blockers: string[];
  key_observations: string[];
  perspectives: {
    marketing?: LandingPerspectiveData;
    sales?: LandingPerspectiveData;
    subject_matter?: LandingPerspectiveData;
    seo_functionality?: LandingPerspectiveData;
    [key: string]: LandingPerspectiveData | undefined;
  };
  gap_analysis: LandingGapAnalysisData;
  prioritized_recommendations: LandingPrioritizedRecommendation[];
  all_findings?: PageAuditFinding[];
  coverage_indicators?: {
    rendered_dom_utilized: boolean;
    browser_telemetry_included: boolean;
    console_errors_count: number;
    failed_network_requests: number;
    load_time_ms: number;
    word_count: number;
  };
  unavailable_data_indicators?: string[];
  uncertainties?: string[];
  ib_context?: {
    is_ib_page: boolean;
    curriculum_detected: string[];
    official_references: string[];
    subject_matter_notes: string;
  } | null;
}

/* ================================================================== */
/* Marketing Intelligence Agent                                        */
/* ================================================================== */

export type MarketingCriterion =
  | "audience_intent"
  | "value_proposition"
  | "content_quality"
  | "visitor_journey"
  | "brand_positioning";

export type MarketingPriority = "Critical" | "High" | "Medium" | "Low";
export type MarketingLevel = "Low" | "Medium" | "High";

export type MarketingMetric =
  | "organic_traffic"
  | "engagement"
  | "conversion"
  | "bounce_rate"
  | "trust_credibility"
  | "lead_quality"
  | "brand_clarity";

export interface MarketingImpactEffect {
  metric: MarketingMetric;
  direction: "increase" | "decrease" | "neutral";
  magnitude: MarketingLevel;
  good_for_business: boolean;
  explanation: string;
}

export interface MarketingActionItem {
  title: string;
  criterion: MarketingCriterion;
  priority: MarketingPriority;
  complexity: MarketingLevel;
  current_situation: string;
  recommended_change: string;
  reason: string;
  expected_outcome: string;
  why_better: string;
  impact_level: MarketingLevel;
  nature_of_impact: MarketingImpactEffect[];
  evidence: string[];
  success_metric: string;
  confidence: MarketingLevel;
  // enriched by agent
  rank?: number;
  page_url?: string;
  page_type?: string;
}

export interface MarketingCriterionAssessment {
  criterion: MarketingCriterion;
  score: number; // 1–10
  current_situation: string;
  strengths: string[];
  gaps: string[];
}

export interface MarketingAudienceFit {
  identified_audiences: string[];
  likely_visitor_intent: string;
  intent_match: MarketingLevel;
  audience_too_broad_or_unclear: boolean;
  assessment: string;
}

export interface MarketingPageReport {
  url: string;
  page_type: string;
  summary: string;
  audience_fit: MarketingAudienceFit;
  criteria: MarketingCriterionAssessment[];
  positioning_gaps: string[];
  messaging_weaknesses: string[];
  content_improvements: string[];
  missing_information: string[];
  unsupported_or_vague_claims: string[];
  action_items: MarketingActionItem[];
  html_signals?: {
    title?: string;
    meta_description?: string;
    headings?: Array<{ tag: string; text: string }>;
    calls_to_action?: Array<{ text: string; href?: string }>;
    word_count?: number;
    images_total?: number;
    images_missing_alt?: number;
    has_structured_data?: boolean;
    forms_count?: number;
    internal_link_count?: number;
  };
}

export interface MarketingResearchBrief {
  business_summary: string;
  likely_audiences: string[];
  competitors: string[];
  external_reputation_notes: string;
  priority_pages: string[];
  brand_document_notes: string;
}

export interface MarketingSiteSynthesis {
  executive_summary: string;
  overall_marketing_score: number; // 1–10
  audience_fit_summary: string;
  cross_page_inconsistencies: string[];
  strategic_positioning_gaps: string[];
  sequencing_rationale: string;
}

export interface MarketingRunResult {
  site: MarketingSiteSynthesis;
  pages: MarketingPageReport[];
  roadmap: MarketingActionItem[];
  failed_pages: Array<{ url: string; error: string }>;
}

export interface MarketingRun {
  id: number;
  audit_id: string;
  url: string;
  status: "queued" | "running" | "done" | "failed";
  research_brief: MarketingResearchBrief | null;
  result: MarketingRunResult | null;
  error: string;
  created_at: string;
  updated_at: string;
}
