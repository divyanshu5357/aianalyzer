'use client';

import React, { useCallback, useEffect, useState, useMemo } from 'react';
import StateReportTable from '@/components/StateReportTable';
import StateInvestigationDrawer from '@/components/StateInvestigationDrawer';
import { getStateReport } from '@/lib/api/states';
import { useApp } from '@/context/AppContext';
import dashboardCache from '@/lib/cache/dashboardCache';
import { prefetchTopStatesChildren } from '@/lib/cache/prefetch';
import type { StateReportRow, StateReportResponse } from '@/lib/api/types';

export default function StateAnalysisPage() {
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
  const cachedUi = dashboardCache.getStateUiState();
  const [selectedState, setSelectedState] = useState<string | null>(() => cachedUi.selectedState);
  const [isInvestigationOpen, setIsInvestigationOpen] = useState<boolean>(() => cachedUi.isDrawerOpen);

  const [sortBy, setSortBy] = useState(cachedUi.sortBy || 'cy_leads');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(cachedUi.sortOrder || 'desc');

  const initialKey = dashboardCache.buildKey("states:report", {
    academic_year: activeYear,
    campus: selectedCampus,
    from_date: appliedFromDate,
    to_date: appliedToDate,
    sort_by: sortBy,
    sort_order: sortOrder,
  });
  const cachedInitialReport = dashboardCache.peekMemory<StateReportResponse>(initialKey);

  const [report, setReport] = useState<StateReportResponse | null>(() => cachedInitialReport);
  const [loading, setLoading] = useState<boolean>(() => !cachedInitialReport);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = useCallback(
    (by: string, order: string) => {
      const key = dashboardCache.buildKey("states:report", {
        academic_year: activeYear,
        campus: selectedCampus,
        from_date: appliedFromDate,
        to_date: appliedToDate,
        sort_by: by,
        sort_order: order,
      });

      setError(null);

      const cached = dashboardCache.swr<StateReportResponse>(
        key,
        () =>
          getStateReport(
            {
              academic_year: activeYear,
              campus: selectedCampus,
              from_date: appliedFromDate || undefined,
              to_date: appliedToDate || undefined,
              sort_by: by,
              sort_order: order,
            }
          ),
        (freshData) => {
          setReport(freshData);
          setLoading(false);
          if (freshData?.rows) {
            prefetchTopStatesChildren(freshData.rows, {
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
          prefetchTopStatesChildren(cached.rows, {
            academic_year: activeYear,
            campus: selectedCampus,
            from_date: appliedFromDate || undefined,
            to_date: appliedToDate || undefined,
          });
        }
      } else {
        setLoading(true);
      }
    },
    [activeYear, selectedCampus, appliedFromDate, appliedToDate, refreshTrigger]
  );

  // Trigger fetch when scope or sort changes
  useEffect(() => {
    fetchReport(sortBy, sortOrder);
  }, [fetchReport, sortBy, sortOrder, refreshTrigger]);

  function handleSortChange(col: string, order: 'asc' | 'desc') {
    setSortBy(col);
    setSortOrder(order);
  }

  // Health summary metrics across unique states
  const { attentionCount, watchCount, healthyCount, firstAttentionState } = useMemo(() => {
    let att = 0;
    let wt = 0;
    let hl = 0;
    let firstAtt: string | null = null;
    const seen = new Set<string>();

    report?.rows?.forEach((r) => {
      const name = r.state || r.name;
      if (name && !seen.has(name)) {
        seen.add(name);
        const varAdm = r.var_adm ?? (r.cy_adm - r.py_adm);
        const varAdmPct = r.var_adm_pct ?? (r.py_adm > 0 ? (varAdm / r.py_adm) * 100 : 0);
        const varConv = (r.lead_adm_pct ?? 0) - (r.py_adm > 0 && r.py_leads > 0 ? (r.py_adm / r.py_leads) * 100 : 0);

        if (varAdm <= -50 || varAdmPct <= -15 || varConv <= -1.5) {
          att++;
          if (!firstAtt) firstAtt = name;
        } else if (varAdm < 0 || varConv < 0) {
          wt++;
        } else {
          hl++;
        }
      }
    });

    return { attentionCount: att, watchCount: wt, healthyCount: hl, firstAttentionState: firstAtt };
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
    <div className={`min-h-screen flex flex-col transition-colors duration-200 ${
      isDark ? 'bg-[#0B0F19] text-slate-100' : 'bg-slate-50 text-slate-900'
    }`}>
      {/* Page Header */}
      <div className={`border-b px-3 sm:px-6 pt-3 sm:pt-5 pb-3 sm:pb-4 shrink-0 ${
        isDark ? 'border-[#1E293B]' : 'border-slate-200'
      }`}>
        <div className="flex items-start justify-between gap-3 sm:gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className={`w-6 h-6 sm:w-7 sm:h-7 rounded-lg flex items-center justify-center ${
                isDark ? 'bg-indigo-600/20' : 'bg-indigo-50'
              }`}>
                <svg
                  className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
              </div>
              <h1 className={`text-sm sm:text-base font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>
                State Wise Analysis
              </h1>
            </div>
            <p className={`text-xs hidden sm:block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              3-level drill-down: State Group → Source Category → Sub-Source. All metrics server-side.
            </p>
          </div>

          {/* Header Action Area: AI Insights Entry Button + KPI Pills */}
          <div className="flex items-center gap-3 flex-wrap">
            {report && (
              <button
                type="button"
                onClick={() => {
                  if (!selectedState && firstAttentionState) {
                    setSelectedState(firstAttentionState);
                  } else if (!selectedState && report.rows[0]) {
                    setSelectedState(report.rows[0].state || report.rows[0].name);
                  }
                  setIsInvestigationOpen(true);
                }}
                className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all shadow-md hover:scale-[1.02] cursor-pointer border ${
                  isDark
                    ? 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 text-white border-indigo-400/30 shadow-indigo-950/40 hover:shadow-indigo-900/60'
                    : 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white border-indigo-500/30 shadow-indigo-200 hover:shadow-indigo-300'
                }`}
                title="Open State Performance Insight & Course Groups Analysis"
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
                  { label: 'State Groups', value: String(report.count), color: isDark ? 'text-indigo-300' : 'text-indigo-600' },
                  { label: 'CY Leads', value: report.total.cy_leads.toLocaleString(), color: isDark ? 'text-white' : 'text-slate-900' },
                  { label: 'CY Adm', value: report.total.cy_adm.toLocaleString(), color: isDark ? 'text-emerald-300' : 'text-emerald-600' },
                  { label: 'Net Adm', value: report.total.net_admissions.toLocaleString(), color: isDark ? 'text-sky-300' : 'text-sky-600' },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    className={`flex items-center gap-1 sm:gap-2 border rounded-lg px-2 sm:px-3 py-1 sm:py-1.5 ${
                      isDark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-200 shadow-xs'
                    }`}
                  >
                    <span className={`text-[9px] sm:text-[10px] uppercase tracking-wider ${
                      isDark ? 'text-gray-400' : 'text-slate-500'
                    }`}>
                      {label}
                    </span>
                    <span className={`text-xs sm:text-sm font-bold ${color}`}>{value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Legend & Hint */}
      <div className={`px-6 py-2 flex gap-4 border-b shrink-0 flex-wrap ${
        isDark ? 'border-white/5' : 'border-slate-100'
      }`}>
        {[
          { color: isDark ? 'bg-slate-300' : 'bg-slate-500', label: 'L1 State Group' },
          { color: 'bg-emerald-500', label: 'L2 Source Category' },
          { color: 'bg-amber-400', label: 'L3 Sub-Source' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${color}`} />
            <span className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-slate-400'}`}>
              {label}
            </span>
          </div>
        ))}
        <div className={`ml-auto text-[10px] hidden md:block ${isDark ? 'text-gray-600' : 'text-slate-400'}`}>
          ▸ expand · ▾ collapse · click any row for Insight · click column ↑↓ to sort
        </div>
      </div>

      {/* Table Frame */}
      <div className="flex-1 px-4 py-3 min-h-0">
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
              className={`text-xs border rounded-lg px-3 py-1.5 transition-colors cursor-pointer ${
                isDark ? 'text-gray-400 hover:text-white border-white/10' : 'text-slate-500 hover:text-slate-900 border-slate-200'
              }`}
            >
              Retry
            </button>
          </div>
        ) : (
          <StateReportTable
            topRows={report?.rows ?? []}
            totalRow={report?.total as StateReportRow}
            filters={scopeFilters}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSortChange={handleSortChange}
            selectedState={selectedState}
            onSelectState={(st) => {
              setSelectedState(st);
              setIsInvestigationOpen(true);
            }}
            loading={loading && !report}
            isDark={isDark}
          />
        )}
      </div>

      {/* State Investigation Drawer */}
      <StateInvestigationDrawer
        isOpen={isInvestigationOpen}
        onClose={() => setIsInvestigationOpen(false)}
        initialState={selectedState || report?.rows[0]?.state || report?.rows[0]?.name || 'Punjab'}
        availableStates={report?.rows ?? []}
        scopeParams={{
          academic_year: activeYear,
          campus: selectedCampus,
          from_date: appliedFromDate || undefined,
          to_date: appliedToDate || undefined,
        }}
        isDark={isDark}
        onSelectState={(st) => setSelectedState(st)}
      />
    </div>
  );
}
