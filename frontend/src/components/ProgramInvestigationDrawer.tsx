'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { getProgramInvestigation } from '@/lib/api/programs';
import dashboardCache from '@/lib/cache/dashboardCache';
import type { ProgramInvestigationNode, InvestigationDriver, ProgramHealth, ProgramReportRow } from '@/lib/api/types';

interface ProgramInvestigationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  initialProgram: string | null;
  availablePrograms: ProgramReportRow[];
  scopeParams: {
    academic_year?: number;
    campus?: string;
    from_date?: string;
    to_date?: string;
  };
  isDark?: boolean;
  onSelectProgram?: (program: string) => void;
}

interface DrilldownStep {
  dimension: string;
  dimensionLabel: string;
  value: string;
}

export default function ProgramInvestigationDrawer({
  isOpen,
  onClose,
  initialProgram,
  availablePrograms,
  scopeParams,
  isDark = true,
  onSelectProgram,
}: ProgramInvestigationDrawerProps) {
  // Current active program
  const [selectedProgram, setSelectedProgram] = useState<string>(() => {
    return initialProgram || availablePrograms[0]?.program_group || availablePrograms[0]?.program || 'CSE';
  });

  // Filter dropdown: issues only vs all
  const [issuesOnly, setIssuesOnly] = useState<boolean>(false);

  // Drilldown hierarchy path
  const [drillPath, setDrillPath] = useState<DrilldownStep[]>([]);

  // Active investigation data
  const [nodeData, setNodeData] = useState<ProgramInvestigationNode | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [subProgTab, setSubProgTab] = useState<'dropping' | 'expanding'>('dropping');

  // Expanded [Why?] panels by driver id
  const [expandedDriverIds, setExpandedDriverIds] = useState<Set<string>>(new Set());

  // Child drivers cache for lazy [Why?] expansion
  const [childDriversMap, setChildDriversMap] = useState<Record<string, { loading: boolean; drivers: InvestigationDriver[]; error?: string }>>({});

  // Abort controller ref for in-flight requests
  const abortRef = useRef<AbortController | null>(null);

  // Sync initialProgram if prop changes
  useEffect(() => {
    if (initialProgram && initialProgram !== selectedProgram) {
      if (abortRef.current) abortRef.current.abort();
      setSelectedProgram(initialProgram);
      setDrillPath([]);
      setExpandedDriverIds(new Set());
      setChildDriversMap({});
      setError(null);
    }
  }, [initialProgram, selectedProgram]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // Persist drawer state to cache
  useEffect(() => {
    dashboardCache.setProgramUiState({
      selectedProgram,
      isDrawerOpen: isOpen,
      issuesOnly,
    });
  }, [selectedProgram, isOpen, issuesOnly]);

  // Fetch node data (with caching & abort control)
  const fetchInvestigation = useCallback(
    async (prog: string, currentDrill: DrilldownStep | null = null) => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

      const cacheKey = dashboardCache.buildKey('programs:investigation', {
        program_group: prog,
        academic_year: scopeParams.academic_year,
        campus: scopeParams.campus,
        from_date: scopeParams.from_date,
        to_date: scopeParams.to_date,
        dimension: currentDrill?.dimension,
        parent_value: currentDrill?.value,
      });

      const cached = dashboardCache.peek<ProgramInvestigationNode>(cacheKey);
      if (cached) {
        setNodeData(cached);
        setLoading(false);
      }

      try {
        const fresh = await getProgramInvestigation(
          {
            program_group: prog,
            academic_year: scopeParams.academic_year,
            campus: scopeParams.campus,
            from_date: scopeParams.from_date,
            to_date: scopeParams.to_date,
            dimension: currentDrill?.dimension,
            parent_value: currentDrill?.value,
          },
          { signal: controller.signal }
        );

        if (controller.signal.aborted) return;
        dashboardCache.set(cacheKey, fresh, 60000); // 1 min TTL
        setNodeData(fresh);
        setError(null);
      } catch (err: any) {
        if (controller.signal.aborted || err?.name === 'AbortError') {
          return;
        }
        if (!cached) {
          setError(err?.message || 'Failed to load program investigation');
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [scopeParams]
  );

  // Fetch when program or active drilldown changes
  useEffect(() => {
    if (!isOpen || !selectedProgram) return;
    const currentDrill = drillPath.length > 0 ? drillPath[drillPath.length - 1] : null;
    fetchInvestigation(selectedProgram, currentDrill);
  }, [isOpen, selectedProgram, drillPath, fetchInvestigation]);

  // Handle ESC key to close
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Programs for selector
  const programOptions = React.useMemo(() => {
    // Unique program groups or programs
    const unique = new Map<string, { label: string; health?: ProgramHealth }>();
    availablePrograms.forEach((p) => {
      const name = p.program_group || p.program;
      if (name && !unique.has(name)) {
        unique.set(name, { label: name, health: p.health });
      }
    });

    const list = Array.from(unique.entries()).map(([name, info]) => ({
      name,
      ...info,
    }));

    if (issuesOnly) {
      return list.filter((p) => p.health?.status === 'attention' || p.health?.status === 'watch');
    }
    return list;
  }, [availablePrograms, issuesOnly]);

  const issuesCount = React.useMemo(() => {
    const seen = new Set<string>();
    let count = 0;
    availablePrograms.forEach((p) => {
      const name = p.program_group || p.program;
      if (name && !seen.has(name)) {
        seen.add(name);
        if (p.health?.status === 'attention' || p.health?.status === 'watch') {
          count++;
        }
      }
    });
    return count;
  }, [availablePrograms]);

  // Handle program switch
  function handleSelectProgram(prog: string) {
    setSelectedProgram(prog);
    setDrillPath([]);
    setExpandedDriverIds(new Set());
    setChildDriversMap({});
    onSelectProgram?.(prog);
  }

  // Next / Previous program navigation
  const currentIndex = programOptions.findIndex((p) => p.name === selectedProgram);
  function handleNextProgram() {
    if (currentIndex < programOptions.length - 1) {
      handleSelectProgram(programOptions[currentIndex + 1].name);
    }
  }
  function handlePrevProgram() {
    if (currentIndex > 0) {
      handleSelectProgram(programOptions[currentIndex - 1].name);
    }
  }

  // Toggle [Why?] expand on a driver card
  async function toggleWhy(driver: InvestigationDriver) {
    const next = new Set(expandedDriverIds);
    const isExpanding = !next.has(driver.id);

    if (isExpanding) {
      next.add(driver.id);
      setExpandedDriverIds(next);

      // If child drivers not yet loaded, lazy fetch them across alternative dimension
      if (!childDriversMap[driver.id]) {
        setChildDriversMap((prev) => ({
          ...prev,
          [driver.id]: { loading: true, drivers: [] },
        }));

        try {
          // Drill into this driver's dimension to get granular evidence
          const childNode = await getProgramInvestigation({
            program_group: selectedProgram,
            academic_year: scopeParams.academic_year,
            campus: scopeParams.campus,
            from_date: scopeParams.from_date,
            to_date: scopeParams.to_date,
            dimension: driver.dimension,
            parent_value: driver.name,
          });

          const combined = [
            ...(childNode.issues || []),
            ...(childNode.positive_drivers || []),
          ];

          setChildDriversMap((prev) => ({
            ...prev,
            [driver.id]: { loading: false, drivers: combined },
          }));
        } catch (err: any) {
          setChildDriversMap((prev) => ({
            ...prev,
            [driver.id]: { loading: false, drivers: [], error: err.message },
          }));
        }
      }
    } else {
      next.delete(driver.id);
      setExpandedDriverIds(next);
    }
  }

  // Drill deeper into a driver dimension
  function handleDrillDown(driver: InvestigationDriver) {
    setDrillPath((prev) => [
      ...prev,
      {
        dimension: driver.dimension,
        dimensionLabel: driver.dimension_label,
        value: driver.name,
      },
    ]);
    setExpandedDriverIds(new Set());
    setChildDriversMap({});
  }

  // Step back in breadcrumbs
  function handleStepBack(index: number) {
    if (index === -1) {
      setDrillPath([]);
    } else {
      setDrillPath((prev) => prev.slice(0, index + 1));
    }
    setExpandedDriverIds(new Set());
    setChildDriversMap({});
  }

  if (!isOpen) return null;

  const health = nodeData?.health;
  const metrics = nodeData?.metrics;

  const dimensionIcon = (dim: string) => {
    switch (dim.toLowerCase()) {
      case 'state':
        return '📍';
      case 'lead_type':
        return '🎯';
      case 'main_source':
      case 'source':
        return '📢';
      case 'counsellor':
        return '👤';
      default:
        return '🔍';
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm transition-opacity duration-300"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="investigation-title"
    >
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div
          className={`w-screen max-w-2xl flex flex-col shadow-2xl border-l transition-transform duration-300 transform translate-x-0 ${
            isDark
              ? 'bg-[#0E131F] border-slate-800 text-slate-100'
              : 'bg-white border-slate-200 text-slate-900'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header Bar */}
          <div
            className={`px-6 py-4 border-b flex items-center justify-between gap-4 shrink-0 ${
              isDark ? 'border-slate-800 bg-[#121829]' : 'border-slate-100 bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 text-white font-bold text-base">
                ✨
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 id="investigation-title" className="text-base font-bold tracking-tight">
                    Program Performance Insight
                  </h2>
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                      isDark ? 'bg-indigo-900/60 text-indigo-300 border border-indigo-700/50' : 'bg-indigo-100 text-indigo-700'
                    }`}
                  >
                    Root Cause Analysis
                  </span>
                </div>
                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                  Cross-dimension driver analysis & business evidence
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className={`p-1.5 rounded-lg border transition-colors ${
                  isDark
                    ? 'border-slate-700/80 text-slate-400 hover:text-white hover:bg-slate-800'
                    : 'border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-100'
                }`}
                title="Close drawer (ESC)"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Program Switcher & Filter Ribbon */}
          <div
            className={`px-5 py-2.5 border-b flex items-center justify-between gap-3 shrink-0 ${
              isDark ? 'border-slate-800/80 bg-[#101626]' : 'border-slate-100 bg-slate-50/50'
            }`}
          >
            {/* Left: Program dropdown & Prev/Next navigation */}
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <label htmlFor="prog-select" className={`text-xs font-semibold shrink-0 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                Program:
              </label>
              <div className="min-w-0 flex-1 max-w-[240px] sm:max-w-[320px]">
                <select
                  id="prog-select"
                  value={selectedProgram}
                  onChange={(e) => handleSelectProgram(e.target.value)}
                  className={`w-full text-xs font-semibold rounded-lg px-2.5 py-1.5 border outline-none truncate transition-all cursor-pointer ${
                    isDark
                      ? 'bg-[#182035] border-slate-700 text-white focus:border-indigo-500'
                      : 'bg-white border-slate-300 text-slate-900 focus:border-indigo-600'
                  }`}
                >
                  {programOptions.map((p) => {
                    const badgeIcon = p.health?.status === 'attention' ? '🔴 ' : p.health?.status === 'watch' ? '🟡 ' : '🟢 ';
                    const statusLabel = p.health?.label || 'Healthy';
                    return (
                      <option key={p.name} value={p.name}>
                        {badgeIcon} {p.name} ({statusLabel})
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Prev / Next buttons */}
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  disabled={currentIndex <= 0}
                  onClick={handlePrevProgram}
                  className={`p-1.5 rounded border text-xs disabled:opacity-30 disabled:cursor-not-allowed transition-all ${
                    isDark ? 'border-slate-700 hover:bg-slate-800 text-slate-300' : 'border-slate-200 hover:bg-slate-100 text-slate-600'
                  }`}
                  title="Previous program"
                >
                  ◀
                </button>
                <button
                  type="button"
                  disabled={currentIndex >= programOptions.length - 1}
                  onClick={handleNextProgram}
                  className={`p-1.5 rounded border text-xs disabled:opacity-30 disabled:cursor-not-allowed transition-all ${
                    isDark ? 'border-slate-700 hover:bg-slate-800 text-slate-300' : 'border-slate-200 hover:bg-slate-100 text-slate-600'
                  }`}
                  title="Next program"
                >
                  ▶
                </button>
              </div>
            </div>

            {/* Right: Quick Filter: Issues Only */}
            <div className="shrink-0">
              <button
                type="button"
                onClick={() => setIssuesOnly(!issuesOnly)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer whitespace-nowrap ${
                  issuesOnly
                    ? isDark
                      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 shadow-xs'
                      : 'bg-rose-50 text-rose-700 border-rose-200 shadow-xs'
                    : isDark
                    ? 'bg-slate-800/70 text-slate-300 border-slate-700 hover:bg-slate-800'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                <span>Issues Only</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                    issuesOnly
                      ? 'bg-rose-500 text-white font-bold'
                      : isDark
                      ? 'bg-slate-700 text-slate-300'
                      : 'bg-slate-200 text-slate-700'
                  }`}
                >
                  {issuesCount}
                </span>
              </button>
            </div>
          </div>

          {/* Drilldown Breadcrumbs Bar */}
          {drillPath.length > 0 && (
            <div
              className={`px-6 py-2 border-b flex items-center gap-2 text-xs overflow-x-auto shrink-0 ${
                isDark ? 'border-slate-800 bg-[#0B0F19]' : 'border-slate-100 bg-slate-100/50'
              }`}
            >
              <span className={`text-[10px] uppercase font-bold tracking-wider ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                Path:
              </span>
              <button
                type="button"
                onClick={() => handleStepBack(-1)}
                className={`hover:underline font-semibold cursor-pointer ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}
              >
                {selectedProgram} (Overview)
              </button>

              {drillPath.map((step, idx) => (
                <React.Fragment key={idx}>
                  <span className={isDark ? 'text-slate-600' : 'text-slate-400'}>›</span>
                  <button
                    type="button"
                    onClick={() => handleStepBack(idx)}
                    className={`cursor-pointer hover:underline ${
                      idx === drillPath.length - 1
                        ? isDark
                          ? 'text-white font-bold'
                          : 'text-slate-900 font-bold'
                        : isDark
                        ? 'text-indigo-400'
                        : 'text-indigo-600'
                    }`}
                  >
                    {dimensionIcon(step.dimension)} {step.dimensionLabel}: <span className="font-semibold">{step.value}</span>
                  </button>
                </React.Fragment>
              ))}

              <button
                type="button"
                onClick={() => handleStepBack(-1)}
                className={`ml-auto text-[10px] px-2 py-0.5 rounded border transition-colors ${
                  isDark ? 'border-slate-700 text-slate-400 hover:text-white' : 'border-slate-200 text-slate-500 hover:text-slate-800'
                }`}
              >
                ↺ Reset Tree
              </button>
            </div>
          )}

          {/* Body Content (Scrollable) */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
            {loading && !nodeData && (
              <div className="py-20 flex flex-col items-center justify-center gap-3">
                <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                  Analyzing evidence across State, Lead Type, Source, and Counsellors...
                </p>
              </div>
            )}

            {error && !nodeData && (
              <div className="p-4 rounded-xl border border-red-500/20 bg-red-500/10 text-red-400 text-xs flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold mb-1">Investigation Notice</p>
                  <p>{error}</p>
                  <button
                    type="button"
                    onClick={() => fetchInvestigation(selectedProgram)}
                    className="mt-2 px-3 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded text-xs transition-colors cursor-pointer"
                  >
                    Retry
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="text-red-400 hover:text-red-200 text-sm font-bold cursor-pointer"
                  title="Dismiss notice"
                >
                  ✕
                </button>
              </div>
            )}

            {nodeData && (
              <>
                {/* 1. 5-Second Executive Digest Card */}
                <div
                  className={`p-4 rounded-2xl border transition-all ${
                    isDark
                      ? 'bg-gradient-to-br from-[#151D33] to-[#12182B] border-slate-700/80 shadow-lg'
                      : 'bg-gradient-to-br from-slate-50 to-white border-slate-200 shadow-sm'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-bold">{selectedProgram} Executive Digest</h3>
                        {health && (
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold ${
                              health.status === 'attention'
                                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                : health.status === 'watch'
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            }`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                health.status === 'attention'
                                  ? 'bg-rose-500 animate-pulse'
                                  : health.status === 'watch'
                                  ? 'bg-amber-400'
                                  : 'bg-emerald-400'
                              }`}
                            />
                            {health.label}
                          </span>
                        )}
                      </div>
                      {health?.reason && (
                        <p className={`text-xs mt-1 ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                          {health.reason}
                        </p>
                      )}
                    </div>

                    {/* Classification pill */}
                    {nodeData.primary_issue_type && (
                      <span
                        className={`text-[10px] font-mono uppercase px-2.5 py-1 rounded-md border tracking-wider font-semibold ${
                          nodeData.primary_issue_type.includes('CONVERSION') || nodeData.primary_issue_type.includes('DEFICIT')
                            ? isDark
                              ? 'bg-rose-950/60 text-rose-300 border-rose-800/80'
                              : 'bg-rose-50 text-rose-700 border-rose-200'
                            : isDark
                            ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80'
                            : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        }`}
                      >
                        {nodeData.primary_issue_type.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>

                  {/* Metrics Ribbon */}
                  {metrics && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-700/40">
                      <div className={`p-2.5 rounded-xl border ${isDark ? 'bg-black/20 border-white/5' : 'bg-white border-slate-200'}`}>
                        <span className={`text-[10px] uppercase font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Admissions</span>
                        <div className="flex items-baseline gap-1.5 mt-0.5">
                          <span className="text-base font-bold tabular-nums">{metrics.cy_admissions.toLocaleString()}</span>
                          <span className={`text-xs font-semibold tabular-nums ${metrics.var_admissions >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {metrics.var_admissions >= 0 ? '+' : ''}{metrics.var_admissions} ({metrics.var_admissions_pct >= 0 ? '+' : ''}{metrics.var_admissions_pct}%)
                          </span>
                        </div>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>vs PY {metrics.py_admissions.toLocaleString()}</span>
                      </div>

                      <div className={`p-2.5 rounded-xl border ${isDark ? 'bg-black/20 border-white/5' : 'bg-white border-slate-200'}`}>
                        <span className={`text-[10px] uppercase font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Leads</span>
                        <div className="flex items-baseline gap-1.5 mt-0.5">
                          <span className="text-base font-bold tabular-nums">{metrics.cy_leads.toLocaleString()}</span>
                          <span className={`text-xs font-semibold tabular-nums ${metrics.var_leads >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {metrics.var_leads >= 0 ? '+' : ''}{metrics.var_leads_pct}%
                          </span>
                        </div>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>vs PY {metrics.py_leads.toLocaleString()}</span>
                      </div>

                      <div className={`p-2.5 rounded-xl border ${isDark ? 'bg-black/20 border-white/5' : 'bg-white border-slate-200'}`}>
                        <span className={`text-[10px] uppercase font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Conversion</span>
                        <div className="flex items-baseline gap-1.5 mt-0.5">
                          <span className="text-base font-bold tabular-nums">{metrics.conversion_rate_cy.toFixed(1)}%</span>
                          <span className={`text-xs font-semibold tabular-nums ${metrics.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {metrics.var_conversion_rate >= 0 ? '+' : ''}{metrics.var_conversion_rate.toFixed(1)}%
                          </span>
                        </div>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY {metrics.conversion_rate_py.toFixed(1)}%</span>
                      </div>

                      <div className={`p-2.5 rounded-xl border ${isDark ? 'bg-black/20 border-white/5' : 'bg-white border-slate-200'}`}>
                        <span className={`text-[10px] uppercase font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>CUCET Reg.</span>
                        <div className="flex items-baseline gap-1.5 mt-0.5">
                          <span className="text-base font-bold tabular-nums">{metrics.cy_cucet.toLocaleString()}</span>
                          <span className={`text-xs font-semibold tabular-nums ${metrics.var_cucet >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {metrics.var_cucet >= 0 ? '+' : ''}{metrics.var_cucet_pct}%
                          </span>
                        </div>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY {metrics.py_cucet.toLocaleString()}</span>
                      </div>
                    </div>
                  )}

                  {/* Narrative Observations */}
                  <div className="mt-3 space-y-2 text-xs">
                    <div className="flex items-start gap-2">
                      <span className="text-indigo-400 font-bold shrink-0">▸ What Changed:</span>
                      <span className={isDark ? 'text-slate-200' : 'text-slate-700'}>{nodeData.what_changed} {nodeData.main_issue}</span>
                    </div>

                    {nodeData.strongest_negative_driver && (
                      <div className="flex items-start gap-2">
                        <span className="text-rose-400 font-bold shrink-0">▸ Negative Drag:</span>
                        <span className={isDark ? 'text-slate-300' : 'text-slate-600'}>{nodeData.strongest_negative_driver}</span>
                      </div>
                    )}

                    {nodeData.strongest_positive_driver && (
                      <div className="flex items-start gap-2">
                        <span className="text-emerald-400 font-bold shrink-0">▸ Growth Catalyst:</span>
                        <span className={isDark ? 'text-slate-300' : 'text-slate-600'}>{nodeData.strongest_positive_driver}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 2. Programs & Specializations Breakdown (identifying dropping programs + root causes) */}
                {nodeData.sub_programs_analysis && nodeData.sub_programs_analysis.total_count > 1 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div>
                        <h4 className="text-xs uppercase tracking-wider font-bold text-indigo-400 flex items-center gap-1.5">
                          <span>🎯</span> Programs & Specializations Breakdown ({nodeData.sub_programs_analysis.total_count})
                        </h4>
                        <p className={`text-[11px] mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                          Course-level intake drivers under {selectedProgram} ({nodeData.sub_programs_analysis.dropping_count} dropping)
                        </p>
                      </div>

                      {/* Filter Tabs */}
                      <div className={`flex items-center p-0.5 rounded-lg border text-xs ${isDark ? 'bg-[#101626] border-slate-700/80' : 'bg-slate-100 border-slate-200'}`}>
                        <button
                          type="button"
                          onClick={() => setSubProgTab('dropping')}
                          className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                            subProgTab === 'dropping'
                              ? 'bg-rose-500 text-white shadow-xs'
                              : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          <span>📉 Dropping Programs</span>
                          <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                            subProgTab === 'dropping' ? 'bg-white/25 text-white' : 'bg-rose-500/20 text-rose-400'
                          }`}>
                            {nodeData.sub_programs_analysis.dropping_count}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setSubProgTab('expanding')}
                          className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                            subProgTab === 'expanding'
                              ? 'bg-emerald-600 text-white shadow-xs'
                              : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          <span>📈 Expanding Programs</span>
                          <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                            subProgTab === 'expanding' ? 'bg-white/25 text-white' : 'bg-emerald-500/20 text-emerald-400'
                          }`}>
                            {nodeData.sub_programs_analysis.expanding_count}
                          </span>
                        </button>
                      </div>
                    </div>

                    {/* Content List */}
                    <div className="space-y-2.5">
                      {subProgTab === 'dropping' ? (
                        nodeData.sub_programs_analysis.dropping_programs.length === 0 ? (
                          <div className={`p-4 rounded-xl border text-center text-xs ${isDark ? 'border-slate-800 bg-[#121829] text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
                            ✨ No dropping programs detected under {selectedProgram}. All specializations are expanding or stable.
                          </div>
                        ) : (
                          nodeData.sub_programs_analysis.dropping_programs.map((sp) => (
                            <div
                              key={sp.program_code}
                              className={`p-3.5 rounded-xl border transition-all ${
                                isDark
                                  ? 'bg-[#141B2E] border-slate-700/80 hover:border-rose-500/40'
                                  : 'bg-white border-slate-200 hover:border-rose-300 shadow-xs'
                              }`}
                            >
                              {/* Header: Title + Root Cause Badge */}
                              <div className="flex items-start justify-between gap-3 mb-2 flex-wrap sm:flex-nowrap">
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-xs font-bold leading-snug" title={sp.program_name}>
                                      {sp.program_name}
                                    </span>
                                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0 ${
                                      isDark ? 'bg-black/30 border-white/10 text-slate-400' : 'bg-slate-100 border-slate-200 text-slate-600'
                                    }`}>
                                      {sp.program_code}
                                    </span>
                                  </div>
                                </div>

                                <div className="shrink-0 flex items-center gap-2">
                                  <span
                                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold border shadow-xs ${
                                      sp.issue_type === 'CONVERSION_COLLAPSE'
                                        ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                                        : sp.issue_type === 'LEAD_VOLUME_DEFICIT'
                                        ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                                        : 'bg-orange-500/15 text-orange-300 border-orange-500/30'
                                    }`}
                                  >
                                    {sp.issue_badge}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => handleSelectProgram(sp.program_code)}
                                    className={`text-[10px] px-2 py-0.5 rounded border transition-colors cursor-pointer flex items-center gap-1 ${
                                      isDark ? 'border-slate-700 text-indigo-400 hover:text-white hover:bg-slate-800' : 'border-slate-300 text-indigo-600 hover:bg-indigo-50'
                                    }`}
                                    title={`Investigate ${sp.program_code} across dimensions`}
                                  >
                                    <span>Investigate</span>
                                    <span>→</span>
                                  </button>
                                </div>
                              </div>

                              {/* Plain-English Root Cause Box */}
                              <div
                                className={`px-3 py-2 rounded-lg text-xs mb-2.5 flex items-start gap-2 border ${
                                  sp.issue_type === 'CONVERSION_COLLAPSE'
                                    ? isDark
                                      ? 'bg-amber-950/25 text-amber-200 border-amber-500/30'
                                      : 'bg-amber-50 text-amber-900 border-amber-200'
                                    : isDark
                                    ? 'bg-rose-950/25 text-rose-200 border-rose-500/30'
                                    : 'bg-rose-50 text-rose-900 border-rose-200'
                                }`}
                              >
                                <span className="font-bold shrink-0">
                                  {sp.issue_type === 'CONVERSION_COLLAPSE'
                                    ? '⚡ Issue:'
                                    : sp.issue_type === 'LEAD_VOLUME_DEFICIT'
                                    ? '📉 Issue:'
                                    : '⚠️ Issue:'}
                                </span>
                                <span>{sp.diagnosis}</span>
                              </div>

                              {/* Key Intake Metrics */}
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div className={`p-2 rounded-lg border ${isDark ? 'bg-black/20 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                                  <div className={`text-[10px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Admissions</div>
                                  <div className="flex items-baseline gap-1 mt-0.5 flex-wrap">
                                    <span className="font-bold tabular-nums text-rose-400">{sp.cy_admissions}</span>
                                    <span className="text-[10px] text-rose-400/80 font-semibold tabular-nums">
                                      ({sp.var_admissions >= 0 ? '+' : ''}{sp.var_admissions}, {sp.var_admissions_pct >= 0 ? '+' : ''}{sp.var_admissions_pct.toFixed(1)}%)
                                    </span>
                                  </div>
                                  <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.py_admissions}</div>
                                </div>

                                <div className={`p-2 rounded-lg border ${isDark ? 'bg-black/20 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                                  <div className={`text-[10px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Leads</div>
                                  <div className="flex items-baseline gap-1 mt-0.5 flex-wrap">
                                    <span className="font-bold tabular-nums">{sp.cy_leads.toLocaleString()}</span>
                                    <span className={`text-[10px] font-semibold tabular-nums ${sp.var_leads >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                      ({sp.var_leads_pct >= 0 ? '+' : ''}{sp.var_leads_pct.toFixed(1)}%)
                                    </span>
                                  </div>
                                  <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.py_leads.toLocaleString()}</div>
                                </div>

                                <div className={`p-2 rounded-lg border ${isDark ? 'bg-black/20 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                                  <div className={`text-[10px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Conversion</div>
                                  <div className="flex items-baseline gap-1 mt-0.5 flex-wrap">
                                    <span className="font-bold tabular-nums">{sp.conversion_rate_cy.toFixed(1)}%</span>
                                    <span className={`text-[10px] font-semibold tabular-nums ${sp.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                      ({sp.var_conversion_rate >= 0 ? '+' : ''}{sp.var_conversion_rate.toFixed(1)}% pts)
                                    </span>
                                  </div>
                                  <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.conversion_rate_py.toFixed(1)}%</div>
                                </div>
                              </div>
                            </div>
                          ))
                        )
                      ) : (
                        nodeData.sub_programs_analysis.expanding_programs.slice(0, 8).map((sp) => (
                          <div
                            key={sp.program_code}
                            className={`p-3.5 rounded-xl border transition-all ${
                              isDark
                                ? 'bg-[#141B2E] border-slate-700/80 hover:border-emerald-500/40'
                                : 'bg-white border-slate-200 hover:border-emerald-300 shadow-xs'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3 mb-2 flex-wrap sm:flex-nowrap">
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-xs font-bold leading-snug" title={sp.program_name}>
                                    {sp.program_name}
                                  </span>
                                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0 ${
                                    isDark ? 'bg-black/30 border-white/10 text-slate-400' : 'bg-slate-100 border-slate-200 text-slate-600'
                                  }`}>
                                    {sp.program_code}
                                  </span>
                                </div>
                              </div>
                              <div className="shrink-0 flex items-center gap-2">
                                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold border shadow-xs bg-emerald-500/15 text-emerald-300 border-emerald-500/30">
                                  {sp.issue_badge}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => handleSelectProgram(sp.program_code)}
                                  className={`text-[10px] px-2 py-0.5 rounded border transition-colors cursor-pointer flex items-center gap-1 ${
                                    isDark ? 'border-slate-700 text-indigo-400 hover:text-white hover:bg-slate-800' : 'border-slate-300 text-indigo-600 hover:bg-indigo-50'
                                  }`}
                                  title={`Investigate ${sp.program_code} across dimensions`}
                                >
                                  <span>Investigate</span>
                                  <span>→</span>
                                </button>
                              </div>
                            </div>

                            <p className={`text-xs mb-2.5 ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                              {sp.diagnosis}
                            </p>

                            <div className="grid grid-cols-3 gap-2 text-xs">
                              <div className={`p-2 rounded-lg border ${isDark ? 'bg-black/20 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                                <div className={`text-[10px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Admissions</div>
                                <div className="flex items-baseline gap-1 mt-0.5 flex-wrap">
                                  <span className="font-bold tabular-nums text-emerald-400">{sp.cy_admissions}</span>
                                  <span className="text-[10px] text-emerald-400 font-semibold tabular-nums">
                                    (+{sp.var_admissions})
                                  </span>
                                </div>
                                <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.py_admissions}</div>
                              </div>

                              <div className={`p-2 rounded-lg border ${isDark ? 'bg-black/20 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                                <div className={`text-[10px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Leads</div>
                                <div className="flex items-baseline gap-1 mt-0.5 flex-wrap">
                                  <span className="font-bold tabular-nums">{sp.cy_leads.toLocaleString()}</span>
                                  <span className="text-[10px] text-emerald-400 font-semibold tabular-nums">
                                    ({sp.var_leads_pct >= 0 ? '+' : ''}{sp.var_leads_pct.toFixed(1)}%)
                                  </span>
                                </div>
                                <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.py_leads.toLocaleString()}</div>
                              </div>

                              <div className={`p-2 rounded-lg border ${isDark ? 'bg-black/20 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                                <div className={`text-[10px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Conversion</div>
                                <div className="flex items-baseline gap-1 mt-0.5 flex-wrap">
                                  <span className="font-bold tabular-nums">{sp.conversion_rate_cy.toFixed(1)}%</span>
                                  <span className={`text-[10px] font-semibold tabular-nums ${sp.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                    ({sp.var_conversion_rate >= 0 ? '+' : ''}{sp.var_conversion_rate.toFixed(1)}% pts)
                                  </span>
                                </div>
                                <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.conversion_rate_py.toFixed(1)}%</div>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}

                {/* 3. Detected Issues & Root Driver Investigation Tree */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs uppercase tracking-wider font-bold text-rose-400 flex items-center gap-1.5">
                        <span>⚠️</span> Root Drivers & Detected Contractions ({nodeData.issues?.length || 0})
                      </h4>
                    </div>
                    <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                      Click [Why?] for underlying evidence & drilldown
                    </span>
                  </div>

                  {(!nodeData.issues || nodeData.issues.length === 0) ? (
                    <div className={`p-4 rounded-xl border text-center text-xs ${isDark ? 'border-slate-800 bg-[#121829] text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
                      🎉 No material performance contractions detected for this scope. Core channels are performing within healthy bounds.
                    </div>
                  ) : (
                    nodeData.issues.map((driver) => {
                      const isExpanded = expandedDriverIds.has(driver.id);
                      const childInfo = childDriversMap[driver.id];

                      return (
                        <div
                          key={driver.id}
                          className={`rounded-xl border transition-all overflow-hidden ${
                            isDark
                              ? 'bg-[#13192B] border-slate-800 hover:border-slate-700'
                              : 'bg-white border-slate-200 hover:border-slate-300 shadow-xs'
                          }`}
                        >
                          {/* Driver Card Header */}
                          <div className="p-3.5 flex items-start justify-between gap-3">
                            <div className="flex items-start gap-2.5">
                              <span className="text-lg leading-none mt-0.5">{dimensionIcon(driver.dimension)}</span>
                              <div>
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-xs font-bold">{driver.title}</span>
                                  <span
                                    className={`text-[9px] font-semibold px-1.5 py-0.2 rounded ${
                                      driver.var_adm <= -20
                                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                    }`}
                                  >
                                    {driver.badge}
                                  </span>
                                </div>
                                <p className={`text-xs mt-1 ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                                  {driver.description}
                                </p>
                              </div>
                            </div>

                            {/* [Why?] Button */}
                            <button
                              type="button"
                              onClick={() => toggleWhy(driver)}
                              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer shadow-xs border ${
                                isExpanded
                                  ? 'bg-indigo-600 text-white border-indigo-500'
                                  : isDark
                                  ? 'bg-indigo-950/80 text-indigo-300 border-indigo-800 hover:bg-indigo-900'
                                  : 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100'
                              }`}
                            >
                              <span>{isExpanded ? '▾ Close' : '▸ Why?'}</span>
                            </button>
                          </div>

                          {/* Expandable Why? Panel with Lazy Child Drivers & Evidence */}
                          {isExpanded && (
                            <div
                              className={`px-4 py-3 border-t text-xs space-y-3 ${
                                isDark ? 'border-slate-800 bg-[#0E1322]' : 'border-slate-100 bg-slate-50'
                              }`}
                            >
                              <div className="flex items-center justify-between flex-wrap gap-2">
                                <span className="font-semibold text-indigo-400">
                                  Underlying Channel Evidence for {driver.name}:
                                </span>
                                {driver.can_drill_down && (
                                  <button
                                    type="button"
                                    onClick={() => handleDrillDown(driver)}
                                    className={`text-[11px] font-bold px-2.5 py-1 rounded border transition-all cursor-pointer ${
                                      isDark
                                        ? 'bg-indigo-900/60 border-indigo-700 text-indigo-200 hover:bg-indigo-800'
                                        : 'bg-indigo-100 border-indigo-300 text-indigo-800 hover:bg-indigo-200'
                                    }`}
                                  >
                                    Focus & Drill into {driver.name} →
                                  </button>
                                )}
                              </div>

                              {childInfo?.loading && (
                                <div className="py-4 flex items-center justify-center gap-2 text-slate-400">
                                  <div className="w-4 h-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
                                  <span>Tracing root cause across sub-dimensions...</span>
                                </div>
                              )}

                              {childInfo?.drivers && childInfo.drivers.length > 0 && (
                                <div className="space-y-2">
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                    {childInfo.drivers.slice(0, 4).map((child) => (
                                      <div
                                        key={child.id}
                                        className={`p-2.5 rounded-lg border text-[11px] ${
                                          child.var_adm < 0
                                            ? isDark
                                              ? 'bg-rose-950/20 border-rose-900/40 text-rose-200'
                                              : 'bg-rose-50 border-rose-200 text-rose-900'
                                            : isDark
                                            ? 'bg-emerald-950/20 border-emerald-900/40 text-emerald-200'
                                            : 'bg-emerald-50 border-emerald-200 text-emerald-900'
                                        }`}
                                      >
                                        <div className="flex items-center justify-between font-semibold">
                                          <span>{dimensionIcon(child.dimension)} {child.dimension_label}: {child.name}</span>
                                          <span className="tabular-nums font-bold">
                                            {child.var_adm >= 0 ? '+' : ''}{child.var_adm} Adm
                                          </span>
                                        </div>
                                        <div className="mt-1 text-[10px] opacity-80 flex justify-between">
                                          <span>Leads: {child.cy_leads || 0} ({child.var_leads_pct || 0}%)</span>
                                          <span>Conv: {child.conversion_rate || 0}%</span>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Executive guidance */}
                              <div className={`p-2.5 rounded-lg border text-[11px] ${isDark ? 'bg-indigo-950/30 border-indigo-800/40 text-indigo-200' : 'bg-indigo-50 border-indigo-100 text-indigo-900'}`}>
                                <span className="font-bold">💡 Recommended Action: </span>
                                {driver.dimension === 'state'
                                  ? `Audit regional counsellor coverage and school outreach in ${driver.name} to address the ${driver.var_adm} admission deficit.`
                                  : driver.dimension === 'lead_type'
                                  ? `Review lead quality and response SLA for ${driver.name} channels.`
                                  : driver.dimension === 'counsellor'
                                  ? `Review pipeline follow-up velocity and pending CUCET registrations with counsellor ${driver.name}.`
                                  : `Re-evaluate spend allocation and lead qualification criteria for source channel '${driver.name}'.`}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>

                {/* 3. Positive Expansion Drivers */}
                {nodeData.positive_drivers && nodeData.positive_drivers.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs uppercase tracking-wider font-bold text-emerald-400 flex items-center gap-1.5">
                        <span>🚀</span> Top Growth & Expansion Drivers ({nodeData.positive_drivers.length})
                      </h4>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {nodeData.positive_drivers.map((driver) => (
                        <div
                          key={driver.id}
                          className={`p-3 rounded-xl border text-xs ${
                            isDark ? 'bg-[#13192B] border-slate-800' : 'bg-white border-slate-200 shadow-xs'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold flex items-center gap-1.5">
                              <span>{dimensionIcon(driver.dimension)}</span>
                              {driver.title}
                            </span>
                            <span className="text-xs font-bold text-emerald-400 tabular-nums">
                              +{driver.var_adm} Adm
                            </span>
                          </div>
                          <p className={`text-[11px] mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                            {driver.description}
                          </p>
                          {driver.can_drill_down && (
                            <button
                              type="button"
                              onClick={() => handleDrillDown(driver)}
                              className="mt-2 text-[10px] text-indigo-400 hover:underline font-semibold cursor-pointer"
                            >
                              Explore {driver.name} Channel →
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Drawer Footer */}
          <div
            className={`px-6 py-3 border-t flex items-center justify-between text-xs shrink-0 ${
              isDark ? 'border-slate-800 bg-[#121829] text-slate-400' : 'border-slate-100 bg-slate-50 text-slate-500'
            }`}
          >
            <span>ESC to close</span>
            <button
              type="button"
              onClick={onClose}
              className={`px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                isDark
                  ? 'border-slate-700 bg-slate-800 hover:bg-slate-700 text-white'
                  : 'border-slate-200 bg-white hover:bg-slate-100 text-slate-800'
              }`}
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
