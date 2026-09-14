'use client';

import React, { useState, useRef, useEffect } from 'react';
import { POPULAR_SOURCES } from '@/lib/dimensions/programDimensions';

export interface StateFilterState {
  regionType: 'ALL' | 'GEN' | 'INT'; // ALL = All 26 state groups, GEN = Domestic (25), INT = International (1)
  activeMetric: 'lead_cucet_pct' | 'lead_adm_pct' | 'cucet_adm_pct' | null;
  source: string;
}

interface StateFilterBarProps {
  filters: StateFilterState;
  onChange: (filters: StateFilterState) => void;
  onSortMetric: (metric: 'lead_cucet_pct' | 'lead_adm_pct' | 'cucet_adm_pct') => void;
  onReset: () => void;
  isDark?: boolean;
}

export default function StateFilterBar({
  filters,
  onChange,
  onSortMetric,
  onReset,
  isDark = true,
}: StateFilterBarProps) {
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const barRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (barRef.current && !barRef.current.contains(event.target as Node)) {
        setOpenDropdown(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleDropdown = (name: string) => {
    setOpenDropdown((prev) => (prev === name ? null : name));
  };

  const handleRegionChange = (type: 'ALL' | 'GEN' | 'INT') => {
    onChange({ ...filters, regionType: type });
  };

  const handleMetricClick = (metric: 'lead_cucet_pct' | 'lead_adm_pct' | 'cucet_adm_pct') => {
    const nextMetric = filters.activeMetric === metric ? null : metric;
    onChange({
      ...filters,
      activeMetric: nextMetric,
    });
    onSortMetric(metric);
  };

  // Active filters badge count
  const activeCount =
    (filters.regionType !== 'ALL' ? 1 : 0) +
    (filters.source !== 'All' ? 1 : 0) +
    (filters.activeMetric !== null ? 1 : 0);

  const btnBase = `w-full flex items-center justify-between px-3 py-1.5 sm:py-2 rounded-lg text-xs font-medium transition-all cursor-pointer border shadow-2xs ${
    isDark
      ? 'bg-[#141a29] border-white/10 text-slate-200 hover:border-white/20 hover:bg-[#1a2236]'
      : 'bg-white border-slate-200 text-slate-800 hover:border-slate-300 hover:bg-slate-50'
  }`;

  const labelBase = `text-[10px] sm:text-[11px] font-semibold uppercase tracking-wider ${
    isDark ? 'text-slate-400' : 'text-slate-500'
  }`;

  const popoverBase = `absolute top-full left-0 mt-1.5 rounded-xl shadow-2xl border p-1.5 z-50 text-xs ${
    isDark
      ? 'bg-[#141a29] border-white/15 text-white'
      : 'bg-white border-slate-200 text-slate-900 shadow-slate-300/50'
  }`;

  const regionLabels: Record<'ALL' | 'GEN' | 'INT', string> = {
    ALL: 'All States (26)',
    GEN: 'Domestic (25)',
    INT: 'International (1)',
  };

  return (
    <div
      ref={barRef}
      className={`relative z-40 border-b px-3 sm:px-6 py-2.5 transition-colors select-none ${
        isDark ? 'bg-[#0d101d] border-white/10' : 'bg-slate-50/80 border-slate-200'
      }`}
    >
      <div className="flex items-center justify-between gap-2.5 sm:gap-4 flex-wrap">
        
        {/* Left Controls Row */}
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap flex-1 min-w-0">
          
          {/* 1. Region Filter (All / Domestic / International) */}
          <div className="relative flex flex-col gap-1 min-w-[130px] sm:min-w-[150px] flex-1 sm:flex-none">
            <label className={labelBase}>Region Scope</label>
            <button
              type="button"
              onClick={() => toggleDropdown('region')}
              className={`${btnBase} ${
                filters.regionType !== 'ALL'
                  ? (isDark ? 'border-amber-500/50 text-amber-300 bg-amber-950/30' : 'border-amber-300 text-amber-700 bg-amber-50')
                  : ''
              }`}
            >
              <span className="truncate">{regionLabels[filters.regionType]}</span>
              <svg
                className={`w-3.5 h-3.5 shrink-0 transition-transform text-slate-400 ${
                  openDropdown === 'region' ? 'rotate-180 text-amber-500' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'region' && (
              <div className={`${popoverBase} w-48`}>
                {(['ALL', 'GEN', 'INT'] as const).map((r) => (
                  <div
                    key={r}
                    onClick={() => {
                      handleRegionChange(r);
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 rounded-lg cursor-pointer flex items-center justify-between transition-colors ${
                      filters.regionType === r
                        ? (isDark ? 'bg-amber-600/20 text-amber-300 font-bold' : 'bg-amber-50 text-amber-700 font-bold')
                        : (isDark ? 'hover:bg-amber-600/20 hover:text-amber-300 text-slate-200' : 'hover:bg-amber-50 hover:text-amber-700 text-slate-800')
                    }`}
                  >
                    <span>{regionLabels[r]}</span>
                    {filters.regionType === r && <span className="text-amber-500">✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 2. Source Filter */}
          <div className="relative flex flex-col gap-1 min-w-[115px] sm:min-w-[130px] flex-1 sm:flex-none">
            <label className={labelBase}>Acquisition Source</label>
            <button
              type="button"
              onClick={() => toggleDropdown('source')}
              className={`${btnBase} ${
                filters.source !== 'All'
                  ? (isDark ? 'border-indigo-500/50 text-indigo-300 bg-indigo-950/30' : 'border-indigo-300 text-indigo-700 bg-indigo-50')
                  : ''
              }`}
            >
              <span className="truncate">{filters.source}</span>
              <svg
                className={`w-3.5 h-3.5 shrink-0 transition-transform text-slate-400 ${
                  openDropdown === 'source' ? 'rotate-180 text-indigo-500' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'source' && (
              <div className={`${popoverBase} w-52 max-h-60 overflow-y-auto scrollbar-thin`}>
                {POPULAR_SOURCES.map((src) => (
                  <div
                    key={src}
                    onClick={() => {
                      onChange({ ...filters, source: src });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 rounded-lg cursor-pointer flex items-center justify-between transition-colors ${
                      filters.source === src
                        ? (isDark ? 'bg-indigo-600/20 text-indigo-300 font-bold' : 'bg-indigo-50 text-indigo-700 font-bold')
                        : (isDark ? 'hover:bg-indigo-600/20 hover:text-indigo-300 text-slate-200' : 'hover:bg-indigo-50 hover:text-indigo-700 text-slate-800')
                    }`}
                  >
                    <span className="truncate">{src}</span>
                    {filters.source === src && <span className="text-indigo-500">✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 3. Conversion Metric Sort & Highlight Actions */}
          <div className="flex flex-col gap-1 shrink-0 pt-2 sm:pt-0">
            <label className={labelBase}>Sort by Conversion</label>
            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
              {[
                { key: 'lead_cucet_pct' as const, label: 'Lead-Cucet %' },
                { key: 'lead_adm_pct' as const, label: 'Lead-Adm %' },
                { key: 'cucet_adm_pct' as const, label: 'Cucet- Adm %' },
              ].map(({ key, label }) => {
                const isActive = filters.activeMetric === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => handleMetricClick(key)}
                    className={`px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer border shadow-2xs ${
                      isActive
                        ? (isDark
                            ? 'bg-indigo-600 text-white border-indigo-500 shadow-indigo-900/50'
                            : 'bg-indigo-600 text-white border-indigo-600 shadow-indigo-200')
                        : (isDark
                            ? 'bg-[#141a29] text-slate-300 border-white/10 hover:border-white/20 hover:text-white'
                            : 'bg-white text-slate-700 border-slate-200 hover:border-slate-300 hover:text-slate-900')
                    }`}
                    title={`Sort state ranking by ${label}`}
                  >
                    <span>{label}</span>
                    {isActive && <span className="ml-1 text-[10px]">↓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Clear Filters Button (shown when any filter active) */}
        {activeCount > 0 && (
          <div className="flex items-center gap-2 shrink-0 pt-2 sm:pt-0">
            <button
              type="button"
              onClick={onReset}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 border ${
                isDark
                  ? 'bg-rose-950/40 text-rose-300 border-rose-800/40 hover:bg-rose-900/40'
                  : 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100'
              }`}
              title="Reset all filters"
            >
              <span>✕ Reset Filters ({activeCount})</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
