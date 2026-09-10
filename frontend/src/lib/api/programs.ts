import { apiRequest } from './client';
import type {
  ProgramReportParams,
  ProgramReportResponse,
  ProgramHierarchyParams,
  ProgramHierarchyResponse,
  ProgramInsightParams,
  ProgramInsightData,
} from './types';

export async function getProgramReport(
  params: ProgramReportParams = {},
  options?: RequestInit
): Promise<ProgramReportResponse> {
  const query = new URLSearchParams();
  if (params.academic_year) query.set('academic_year', String(params.academic_year));
  if (params.campus && params.campus.toLowerCase() !== 'all campuses') query.set('campus', params.campus);
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);

  const res = await apiRequest<{ success: boolean; data: ProgramReportResponse }>(
    `/api/programs/report?${query.toString()}`,
    options
  );
  return res.data;
}

export async function getProgramHierarchyChildren(
  params: ProgramHierarchyParams,
  options?: RequestInit
): Promise<ProgramHierarchyResponse> {
  const query = new URLSearchParams();
  query.set('level', params.level);
  if (params.academic_year) query.set('academic_year', String(params.academic_year));
  if (params.campus && params.campus.toLowerCase() !== 'all campuses') query.set('campus', params.campus);
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);
  if (params.program_group) query.set('program_group', params.program_group);
  if (params.program_code) query.set('program_code', params.program_code);
  if (params.program) query.set('program', params.program);
  if (params.lead_type) query.set('lead_type', params.lead_type);
  if (params.source_category) query.set('source_category', params.source_category);
  if (params.main_source) query.set('main_source', params.main_source);
  if (params.sub_source) query.set('sub_source', params.sub_source);
  if (params.report_source) query.set('report_source', params.report_source);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);

  const res = await apiRequest<{ success: boolean; data: ProgramHierarchyResponse }>(
    `/api/programs/report/children?${query.toString()}`,
    options
  );
  return res.data;
}

export async function getProgramInsights(
  params: ProgramInsightParams,
  options?: RequestInit
): Promise<ProgramInsightData> {
  const query = new URLSearchParams();
  query.set('program_group', params.program_group);
  if (params.academic_year) query.set('academic_year', String(params.academic_year));
  if (params.campus && params.campus.toLowerCase() !== 'all campuses') query.set('campus', params.campus);
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);

  const res = await apiRequest<{ success: boolean; data: ProgramInsightData }>(
    `/api/programs/insights?${query.toString()}`,
    options
  );
  return res.data;
}
