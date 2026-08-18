const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface FunnelStageData {
  leads: number;
  cucet: number;
  admission: number;
}

export interface FunnelConversionRates {
  lead_cucet_percent: number;
  lead_admission_percent: number;
  cucet_admission_percent: number;
}

export interface FunnelYoYChange {
  leads_percent: number | null;
  cucet_percent: number | null;
  admission_percent: number | null;
}

export interface FunnelResponse {
  current_year: number;
  previous_year: number;
  current_year_funnel: FunnelStageData;
  previous_year_funnel: FunnelStageData;
  conversion_rates: FunnelConversionRates;
  year_over_year_change: FunnelYoYChange;
}

export interface SourcePerformanceMetrics {
  leads: number;
  cucet: number;
  admission: number;
  lead_cucet_percent: number | null;
  lead_admission_percent: number | null;
  cucet_admission_percent: number | null;
}

export interface SourcePerformanceItem {
  main_source: string;
  source: string;
  current_year: number;
  previous_year: number;
  current: SourcePerformanceMetrics;
  previous: SourcePerformanceMetrics;
  lead_growth_percent: number | null;
  admission_growth_percent: number | null;
  performance_flag: "high_leads_low_conversion" | "strong" | "normal" | string;
  growth_status: "new_source" | "dropped" | "increased" | "decreased" | "unchanged" | string;
}

export interface SourceHierarchyNode {
  name: string;
  raw_name: string;
  leads: number;
  cucet: number;
  admission: number;
  py_leads: number;
  py_cucet: number;
  py_admission: number;
  performance: string;
  children?: SourceHierarchyNode[];
}

export interface SourceDetailResponse {
  year: number;
  main_source: string;
  source: string;
  funnel: {
    leads: number;
    cucet: number;
    admission: number;
  };
  conversion: {
    lead_cucet_percent: number | null;
    lead_admission_percent: number | null;
    cucet_admission_percent: number | null;
  };
  performance: "high_leads_low_conversion" | "strong" | "normal" | string;
}

export interface ColumnMappingItem {
  original_column: string;
  canonical_field: string;
  confidence?: number;
  is_ambiguous?: boolean;
  reasoning?: string;
}

export interface UploadedFileProfile {
  rows: number;
  columns: number;
  quality_score?: number | null;
  [key: string]: unknown;
}

export interface UploadedFileItem {
  dataset_id: string;
  filename: string;
  file_type: string;
  status: string;
  staged_rows: number;
  normalized_rows?: number;
  column_mappings?: ColumnMappingItem[];
  profile: UploadedFileProfile;
}


export interface FileUploadResponse {
  status: string;
  file_count: number;
  files: UploadedFileItem[];
}

export interface ActiveDatasetInfo {
  id: string;
  dataset_name: string;
  original_filename: string;
  row_count: number;
  column_count: number;
  status: string;
  created_at: string;
  quality_score: number | null;
  academic_label?: string | null;
  upload_version?: number | null;
}

export async function getActiveDataset(): Promise<{ active: boolean; dataset: ActiveDatasetInfo | null }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/data/active`);
    if (!response.ok) {
      return { active: false, dataset: null };
    }
    return response.json();
  } catch {
    return { active: false, dataset: null };
  }
}

export interface ChatRecommendation {
  label: string;
  question: string;
}

export interface AnalysisSection {
  type: "metric_table" | "driver_table" | "observation_list" | "text_block";
  title?: string;
  columns?: string[];
  data?: Record<string, unknown>[];
  items?: string[];
  content?: string;
}

export interface ChatResponse {
  question: string;
  answer: string;
  conversation_id?: string;
  year?: number;
  funnel?: FunnelResponse;
  source_performance?: SourcePerformanceItem[];
  recommendations?: ChatRecommendation[];
  sections?: AnalysisSection[];
  debug?: Record<string, unknown>;
  [key: string]: unknown;
}

export async function getFunnel(year: number): Promise<FunnelResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/analytics/funnel?year=${year}`
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch funnel data");
  }

  return response.json();
}

