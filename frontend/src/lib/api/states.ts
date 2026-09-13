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
  params: StateReportParams = {},
  options?: RequestInit
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
    `/api/states/report?${query.toString()}`,
    options
  );
  return res.data;
}

export async function getStateHierarchyChildren(
  params: StateHierarchyParams,
  options?: RequestInit
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
    `/api/states/report/children?${query.toString()}`,
    options
  );
  return res.data;
}

// ── Course Group Normalization ───────────────────────────────────────────────

export function normalizeCourseGroup(code?: string, name?: string): string {
  const c = (code || '').toUpperCase().trim();
  const n = (name || '').toUpperCase().trim();

  if (c.startsWith('CS') || n.includes('COMPUTER SCIENCE') || n.includes('CSE')) return 'CSE';
  if (c.startsWith('BB') || n.includes('BUSINESS ADMIN') || n.includes('BBA')) return 'BBA';
  if (c.startsWith('MB') || n.includes('MASTER OF BUSINESS') || n.includes('MBA')) return 'MBA';
  if (c.startsWith('BS') || n.includes('BACHELOR OF SCIENCE') || n.includes('B.SC')) return 'B.Sc.';
  if (c.startsWith('LW') || n.includes('LAW') || n.includes('LLB')) return 'LAW';
  if (c.startsWith('BC') || n.includes('COMMERCE') || n.includes('B.COM')) return 'B.COM';
  if (c.startsWith('CA') || n.includes('COMPUTER APPLICATIONS') || n.includes('BCA')) return 'BCA';
  if (c.startsWith('PT') || n.includes('PHYSIOTHERAPY') || n.includes('BPT') || n.includes('MPT')) return 'Physiotherapy';
  if (c.startsWith('PH') || n.includes('PHARM') || n.includes('PHARMA')) return 'Pharmacy';
  if (c.startsWith('BT') || c.startsWith('CE') || c.startsWith('ME') || c.startsWith('EE') || c.startsWith('EC') || n.includes('BACHELOR OF ENGINEERING') || n.includes('B.E.')) return 'B.E.';
  if (c.startsWith('BD') || n.includes('DESIGN') || n.includes('B.DES')) return 'B.Des';
  if (c.startsWith('MC') || n.includes('MASTER OF COMPUTER') || n.includes('MCA')) return 'MCA';
  if (c.startsWith('AR') || n.includes('ARCHITECTURE')) return 'Architecture';
  if (c.startsWith('BA') || n.includes('BACHELOR OF ARTS')) return 'BA';
  if (c.startsWith('MS') || n.includes('MASTER OF SCIENCE') || n.includes('M.SC')) return 'M.Sc.';
  if (c.startsWith('HM') || n.includes('HOTEL')) return 'Hotel Management';
  if (c.startsWith('NR') || n.includes('NURSING')) return 'Nursing';
  if (c.startsWith('AG') || n.includes('AGRICULTURE')) return 'Agriculture';
  if (c.startsWith('OP') || n.includes('OPTO') || n.includes('OPTOMETRY')) return 'Optometry';
  if (c.startsWith('MT') || n.includes('MASTER OF ENGINEERING') || n.includes('M.TECH')) return 'M.Tech / ME';
  if (c.startsWith('SP') || n.includes('SPORT') || n.includes('PHYSICAL ED')) return 'Sports Education';
  if (c.startsWith('FA') || n.includes('FINE ART')) return 'Fine Arts';

  return 'Other Programs';
}

// ── State Performance Investigation & Course Group Analysis ─────────────────

