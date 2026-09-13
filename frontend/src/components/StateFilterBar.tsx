'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import { POPULAR_SOURCES } from '@/lib/dimensions/programDimensions';

export interface StateFilterState {
  regionType: 'GEN' | 'INT'; // GEN = Domestic Indian states, INT = International
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
  const {
    selectedCampus,
    setSelectedCampus,
    fromDate,
    setFromDate,
    toDate,
    setToDate,
    applyDateRange,
    resetDateRange,
    appliedFromDate,
    appliedToDate,
  } = useApp();

  const [isSourceOpen, setIsSourceOpen] = useState(false);
  const sourceRef = useRef<HTMLDivElement>(null);

  // Close source dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (sourceRef.current && !sourceRef.current.contains(event.target as Node)) {
        setIsSourceOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleRegionToggle = (type: 'GEN' | 'INT') => {
    onChange({ ...filters, regionType: type });
  };

  const handleMetricClick = (metric: 'lead_cucet_pct' | 'lead_adm_pct' | 'cucet_adm_pct') => {
    onChange({
      ...filters,
      activeMetric: filters.activeMetric === metric ? null : metric,
    });
    onSortMetric(metric);
  };

  const handleDateChange = (from: string, to: string) => {
    setFromDate(from);
    setToDate(to);
  };

  const handleApplyDates = () => {
    applyDateRange();
  };

