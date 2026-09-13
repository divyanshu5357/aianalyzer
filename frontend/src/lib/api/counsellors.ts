/**
 * Counsellor Operations, Activity Reports, and Export API
 */
import { API_BASE_URL } from "./client";
import type {
  CounsellorListItem,
  CounsellorsListResponse,
  CounsellorDetailReport,
} from "./types";

/**
 * Deduplicate counsellors ensuring each staff member has a single entry identified by
 * their unique Employee ID (e.g. E14865, NL42, L100624) or normalized name.
 * Combines leads assigned, admissions, and recalculates conversion rates.
 */
export function deduplicateCounsellors(items: CounsellorListItem[]): CounsellorListItem[] {
  if (!items || items.length === 0) return [];
  const merged = new Map<string, CounsellorListItem>();

  for (const c of items) {
    // 1. Identify canonical employee ID (matching pattern like E14865, NL42, L100624)
    let empId: string | null = null;
    for (const candidate of [c.owner_id, c.employee_id, c.raw_counsellor, c.counsellor]) {
      if (!candidate) continue;
      const m = String(candidate).match(/\b([A-Za-z]{1,3}\d{2,7})\b/);
      if (m) {
        empId = m[1].toUpperCase();
        break;
      }
    }

    // 2. Determine unique key: by Employee ID if available, else normalized name
    const key = empId
      ? `EMP:${empId}`
      : `NAME:${(c.counsellor_name || c.counsellor || "").trim().toLowerCase().replace(/\s+/g, " ")}`;

    const existing = merged.get(key);
    const leads = Number(c.leads_assigned || 0);
    const admissions = Number(c.admissions || 0);

    if (!existing) {
      // Clean display name by stripping trailing employee ID if present
      let cleanName = (c.counsellor_name || c.counsellor || "").trim();
      if (empId) {
        cleanName = cleanName.replace(new RegExp(`\\s*${empId}\\s*$`, "i"), "").trim() || cleanName;
      }

      merged.set(key, {
        ...c,
        counsellor_name: cleanName,
        owner_id: empId || c.owner_id || null,
        employee_id: empId || c.employee_id || empId || undefined,
        leads_assigned: leads,
        admissions: admissions,
      });
    } else {
      existing.leads_assigned += leads;
      existing.admissions += admissions;

      // Choose preferred display name:
      // Prefer the variant that has actual leads/admissions, or Title Case over ALL-CAPS
      const currName = (c.counsellor_name || c.counsellor || "").trim();
      const prevName = existing.counsellor_name || "";
      const isPrevAllUpper = prevName.length > 2 && prevName === prevName.toUpperCase();
      const isCurrAllUpper = currName.length > 2 && currName === currName.toUpperCase();

      if (leads > existing.leads_assigned - leads || (isPrevAllUpper && !isCurrAllUpper)) {
        let cleanCurr = currName;
        if (empId) {
          cleanCurr = cleanCurr.replace(new RegExp(`\\s*${empId}\\s*$`, "i"), "").trim() || cleanCurr;
        }
        if (cleanCurr) {
          existing.counsellor_name = cleanCurr;
        }
        existing.counsellor = c.counsellor || existing.counsellor;
        existing.raw_counsellor = c.raw_counsellor || existing.raw_counsellor;
      }

      if (empId && !existing.owner_id) {
        existing.owner_id = empId;
        existing.employee_id = empId;
      }
    }
  }

  const result: CounsellorListItem[] = [];
  for (const item of merged.values()) {
    const leads = item.leads_assigned;
    const adm = item.admissions;
    const conv = leads > 0 ? Number(((adm / leads) * 100).toFixed(2)) : 0.0;
    item.conversion_rate = conv;
    item.conversion_rate_display = `${conv.toFixed(2)}%`;
    result.push(item);
  }

  return result.sort((a, b) => b.leads_assigned - a.leads_assigned);
}

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
  const rawData: CounsellorsListResponse = await response.json();
  const dedupedCounsellors = deduplicateCounsellors(rawData.counsellors || []);

  const totalLeads = dedupedCounsellors.reduce((acc, c) => acc + (c.leads_assigned || 0), 0);
  const totalAdm = dedupedCounsellors.reduce((acc, c) => acc + (c.admissions || 0), 0);
  const overallConv = totalLeads > 0 ? Number(((totalAdm / totalLeads) * 100).toFixed(2)) : 0.0;

  return {
    ...rawData,
    total_counsellors: dedupedCounsellors.length,
    summary: {
      total_leads_assigned: totalLeads,
      total_admissions: totalAdm,
      overall_conversion_rate: overallConv,
      conversion_rate_display: `${overallConv.toFixed(2)}%`,
    },
    summary_kpis: rawData.summary_kpis
      ? {
          ...rawData.summary_kpis,
          total_counsellors: dedupedCounsellors.length,
          total_leads_assigned: totalLeads,
          total_admissions: totalAdm,
          overall_conversion_rate: overallConv,
        }
      : undefined,
    counsellors: dedupedCounsellors,
  };
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
