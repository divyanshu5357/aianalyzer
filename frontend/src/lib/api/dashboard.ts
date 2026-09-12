/**
 * Executive Dashboard and Entity Analytics API
 */
import { API_BASE_URL, readApiError, buildDashboardQuery } from "./client";
import dashboardCache from "../cache/dashboardCache";
import type {
  DashboardFilters,
  DashboardFilterOptionsResponse,
  OverviewResponse,
  InsightItem,
  EntityDetailResponse,
  MonthlyTrendItem,
  PerformanceRankingsResponse,
  GenderAdmissionsResponse,
  StateAdmissionsResponse,
  InternationalAdmissionsResponse,
  ResolvedScopeResponse,
  TopPerformersResponse,
  ExploreResponse,
  HierarchyClusterResponse,
  HierarchyDrilldownResponse,
  CompareResponse,
} from "./types";

export async function getDashboardScope(campus?: string, years?: number[]): Promise<ResolvedScopeResponse> {
  const params = new URLSearchParams();
  if (campus && campus !== "all") params.set("campus", campus);
  if (years && years.length > 0) params.set("years", years.join(","));
  const response = await fetch(`${API_BASE_URL}/api/dashboard/scope?${params.toString()}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch resolved dataset scope");
  }
  return response.json();
}

export async function getDashboardFilterOptions(session?: string, campus?: string, years?: number[], options?: RequestInit): Promise<DashboardFilterOptionsResponse> {
  const cacheKey = dashboardCache.buildKey("dashboard:options", {
    session: session && session !== "all" ? session : undefined,
    campus: campus && campus !== "all" ? campus : undefined,
    years: years?.length ? years.join(",") : undefined,
  });

  return dashboardCache.fetchWithCache(cacheKey, async () => {
    const params = new URLSearchParams();
    if (session && session !== "all") params.set("academic_session", session);
    if (campus && campus !== "all") params.set("campus", campus);
    if (years && years.length > 0) params.set("years", years.join(","));
    const response = await fetch(`${API_BASE_URL}/api/dashboard/options?${params.toString()}`, options);
    if (!response.ok) {
      throw new Error(await readApiError(response, "Failed to fetch filter options"));
    }
    return response.json();
  });
}

export async function getDashboardOverview(filters?: DashboardFilters, options?: RequestInit): Promise<OverviewResponse> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/overview${query}`, options);
  if (!response.ok) {
    throw new Error(await readApiError(response, "Failed to fetch dashboard overview"));
  }
  return response.json();
}

export async function getDashboardInsights(filters?: DashboardFilters, options?: RequestInit): Promise<InsightItem[]> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/insights${query}`, options);
  if (!response.ok) {
    throw new Error(await readApiError(response, "Failed to fetch dashboard insights"));
  }
  return response.json();
}

export async function getDashboardTopPerformers(metric: string, filters?: DashboardFilters, options?: RequestInit): Promise<TopPerformersResponse> {
  const query = buildDashboardQuery(filters);
  const prefix = query ? `${query}&` : "?";
  const response = await fetch(`${API_BASE_URL}/api/dashboard/top-performers${prefix}metric=${metric}`, options);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch top performers");
  }
  return response.json();
}

export async function getDashboardMonthlyTrend(
  arg1?: string | DashboardFilters,
  arg2?: string | DashboardFilters | RequestInit,
  arg3?: RequestInit
): Promise<MonthlyTrendItem[]> {
  let metric: string | undefined;
  let filters: DashboardFilters | undefined;
  let options: RequestInit | undefined;

  if (typeof arg1 === "string") {
    metric = arg1;
    if (arg2 && typeof arg2 === "object") filters = arg2 as DashboardFilters;
    options = arg3;
  } else {
    filters = arg1 as DashboardFilters | undefined;
    if (typeof arg2 === "string") metric = arg2;
    else if (arg2 && typeof arg2 === "object") options = arg2 as RequestInit;
    if (arg3) options = arg3;
  }

  const query = buildDashboardQuery(filters);
  const prefix = query ? `${query}&` : "?";
  const url = metric
    ? `${API_BASE_URL}/api/dashboard/monthly-trend${prefix}metric=${encodeURIComponent(metric)}`
    : `${API_BASE_URL}/api/dashboard/monthly-trend${query}`;
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await readApiError(response, "Failed to fetch monthly trend data"));
  }
  return response.json();
}

export async function getDashboardPerformanceRankings(
  dimension: string,
  filters?: DashboardFilters,
  options?: RequestInit
): Promise<PerformanceRankingsResponse> {
  const params = new URLSearchParams();
  params.set("dimension", dimension);
  if (filters) {
    if (filters.academic_session && filters.academic_session !== "all") params.set("academic_session", filters.academic_session);
    if (filters.campus && filters.campus !== "all") params.set("campus", filters.campus);
    if (filters.state && filters.state !== "all") params.set("state", filters.state);
    if (filters.source && filters.source !== "all") params.set("source", filters.source);
    if (filters.program && filters.program !== "all") params.set("program", filters.program);
    if (filters.years && filters.years.length > 0) params.set("years", filters.years.join(","));
    if (filters.from_date && filters.from_date.trim()) params.set("from_date", filters.from_date.trim());
    if (filters.to_date && filters.to_date.trim()) params.set("to_date", filters.to_date.trim());
  }
  const response = await fetch(
    `${API_BASE_URL}/api/dashboard/performance-rankings?${params.toString()}`,
    options
  );
  if (!response.ok) {
    throw new Error(await readApiError(response, "Failed to fetch performance rankings"));
  }
  return response.json();
}

export async function getEntityDetail(dimension: string, value: string, filters?: DashboardFilters, options?: RequestInit): Promise<EntityDetailResponse> {
  const query = buildDashboardQuery(filters);
  const prefix = query ? `${query}&` : "?";
  const url = `${API_BASE_URL}/api/dashboard/entity${prefix}dimension=${encodeURIComponent(dimension)}&value=${encodeURIComponent(value)}`;
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorText = await readApiError(response, "Failed to fetch entity details");
    throw new Error(errorText);
  }
  return response.json();
}

export async function getDashboardExplore(
  dimension: string,
  metric: string,
  limit: number = 10,
  filters?: DashboardFilters
): Promise<ExploreResponse> {
  let query = `?dimension=${encodeURIComponent(dimension)}&metric=${encodeURIComponent(metric)}&limit=${limit}`;
  const fQuery = buildDashboardQuery(filters);
  if (fQuery) {
    query += `&${fQuery.substring(1)}`;
  }
  const response = await fetch(`${API_BASE_URL}/api/dashboard/explore${query}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch exploration data");
  }
  return response.json();
}

