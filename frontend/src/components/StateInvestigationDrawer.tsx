'use client';

import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { getStateInvestigation } from '@/lib/api/states';
import dashboardCache from '@/lib/cache/dashboardCache';
import type {
  StateInvestigationNode,
  InvestigationDriver,
  ProgramHealth,
  StateReportRow,
  StateCourseGroupItem,
} from '@/lib/api/types';

interface StateInvestigationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  initialState: string | null;
  availableStates: StateReportRow[];
  scopeParams: {
    academic_year?: number;
    campus?: string;
    from_date?: string;
    to_date?: string;
  };
  isDark?: boolean;
  onSelectState?: (state: string) => void;
}

interface DrilldownStep {
  dimension: string;
  dimensionLabel: string;
  value: string;
}

export default function StateInvestigationDrawer({
  isOpen,
  onClose,
  initialState,
  availableStates,
  scopeParams,
  isDark = true,
  onSelectState,
}: StateInvestigationDrawerProps) {
  // Current active state
  const [selectedState, setSelectedState] = useState<string>(() => {
    return initialState || availableStates[0]?.state || availableStates[0]?.name || 'Punjab';
  });

  // Filter dropdown: issues only vs all
  const [issuesOnly, setIssuesOnly] = useState<boolean>(false);

  // Active tab in drawer
  const [activeTab, setActiveTab] = useState<'courses' | 'dropping' | 'expanding' | 'drivers'>('courses');

  // Search filter for course groups table
  const [courseSearch, setCourseSearch] = useState<string>('');

  // Course group sort column & direction
  const [courseSortCol, setCourseSortCol] = useState<keyof StateCourseGroupItem>('cy_admissions');
  const [courseSortDir, setCourseSortDir] = useState<'asc' | 'desc'>('desc');

  // Drilldown hierarchy path
  const [drillPath, setDrillPath] = useState<DrilldownStep[]>([]);

  // Active investigation data
  const [nodeData, setNodeData] = useState<StateInvestigationNode | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Expanded [Why?] panels by driver id
  const [expandedDriverIds, setExpandedDriverIds] = useState<Set<string>>(new Set());

  // Child drivers cache for lazy [Why?] expansion
  const [childDriversMap, setChildDriversMap] = useState<Record<string, { loading: boolean; drivers: InvestigationDriver[]; error?: string }>>({});

  // Abort controller ref for in-flight requests
  const abortRef = useRef<AbortController | null>(null);

  // Sync initialState if prop changes
  useEffect(() => {
    if (initialState && initialState !== selectedState) {
      if (abortRef.current) abortRef.current.abort();
      setSelectedState(initialState);
      setDrillPath([]);
      setExpandedDriverIds(new Set());
      setChildDriversMap({});
      setError(null);
    }
  }, [initialState, selectedState]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // Persist drawer state to cache
  useEffect(() => {
    dashboardCache.setStateUiState({
      selectedState,
      isDrawerOpen: isOpen,
      issuesOnly,
    });
  }, [selectedState, isOpen, issuesOnly]);

  // Fetch state investigation data
  const fetchInvestigation = useCallback(
    async (st: string, currentDrill: DrilldownStep | null = null) => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

      const cacheKey = dashboardCache.buildKey('states:investigation', {
        state: st,
        academic_year: scopeParams.academic_year,
        campus: scopeParams.campus,
        from_date: scopeParams.from_date,
        to_date: scopeParams.to_date,
        dimension: currentDrill?.dimension,
        parent_value: currentDrill?.value,
      });

      const cached = dashboardCache.peek<StateInvestigationNode>(cacheKey);
      if (cached) {
        setNodeData(cached);
        setLoading(false);
      }

      try {
        const fresh = await getStateInvestigation(
          {
            state: st,
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
          setError(err?.message || 'Failed to load state investigation');
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [scopeParams]
  );

  // Fetch when state or active drilldown changes
  useEffect(() => {
    if (!isOpen || !selectedState) return;
    const currentDrill = drillPath.length > 0 ? drillPath[drillPath.length - 1] : null;
    fetchInvestigation(selectedState, currentDrill);
  }, [isOpen, selectedState, drillPath, fetchInvestigation]);

  // Handle ESC key to close
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Compute state health dynamically from available row data
  const getStateHealth = useCallback((row?: StateReportRow): ProgramHealth => {
    if (!row) {
      return { status: 'healthy', label: 'Healthy', reason: 'Normal operations', color: '#10b981', badge: 'Healthy' };
    }
    const varAdm = row.var_adm ?? (row.cy_adm - row.py_adm);
    const varAdmPct = row.var_adm_pct ?? (row.py_adm > 0 ? (varAdm / row.py_adm) * 100 : 0);
    const varConv = (row.lead_adm_pct ?? 0) - (row.py_adm > 0 && row.py_leads > 0 ? (row.py_adm / row.py_leads) * 100 : 0);

    if (varAdm <= -50 || varAdmPct <= -15 || varConv <= -1.5) {
      return {
        status: 'attention',
        label: 'Needs Attention',
        reason: `Admissions contracted by ${Math.abs(varAdm).toLocaleString()} (${varAdmPct.toFixed(1)}%) vs PY`,
        color: '#ef4444',
        badge: 'Critical',
      };
    }
    if (varAdm < 0 || varConv < 0) {
      return {
        status: 'watch',
        label: 'Watchlist',
        reason: `Mild contraction of ${Math.abs(varAdm).toLocaleString()} admissions vs PY`,
        color: '#f59e0b',
        badge: 'Watch',
      };
    }
    return {
      status: 'healthy',
      label: 'Healthy',
      reason: `Intake expanding +${varAdm.toLocaleString()} (+${varAdmPct.toFixed(1)}%) YoY`,
      color: '#10b981',
      badge: 'Healthy',
    };
  }, []);

  // States for selector
  const stateOptions = useMemo(() => {
    const unique = new Map<string, { label: string; health: ProgramHealth; admissions: number }>();
    availableStates.forEach((s) => {
      const name = s.state || s.name;
      if (name && !unique.has(name)) {
        unique.set(name, {
          label: name,
          health: getStateHealth(s),
          admissions: s.cy_adm,
        });
      }
    });

    const list = Array.from(unique.entries()).map(([name, info]) => ({
      name,
      ...info,
    }));

    if (issuesOnly) {
      return list.filter((s) => s.health.status === 'attention' || s.health.status === 'watch');
    }
    return list;
  }, [availableStates, issuesOnly, getStateHealth]);

  const issuesCount = useMemo(() => {
    const seen = new Set<string>();
    let count = 0;
    availableStates.forEach((s) => {
      const name = s.state || s.name;
      if (name && !seen.has(name)) {
        seen.add(name);
        const health = getStateHealth(s);
        if (health.status === 'attention' || health.status === 'watch') {
          count++;
        }
      }
    });
    return count;
  }, [availableStates, getStateHealth]);

  // Handle state switch
  function handleSelectState(st: string) {
    setSelectedState(st);
    setDrillPath([]);
    setExpandedDriverIds(new Set());
    setChildDriversMap({});
    onSelectState?.(st);
  }

  // Next / Previous state navigation
  const currentIndex = stateOptions.findIndex((s) => s.name === selectedState);
  function handleNextState() {
    if (currentIndex < stateOptions.length - 1) {
      handleSelectState(stateOptions[currentIndex + 1].name);
    }
  }
  function handlePrevState() {
    if (currentIndex > 0) {
      handleSelectState(stateOptions[currentIndex - 1].name);
    }
  }

  // Toggle [Why?] expand on a driver card
  async function toggleWhy(driver: InvestigationDriver) {
    const next = new Set(expandedDriverIds);
    const isExpanding = !next.has(driver.id);

    if (isExpanding) {
      next.add(driver.id);
      setExpandedDriverIds(next);

      if (!childDriversMap[driver.id]) {
        setChildDriversMap((prev) => ({
          ...prev,
          [driver.id]: { loading: true, drivers: [] },
        }));

        try {
          const childNode = await getStateInvestigation({
            state: selectedState,
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

  // Sort course groups
  const sortedCourseGroups = useMemo(() => {
    if (!nodeData?.course_groups) return [];
    let list = [...nodeData.course_groups];
    if (courseSearch.trim()) {
      const q = courseSearch.toLowerCase();
      list = list.filter((cg) => cg.course_group.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      const valA = a[courseSortCol];
      const valB = b[courseSortCol];
      if (typeof valA === 'string' && typeof valB === 'string') {
        return courseSortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return courseSortDir === 'asc' ? Number(valA || 0) - Number(valB || 0) : Number(valB || 0) - Number(valA || 0);
    });
    return list;
  }, [nodeData?.course_groups, courseSearch, courseSortCol, courseSortDir]);

  function handleCourseSort(col: keyof StateCourseGroupItem) {
    if (courseSortCol === col) {
      setCourseSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setCourseSortCol(col);
      setCourseSortDir('desc');
    }
  }

  if (!isOpen) return null;

  const health = nodeData?.health;
  const metrics = nodeData?.metrics;
  const highlights = nodeData?.course_highlights;

  const dimensionIcon = (dim: string) => {
    switch (dim.toLowerCase()) {
      case 'program':
      case 'program_group':
        return '🎓';
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
      aria-labelledby="state-investigation-title"
    >
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-6 sm:pl-10">
        <div
          className={`w-screen max-w-3xl flex flex-col shadow-2xl border-l transition-transform duration-300 transform translate-x-0 ${
            isDark ? 'bg-[#0E131F] border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header Bar */}
          <div
            className={`px-5 sm:px-6 py-3.5 sm:py-4 border-b flex items-center justify-between gap-4 shrink-0 ${
              isDark ? 'border-slate-800 bg-[#121829]' : 'border-slate-100 bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 text-white font-bold text-base">
                ✨
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 id="state-investigation-title" className="text-base font-bold tracking-tight">
                    State Performance Insight
                  </h2>
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                      isDark ? 'bg-indigo-900/60 text-indigo-300 border border-indigo-700/50' : 'bg-indigo-100 text-indigo-700'
                    }`}
                  >
                    Course Group & Root Cause
                  </span>
                </div>
                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                  Course groups breakdown, admissions, leads, CUCET & conversion drivers
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

          {/* State Switcher & Filter Ribbon */}
          <div
            className={`px-5 py-2.5 border-b flex items-center justify-between gap-3 shrink-0 ${
              isDark ? 'border-slate-800/80 bg-[#101626]' : 'border-slate-100 bg-slate-50/50'
            }`}
          >
            {/* Left: State dropdown & Prev/Next navigation */}
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <label htmlFor="state-select" className={`text-xs font-semibold shrink-0 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                State:
              </label>
              <div className="min-w-0 flex-1 max-w-[240px] sm:max-w-[320px]">
                <select
                  id="state-select"
                  value={selectedState}
                  onChange={(e) => handleSelectState(e.target.value)}
                  className={`w-full text-xs font-semibold rounded-lg px-2.5 py-1.5 border outline-none truncate transition-all cursor-pointer ${
                    isDark
                      ? 'bg-[#182035] border-slate-700 text-white focus:border-indigo-500'
                      : 'bg-white border-slate-300 text-slate-900 focus:border-indigo-600'
                  }`}
                >
                  {stateOptions.map((s) => {
                    const badgeIcon = s.health.status === 'attention' ? '🔴 ' : s.health.status === 'watch' ? '🟡 ' : '🟢 ';
                    return (
                      <option key={s.name} value={s.name}>
                        {badgeIcon} {s.name} ({s.admissions.toLocaleString()} Adm)
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
                  onClick={handlePrevState}
                  className={`p-1.5 rounded border text-xs disabled:opacity-30 disabled:cursor-not-allowed transition-all ${
                    isDark ? 'border-slate-700 hover:bg-slate-800 text-slate-300' : 'border-slate-200 hover:bg-slate-100 text-slate-600'
                  }`}
                  title="Previous state"
                >
                  ◀
                </button>
                <button
                  type="button"
                  disabled={currentIndex >= stateOptions.length - 1}
                  onClick={handleNextState}
                  className={`p-1.5 rounded border text-xs disabled:opacity-30 disabled:cursor-not-allowed transition-all ${
                    isDark ? 'border-slate-700 hover:bg-slate-800 text-slate-300' : 'border-slate-200 hover:bg-slate-100 text-slate-600'
                  }`}
                  title="Next state"
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
                {selectedState} (Overview)
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
                ↺ Reset
              </button>
            </div>
          )}

          {/* Body Content (Scrollable) */}
          <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-5 space-y-6">
            {loading && !nodeData && (
              <div className="py-20 flex flex-col items-center justify-center gap-3">
                <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
                <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                  Analyzing course groups, admissions, leads & CUCET across {selectedState}...
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
                    onClick={() => fetchInvestigation(selectedState)}
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
                {/* 1. Executive Digest & Health Card */}
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
                        <h3 className="text-base font-bold flex items-center gap-1.5">
                          <span>📍</span> {selectedState} Executive Digest
                        </h3>
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

                    <span
                      className={`text-[10px] font-mono uppercase px-2.5 py-1 rounded-md border tracking-wider font-semibold ${
                        (metrics?.var_admissions ?? 0) >= 0
                          ? isDark ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80' : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : isDark ? 'bg-rose-950/60 text-rose-300 border-rose-800/80' : 'bg-rose-50 text-rose-700 border-rose-200'
                      }`}
                    >
                      {(metrics?.var_admissions ?? 0) >= 0 ? 'GROWTH STATE' : 'CONTRACTION STATE'}
                    </span>
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
                          <span className="text-base font-bold tabular-nums">{metrics.conversion_rate_cy.toFixed(2)}%</span>
                          <span className={`text-xs font-semibold tabular-nums ${metrics.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {metrics.var_conversion_rate >= 0 ? '+' : ''}{metrics.var_conversion_rate.toFixed(2)}%
                          </span>
                        </div>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY {metrics.conversion_rate_py.toFixed(2)}%</span>
                      </div>

                      <div className={`p-2.5 rounded-xl border ${isDark ? 'bg-black/20 border-white/5' : 'bg-white border-slate-200'}`}>
                        <span className={`text-[10px] uppercase font-bold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>CUCET Reg.</span>
                        <div className="flex items-baseline gap-1.5 mt-0.5">
                          <span className="text-base font-bold tabular-nums">{metrics.cy_cucet.toLocaleString()}</span>
                          <span className={`text-xs font-semibold tabular-nums ${metrics.var_cucet >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {metrics.var_cucet >= 0 ? '+' : ''}{metrics.var_cucet_pct}%
                          </span>
                        </div>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>vs PY {metrics.py_cucet.toLocaleString()}</span>
                      </div>
                    </div>
                  )}

                  {/* Summary digest narrative */}
                  <div className="mt-3 text-xs flex items-start gap-2">
                    <span className="text-indigo-400 font-bold shrink-0">▸ Summary:</span>
                    <span className={isDark ? 'text-slate-200' : 'text-slate-700'}>{nodeData.summary_digest}</span>
                  </div>
                </div>

                {/* 2. Course Group Highlights Grid (Top vs Lowest across Admission, Leads, CUCET, Conversion) */}
                {highlights && (
                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs uppercase tracking-wider font-bold text-indigo-400 flex items-center gap-1.5">
                        <span>⭐</span> State Highlights: Top & Lowest Course Groups
                      </h4>
                      <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        Computed across all course intakes in {selectedState}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                      {/* Highlight 1: Admissions */}
                      <div
                        className={`p-3 rounded-xl border flex flex-col justify-between ${
                          isDark ? 'bg-[#121828] border-slate-700/80' : 'bg-white border-slate-200 shadow-xs'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] uppercase font-bold text-emerald-400 flex items-center gap-1">
                            <span>🎓</span> Admissions
                          </span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold ${isDark ? 'bg-emerald-950/50 text-emerald-300' : 'bg-emerald-50 text-emerald-700'}`}>
                            Volume
                          </span>
                        </div>
                        {highlights.highest_admissions && (
                          <div className="mb-2">
                            <div className="text-xs font-bold truncate" title={highlights.highest_admissions.name}>
                              ▲ Highest: <span className="text-emerald-400">{highlights.highest_admissions.name}</span>
                            </div>
                            <div className="text-[11px] font-mono mt-0.5">
                              {highlights.highest_admissions.value.toLocaleString()} Adm{' '}
                              <span className={highlights.highest_admissions.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                ({highlights.highest_admissions.change >= 0 ? '+' : ''}{highlights.highest_admissions.change})
                              </span>
                            </div>
                          </div>
                        )}
                        {highlights.lowest_admissions && (
                          <div className={`pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                            <div className="text-[11px] font-medium truncate text-slate-400" title={highlights.lowest_admissions.name}>
                              ▼ Lowest/Contracting: <span className="font-semibold text-rose-400">{highlights.lowest_admissions.name}</span>
                            </div>
                            <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                              {highlights.lowest_admissions.value.toLocaleString()} Adm ({highlights.lowest_admissions.change >= 0 ? '+' : ''}{highlights.lowest_admissions.change})
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Highlight 2: Leads */}
                      <div
                        className={`p-3 rounded-xl border flex flex-col justify-between ${
                          isDark ? 'bg-[#121828] border-slate-700/80' : 'bg-white border-slate-200 shadow-xs'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] uppercase font-bold text-sky-400 flex items-center gap-1">
                            <span>🎯</span> Leads
                          </span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold ${isDark ? 'bg-sky-950/50 text-sky-300' : 'bg-sky-50 text-sky-700'}`}>
                            Reach
                          </span>
                        </div>
                        {highlights.highest_leads && (
                          <div className="mb-2">
                            <div className="text-xs font-bold truncate" title={highlights.highest_leads.name}>
                              ▲ Highest: <span className="text-sky-400">{highlights.highest_leads.name}</span>
                            </div>
                            <div className="text-[11px] font-mono mt-0.5">
                              {highlights.highest_leads.value.toLocaleString()} Leads{' '}
                              <span className={highlights.highest_leads.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                ({highlights.highest_leads.pct >= 0 ? '+' : ''}{highlights.highest_leads.pct}%)
                              </span>
                            </div>
                          </div>
                        )}
                        {highlights.lowest_leads && (
                          <div className={`pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                            <div className="text-[11px] font-medium truncate text-slate-400" title={highlights.lowest_leads.name}>
                              ▼ Lowest: <span className="font-semibold text-slate-300">{highlights.lowest_leads.name}</span>
                            </div>
                            <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                              {highlights.lowest_leads.value.toLocaleString()} Leads
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Highlight 3: CUCET */}
                      <div
                        className={`p-3 rounded-xl border flex flex-col justify-between ${
                          isDark ? 'bg-[#121828] border-slate-700/80' : 'bg-white border-slate-200 shadow-xs'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] uppercase font-bold text-amber-400 flex items-center gap-1">
                            <span>📝</span> CUCET Reg.
                          </span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold ${isDark ? 'bg-amber-950/50 text-amber-300' : 'bg-amber-50 text-amber-700'}`}>
                            Exams
                          </span>
                        </div>
                        {highlights.highest_cucet && (
                          <div className="mb-2">
                            <div className="text-xs font-bold truncate" title={highlights.highest_cucet.name}>
                              ▲ Highest: <span className="text-amber-400">{highlights.highest_cucet.name}</span>
                            </div>
                            <div className="text-[11px] font-mono mt-0.5">
                              {highlights.highest_cucet.value.toLocaleString()} CUCET{' '}
                              <span className={highlights.highest_cucet.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                ({highlights.highest_cucet.pct >= 0 ? '+' : ''}{highlights.highest_cucet.pct}%)
                              </span>
                            </div>
                          </div>
                        )}
                        {highlights.lowest_cucet && (
                          <div className={`pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                            <div className="text-[11px] font-medium truncate text-slate-400" title={highlights.lowest_cucet.name}>
                              ▼ Lowest: <span className="font-semibold text-slate-300">{highlights.lowest_cucet.name}</span>
                            </div>
                            <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                              {highlights.lowest_cucet.value.toLocaleString()} CUCET
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Highlight 4: Conversion Rate */}
                      <div
                        className={`p-3 rounded-xl border flex flex-col justify-between ${
                          isDark ? 'bg-[#121828] border-slate-700/80' : 'bg-white border-slate-200 shadow-xs'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] uppercase font-bold text-purple-400 flex items-center gap-1">
                            <span>⚡</span> Conversion %
                          </span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold ${isDark ? 'bg-purple-950/50 text-purple-300' : 'bg-purple-50 text-purple-700'}`}>
                            Efficiency
                          </span>
                        </div>
                        {highlights.highest_conversion && (
                          <div className="mb-2">
                            <div className="text-xs font-bold truncate" title={highlights.highest_conversion.name}>
                              ▲ Highest: <span className="text-purple-400">{highlights.highest_conversion.name}</span>
                            </div>
                            <div className="text-[11px] font-mono mt-0.5">
                              <span className="font-bold text-emerald-400">{highlights.highest_conversion.rate.toFixed(2)}%</span>{' '}
                              ({highlights.highest_conversion.admissions.toLocaleString()} Adm)
                            </div>
                          </div>
                        )}
                        {highlights.lowest_conversion && (
                          <div className={`pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
                            <div className="text-[11px] font-medium truncate text-slate-400" title={highlights.lowest_conversion.name}>
                              ▼ Lowest: <span className="font-semibold text-rose-400">{highlights.lowest_conversion.name}</span>
                            </div>
                            <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                              <span className="font-bold text-rose-400">{highlights.lowest_conversion.rate.toFixed(2)}%</span> ({highlights.lowest_conversion.admissions.toLocaleString()} Adm)
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* 3. Tabbed Deep-Dive Section */}
                <div className="space-y-3">
                  {/* Tab Navigation Ribbon */}
                  <div className={`flex items-center gap-1 p-1 rounded-xl border text-xs overflow-x-auto ${isDark ? 'bg-[#101626] border-slate-800' : 'bg-slate-100 border-slate-200'}`}>
                    <button
                      type="button"
                      onClick={() => setActiveTab('courses')}
                      className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                        activeTab === 'courses'
                          ? isDark ? 'bg-indigo-600 text-white shadow-xs' : 'bg-white text-indigo-700 shadow-xs'
                          : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span>🏛️ Course Groups</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${activeTab === 'courses' ? 'bg-white/20' : isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-200 text-slate-700'}`}>
                        {nodeData.course_groups?.length || 0}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActiveTab('dropping')}
                      className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                        activeTab === 'dropping'
                          ? 'bg-rose-500 text-white shadow-xs'
                          : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span>📉 Dropping Programs</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${activeTab === 'dropping' ? 'bg-white/25 text-white' : 'bg-rose-500/20 text-rose-400'}`}>
                        {nodeData.sub_programs_analysis?.dropping_count || 0}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActiveTab('expanding')}
                      className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                        activeTab === 'expanding'
                          ? 'bg-emerald-600 text-white shadow-xs'
                          : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span>📈 Expanding Programs</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${activeTab === 'expanding' ? 'bg-white/25 text-white' : 'bg-emerald-500/20 text-emerald-400'}`}>
                        {nodeData.sub_programs_analysis?.expanding_count || 0}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActiveTab('drivers')}
                      className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                        activeTab === 'drivers'
                          ? 'bg-purple-600 text-white shadow-xs'
                          : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span>⚠️ Channel Drivers</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${activeTab === 'drivers' ? 'bg-white/25 text-white' : 'bg-purple-500/20 text-purple-400'}`}>
                        {nodeData.issues?.length || 0}
                      </span>
                    </button>
                  </div>

                  {/* Tab 1: Course Groups Table */}
                  {activeTab === 'courses' && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex-1 min-w-[180px] max-w-xs relative">
                          <input
                            type="text"
                            value={courseSearch}
                            onChange={(e) => setCourseSearch(e.target.value)}
                            placeholder="Filter course groups (e.g. CSE, MBA)..."
                            className={`w-full text-xs rounded-lg pl-8 pr-3 py-1.5 border outline-none transition-all ${
                              isDark ? 'bg-[#121828] border-slate-700 text-white placeholder-slate-500 focus:border-indigo-500' : 'bg-white border-slate-200 text-slate-900 placeholder-slate-400 focus:border-indigo-500'
                            }`}
                          />
                          <span className="absolute left-2.5 top-2 text-xs opacity-50">🔍</span>
                        </div>
                        <span className={`text-[11px] ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                          Showing {sortedCourseGroups.length} course groups in {selectedState}
                        </span>
                      </div>

                      <div className={`overflow-x-auto rounded-xl border ${isDark ? 'border-slate-800 bg-[#101626]' : 'border-slate-200 bg-white shadow-xs'}`}>
                        <table className="w-full text-left border-collapse text-xs">
                          <thead>
                            <tr className={`border-b text-[10px] uppercase font-bold tracking-wider ${isDark ? 'border-slate-800 bg-[#0B0F19] text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-600'}`}>
                              <th
                                onClick={() => handleCourseSort('course_group')}
                                className="px-3 py-2.5 cursor-pointer hover:text-indigo-400 select-none whitespace-nowrap"
                              >
                                Course Group {courseSortCol === 'course_group' && (courseSortDir === 'asc' ? '↑' : '↓')}
                              </th>
                              <th
                                onClick={() => handleCourseSort('cy_leads')}
                                className="px-3 py-2.5 text-right cursor-pointer hover:text-indigo-400 select-none whitespace-nowrap"
                              >
                                Leads (CY / Var) {courseSortCol === 'cy_leads' && (courseSortDir === 'asc' ? '↑' : '↓')}
                              </th>
                              <th
                                onClick={() => handleCourseSort('cy_cucet')}
                                className="px-3 py-2.5 text-right cursor-pointer hover:text-indigo-400 select-none whitespace-nowrap"
                              >
                                CUCET Reg. {courseSortCol === 'cy_cucet' && (courseSortDir === 'asc' ? '↑' : '↓')}
                              </th>
                              <th
                                onClick={() => handleCourseSort('cy_admissions')}
                                className="px-3 py-2.5 text-right cursor-pointer hover:text-indigo-400 select-none whitespace-nowrap"
                              >
                                Admissions (CY / Var) {courseSortCol === 'cy_admissions' && (courseSortDir === 'asc' ? '↑' : '↓')}
                              </th>
                              <th
                                onClick={() => handleCourseSort('conversion_rate_cy')}
                                className="px-3 py-2.5 text-right cursor-pointer hover:text-indigo-400 select-none whitespace-nowrap"
                              >
                                Conv. % {courseSortCol === 'conversion_rate_cy' && (courseSortDir === 'asc' ? '↑' : '↓')}
                              </th>
                              <th
                                onClick={() => handleCourseSort('share_pct')}
                                className="px-3 py-2.5 text-right cursor-pointer hover:text-indigo-400 select-none whitespace-nowrap"
                              >
                                State Share {courseSortCol === 'share_pct' && (courseSortDir === 'asc' ? '↑' : '↓')}
                              </th>
                              <th className="px-3 py-2.5 text-center whitespace-nowrap">Specializations</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/40">
                            {sortedCourseGroups.length === 0 ? (
                              <tr>
                                <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                                  No course groups matching &quot;{courseSearch}&quot; in {selectedState}.
                                </td>
                              </tr>
                            ) : (
                              sortedCourseGroups.map((cg) => {
                                const admUp = cg.var_admissions >= 0;
                                const leadsUp = cg.var_leads >= 0;

                                return (
                                  <tr
                                    key={cg.course_group}
                                    className={`transition-colors ${
                                      isDark ? 'hover:bg-indigo-950/20' : 'hover:bg-slate-50'
                                    }`}
                                  >
                                    <td className="px-3 py-2.5 font-bold flex items-center gap-2">
                                      <span
                                        className={`w-2 h-2 rounded-full ${
                                          cg.status === 'positive'
                                            ? 'bg-emerald-400'
                                            : cg.status === 'negative'
                                            ? 'bg-rose-500'
                                            : 'bg-slate-400'
                                        }`}
                                      />
                                      <span className={isDark ? 'text-white' : 'text-slate-900'}>{cg.course_group}</span>
                                    </td>
                                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                                      <div>{cg.cy_leads.toLocaleString()}</div>
                                      <div className={`text-[10px] ${leadsUp ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {leadsUp ? '+' : ''}{cg.var_leads_pct.toFixed(1)}%
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                                      <div>{cg.cy_cucet.toLocaleString()}</div>
                                      <div className="text-[10px] text-amber-400">
                                        {cg.lead_to_cucet_pct.toFixed(1)}% reg
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                                      <div className="font-bold text-emerald-400">{cg.cy_admissions.toLocaleString()}</div>
                                      <div className={`text-[10px] font-semibold ${admUp ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {admUp ? '+' : ''}{cg.var_admissions} ({admUp ? '+' : ''}{cg.var_admissions_pct.toFixed(1)}%)
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                                      <div className="font-bold">{cg.conversion_rate_cy.toFixed(2)}%</div>
                                      <div className={`text-[10px] ${cg.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {cg.var_conversion_rate >= 0 ? '+' : ''}{cg.var_conversion_rate.toFixed(2)}% pts
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                                      <div className="font-bold text-indigo-400">{cg.share_pct.toFixed(1)}%</div>
                                    </td>
                                    <td className="px-3 py-2.5 text-center">
                                      <span
                                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                          cg.dropping_count > 0
                                            ? isDark ? 'bg-rose-500/20 text-rose-300' : 'bg-rose-50 text-rose-700'
                                            : isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-emerald-50 text-emerald-700'
                                        }`}
                                      >
                                        <span>{cg.programs_count} progs</span>
                                        {cg.dropping_count > 0 && <span className="text-rose-400">({cg.dropping_count} 📉)</span>}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Tab 2: Dropping Programs */}
                  {activeTab === 'dropping' && (
                    <div className="space-y-2.5">
                      {nodeData.sub_programs_analysis?.dropping_programs.length === 0 ? (
                        <div className={`p-6 rounded-xl border text-center text-xs ${isDark ? 'border-slate-800 bg-[#121829] text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
                          ✨ No contracting programs identified in {selectedState}. All active courses are expanding or stable.
                        </div>
                      ) : (
                        nodeData.sub_programs_analysis?.dropping_programs.map((sp) => (
                          <div
                            key={sp.program_code}
                            className={`p-3.5 rounded-xl border transition-all ${
                              isDark ? 'bg-[#141B2E] border-slate-700/80 hover:border-rose-500/40' : 'bg-white border-slate-200 hover:border-rose-300 shadow-xs'
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
                            </div>

                            <div
                              className={`px-3 py-2 rounded-lg text-xs mb-2.5 flex items-start gap-2 border ${
                                sp.issue_type === 'CONVERSION_COLLAPSE'
                                  ? isDark ? 'bg-amber-950/25 text-amber-200 border-amber-500/30' : 'bg-amber-50 text-amber-900 border-amber-200'
                                  : isDark ? 'bg-rose-950/25 text-rose-200 border-rose-500/30' : 'bg-rose-50 text-rose-900 border-rose-200'
                              }`}
                            >
                              <span className="font-bold shrink-0">⚠️ Diagnosis:</span>
                              <span>{sp.diagnosis}</span>
                            </div>

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
                                  <span className="font-bold tabular-nums">{sp.conversion_rate_cy.toFixed(2)}%</span>
                                  <span className={`text-[10px] font-semibold tabular-nums ${sp.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                    ({sp.var_conversion_rate >= 0 ? '+' : ''}{sp.var_conversion_rate.toFixed(2)}% pts)
                                  </span>
                                </div>
                                <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.conversion_rate_py.toFixed(2)}%</div>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* Tab 3: Expanding Programs */}
                  {activeTab === 'expanding' && (
                    <div className="space-y-2.5">
                      {nodeData.sub_programs_analysis?.expanding_programs.length === 0 ? (
                        <div className={`p-6 rounded-xl border text-center text-xs ${isDark ? 'border-slate-800 bg-[#121829] text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
                          No expanding programs detected for this period.
                        </div>
                      ) : (
                        nodeData.sub_programs_analysis?.expanding_programs.slice(0, 12).map((sp) => (
                          <div
                            key={sp.program_code}
                            className={`p-3.5 rounded-xl border transition-all ${
                              isDark ? 'bg-[#141B2E] border-slate-700/80 hover:border-emerald-500/40' : 'bg-white border-slate-200 hover:border-emerald-300 shadow-xs'
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
                              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold border shadow-xs bg-emerald-500/15 text-emerald-300 border-emerald-500/30">
                                {sp.issue_badge}
                              </span>
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
                                  <span className="font-bold tabular-nums">{sp.conversion_rate_cy.toFixed(2)}%</span>
                                  <span className={`text-[10px] font-semibold tabular-nums ${sp.var_conversion_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                    ({sp.var_conversion_rate >= 0 ? '+' : ''}{sp.var_conversion_rate.toFixed(2)}% pts)
                                  </span>
                                </div>
                                <div className={`text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>PY: {sp.conversion_rate_py.toFixed(2)}%</div>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* Tab 4: Channel Drivers Across State */}
                  {activeTab === 'drivers' && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs uppercase tracking-wider font-bold text-rose-400 flex items-center gap-1.5">
                          <span>⚠️</span> Detected Issues & Negative Drag in {selectedState} ({nodeData.issues?.length || 0})
                        </h4>
                        <span className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                          Click [Why?] for underlying evidence
                        </span>
                      </div>

                      {(!nodeData.issues || nodeData.issues.length === 0) ? (
                        <div className={`p-4 rounded-xl border text-center text-xs ${isDark ? 'border-slate-800 bg-[#121829] text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
                          🎉 No material performance contractions detected for {selectedState}. Core channels are performing within healthy bounds.
                        </div>
                      ) : (
                        nodeData.issues.map((driver) => {
                          const isExpanded = expandedDriverIds.has(driver.id);
                          const childInfo = childDriversMap[driver.id];

                          return (
                            <div
                              key={driver.id}
                              className={`rounded-xl border transition-all overflow-hidden ${
                                isDark ? 'bg-[#13192B] border-slate-800 hover:border-slate-700' : 'bg-white border-slate-200 hover:border-slate-300 shadow-xs'
                              }`}
                            >
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

                              {isExpanded && (
                                <div
                                  className={`px-4 py-3 border-t text-xs space-y-3 ${
                                    isDark ? 'border-slate-800 bg-[#0E1322]' : 'border-slate-100 bg-slate-50'
                                  }`}
                                >
                                  <div className="flex items-center justify-between flex-wrap gap-2">
                                    <span className="font-semibold text-indigo-400">
                                      Underlying Evidence for {driver.name}:
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

                                  <div className={`p-2.5 rounded-lg border text-[11px] ${isDark ? 'bg-indigo-950/30 border-indigo-800/40 text-indigo-200' : 'bg-indigo-50 border-indigo-100 text-indigo-900'}`}>
                                    <span className="font-bold">💡 Recommended Action: </span>
                                    {driver.dimension === 'program' || driver.dimension === 'program_group'
                                      ? `Adjust fee structures or scholarship quotas for ${driver.name} in ${selectedState} to recover the ${driver.var_adm} admission deficit.`
                                      : driver.dimension === 'lead_type'
                                      ? `Audit marketing campaigns and enquiry verification for ${driver.name} leads originating from ${selectedState}.`
                                      : driver.dimension === 'counsellor'
                                      ? `Review regional follow-up SLA and counselling touchpoints with counsellor ${driver.name} for ${selectedState} applicants.`
                                      : `Investigate conversion dropoffs in ${driver.name} for ${selectedState}.`}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
