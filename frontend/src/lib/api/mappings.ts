/**
 * Dataset Column Mapping and Data Quality Verification API
 */
import { API_BASE_URL } from "./client";
import type {
  MappingDecisionPayload,
  DataQualityReport,
} from "./types";

export async function executeMappingForDataset(
  datasetId: string,
  decisions?: MappingDecisionPayload[],
  sourceFile: string = "upload",
  sheetName: string = "default"
): Promise<{ status: string; dataset_id: string; normalized_rows: number; data_quality?: DataQualityReport }> {
  const response = await fetch(`${API_BASE_URL}/api/mapping/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: datasetId,
      source_file: sourceFile,
      sheet_name: sheetName,
      decisions: decisions || [],
    }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to execute dataset mapping.");
  }
  return response.json();
}

export async function getMappingPreviewQuality(datasetId: string): Promise<DataQualityReport> {
  const response = await fetch(`${API_BASE_URL}/api/mapping/preview-quality?dataset_id=${encodeURIComponent(datasetId)}`, {
    method: "POST",
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Failed to fetch data quality preview.");
  }
  return response.json();
}

export async function approveBatchMappings(mappings: any[], workbookType: string = "raw_data"): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/api/mapping/approve-batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mappings, workbook_type: workbookType }),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to approve batch mappings");
  }
  return response.json();
}
