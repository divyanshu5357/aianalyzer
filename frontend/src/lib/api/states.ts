/**
 * State-Wise Analysis API client module — Phase 13
 * 100% server-side aggregated PostgreSQL queries with strict lazy hierarchical loading.
 * Zero raw CRM records are sent to client.
 */

import { apiRequest } from './client';
import type {
  StateReportParams,
  StateReportResponse,
  StateHierarchyParams,
  StateHierarchyResponse,
} from './types';

export async function getStateReport(
  params: StateReportParams = {}
): Promise<StateReportResponse> {
  const query = new URLSearchParams();
  if (params.academic_year) query.set('academic_year', String(params.academic_year));
  if (params.campus && params.campus.toLowerCase() !== 'all campuses' && params.campus.toLowerCase() !== 'all') {
    query.set('campus', params.campus);
  }
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);

  const res = await apiRequest<{ success: boolean; data: StateReportResponse }>(
    `/api/states/report?${query.toString()}`
  );
  return res.data;
}

export async function getStateHierarchyChildren(
  params: StateHierarchyParams
): Promise<StateHierarchyResponse> {
  const query = new URLSearchParams();
  query.set('level', params.level);
  query.set('state', params.state);
  if (params.source_category) query.set('source_category', params.source_category);
  if (params.academic_year) query.set('academic_year', String(params.academic_year));
  if (params.campus && params.campus.toLowerCase() !== 'all campuses' && params.campus.toLowerCase() !== 'all') {
    query.set('campus', params.campus);
  }
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);

  const res = await apiRequest<{ success: boolean; data: StateHierarchyResponse }>(
    `/api/states/report/children?${query.toString()}`
  );
  return res.data;
}