  return (
    <div
      className={`relative z-40 border-b px-3 sm:px-6 py-2.5 transition-colors select-none ${
        isDark ? 'bg-[#0d101d] border-white/10' : 'bg-white border-slate-200'
      }`}
    >
      <div className="flex items-center justify-between gap-3 sm:gap-4 flex-wrap pb-1">
        {/* Left Side: Title + Globe Icon + GEN/INT Toggle (Image 2) */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2">
            {/* Globe SVG matching Image 2 */}
            <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-[#003882] flex items-center justify-center text-white shrink-0 shadow-xs">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                <path d="M2 12h20" />
              </svg>
            </div>
            <h1 className={`text-sm sm:text-base font-bold tracking-tight whitespace-nowrap ${
              isDark ? 'text-white' : 'text-slate-900'
            }`}>
              State Wise Analysis
            </h1>
          </div>

          {/* GEN | INT Toggle Buttons (Image 2 - gold/yellow background) */}
          <div className="flex items-center rounded-sm bg-[#e2b857] p-0.5 shadow-xs shrink-0 text-[11px] font-bold text-slate-900">
            <button
              type="button"
              onClick={() => handleRegionToggle('GEN')}
              className={`px-2.5 py-1 rounded-xs transition-all cursor-pointer ${
                filters.regionType === 'GEN'
                  ? 'bg-[#caa242] text-slate-950 shadow-inner'
                  : 'hover:bg-[#d8b04e] text-slate-800'
              }`}
              title="General / Domestic Indian States"
            >
              GEN
            </button>
            <button
              type="button"
              onClick={() => handleRegionToggle('INT')}
              className={`px-2.5 py-1 rounded-xs transition-all cursor-pointer ${
                filters.regionType === 'INT'
                  ? 'bg-[#caa242] text-slate-950 shadow-inner'
                  : 'hover:bg-[#d8b04e] text-slate-800'
              }`}
              title="International States / Countries"
            >
              INT
            </button>
            <span className="px-1 text-slate-700 text-xs font-semibold">›</span>
          </div>
        </div>

        {/* Center: Three Bright Blue Metric Action Buttons (Image 2) */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
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
                className={`px-3 sm:px-4 py-1.5 rounded-sm text-xs font-serif italic text-white transition-all shadow-md cursor-pointer ${
                  isActive
                    ? 'bg-[#0022ff] ring-2 ring-white/80 scale-[1.02]'
                    : 'bg-[#0000ff] hover:bg-[#0022ff]'
                }`}
                title={`Sort and highlight by ${label}`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Right Side: Select Source Here ↓ + Select Date Here ↓ + MH/LKO (Image 2) */}
        <div className="flex items-end gap-2.5 sm:gap-3 shrink-0 ml-auto">
          
          {/* Select Source Here ↓ */}
          <div ref={sourceRef} className="relative flex flex-col gap-1 min-w-[120px] sm:min-w-[140px]">
            <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Select Source Here ↓
            </label>
            <button
              type="button"
              onClick={() => setIsSourceOpen((prev) => !prev)}
              className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-medium border transition-colors cursor-pointer ${
                isDark
                  ? 'bg-slate-800/80 text-white border-white/10 hover:border-white/20'
                  : 'bg-slate-100/90 text-slate-900 border-slate-300 hover:border-slate-400'
              }`}
            >
              <span className="truncate">{filters.source}</span>
              <svg
                className={`w-3.5 h-3.5 ml-1 text-slate-400 transition-transform ${
                  isSourceOpen ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {isSourceOpen && (
              <div
                className={`absolute top-full right-0 mt-1 w-48 max-h-60 overflow-y-auto rounded-md shadow-xl py-1 z-50 text-xs border scrollbar-thin ${
                  isDark
                    ? 'bg-[#141a29] border-white/15 text-white'
                    : 'bg-white border-slate-200 text-slate-900'
                }`}
              >
                {POPULAR_SOURCES.map((src) => (
                  <div
                    key={src}
                    onClick={() => {
                      onChange({ ...filters, source: src });
                      setIsSourceOpen(false);
                    }}
                    className={`px-3 py-1.5 cursor-pointer flex items-center justify-between ${
                      filters.source === src
                        ? isDark
                          ? 'bg-indigo-600/30 text-indigo-300 font-bold'
                          : 'bg-indigo-50 text-indigo-600 font-bold'
                        : isDark
                        ? 'hover:bg-white/5'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    <span>{src}</span>
                    {filters.source === src && <span>✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Select Date Here ↓ + Eraser reset button (Image 2) */}
          <div className="flex flex-col gap-1 shrink-0">
            <div className="flex items-center justify-between">
              <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                Select Date Here ↓
              </label>
            </div>
            <div className="flex items-center gap-1.5">
              <input
                type="date"
                value={fromDate || appliedFromDate || ''}
                onChange={(e) => {
                  handleDateChange(e.target.value, toDate || appliedToDate || '');
                }}
                onBlur={handleApplyDates}
                className={`px-2 py-1 text-xs font-semibold rounded border cursor-pointer ${
                  isDark
                    ? 'bg-slate-800/90 text-sky-300 border-slate-700 hover:border-slate-600'
                    : 'bg-indigo-50/70 text-indigo-900 border-indigo-200 hover:border-indigo-300'
                }`}
                style={{ width: '130px' }}
              />
              <input
                type="date"
                value={toDate || appliedToDate || ''}
                onChange={(e) => {
                  handleDateChange(fromDate || appliedFromDate || '', e.target.value);
                }}
                onBlur={handleApplyDates}
                className={`px-2 py-1 text-xs font-semibold rounded border cursor-pointer ${
                  isDark
                    ? 'bg-slate-800/90 text-sky-300 border-slate-700 hover:border-slate-600'
                    : 'bg-indigo-50/70 text-indigo-900 border-indigo-200 hover:border-indigo-300'
                }`}
                style={{ width: '130px' }}
              />

              {/* Eraser Icon button from Image 2 */}
              <button
                type="button"
                onClick={() => {
                  resetDateRange();
                  onReset();
                }}
                title="Clear date filter & reset"
                className={`p-1.5 rounded transition-colors cursor-pointer text-xs ${
                  isDark
                    ? 'text-gray-400 hover:text-white hover:bg-white/10'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>

          {/* Campus Buttons: MH & LKO */}
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={() => setSelectedCampus(selectedCampus === 'Mohali' ? 'all' : 'Mohali')}
              className={`px-3 py-1.5 rounded text-xs font-bold transition-all cursor-pointer shadow-xs ${
                selectedCampus === 'Mohali'
                  ? 'bg-[#1e293b] text-white ring-2 ring-indigo-400'
                  : isDark
                  ? 'bg-[#2d3238] text-slate-200 hover:bg-[#3d4248]'
                  : 'bg-slate-700 text-white hover:bg-slate-800'
              }`}
              title="Filter by Mohali Campus"
            >
              MH
            </button>
            <button
              type="button"
              onClick={() => setSelectedCampus(selectedCampus === 'Lucknow' ? 'all' : 'Lucknow')}
              className={`px-3 py-1.5 rounded text-xs font-bold transition-all cursor-pointer shadow-xs ${
                selectedCampus === 'Lucknow'
                  ? 'bg-[#eab308] text-slate-950 ring-2 ring-amber-400'
                  : 'bg-[#e5c464] text-slate-900 hover:bg-[#dbc058]'
              }`}
              title="Filter by Lucknow Campus"
            >
              LKO
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
