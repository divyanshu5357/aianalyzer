'use client';

import React, { useCallback, useEffect, useState, useMemo } from 'react';
import ProgramReportTable from '@/components/ProgramReportTable';
import ProgramInvestigationDrawer from '@/components/ProgramInvestigationDrawer';
import { getProgramReport } from '@/lib/api/programs';
import { useApp } from '@/context/AppContext';
import dashboardCache from '@/lib/cache/dashboardCache';
import { prefetchTopProgramsChildren } from '@/lib/cache/prefetch';
import type { ProgramReportRow, ProgramReportResponse } from '@/lib/api/types';

export default function ProgramsPage() {
  const {
    theme,
    selectedCampus,
    appliedFromDate,
    appliedToDate,
    year,
    periods,
    refreshTrigger,
  } = useApp();
  const isDark = theme === 'dark';

  const activeYear = year || (periods.length > 0 ? (periods[0].period_end_year || periods[0].period_start_year || undefined) : undefined);

  // Cached UI state
  const cachedUi = dashboardCache.getProgramUiState();
  const [selectedProgram, setSelectedProgram] = useState<string | null>(() => cachedUi.selectedProgram);
  const [isInvestigationOpen, setIsInvestigationOpen] = useState<boolean>(() => cachedUi.isDrawerOpen);

  const [sortBy, setSortBy] = useState(cachedUi.sortBy || 'cy_leads');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(cachedUi.sortOrder || 'desc');

  const initialKey = dashboardCache.buildKey("programs:report", {
    academic_year: activeYear,
    campus: selectedCampus,
    from_date: appliedFromDate,
    to_date: appliedToDate,
    sort_by: sortBy,
    sort_order: sortOrder,
  });
  const cachedInitialReport = dashboardCache.peek<ProgramReportResponse>(initialKey);

  const [report, setReport] = useState<ProgramReportResponse | null>(() => cachedInitialReport);
  const [loading, setLoading] = useState<boolean>(() => !cachedInitialReport);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = useCallback((by: string, order: string) => {
    const key = dashboardCache.buildKey("programs:report", {
      academic_year: activeYear,
      campus: selectedCampus,
      from_date: appliedFromDate,
      to_date: appliedToDate,
      sort_by: by,
      sort_order: order,
    });

    const signal = dashboardCache.getScopedSignal("programs:report");
    setError(null);

    const cached = dashboardCache.swr<ProgramReportResponse>(
      key,
      () =>
        getProgramReport(
          {
            academic_year: activeYear,
            campus: selectedCampus,
            from_date: appliedFromDate || undefined,
            to_date: appliedToDate || undefined,
            sort_by: by,
            sort_order: order,
          },
          { signal }
        ),
      (freshData) => {
        setReport(freshData);
        setLoading(false);
        if (freshData?.rows) {
          prefetchTopProgramsChildren(freshData.rows, {
            academic_year: activeYear,
            campus: selectedCampus,
            from_date: appliedFromDate || undefined,
            to_date: appliedToDate || undefined,
          });
        }
      },
      { forceRefresh: refreshTrigger > 0 }
    );

    if (cached) {
      setReport(cached);
      setLoading(false);
      if (cached?.rows) {
        prefetchTopProgramsChildren(cached.rows, {
          academic_year: activeYear,
          campus: selectedCampus,
          from_date: appliedFromDate || undefined,
          to_date: appliedToDate || undefined,
        });
      }
    } else {
      setLoading(true);
    }
  }, [activeYear, selectedCampus, appliedFromDate, appliedToDate, refreshTrigger]);

  useEffect(() => {
    fetchReport(sortBy, sortOrder);
    return () => {
      dashboardCache.abortScope("programs:report");
    };
  }, [fetchReport, sortBy, sortOrder, refreshTrigger]);

  function handleSortChange(col: string, order: 'asc' | 'desc') {
    setSortBy(col);
    setSortOrder(order);
  }

  // Health summary metrics across unique programs
  const { attentionCount, watchCount, healthyCount, firstAttentionProgram } = useMemo(() => {
    let att = 0;
    let wt = 0;
    let hl = 0;
    let firstAtt: string | null = null;
    const seen = new Set<string>();

    report?.rows?.forEach((r) => {
      const name = r.program_group || r.program;
      if (name && !seen.has(name)) {
        seen.add(name);
        if (r.health?.status === 'attention') {
          att++;
          if (!firstAtt) firstAtt = name;
        } else if (r.health?.status === 'watch') {
          wt++;
        } else {
          hl++;
        }
      }
    });

    return { attentionCount: att, watchCount: wt, healthyCount: hl, firstAttentionProgram: firstAtt };
  }, [report?.rows]);

  const scopeFilters = {
    academic_year: activeYear,
    campus: selectedCampus,
    from_date: appliedFromDate || undefined,
    to_date: appliedToDate || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  };

  return (
    <div className={`min-h-screen flex flex-col transition-colors duration-200 ${isDark ? 'bg-[#0B0F19] text-slate-100' : 'bg-slate-50 text-slate-900'}`}>

      {/* Page Header */}
      <div className={`border-b px-3 sm:px-6 pt-3 sm:pt-5 pb-3 sm:pb-4 shrink-0 ${isDark ? 'border-[#1E293B]' : 'border-slate-200'}`}>
        <div className="flex items-start justify-between gap-3 sm:gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className={`w-6 h-6 sm:w-7 sm:h-7 rounded-lg flex items-center justify-center ${isDark ? 'bg-indigo-600/20' : 'bg-indigo-50'}`}>
                <svg className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.57 50.57 0 00-2.658-.813A59.905 59.905 0 0112 3.493a59.902 59.902 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.697 50.697 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" />
                </svg>
              </div>
              <h1 className={`text-sm sm:text-base font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>Program Performance</h1>
            </div>
            <p className={`text-xs hidden sm:block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              5-level drill-down: Program Group → Program → Lead Type → Main Source → Report Source. All metrics server-side.
            </p>
          </div>

          {/* Header Action Area: Single AI Insights Entry Button + KPI Pills */}
          <div className="flex items-center gap-3 flex-wrap">
            {report && (
              <button
                type="button"
                onClick={() => {
                  if (!selectedProgram && firstAttentionProgram) {
                    setSelectedProgram(firstAttentionProgram);
                  }
                  setIsInvestigationOpen(true);
                }}
                className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all shadow-md hover:scale-[1.02] cursor-pointer border ${
                  isDark
                    ? 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 text-white border-indigo-400/30 shadow-indigo-950/40 hover:shadow-indigo-900/60'
                    : 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white border-indigo-500/30 shadow-indigo-200 hover:shadow-indigo-300'
                }`}
                title="Open Performance Insight & Root Cause Analysis"
              >
                <span className="text-sm leading-none">✨</span>
                <span>Insight</span>
                {attentionCount > 0 || watchCount > 0 ? (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-extrabold bg-rose-500 text-white shadow-xs">
                    {attentionCount + watchCount} Issues
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500 text-white">
                    Healthy
                  </span>
                )}
              </button>
            )}

            {/* Stats pills */}
            {report && (
              <div className="flex gap-1.5 sm:gap-2 flex-wrap">
                {[
                  { label: 'Programs', value: String(report.count), color: isDark ? 'text-indigo-300' : 'text-indigo-600' },
                  { label: 'CY Leads', value: report.total.cy_leads.toLocaleString(), color: isDark ? 'text-white' : 'text-slate-900' },
                  { label: 'CY Adm', value: report.total.cy_adm.toLocaleString(), color: isDark ? 'text-emerald-300' : 'text-emerald-600' },
                  { label: 'Net Adm', value: report.total.net_admissions.toLocaleString(), color: isDark ? 'text-sky-300' : 'text-sky-600' },
                ].map(({ label, value, color }) => (
                  <div key={label} className={`flex items-center gap-1 sm:gap-2 border rounded-lg px-2 sm:px-3 py-1 sm:py-1.5 ${isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200 shadow-sm'}`}>
                    <span className={`text-[9px] sm:text-[10px] uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{label}</span>
                    <span className={`text-xs sm:text-sm font-bold ${color}`}>{value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Legend - hidden on mobile */}
      <div className={`hidden sm:flex px-6 py-2 gap-4 border-b shrink-0 flex-wrap ${isDark ? 'border-white/5' : 'border-slate-100'}`}>
        {[
          { color: isDark ? 'bg-slate-300' : 'bg-slate-500', label: 'L1 Program Group' },
          { color: 'bg-indigo-400', label: 'L2 Program' },
          { color: 'bg-sky-400', label: 'L3 Lead Type' },
          { color: 'bg-emerald-400', label: 'L4 Main Source' },
          { color: 'bg-amber-400', label: 'L5 Report Source' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${color}`} />
            <span className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{label}</span>
          </div>
        ))}
        <div className={`ml-auto text-[10px] hidden md:flex items-center gap-2 ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>
          <span>▸ expand · ▾ collapse</span>
          <span className="text-indigo-400 font-medium">· click any row for Insight</span>
          <span>· click column ↑↓ to sort</span>
        </div>
      </div>
      {/* Mobile hint */}
      <div className={`sm:hidden px-3 py-1.5 border-b shrink-0 ${isDark ? 'border-white/5' : 'border-slate-100'}`}>
        <span className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-slate-400'}`}>Tap any program for Insight · <span className="text-emerald-400">▲ up</span> <span className="text-red-400">▼ down</span></span>
      </div>

      {/* Table */}
      <div className="flex-1 px-1.5 sm:px-4 py-2 sm:py-3 min-h-0">
        {error ? (
          <div className="flex flex-col items-center gap-3 py-16">
            <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <p className="text-sm text-red-400">{error}</p>
            <button
              onClick={() => fetchReport(sortBy, sortOrder)}
              className={`text-xs border rounded-lg px-3 py-1.5 transition-colors ${isDark ? 'text-gray-400 hover:text-white border-white/10' : 'text-slate-500 hover:text-slate-900 border-slate-200'}`}
            >
              Retry
            </button>
          </div>
        ) : (
          <ProgramReportTable
            topRows={report?.rows ?? []}
            totalRow={report?.total as ProgramReportRow}
            filters={scopeFilters}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSortChange={handleSortChange}
            selectedProgram={selectedProgram}
            onSelectProgram={(prog) => {
              setSelectedProgram(prog);
              setIsInvestigationOpen(true);
            }}
            loading={loading && !report}
            isDark={isDark}
          />
        )}
      </div>

      {/* AI Performance Investigation Drawer */}
      <ProgramInvestigationDrawer
        isOpen={isInvestigationOpen}
        onClose={() => setIsInvestigationOpen(false)}
        initialProgram={selectedProgram || firstAttentionProgram || report?.rows?.[0]?.program_group || 'CSE'}
        availablePrograms={report?.rows ?? []}
        scopeParams={{
          academic_year: activeYear,
          campus: selectedCampus,
          from_date: appliedFromDate || undefined,
          to_date: appliedToDate || undefined,
        }}
        isDark={isDark}
        onSelectProgram={(prog) => setSelectedProgram(prog)}
      />
    </div>
  );
}