export async function getSourcePerformance(
  year: number
): Promise<{ year: number; sources: SourcePerformanceItem[] }> {
  const response = await fetch(
    `${API_BASE_URL}/api/analytics/source-performance?year=${year}`
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch source performance");
  }

  return response.json();
}

export async function getSourceHierarchy(
  year: number
): Promise<{ year: number; sources: SourceHierarchyNode[] }> {
  const response = await fetch(
    `${API_BASE_URL}/api/analytics/source-hierarchy?year=${year}`
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch source hierarchy");
  }

  return response.json();
}

export async function getSourceDetail(
  year: number,
  mainSource: string,
  source: string
): Promise<SourceDetailResponse | null> {
  const params = new URLSearchParams({
    year: String(year),
    main_source: mainSource,
    source,
  });

  const response = await fetch(
    `${API_BASE_URL}/api/analytics/source-detail?${params.toString()}`
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch source detail");
  }

  return response.json();
}

export async function uploadFiles(files: File[]): Promise<FileUploadResponse> {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(`${API_BASE_URL}/api/data/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let errorMessage = "Failed to upload files";
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage =
          typeof errorJson.detail === "string"
            ? errorJson.detail
            : JSON.stringify(errorJson.detail);
      }
    } catch {
      const errorText = await response.text();
      if (errorText) errorMessage = errorText;
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function askAgent(question: string, conversationId?: string, periodA?: string, periodB?: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      period_a: periodA,
      period_b: periodB,
    }),
  });

  if (!response.ok) {
    let errorMessage = "Failed to process question";
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage =
          typeof errorJson.detail === "string"
            ? errorJson.detail
            : JSON.stringify(errorJson.detail);
      }
    } catch {
      const errorText = await response.text();
      if (errorText) errorMessage = errorText;
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export interface KPIItem {
  cy: number;
  py: number;
  change: number;
  growth_pct: number | null;
}

export interface OverviewResponse {
  current_year: number;
  previous_year: number;
  has_cucet: boolean;
  kpis: {
    leads: KPIItem;
    cucet?: KPIItem;
    admissions: KPIItem;
    conversion_rate: KPIItem;
    cucet_conversion_rate?: KPIItem;
  };
  funnel: {
    stage: string;
    count: number;
    pct_of_leads: number;
    conversion_rate: number;
  }[];
}

export interface InsightItem {
  id: string;
  title: string;
  text: string;
  dimension: string;
  value: string;
}

export interface PerformerItem {
  entity: string;
  value: number;
  count?: number;
  leads?: number;
}

export interface TopPerformersResponse {
  program_name?: PerformerItem[];
  source?: PerformerItem[];
  campus_name?: PerformerItem[];
  state?: PerformerItem[];
  owner?: PerformerItem[];
}

export interface EntityOverview {
  leads: KPIItem;
  admissions: KPIItem;
  conversion_rate: KPIItem;
}

export interface EntityBreakdownItem {
  entity: string;
  leads: number;
  admissions: number;
  conversion_rate: number;
}

export interface EntityDetailResponse {
  dimension: string;
  value: string;
  current_year: number;
  previous_year: number;
  overview: EntityOverview;
  breakdowns: {
    source?: EntityBreakdownItem[];
    campus_name?: EntityBreakdownItem[];
    state?: EntityBreakdownItem[];
    owner?: EntityBreakdownItem[];
  };
}

export interface DashboardFilters {
  academic_session?: string;
  campus?: string;
  state?: string;
  source?: string;
  program?: string;
}

export interface DashboardFilterOptionsResponse {
  academic_sessions: string[];
  campuses: string[];
  states: string[];
  sources: string[];
  programs: string[];
}

function buildDashboardQuery(filters?: DashboardFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.academic_session && filters.academic_session !== "all") params.set("academic_session", filters.academic_session);
  if (filters.campus && filters.campus !== "all") params.set("campus", filters.campus);
  if (filters.state && filters.state !== "all") params.set("state", filters.state);
  if (filters.source && filters.source !== "all") params.set("source", filters.source);
  if (filters.program && filters.program !== "all") params.set("program", filters.program);
  const str = params.toString();
  return str ? `?${str}` : "";
}

export async function getDashboardFilterOptions(session?: string): Promise<DashboardFilterOptionsResponse> {
  const url = `${API_BASE_URL}/api/dashboard/options${session && session !== "all" ? `?academic_session=${encodeURIComponent(session)}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch filter options");
  }
  return response.json();
}

export async function getDashboardOverview(filters?: DashboardFilters): Promise<OverviewResponse> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/overview${query}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch dashboard overview");
  }
  return response.json();
}

export async function getDashboardInsights(filters?: DashboardFilters): Promise<InsightItem[]> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/insights${query}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch dashboard insights");
  }
  return response.json();
}

export async function getDashboardTopPerformers(metric: string): Promise<TopPerformersResponse> {
  const response = await fetch(`${API_BASE_URL}/api/dashboard/top-performers?metric=${metric}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch top performers");
  }
  return response.json();
}

export interface MonthlyTrendItem {
  month: string;
  cy_leads: number;
  cy_cucet: number;
  cy_admission: number;
  py_leads: number;
  py_cucet: number;
  py_admission: number;
  cy_conversion_rate: number;
  py_conversion_rate: number;
}

export interface PerformanceRankingsRow {
  entity: string;
  py_leads: number;
  cy_leads: number;
  py_admission: number;
  cy_admission: number;
  py_conversion_rate: number;
  cy_conversion_rate: number;
  admission_change: number;
  rate_change: number;
}

export interface PerformanceRankingsResponse {
  improvements: PerformanceRankingsRow[];
  declines: PerformanceRankingsRow[];
}

export async function getDashboardMonthlyTrend(filters?: DashboardFilters): Promise<MonthlyTrendItem[]> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/monthly-trend${query}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch monthly trend data");
  }
  return response.json();
}