export async function getHierarchyClusters(
  dimension: string = "source",
  filters?: DashboardFilters
): Promise<HierarchyClusterResponse> {
  let query = `?dimension=${encodeURIComponent(dimension)}`;
  const fQuery = buildDashboardQuery(filters);
  if (fQuery) {
    query += `&${fQuery.substring(1)}`;
  }
  const response = await fetch(`${API_BASE_URL}/api/dashboard/hierarchy/clusters${query}`);
  if (!response.ok) {
    throw new Error("Failed to fetch hierarchy clusters");
  }
  return response.json();
}

export async function getHierarchyDrilldown(
  dimension: string = "source",
  clusterName: string = "IN HOUSE",
  filters?: DashboardFilters
): Promise<HierarchyDrilldownResponse> {
  let query = `?dimension=${encodeURIComponent(dimension)}&cluster_name=${encodeURIComponent(clusterName)}`;
  const fQuery = buildDashboardQuery(filters);
  if (fQuery) {
    query += `&${fQuery.substring(1)}`;
  }
  const response = await fetch(`${API_BASE_URL}/api/dashboard/hierarchy/drilldown${query}`);
  if (!response.ok) {
    throw new Error("Failed to fetch hierarchy drilldown");
  }
  return response.json();
}

export async function getDashboardCompare(
  dimension: string,
  valueA: string,
  valueB: string,
  metric: string,
  filters?: DashboardFilters,
  valueC?: string,
  entities?: string[]
): Promise<CompareResponse> {
  let query = `?dimension=${encodeURIComponent(dimension)}&metric=${encodeURIComponent(metric)}`;
  if (entities && entities.length > 0) {
    query += `&entities=${encodeURIComponent(entities.join(","))}`;
  } else {
    query += `&value_a=${encodeURIComponent(valueA)}&value_b=${encodeURIComponent(valueB)}`;
    if (valueC) {
      query += `&value_c=${encodeURIComponent(valueC)}`;
    }
  }
  const fQuery = buildDashboardQuery(filters);
  if (fQuery) {
    query += `&${fQuery.substring(1)}`;
  }
  const response = await fetch(`${API_BASE_URL}/api/dashboard/compare${query}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to execute comparison");
  }
  return response.json();
}

export async function getDimensionValues(dimension: string, filters?: DashboardFilters): Promise<string[]> {
  let query = `?dimension=${encodeURIComponent(dimension)}`;
  const fQuery = buildDashboardQuery(filters);
  if (fQuery) {
    query += `&${fQuery.substring(1)}`;
  }
  const response = await fetch(`${API_BASE_URL}/api/dashboard/dimension-values${query}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch dimension values");
  }
  return response.json();
}

export async function getAdmissionsByGender(
  filters?: DashboardFilters,
  options?: RequestInit
): Promise<GenderAdmissionsResponse> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/admissions-by-gender${query}`, options);
  if (!response.ok) {
    const err = await readApiError(response, "Failed to fetch admissions by gender");
    throw new Error(err);
  }
  return response.json();
}

export async function getAdmissionsByState(
  filters?: DashboardFilters,
  options?: RequestInit
): Promise<StateAdmissionsResponse> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/admissions-by-state${query}`, options);
  if (!response.ok) {
    const err = await readApiError(response, "Failed to fetch admissions by state");
    throw new Error(err);
  }
  return response.json();
}

export async function getInternationalAdmissions(
  filters?: DashboardFilters,
  options?: RequestInit
): Promise<InternationalAdmissionsResponse> {
  const query = buildDashboardQuery(filters);
  const response = await fetch(`${API_BASE_URL}/api/dashboard/international-admissions${query}`, options);
  if (!response.ok) {
    const err = await readApiError(response, "Failed to fetch international admissions");
    throw new Error(err);
  }
  return response.json();
}
