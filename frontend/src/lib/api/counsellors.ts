/**
 * Counsellor Operations, Activity Reports, and Export API
 */
import { API_BASE_URL } from "./client";
import type {
  CounsellorsListResponse,
  CounsellorDetailReport,
} from "./types";

export async function getCounsellorsList(filters: {
  academic_year?: string;
  campus?: string;
  search?: string;
} = {}): Promise<CounsellorsListResponse> {
  const queryParts: string[] = [];
  if (filters.academic_year && filters.academic_year !== "all") queryParts.push(`academic_year=${encodeURIComponent(filters.academic_year)}`);
  if (filters.campus && filters.campus !== "all") queryParts.push(`campus=${encodeURIComponent(filters.campus)}`);
  if (filters.search && filters.search.trim()) queryParts.push(`search=${encodeURIComponent(filters.search.trim())}`);

  const query = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
  const response = await fetch(`${API_BASE_URL}/api/counsellors${query}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to fetch counsellors list");
  }
  return response.json();
}

export async function getCounsellorReport(
  counsellorIdOrName: string,
  filters: {
    academic_year?: string;
    campus?: string;
  } = {}
): Promise<CounsellorDetailReport> {
  const queryParts: string[] = [];
  if (filters.academic_year && filters.academic_year !== "all") queryParts.push(`academic_year=${encodeURIComponent(filters.academic_year)}`);
  if (filters.campus && filters.campus !== "all") queryParts.push(`campus=${encodeURIComponent(filters.campus)}`);

  const query = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
  const encodedId = encodeURIComponent(counsellorIdOrName.trim());
  const response = await fetch(`${API_BASE_URL}/api/counsellors/${encodedId}/report${query}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to fetch counsellor report");
  }
  return response.json();
}

export async function getCounsellorSummary(filters: {
  academic_year?: string;
  campus?: string;
  counsellor?: string;
  program?: string;
} = {}): Promise<any> {
  const queryParts: string[] = [];
  if (filters.academic_year && filters.academic_year !== "all") queryParts.push(`academic_year=${encodeURIComponent(filters.academic_year)}`);
  if (filters.campus && filters.campus !== "all") queryParts.push(`campus=${encodeURIComponent(filters.campus)}`);
  if (filters.counsellor && filters.counsellor !== "all") queryParts.push(`counsellor=${encodeURIComponent(filters.counsellor)}`);
  if (filters.program && filters.program !== "all") queryParts.push(`program=${encodeURIComponent(filters.program)}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
  const response = await fetch(`${API_BASE_URL}/api/counsellor/summary${query}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to fetch counsellor summary");
  }
  return response.json();
}

export async function getLeadActivityReport(params: {
  academic_year?: string;
  campus?: string;
  counsellor?: string;
  disposition?: string;
  attempt_bucket?: string;
  followup_status?: string;
  search?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<any> {
  const queryParts: string[] = [];
  if (params.academic_year && params.academic_year !== "all") queryParts.push(`academic_year=${encodeURIComponent(params.academic_year)}`);
  if (params.campus && params.campus !== "all") queryParts.push(`campus=${encodeURIComponent(params.campus)}`);
  if (params.counsellor && params.counsellor !== "all") queryParts.push(`counsellor=${encodeURIComponent(params.counsellor)}`);
  if (params.disposition && params.disposition !== "all") queryParts.push(`disposition=${encodeURIComponent(params.disposition)}`);
  if (params.attempt_bucket && params.attempt_bucket !== "all") queryParts.push(`attempt_bucket=${encodeURIComponent(params.attempt_bucket)}`);
  if (params.followup_status && params.followup_status !== "all") queryParts.push(`followup_status=${encodeURIComponent(params.followup_status)}`);
  if (params.search && params.search.trim()) queryParts.push(`search=${encodeURIComponent(params.search.trim())}`);
  if (params.page) queryParts.push(`page=${params.page}`);
  if (params.page_size) queryParts.push(`page_size=${params.page_size}`);

  const query = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
  const response = await fetch(`${API_BASE_URL}/api/counsellor/leads${query}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to fetch lead activity");
  }
  return response.json();
}

export function getCounsellorExportUrl(format: "csv" | "xlsx", reportType: string = "counsellor_performance", filters: any = {}): string {
  const queryParts: string[] = [`export_format=${format}`, `report_type=${reportType}`];
  if (filters.academic_year && filters.academic_year !== "all") queryParts.push(`academic_year=${encodeURIComponent(filters.academic_year)}`);
  if (filters.campus && filters.campus !== "all") queryParts.push(`campus=${encodeURIComponent(filters.campus)}`);
  if (filters.counsellor && filters.counsellor !== "all") queryParts.push(`counsellor=${encodeURIComponent(filters.counsellor)}`);
  return `${API_BASE_URL}/api/counsellor/export?${queryParts.join("&")}`;
}
