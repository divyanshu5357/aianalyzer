/**
 * Admissions and Leads Target Tracking API
 */
import { API_BASE_URL } from "./client";
import type {
  TargetPerformanceResponse,
} from "./types";

export async function getTargetPerformance(
  academicYear?: number,
  campus?: string,
  dimensionType?: string,
  month?: number
): Promise<TargetPerformanceResponse> {
  const queryParts: string[] = [];
  if (academicYear) queryParts.push(`academic_year=${academicYear}`);
  if (campus && campus.toLowerCase() !== "all") queryParts.push(`campus=${encodeURIComponent(campus)}`);
  if (dimensionType && dimensionType.toLowerCase() !== "all") queryParts.push(`dimension_type=${encodeURIComponent(dimensionType)}`);
  if (month !== undefined && month !== null) queryParts.push(`month=${month}`);

  const response = await fetch(`${API_BASE_URL}/api/targets/performance?${queryParts.join("&")}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to fetch target performance");
  }
  return response.json();
}
