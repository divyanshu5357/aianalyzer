/**
 * Dataset Management, Periods, and Admin Configuration API
 */
import { API_BASE_URL, readApiError, parseApiError } from "./client";
import type {
  ActiveDatasetInfo,
  PeriodSummary,
  PeriodCompareResponse,
  PeriodComparisonResult,
  AdminConfigResponse,
  AdminDatasetItem,
  AdminDatasetsResponse,
  BenchmarkSummaryResponse,
  AnalyticsWorkspaceRequest,
  AnalyticsWorkspaceResponse,
  AnalyticsWorkspaceOptionsResponse,
  AnalyticsWorkspaceKind,
} from "./types";

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

export async function enableDatasetAnalytics(
  datasetId: string,
  force: boolean = false
): Promise<{ status: string; success?: boolean; warning?: boolean; message?: string; conflict_id?: string; conflict_name?: string }> {
  const response = await fetch(`${API_BASE_URL}/api/admin/datasets/${datasetId}/enable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to enable dataset analytics");
  }
  return response.json();
}

export async function disableDatasetAnalytics(
  datasetId: string
): Promise<{ status: string; success: boolean }> {
  const response = await fetch(`${API_BASE_URL}/api/admin/datasets/${datasetId}/disable`, {
    method: "POST",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to disable dataset analytics");
  }
  return response.json();
}

export async function updateDatasetMetadata(
  datasetId: string,
  academicYear: number,
  campusName: string,
  datasetName?: string
): Promise<{ status: string; academic_year: number; campus_name: string }> {
  const response = await fetch(`${API_BASE_URL}/api/admin/datasets/${datasetId}/metadata`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      academic_year: academicYear,
      campus_name: campusName,
      dataset_name: datasetName,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to update metadata");
  }
  return response.json();
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