export async function getDashboardPerformanceRankings(
  dimension: string,
  filters?: DashboardFilters
): Promise<PerformanceRankingsResponse> {
  const params = new URLSearchParams();
  params.set("dimension", dimension);
  if (filters) {
    if (filters.academic_session && filters.academic_session !== "all") params.set("academic_session", filters.academic_session);
    if (filters.campus && filters.campus !== "all") params.set("campus", filters.campus);
    if (filters.state && filters.state !== "all") params.set("state", filters.state);
    if (filters.source && filters.source !== "all") params.set("source", filters.source);
    if (filters.program && filters.program !== "all") params.set("program", filters.program);
  }
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/performance-rankings?${params.toString()}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch performance rankings");
  }
  return response.json();
}

export async function getEntityDetail(dimension: string, value: string): Promise<EntityDetailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/entity/${encodeURIComponent(dimension)}/${encodeURIComponent(value)}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch entity details");
  }
  return response.json();
}

export interface ExploreItem {
  entity: string;
  py_leads: number;
  cy_leads: number;
  py_admission: number;
  cy_admission: number;
  py_rate: number;
  cy_rate: number;
  change: number;
  growth_pct: number | null;
}

export interface ExploreResponse {
  positive: ExploreItem[];
  negative: ExploreItem[];
}

export async function getDashboardExplore(
  dimension: string,
  metric: string,
  limit: number = 10
): Promise<ExploreResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/explore?dimension=${encodeURIComponent(
      dimension
    )}&metric=${encodeURIComponent(metric)}&limit=${limit}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch exploration data");
  }
  return response.json();
}

export interface CompareValueData {
  entity: string;
  py_leads: number;
  cy_leads: number;
  py_admission: number;
  cy_admission: number;
  py_rate: number;
  cy_rate: number;
}

export interface CompareResponse {
  dimension: string;
  metric: string;
  value_a: CompareValueData;
  value_b: CompareValueData;
  differences: {
    cy_leads: number;
    py_leads: number;
    cy_admission: number;
    py_admission: number;
    cy_rate: number;
    py_rate: number;
  };
}

export async function getDashboardCompare(
  dimension: string,
  valueA: string,
  valueB: string,
  metric: string
): Promise<CompareResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/compare?dimension=${encodeURIComponent(
      dimension
    )}&value_a=${encodeURIComponent(valueA)}&value_b=${encodeURIComponent(
      valueB
    )}&metric=${encodeURIComponent(metric)}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to execute comparison");
  }
  return response.json();
}