export async function getStateInvestigation(
  params: import('./types').StateInvestigationParams,
  options?: RequestInit
): Promise<import('./types').StateInvestigationNode> {
  const query = new URLSearchParams();
  query.set('program_group', 'ALL');
  query.set('dimension', 'state');
  query.set('parent_value', params.state);
  if (params.academic_year) query.set('academic_year', String(params.academic_year));
  if (params.campus && params.campus.toLowerCase() !== 'all campuses' && params.campus.toLowerCase() !== 'all') {
    query.set('campus', params.campus);
  }
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);

  // 1. Fetch server-side program investigation tree for this state
  const invRes = await apiRequest<any>(`/api/programs/investigation?${query.toString()}`, options);

  // 2. Fetch authentic state report row for CUCET registrations reconciliation
  let stateCucet = invRes.metrics?.cy_cucet || 0;
  let pyStateCucet = invRes.metrics?.py_cucet || 0;
  let varCucet = invRes.metrics?.var_cucet || 0;
  let varCucetPct = invRes.metrics?.var_cucet_pct || 0;

  try {
    const report = await getStateReport({
      academic_year: params.academic_year,
      campus: params.campus,
      from_date: params.from_date,
      to_date: params.to_date,
    }, options);

    if (report && report.rows) {
      const match = report.rows.find((r) => {
        const target = params.state.trim().toLowerCase();
        return (
          (r.name && r.name.trim().toLowerCase() === target) ||
          (r.state && r.state.trim().toLowerCase() === target) ||
          (r.state_key && r.state_key.trim().toLowerCase() === target) ||
          (r.canonical_name && r.canonical_name.trim().toLowerCase() === target) ||
          (r.state_code && r.state_code.trim().toLowerCase() === target) ||
          (r.constituent_states && r.constituent_states.some((c) => c.trim().toLowerCase() === target))
        );
      });
      if (match) {
        stateCucet = match.cy_cucet ?? stateCucet;
        pyStateCucet = match.py_cucet ?? pyStateCucet;
        varCucet = match.var_cucet ?? (pyStateCucet !== null ? stateCucet - pyStateCucet : varCucet);
        varCucetPct = match.var_cucet_pct ?? varCucetPct;
      }
    }
  } catch (e) {
    console.warn('Notice: could not reconcile CUCET with state report:', e);
  }

  // 3. Process sub-programs and roll up into Course Groups
  const dropping = invRes.sub_programs_analysis?.dropping_programs || [];
  const expanding = invRes.sub_programs_analysis?.expanding_programs || [];
  const allProgs = [...dropping, ...expanding];

  const groupMap = new Map<string, any>();

  allProgs.forEach((p) => {
    const grp = normalizeCourseGroup(p.program_code, p.program_name);
    if (!groupMap.has(grp)) {
      groupMap.set(grp, {
        course_group: grp,
        cy_admissions: 0,
        py_admissions: 0,
        cy_leads: 0,
        py_leads: 0,
        programs_count: 0,
        dropping_count: 0,
        expanding_count: 0,
      });
    }
    const item = groupMap.get(grp);
    item.cy_admissions += Number(p.cy_admissions || 0);
    item.py_admissions += Number(p.py_admissions || 0);
    item.cy_leads += Number(p.cy_leads || 0);
    item.py_leads += Number(p.py_leads || 0);
    item.programs_count += 1;
    if (p.var_admissions < 0) item.dropping_count += 1;
    else if (p.var_admissions > 0) item.expanding_count += 1;
  });

  const totAdm = Number(invRes.metrics?.cy_admissions || 1);
  const totLeads = Number(invRes.metrics?.cy_leads || 1);

  const courseGroups: import('./types').StateCourseGroupItem[] = Array.from(groupMap.values()).map((g) => {
    const var_adm = g.cy_admissions - g.py_admissions;
    const var_admissions_pct = g.py_admissions > 0 ? Number(((var_adm / g.py_admissions) * 100).toFixed(1)) : (g.cy_admissions > 0 ? 100.0 : 0.0);
    const var_leads = g.cy_leads - g.py_leads;
    const var_leads_pct = g.py_leads > 0 ? Number(((var_leads / g.py_leads) * 100).toFixed(1)) : (g.cy_leads > 0 ? 100.0 : 0.0);

    const cShare = totLeads > 0 ? g.cy_leads / totLeads : 0;
    const cy_cucet = Math.round(stateCucet * cShare);
    const py_cucet = Math.round(pyStateCucet * (g.py_leads > 0 && invRes.metrics?.py_leads > 0 ? g.py_leads / invRes.metrics.py_leads : cShare));
    const var_cucet_val = cy_cucet - py_cucet;
    const var_cucet_pct_val = py_cucet > 0 ? Number(((var_cucet_val / py_cucet) * 100).toFixed(1)) : 0.0;

    const lead_to_cucet_pct = g.cy_leads > 0 ? Number(((cy_cucet / g.cy_leads) * 100).toFixed(1)) : 0.0;
    const cucet_to_adm_pct = cy_cucet > 0 ? Number(((g.cy_admissions / cy_cucet) * 100).toFixed(1)) : 0.0;
    const conv_cy = g.cy_leads > 0 ? Number(((g.cy_admissions / g.cy_leads) * 100).toFixed(2)) : 0.0;
    const conv_py = g.py_leads > 0 ? Number(((g.py_admissions / g.py_leads) * 100).toFixed(2)) : 0.0;
    const var_conv = Number((conv_cy - conv_py).toFixed(2));
    const share_pct = totAdm > 0 ? Number(((g.cy_admissions / totAdm) * 100).toFixed(1)) : 0.0;

    const status = var_adm > 0 ? 'positive' : var_adm < 0 ? 'negative' : 'neutral';

    return {
      course_group: g.course_group,
      cy_admissions: g.cy_admissions,
      py_admissions: g.py_admissions,
      var_admissions: var_adm,
      var_admissions_pct,
      cy_leads: g.cy_leads,
      py_leads: g.py_leads,
      var_leads,
      var_leads_pct,
      cy_cucet,
      py_cucet,
      var_cucet: var_cucet_val,
      var_cucet_pct: var_cucet_pct_val,
      lead_to_cucet_pct,
      cucet_to_adm_pct,
      conversion_rate_cy: conv_cy,
      conversion_rate_py: conv_py,
      var_conversion_rate: var_conv,
      share_pct,
      status,
      programs_count: g.programs_count,
      dropping_count: g.dropping_count,
      expanding_count: g.expanding_count,
    };
  });

  courseGroups.sort((a, b) => b.cy_admissions - a.cy_admissions);

  // 4. Compute Highlights
  const byAdm = [...courseGroups].sort((a, b) => b.cy_admissions - a.cy_admissions);
  const byLeads = [...courseGroups].sort((a, b) => b.cy_leads - a.cy_leads);
  const byCucet = [...courseGroups].sort((a, b) => b.cy_cucet - a.cy_cucet);
  const activeForConv = courseGroups.filter((g) => g.cy_leads >= 50);
  const byConv = [...(activeForConv.length > 0 ? activeForConv : courseGroups)].sort((a, b) => b.conversion_rate_cy - a.conversion_rate_cy);

  const declining = courseGroups.filter((g) => g.var_admissions < 0).sort((a, b) => a.var_admissions - b.var_admissions);
  const lowestAdm = declining.length > 0 ? declining[0] : (byAdm[byAdm.length - 1] || null);

  const highestAdm = byAdm[0] || null;
  const highestLeads = byLeads[0] || null;
  const lowestLeads = byLeads.length > 1 ? byLeads[byLeads.length - 1] : null;
  const highestCucet = byCucet[0] || null;
  const lowestCucet = byCucet.length > 1 ? byCucet[byCucet.length - 1] : null;
  const highestConv = byConv[0] || null;
  const lowestConv = byConv.length > 1 ? byConv[byConv.length - 1] : null;

  const course_highlights: import('./types').StateCourseGroupHighlights = {
    highest_admissions: highestAdm ? { name: highestAdm.course_group, value: highestAdm.cy_admissions, change: highestAdm.var_admissions, pct: highestAdm.var_admissions_pct } : null,
    lowest_admissions: lowestAdm ? { name: lowestAdm.course_group, value: lowestAdm.cy_admissions, change: lowestAdm.var_admissions, pct: lowestAdm.var_admissions_pct } : null,
    highest_leads: highestLeads ? { name: highestLeads.course_group, value: highestLeads.cy_leads, change: highestLeads.var_leads, pct: highestLeads.var_leads_pct } : null,
    lowest_leads: lowestLeads ? { name: lowestLeads.course_group, value: lowestLeads.cy_leads, change: lowestLeads.var_leads, pct: lowestLeads.var_leads_pct } : null,
    highest_cucet: highestCucet ? { name: highestCucet.course_group, value: highestCucet.cy_cucet, change: highestCucet.var_cucet, pct: highestCucet.var_cucet_pct } : null,
    lowest_cucet: lowestCucet ? { name: lowestCucet.course_group, value: lowestCucet.cy_cucet, change: lowestCucet.var_cucet, pct: lowestCucet.var_cucet_pct } : null,
    highest_conversion: highestConv ? { name: highestConv.course_group, value: highestConv.cy_leads, rate: highestConv.conversion_rate_cy, admissions: highestConv.cy_admissions } : null,
    lowest_conversion: lowestConv ? { name: lowestConv.course_group, value: lowestConv.cy_leads, rate: lowestConv.conversion_rate_cy, admissions: lowestConv.cy_admissions } : null,
  };

  // 5. Build summary digest
  const admVar = invRes.metrics?.var_admissions ?? ((invRes.metrics?.cy_admissions || 0) - (invRes.metrics?.py_admissions || 0));
  const admVarPct = invRes.metrics?.var_admissions_pct ?? 0;
  const convRate = invRes.metrics?.conversion_rate_cy ?? 0;

  let summary_digest = `${params.state}: Total admissions ${admVar >= 0 ? `increased by +${admVar.toLocaleString()} (+${admVarPct}%)` : `declined by ${admVar.toLocaleString()} (${admVarPct}%)`} with an overall ${convRate}% conversion rate.`;
  if (highestAdm) {
    summary_digest += ` ${highestAdm.course_group} leads intake with ${highestAdm.cy_admissions.toLocaleString()} admissions (${highestAdm.share_pct}% share).`;
  }
  if (lowestAdm && lowestAdm.var_admissions < 0) {
    summary_digest += ` Key contraction observed in ${lowestAdm.course_group} (${lowestAdm.var_admissions.toLocaleString()} admissions YoY).`;
  }

  return {
    success: true,
    state: params.state,
    academic_year: invRes.academic_year || params.academic_year || 2026,
    campus: invRes.campus || params.campus,
    health: invRes.health,
    summary_digest,
    metrics: {
      ...invRes.metrics,
      cy_cucet: stateCucet,
      py_cucet: pyStateCucet,
      var_cucet: varCucet,
      var_cucet_pct: varCucetPct,
    },
    issues: invRes.issues || [],
    positive_drivers: invRes.positive_drivers || [],
    course_groups: courseGroups,
    course_highlights,
    sub_programs_analysis: invRes.sub_programs_analysis || {
      total_count: allProgs.length,
      dropping_count: dropping.length,
      expanding_count: expanding.length,
      dropping_programs: dropping,
      expanding_programs: expanding,
    },
    next_dimensions: invRes.next_dimensions || ['lead_type', 'main_source', 'counsellor'],
  };
}

