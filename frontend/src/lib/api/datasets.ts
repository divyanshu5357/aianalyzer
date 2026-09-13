/**
 * Dataset Management, Periods, and Admin Configuration API
 */
import { API_BASE_URL, readApiError, parseApiError } from "./client";
import dashboardCache from "../cache/dashboardCache";
import type {
  ActiveDatasetInfo,
  PeriodSummary,
  AdminConfigResponse,
  AdminDatasetItem,
  AdminDatasetsResponse,
  BenchmarkSummaryResponse,
  MastersStatusResponse,
} from "./types";

export async function getActiveDataset(
  academicYear?: number,
  campus?: string
): Promise<{ active: boolean; dataset: ActiveDatasetInfo | null }> {
  const cacheKey = dashboardCache.buildKey("data:active", {
    academic_year: academicYear,
    campus: campus && campus.toLowerCase() !== "all" ? campus : undefined,
  });

  return dashboardCache.fetchWithCache(cacheKey, async () => {
    try {
      const params = new URLSearchParams();
      if (academicYear) params.set("academic_year", String(academicYear));
      if (campus && campus.toLowerCase() !== "all") params.set("campus", campus);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const response = await fetch(`${API_BASE_URL}/api/data/active${qs}`);
      if (!response.ok) {
        return { active: false, dataset: null };
      }
      return response.json();
    } catch {
      return { active: false, dataset: null };
    }
  });
}

export async function getAllPeriods(): Promise<{ total: number; periods: PeriodSummary[]; years: number[] }> {
  const cacheKey = "system:periods:all";
  return dashboardCache.fetchWithCache(cacheKey, async () => {
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
  });
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
  datasetName?: string,
  workbookType?: string
): Promise<{ status: string; academic_year: number; campus_name: string; workbook_type?: string }> {
  const response = await fetch(`${API_BASE_URL}/api/admin/datasets/${datasetId}/metadata`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      academic_year: academicYear,
      campus_name: campusName,
      dataset_name: datasetName,
      workbook_type: workbookType,
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

export async function getMastersStatus(): Promise<MastersStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/admin/masters-status`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(parseApiError(errorText, "Failed to fetch master status"));
  }
  return response.json();
}