export async function getDimensionValues(dimension: string): Promise<string[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/dimension-values?dimension=${encodeURIComponent(
      dimension
    )}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch dimension values");
  }
  return response.json();
}

// ============================================================
// Period / Academic-Year API
// ============================================================

export interface PeriodSummary {
  academic_label: string;
  period_start_year: number | null;
  period_end_year: number | null;
  latest_version: number;
  total_versions: number;
  active_dataset_id: string | null;
  active_filename: string | null;
  active_created_at: string | null;
}

export interface PeriodDetection {
  period_start_year: number | null;
  period_end_year: number | null;
  academic_label: string | null;
  confidence: number;
  detection_method: string;
}

export interface PeriodConflictInfo {
  has_conflict: boolean;
  academic_label: string;
  existing_dataset: {
    dataset_id: string;
    original_filename: string;
    upload_version: number;
    is_period_active: boolean;
    created_at: string;
  } | null;
  next_version: number;
  allowed_actions: string[];
}

export interface UploadedFileItemExtended extends UploadedFileItem {
  upload_status?: "confirmed" | "pending_confirmation" | "period_unknown" | "conflict";
  period_detection?: PeriodDetection;
  conflict?: PeriodConflictInfo;
  available_periods?: string[];
  error_detail?: string | null;
}

export interface FileUploadResponseExtended {
  status: string;
  file_count: number;
  files: UploadedFileItemExtended[];
}

export async function getAllPeriods(): Promise<{ total: number; periods: PeriodSummary[]; years: number[] }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/periods`);
    if (!response.ok) return { total: 0, periods: [], years: [] };
    const data = await response.json();
    return {
      total: data.total || 0,
      periods: data.periods || [],
      years: data.years || [],
    };
  } catch {
    return { total: 0, periods: [], years: [] };
  }
}

export interface PeriodCompareItem {
  name: string;
  period_a_value: number;
  period_b_value: number;
  absolute_change: number;
  growth_percent: number | null;
  period_a_rate?: number;
  period_b_rate?: number;
  rate_change_percentage_points?: number;
}

export interface PeriodCompareResponse {
  period_a: string;
  period_b: string;
  dimension: string;
  metric: string;
  columns: string[];
  data: PeriodCompareItem[];
}

export async function getPeriodsCompare(
  periodA: string,
  periodB: string,
  metric: string,
  dimension: string,
  limit: number = 20
): Promise<PeriodCompareResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/periods/compare?period_a=${encodeURIComponent(
      periodA
    )}&period_b=${encodeURIComponent(periodB)}&metric=${encodeURIComponent(
      metric
    )}&dimension=${encodeURIComponent(dimension)}&limit=${limit}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch period comparison");
  }
  return response.json();
}

export interface PeriodTrendResponse {
  dimension: string;
  metric: string;
  periods: string[];
  data: Record<string, any>[];
}

export async function getPeriodsTrend(
  metric: string,
  dimension: string
): Promise<PeriodTrendResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/periods/trend?metric=${encodeURIComponent(
      metric
    )}&dimension=${encodeURIComponent(dimension)}`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch historical trend");
  }
  return response.json();
}

export type AnalyticsWorkspaceKind = "source" | "program";
export type AnalyticsMetric = "leads" | "admissions" | "conversion_rate";
export type AnalyticsPerformance = "all" | "increased" | "decreased";
export type AnalyticsDisplay = "exact" | "percentage" | "both";

export interface AnalyticsWorkspaceRow {
  source?: string;
  state?: string | null;
  program?: string;
  specialization?: string | null;
  period_a_leads: number;
  period_b_leads: number;
  lead_change: number;
  lead_change_percent: number | null;
  period_a_admissions: number;
  period_b_admissions: number;
  admission_change: number;
  admission_change_percent: number | null;
  period_a_conversion: number;
  period_b_conversion: number;
  conversion_change_percentage_points: number;
  period_a_value: number;
  period_b_value: number;
  absolute_change: number;
  growth_percent: number | null;
}

