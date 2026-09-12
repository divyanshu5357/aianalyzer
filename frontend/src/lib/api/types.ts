/**
 * Domain Types and Interfaces for API Layer
 */

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

export interface DataQualityReport {
  rows_read: number;
  rows_processed: number;
  mapping_coverage_pct: number;
  blank_program_code: number;
  unknown_program_code: number;
  invalid_prospect_id_count: number;
  duplicate_prospect_id: number;
}

export interface MappingDecisionPayload {
  id?: string;
  action: "approve" | "reject" | "edit";
  source_file?: string;
  source_sheet?: string;
  source_column: string;
  target_entity: string;
  target_column: string;
  confidence?: number;
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

export interface IngestionJobStatus {
  job_id: string;
  dataset_id: string | null;
  filename: string;
  stage: "parsing" | "staging" | "validation" | "normalization" | "finalization" | "completed" | "failed" | string;
  status: "processing" | "completed" | "failed" | string;
  progress_percent: number;
  total_rows: number;
  processed_rows: number;
  message: string;
  error: string | null;
  result_data?: FileUploadResponse;
  updated_at: string;
}

export interface UploadProgressEvent {
  filename: string;
  loaded: number;
  total: number;
}

export interface TargetItem {
  dimension_type: string;
  dimension_value: string;
  month?: number | null;
  target_leads: number;
  actual_leads?: number | null;
  leads_achievement_pct?: number | null;
  target_admissions: number;
  actual_admissions?: number | null;
  admissions_achievement_pct?: number | null;
  status: string;
}

export interface TargetPerformanceResponse {
  academic_year: number;
  campus: string;
  has_actual_data: boolean;
  max_actual_month?: number | null;
  summary: {
    target_leads: number;
    actual_leads?: number | null;
    leads_achievement_pct?: number | null;
    target_admissions: number;
    actual_admissions?: number | null;
    admissions_achievement_pct?: number | null;
  };
  items: TargetItem[];
}

export interface KPISubMetric {
  label: string;
  full_label?: string;
  cy: number;
  py?: number | null;
  gross_cy?: number;
  gross_py?: number | null;
  refunds_cy?: number;
  refunds_py?: number | null;
  change?: number | null;
  growth_pct?: number | null;
}

export interface KPIItem {
  cy: number;
  py?: number | null;
  change?: number | null;
  growth_pct?: number | null;
  sub_metric?: KPISubMetric;
}

export interface OverviewResponse {
  current_year: number;
  previous_year?: number | null;
  dataset_count?: number;
  has_cucet: boolean;
  from_date?: string | null;
  to_date?: string | null;
  py_from_date?: string | null;
  py_to_date?: string | null;
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
  years?: number[];
  from_date?: string;
  to_date?: string;
}

export interface DashboardDateRangeOption {
  min_date: string;
  max_date: string;
  default_from: string;
  default_to: string;
}

export interface DashboardFilterOptionsResponse {
  academic_sessions: string[];
  campuses: string[];
  states: string[];
  sources: string[];
  programs: string[];
  lead_types?: string[];
  date_range?: DashboardDateRangeOption;
}

export interface ResolvedScopeDatasetItem {
  id: string;
  dataset_name: string;
  campus: string;
  academic_year: number;
  row_count: number;
  is_analytics_enabled: boolean;
}

export interface ResolvedScopeResponse {
  scope: {
    campus: string;
    years: number[];
  };
  datasets: ResolvedScopeDatasetItem[];
  dataset_ids: string[];
  cy_year: number;
  py_year: number | null;
  cy_dataset_ids: string[];
  py_dataset_ids: string[];
  total_rows: number;
}

export interface MonthlyTrendItem {
  month: string;
  cy_leads: number;
  cy_cucet: number;
  cy_admission: number;
  py_leads: number;
  py_cucet: number;
  py_admission: number;
  target_leads?: number;
  target_cucet?: number;
  target_admission?: number;
  cy_conversion_rate?: number;
  py_conversion_rate?: number;
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

export interface CompareValueData {
  entity: string;
  py_leads?: number;
  cy_leads?: number;
  py_admission?: number;
  cy_admission?: number;
  py_rate?: number;
  cy_rate?: number;
  is_top_performer?: boolean;
}

export interface ClusterItem {
  cluster_name: string;
  cy_leads: number;
  cy_admission: number;
  cy_rate: number;
  py_leads: number;
  py_admission: number;
  py_rate: number;
  item_count: number;
  share_pct: number;
}

export interface HierarchyClusterResponse {
  dimension: string;
  level: number;
  clusters: ClusterItem[];
  total_clusters: number;
}

export interface DrilldownItem {
  item_name: string;
  cy_leads: number;
  cy_admission: number;
  cy_rate: number;
  py_leads: number;
  py_admission: number;
  py_rate: number;
  share_of_cluster_pct: number;
}

export interface HierarchyDrilldownResponse {
  dimension: string;
  level: number;
  cluster_name: string;
  items: DrilldownItem[];
  total_items: number;
}

export interface CompareResponse {
  dimension: string;
  metric: string;
  entities?: CompareValueData[];
  top_performer?: {
    entity: string;
    cy_rate: number;
  };
  value_a: CompareValueData;
  value_b: CompareValueData;
  value_c?: CompareValueData;
  differences: {
    cy_leads?: number;
    py_leads?: number;
    cy_admission?: number;
    py_admission?: number;
    cy_rate?: number;
    py_rate?: number;
  };
}

export interface GenderAdmissionItem {
  gender: string;
  admissions: number;
  share_pct: number;
}

export interface GenderMonthItem {
  month_key: string;
  month: string;
  month_display: string;
  total: number;
  [gender: string]: any;
}

export interface GenderAdmissionsResponse {
  status: string;
  academic_year: number;
  campus: string;
  total_admissions: number;
  gender_categories: string[];
  months: GenderMonthItem[];
  genders: GenderAdmissionItem[];
}

export interface StateAdmissionItem {
  state_code: string;
  state_name: string;
  admissions: number;
  leads: number;
  cy_admissions: number;
  cy_leads: number;
  py_admissions: number | null;
  py_leads: number | null;
  variance: number | null;
  variance_pct: number | null;
  direction: "increase" | "decline" | "no_change" | "no_comparison";
  share_pct: number;
}

export interface StateAdmissionsResponse {
  status: string;
  academic_year: number;
  comparison_year: number | null;
  has_py_data: boolean;
  campus: string;
  total_india_admissions: number;
  total_india_leads: number;
  unmapped_admissions: number;
  international_admissions: number;
  states: StateAdmissionItem[];
  top_states?: StateAdmissionItem[];
}

export interface InternationalCountryItem {
  country_code: string;
  country_name: string;
  admissions: number;
  leads: number;
  share_pct: number;
}

export interface InternationalAdmissionsResponse {
  status: string;
  academic_year: number;
  campus: string;
  total_international_admissions: number;
  total_international_leads: number;
  countries: InternationalCountryItem[];
  top_countries: InternationalCountryItem[];
  limitation_note?: string;
}

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
  is_analytics_enabled?: boolean;
  is_period_active: boolean;
  academic_label: string | null;
  academic_year?: number | null;
  campus_name?: string | null;
  workbook_type?: "RAW" | "DIMENSION" | "TARGET" | string | null;
  upload_version: number | null;
  file_checksum: string | null;
  start_month?: number | null;
  end_month?: number | null;
  months_covered?: number[] | null;
  is_completed?: boolean;
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

export interface CounsellorListItem {
  counsellor: string;
  counsellor_name: string;
  owner_id?: string | null;
  raw_counsellor: string;
  employee_id?: string;
  leads_assigned: number;
  admissions: number;
  conversion_rate: number;
  conversion_rate_display: string;
}

export interface SourceCategoryPerformance {
  category: string;
  leads_assigned: number;
  admissions: number;
  conversion_rate: number | null;
  conversion_rate_display: string;
}

export interface CounsellorDetailReport {
  status: string;
  counsellor: {
    counsellor_name: string;
    owner_id?: string | null;
    raw_counsellor: string;
  };
  summary: {
    total_leads_assigned: number;
    total_admissions: number;
    conversion_rate: number | null;
    conversion_rate_display: string;
    best_source_category: string;
  };
  categories: SourceCategoryPerformance[];
}

export interface CounsellorsListResponse {
  status: string;
  total_counsellors: number;
  summary: {
    total_leads_assigned: number;
    total_admissions: number;
    overall_conversion_rate: number;
    conversion_rate_display: string;
  };
  counsellors: CounsellorListItem[];
}


// ─── Phase 12: Program Performance Report ─────────────────────────────────────

export interface RefundPyCy {
  py: number;
  cy: number;
  diff: number;
}

export interface RefundPctPyCy {
  py_pct: number;
  cy_pct: number;
  diff_pct: number;
}

export interface ProgramReportRow {
  id: string;
  program: string;
  level: 1 | 2 | 3 | 4 | 5;
  has_children: boolean;
  py_leads: number;
  cy_leads: number;
  var_leads: number;
  var_leads_pct: number;
  py_cucet: number;
  cy_cucet: number;
  var_cucet: number;
  var_cucet_pct: number;
  lead_cucet_pct: number;
  py_adm: number;
  cy_adm: number;
  var_adm: number;
  var_adm_pct: number;
  lead_adm_pct: number;
  cucet_adm_pct: number;
  lead_trend: number[];
  net_admissions: number;
  refund_py_vs_cy: RefundPyCy;
  refund_pct_py_vs_cy: RefundPctPyCy;
  fee_paid: 'N/A';
  net_fee_paid_pct: 'N/A';
  program_group?: string;
  program_code?: string;
  program_name?: string;
  lead_type?: string;
  main_source?: string;
  report_source?: string;
  source_category?: string;
  sub_source?: string;
}

export interface ProgramReportScope {
  academic_year: number;
  py_year: number;
  campus: string;
  from_date: string | null;
  to_date: string | null;
  sort_by: string;
  sort_order: string;
}

export interface ProgramReportResponse {
  rows: ProgramReportRow[];
  total: ProgramReportRow;
  count: number;
  scope: ProgramReportScope;
}

export interface ProgramHierarchyResponse {
  rows: ProgramReportRow[];
  count: number;
  level: 'program' | 'lead_type' | 'main_source' | 'report_source' | 'branch' | 'source_category' | 'sub_source';
  parent: {
    program_group?: string;
    program_code?: string;
    program?: string;
    lead_type?: string;
    main_source?: string;
    report_source?: string;
    source_category?: string;
    sub_source?: string;
  };
}

export interface ProgramReportParams {
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
  sort_by?: string;
  sort_order?: string;
}

export interface ProgramHierarchyParams {
  level: 'program' | 'lead_type' | 'main_source' | 'report_source' | 'branch' | 'source_category' | 'sub_source';
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
  program_group?: string;
  program_code?: string;
  program?: string;
  lead_type?: string;
  main_source?: string;
  report_source?: string;
  source_category?: string;
  sub_source?: string;
  sort_by?: string;
  sort_order?: string;
}

export interface LeadTypeInsight {
  lead_type: string;
  status: 'good' | 'bad' | 'neutral';
  status_label: string;
  cy_leads: number;
  py_leads: number;
  var_leads: number;
  var_leads_pct: number;
  cy_adm: number;
  py_adm: number;
  var_adm: number;
  var_adm_pct: number;
  conversion_rate: number;
  reason: string;
}

export interface SourceInsight {
  source_name: string;
  lead_type: string;
  status: 'good' | 'bad' | 'neutral';
  cy_leads: number;
  py_leads: number;
  var_leads: number;
  var_leads_pct: number;
  cy_adm: number;
  py_adm: number;
  var_adm: number;
  var_adm_pct: number;
  conversion_rate: number;
}

export interface InsightTakeaway {
  type: 'positive' | 'negative' | 'warning' | 'neutral' | 'action';
  title: string;
  description: string;
}

export interface ProgramInsightMetrics {
  cy_admissions: number;
  py_admissions: number;
  var_admissions: number;
  var_admissions_pct: number;
  cy_leads: number;
  py_leads: number;
  var_leads: number;
  var_leads_pct: number;
  cy_cucet: number;
  py_cucet: number;
  var_cucet: number;
  var_cucet_pct: number;
  conversion_rate_cy: number;
  conversion_rate_py: number;
}

export interface ProgramInsightData {
  program_group: string;
  academic_year: number;
  campus: string;
  trajectory: 'GROWING' | 'DROPPING' | 'STABLE';
  trajectory_status: 'up' | 'down' | 'stable';
  trajectory_badge: string;
  metrics: ProgramInsightMetrics;
  lead_types: LeadTypeInsight[];
  top_growth_sources: SourceInsight[];
  top_drag_sources: SourceInsight[];
  takeaways: InsightTakeaway[];
}

export interface ProgramInsightParams {
  program_group: string;
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
}

// ─── Phase 13: State-Wise Analysis ──────────────────────────────────────────

export interface StateReportRow {
  id: string;
  name: string;
  state: string;
  level: 1 | 2 | 3;
  has_children: boolean;
  status_indicator: 'positive' | 'negative' | 'neutral';
  py_leads: number;
  cy_leads: number;
  var_leads: number;
  var_leads_pct: number;
  py_cucet: number;
  cy_cucet: number;
  var_cucet: number;
  var_cucet_pct: number;
  lead_cucet_pct: number;
  py_adm: number;
  cy_adm: number;
  var_adm: number;
  var_adm_pct: number;
  lead_adm_pct: number;
  cucet_adm_pct: number;
  lead_trend: number[];
  net_admissions: number;
  refund_py_vs_cy: RefundPyCy;
  refund_pct_py_vs_cy: RefundPctPyCy;
  fee_paid: string;
  net_fee_paid_pct: string;
  state_key?: string;
  canonical_name?: string;
  state_code?: string | null;
  source_category?: string;
  sub_source?: string;
}

export interface StateReportScope {
  academic_year: number;
  py_year: number;
  py_available: boolean;
  campus: string;
  from_date: string | null;
  to_date: string | null;
  sort_by: string;
  sort_order: string;
}

export interface StateReportResponse {
  rows: StateReportRow[];
  total: StateReportRow;
  count: number;
  scope: StateReportScope;
}

export interface StateHierarchyResponse {
  rows: StateReportRow[];
  count: number;
  level: 'source_category' | 'sub_source';
  scope: Record<string, any>;
}

export interface StateReportParams {
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
  sort_by?: string;
  sort_order?: string;
}

export interface StateHierarchyParams {
  level: 'source_category' | 'sub_source';
  state: string;
  source_category?: string;
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
  sort_by?: string;
  sort_order?: string;
}

export interface MasterInfo {
  id: string;
  dataset_name: string;
  original_filename: string;
  row_count: number;
  status: string;
  is_active: boolean;
  sheets: string[];
  sheet_count: number;
  created_at: string | null;
}

export interface MastersStatusResponse {
  has_dimension_master: boolean;
  has_target_master: boolean;
  can_upload_raw: boolean;
  dimension_master: MasterInfo | null;
  target_master: MasterInfo | null;
}