export interface AnalyticsWorkspaceFilters {
  state?: string;
  source?: string;
  campus?: string;
  owner?: string;
  program?: string;
  specialization?: string;
}

export interface AnalyticsWorkspaceRequest extends AnalyticsWorkspaceFilters {
  workspace: AnalyticsWorkspaceKind;
  periodA: string;
  periodB: string;
  metric: AnalyticsMetric;
  performance: AnalyticsPerformance;
  sortField: string;
  sortDirection: "asc" | "desc";
  display: AnalyticsDisplay;
  limit: number;
  offset: number;
}

export interface AnalyticsWorkspaceResponse {
  workspace: AnalyticsWorkspaceKind;
  dimension: string;
  period_a: string;
  period_b: string;
  metric: AnalyticsMetric;
  display: AnalyticsDisplay;
  performance: AnalyticsPerformance;
  filters: AnalyticsWorkspaceFilters;
  has_specialization: boolean;
  rows: AnalyticsWorkspaceRow[];
  pagination: {
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

export interface AnalyticsWorkspaceOptionsResponse {
  workspace: AnalyticsWorkspaceKind;
  period_a: string;
  period_b: string;
  options: Record<keyof AnalyticsWorkspaceFilters, string[]>;
}

export function parseApiError(errorText: string, fallback: string): string {
  if (!errorText) return fallback;
  try {
    const parsed = JSON.parse(errorText);
    if (typeof parsed === "object" && parsed !== null) {
      if (typeof parsed.detail === "string") return parsed.detail;
      if (typeof parsed.message === "string") return parsed.message;
      if (typeof parsed.detail === "object" && parsed.detail !== null && (parsed.detail as { msg?: string }).msg) {
        return (parsed.detail as { msg: string }).msg;
      }
    }
  } catch {
    // Return raw text if not JSON
  }
  return errorText;
}

export async function getAnalyticsWorkspace(
  request: AnalyticsWorkspaceRequest
): Promise<AnalyticsWorkspaceResponse> {
  const params = new URLSearchParams({
    workspace: request.workspace,
    period_a: request.periodA,
    period_b: request.periodB,
    metric: request.metric,
    performance: request.performance,
    sort_field: request.sortField,
    sort_direction: request.sortDirection,
    display: request.display,
    limit: String(request.limit),
    offset: String(request.offset),
  });

  (Object.keys(request) as (keyof AnalyticsWorkspaceRequest)[]).forEach((key) => {
    if (["state", "source", "campus", "owner", "program", "specialization"].includes(key)) {
      const value = request[key];
      if (typeof value === "string" && value) params.set(key, value);
    }
  });

  const response = await fetch(`${API_BASE_URL}/api/periods/workspace?${params.toString()}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(parseApiError(errorText, "Failed to load analytics workspace"));
  }
  return response.json();
}

export async function getAnalyticsWorkspaceOptions(
  workspace: AnalyticsWorkspaceKind,
  periodA: string,
  periodB: string
): Promise<AnalyticsWorkspaceOptionsResponse> {
  const params = new URLSearchParams({
    workspace,
    period_a: periodA,
    period_b: periodB,
  });
  const response = await fetch(`${API_BASE_URL}/api/periods/workspace/options?${params.toString()}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(parseApiError(errorText, "Failed to load analytics filter options"));
  }
  return response.json();
}

export async function confirmUpload(
  datasetId: string,
  action: "confirm" | "replace" | "new_version",
  academicLabel: string
): Promise<{ status: string; dataset_id: string; academic_label: string; action_applied: string }> {
  const response = await fetch(`${API_BASE_URL}/api/data/upload/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: datasetId,
      action,
      academic_label: academicLabel,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to confirm upload");
  }
  return response.json();
}

export async function activatePeriodVersion(
  label: string,
  datasetId: string
): Promise<{ status: string; academic_label: string; active_dataset_id: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/periods/${encodeURIComponent(label)}/activate/${datasetId}`,
    { method: "POST" }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to activate period");
  }
  return response.json();
}

export interface PeriodComparisonRow {
  name: string;
  period_a_value: number;
  period_b_value: number;
  change: number;
  pct_change: number | null;
}

export interface PeriodComparisonResult {
  period_a: { label: string; dataset_id: string | null; year: number | null };
  period_b: { label: string; dataset_id: string | null; year: number | null };
  dimension: string;
  metric: string;
  data: PeriodComparisonRow[];
}

export async function comparePeriods(
  periodA: string,
  periodB: string,
  metric: string = "admissions",
  dimension: string = "program_name",
  limit: number = 20
): Promise<PeriodComparisonResult> {
  const params = new URLSearchParams({
    period_a: periodA,
    period_b: periodB,
    metric,
    dimension,
    limit: String(limit),
  });
  const response = await fetch(`${API_BASE_URL}/api/periods/compare?${params}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to compare periods");
  }
  return response.json();
}

// ============================================================
// Admin / Data Management API
// ============================================================

export interface AdminConfigResponse {
  allow_data_reset: boolean;
  app_env: string;
}

export interface AdminDatasetItem {
  id: string;
  dataset_name: string;
  original_filename: string;
  row_count: number;
  column_count: number;
  status: string;
  is_active: boolean;
  is_period_active: boolean;
  academic_label: string | null;
  upload_version: number | null;
  file_checksum: string | null;
  quality_score: number | null;
  created_at: string;
  category: "production" | "test_benchmark";
}

export interface AdminDatasetsResponse {
  total_datasets: number;
  active_dataset: ActiveDatasetInfo | null;
  datasets: AdminDatasetItem[];
}

export interface BenchmarkSummaryResponse {
  candidate_count: number;
  total_rows: number;
  active_dataset_id: string | null;
  candidates: {
    id: string;
    dataset_name: string;
    original_filename: string;
    row_count: number;
    status: string;
    created_at: string;
  }[];
}

export async function getAdminConfig(): Promise<AdminConfigResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/admin/config`);
    if (!response.ok) return { allow_data_reset: false, app_env: "production" };
    return response.json();
  } catch {
    return { allow_data_reset: false, app_env: "production" };
  }
}

export async function listAllDatasets(): Promise<AdminDatasetsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/admin/datasets`);
  if (!response.ok) {
    throw new Error("Failed to load datasets");
  }
  return response.json();
}

export async function activateDataset(
  datasetId: string
): Promise<{ status: string; dataset_id: string; dataset_name: string; academic_label: string | null }> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/datasets/${datasetId}/activate`,
    { method: "POST" }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to activate dataset");
  }
  return response.json();
}

export async function deleteDataset(
  datasetId: string
): Promise<{ status: string; dataset_name: string; was_active: boolean; deleted_staging_rows: number; deleted_analytics_rows: number }> {
  const response = await fetch(
    `${API_BASE_URL}/api/admin/datasets/${datasetId}?confirm=true`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to delete dataset");
  }
  return response.json();
}

export async function getBenchmarkSummary(): Promise<BenchmarkSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/admin/benchmark-summary`);
  if (!response.ok) {
    throw new Error("Failed to load benchmark summary");
  }
  return response.json();
}

export async function clearBenchmarkData(
  dryRun: boolean = false
): Promise<{ status: string; deleted_datasets: number; deleted_staging_rows: number; deleted_analytics_rows: number }> {
  const response = await fetch(`${API_BASE_URL}/api/admin/clear-benchmark`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: dryRun }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to clear benchmark data");
  }
  return response.json();
}

export async function resetAllData(
  confirmationPhrase: string
): Promise<{ status: string; deleted_datasets: number; deleted_staging_rows: number; deleted_analytics_rows: number }> {
  const response = await fetch(`${API_BASE_URL}/api/admin/reset-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation_phrase: confirmationPhrase }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to reset data");
  }
  return response.json();
}

export async function getHistoricalTrends(
  metric: string,
  dimension: string
): Promise<{ dimension: string; metric: string; periods: string[]; data: any[] }> {
  const response = await fetch(`${API_BASE_URL}/api/periods/trend?metric=${encodeURIComponent(metric)}&dimension=${encodeURIComponent(dimension)}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to fetch historical trends");
  }
  return response.json();
}

