'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import {
  LEET_TO_GEN_OPTIONS,
  TOP_15_OPTIONS,
  LEAD_TYPE_OPTIONS,
  POPULAR_SOURCES,
  ALL_PROGRAM_DIMENSIONS,
} from '@/lib/dimensions/programDimensions';

export interface ProgramFilterState {
  leadType: string;
  source: string;
  selectedLeetToGen: string[];
  top15: string;
  programName: string;
}

interface ProgramFilterBarProps {
  filters: ProgramFilterState;
  onChange: (filters: ProgramFilterState) => void;
  onReset: () => void;
  isDark?: boolean;
}

export default function ProgramFilterBar({
  filters,
  onChange,
  onReset,
  isDark = true,
}: ProgramFilterBarProps) {
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

  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const [programSearch, setProgramSearch] = useState('');
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

  const handleLeetToggle = (option: string) => {
    const current = [...filters.selectedLeetToGen];
    const idx = current.indexOf(option);
    if (idx >= 0) {
      current.splice(idx, 1);
    } else {
      current.push(option);
    }
    onChange({ ...filters, selectedLeetToGen: current });
  };

  const handleDateChange = (from: string, to: string) => {
    setFromDate(from);
    setToDate(to);
  };

  const handleApplyDates = () => {
    applyDateRange();
  };

  // Format date YYYY-MM-DD -> DD/MM/YYYY
  const formatDisplayDate = (d?: string | null) => {
    if (!d) return '';
    const parts = d.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return d;
  };

  // Extract unique program groups & names for dropdown
  const uniquePrograms = Array.from(
    new Set(
      ALL_PROGRAM_DIMENSIONS.map((p) => p.short || p.name || p.code).filter(Boolean)
    )
  ).sort();

  const filteredPrograms = programSearch
    ? uniquePrograms.filter((p) =>
        p.toLowerCase().includes(programSearch.toLowerCase())
      )
    : uniquePrograms;

  // Active filters badge count
  const activeCount =
    (filters.leadType !== 'All' ? 1 : 0) +
    (filters.source !== 'All' ? 1 : 0) +
    (filters.selectedLeetToGen.length > 0 ? 1 : 0) +
    (filters.top15 !== 'All' ? 1 : 0) +
    (filters.programName !== 'All' ? 1 : 0) +
    (appliedFromDate || appliedToDate ? 1 : 0);

  return (
    <div
      ref={barRef}
      className={`border-b px-3 sm:px-6 py-2.5 transition-colors select-none ${
        isDark ? 'bg-[#0d101d] border-white/10' : 'bg-white border-slate-200'
      }`}
    >
      <div className="flex items-end justify-between gap-2.5 sm:gap-4 overflow-x-auto pb-1 scrollbar-thin">
        {/* Left Filter Controls Row */}
        <div className="flex items-end gap-2 sm:gap-3 shrink-0">
          
          {/* 1. Lead Type */}
          <div className="relative flex flex-col gap-1 min-w-[100px] sm:min-w-[115px]">
            <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Lead Type
            </label>
            <button
              type="button"
              onClick={() => toggleDropdown('leadType')}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded bg-[#9fe3be] hover:bg-[#8ee0b1] text-slate-900 text-xs font-semibold shadow-xs transition-colors cursor-pointer border border-emerald-400/50"
            >
              <span className="truncate">{filters.leadType}</span>
              <svg
                className={`w-3.5 h-3.5 ml-1 text-slate-800 transition-transform ${
                  openDropdown === 'leadType' ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'leadType' && (
              <div className="absolute top-full left-0 mt-1 w-44 bg-[#9fe3be] border border-emerald-400/60 rounded-md shadow-xl py-1 z-50 text-slate-900 font-medium text-xs">
                {LEAD_TYPE_OPTIONS.map((lt) => (
                  <div
                    key={lt}
                    onClick={() => {
                      onChange({ ...filters, leadType: lt });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 hover:bg-[#86d9a9] cursor-pointer flex items-center justify-between ${
                      filters.leadType === lt ? 'bg-[#7fd4a3] font-bold' : ''
                    }`}
                  >
                    <span>{lt}</span>
                    {filters.leadType === lt && <span>✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 2. Source */}
          <div className="relative flex flex-col gap-1 min-w-[100px] sm:min-w-[120px]">
            <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Source
            </label>
            <button
              type="button"
              onClick={() => toggleDropdown('source')}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded bg-[#9fe3be] hover:bg-[#8ee0b1] text-slate-900 text-xs font-semibold shadow-xs transition-colors cursor-pointer border border-emerald-400/50"
            >
              <span className="truncate">{filters.source}</span>
              <svg
                className={`w-3.5 h-3.5 ml-1 text-slate-800 transition-transform ${
                  openDropdown === 'source' ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'source' && (
              <div className="absolute top-full left-0 mt-1 w-48 max-h-60 overflow-y-auto bg-[#9fe3be] border border-emerald-400/60 rounded-md shadow-xl py-1 z-50 text-slate-900 font-medium text-xs scrollbar-thin">
                {POPULAR_SOURCES.map((src) => (
                  <div
                    key={src}
                    onClick={() => {
                      onChange({ ...filters, source: src });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 hover:bg-[#86d9a9] cursor-pointer flex items-center justify-between ${
                      filters.source === src ? 'bg-[#7fd4a3] font-bold' : ''
                    }`}
                  >
                    <span>{src}</span>
                    {filters.source === src && <span>✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 3. Lee | Gen | ITP (Checkbox Multi-Select Dropdown - Image 1) */}
          <div className="relative flex flex-col gap-1 min-w-[115px] sm:min-w-[130px]">
            <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Lee | Gen | ITP
            </label>
            <button
              type="button"
              onClick={() => toggleDropdown('leetToGen')}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded bg-[#9fe3be] hover:bg-[#8ee0b1] text-slate-900 text-xs font-semibold shadow-xs transition-colors cursor-pointer border border-emerald-400/50"
            >
              <span className="truncate">
                {filters.selectedLeetToGen.length === 0
                  ? 'All'
                  : filters.selectedLeetToGen.length === 1
                  ? filters.selectedLeetToGen[0]
                  : `${filters.selectedLeetToGen.length} selected`}
              </span>
              <svg
                className={`w-3.5 h-3.5 ml-1 text-slate-800 transition-transform ${
                  openDropdown === 'leetToGen' ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'leetToGen' && (
              <div className="absolute top-full left-0 mt-1 w-44 bg-[#9fe3be] border border-emerald-400/60 rounded-md shadow-xl p-2 z-50 text-slate-900 text-xs">
                <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-emerald-500/30 text-[10px] font-bold uppercase tracking-wider text-emerald-900">
                  <span>Categories</span>
                  <button
                    type="button"
                    onClick={() => onChange({ ...filters, selectedLeetToGen: [] })}
                    className="hover:underline cursor-pointer text-emerald-800"
                  >
                    Clear
                  </button>
                </div>
                <div className="space-y-1.5">
                  {LEET_TO_GEN_OPTIONS.map((opt) => {
                    const isChecked = filters.selectedLeetToGen.includes(opt);
                    return (
                      <label
                        key={opt}
                        className="flex items-center gap-2 cursor-pointer hover:bg-[#8ee0b1] p-1 rounded transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleLeetToggle(opt)}
                          className="w-3.5 h-3.5 rounded border-emerald-600 text-emerald-700 focus:ring-emerald-500 cursor-pointer accent-emerald-700"
                        />
                        <span className="font-medium text-slate-900">{opt}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* 4. Top | Next 15 */}
          <div className="relative flex flex-col gap-1 min-w-[100px] sm:min-w-[120px]">
            <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Top | Next 15
            </label>
            <button
              type="button"
              onClick={() => toggleDropdown('top15')}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded bg-[#9fe3be] hover:bg-[#8ee0b1] text-slate-900 text-xs font-semibold shadow-xs transition-colors cursor-pointer border border-emerald-400/50"
            >
              <span className="truncate">{filters.top15}</span>
              <svg
                className={`w-3.5 h-3.5 ml-1 text-slate-800 transition-transform ${
                  openDropdown === 'top15' ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'top15' && (
              <div className="absolute top-full left-0 mt-1 w-44 bg-[#9fe3be] border border-emerald-400/60 rounded-md shadow-xl py-1 z-50 text-slate-900 font-medium text-xs">
                {TOP_15_OPTIONS.map((t) => (
                  <div
                    key={t}
                    onClick={() => {
                      onChange({ ...filters, top15: t });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 hover:bg-[#86d9a9] cursor-pointer flex items-center justify-between ${
                      filters.top15 === t ? 'bg-[#7fd4a3] font-bold' : ''
                    }`}
                  >
                    <span>{t}</span>
                    {filters.top15 === t && <span>✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 5. Program Name */}
          <div className="relative flex flex-col gap-1 min-w-[120px] sm:min-w-[150px]">
            <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Program Name
            </label>
            <button
              type="button"
              onClick={() => toggleDropdown('programName')}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded bg-[#9fe3be] hover:bg-[#8ee0b1] text-slate-900 text-xs font-semibold shadow-xs transition-colors cursor-pointer border border-emerald-400/50"
            >
              <span className="truncate">{filters.programName}</span>
              <svg
                className={`w-3.5 h-3.5 ml-1 text-slate-800 transition-transform ${
                  openDropdown === 'programName' ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'programName' && (
              <div className="absolute top-full left-0 mt-1 w-72 max-h-72 overflow-y-auto bg-[#9fe3be] border border-emerald-400/60 rounded-md shadow-xl p-2 z-50 text-slate-900 text-xs scrollbar-thin">
                <input
                  type="text"
                  placeholder="Search program..."
                  value={programSearch}
                  onChange={(e) => setProgramSearch(e.target.value)}
                  className="w-full px-2 py-1 mb-2 rounded bg-white text-slate-900 border border-emerald-400 text-xs focus:outline-hidden"
                  autoFocus
                />
                <div
                  onClick={() => {
                    onChange({ ...filters, programName: 'All' });
                    setOpenDropdown(null);
                  }}
                  className={`px-2 py-1 rounded hover:bg-[#86d9a9] cursor-pointer mb-1 ${
                    filters.programName === 'All' ? 'bg-[#7fd4a3] font-bold' : ''
                  }`}
                >
                  All Programs
                </div>
                {filteredPrograms.map((p) => (
                  <div
                    key={p}
                    onClick={() => {
                      onChange({ ...filters, programName: p });
                      setOpenDropdown(null);
                    }}
                    className={`px-2 py-1 rounded hover:bg-[#86d9a9] cursor-pointer truncate ${
                      filters.programName === p ? 'bg-[#7fd4a3] font-bold' : ''
                    }`}
                    title={p}
                  >
                    {p}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 6. Select Date Here ↓ (Dual date picker from Image 1) */}
          <div className="flex flex-col gap-1 shrink-0">
            <div className="flex items-center justify-between">
              <label className={`text-[11px] font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                Select Date Here ↓
              </label>
              {(appliedFromDate || appliedToDate) && (
                <button
                  type="button"
                  onClick={resetDateRange}
                  title="Clear custom date filter"
                  className="text-[10px] text-indigo-400 hover:text-indigo-300 cursor-pointer ml-2"
                >
                  Reset
                </button>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {/* From Date Input */}
              <div className="relative">
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
              </div>

              {/* To Date Input */}
              <div className="relative">
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
              </div>
            </div>
          </div>
        </div>

        {/* Right Action Area: Campus Buttons + Open Slicers */}
        <div className="flex items-center gap-2 shrink-0 ml-auto pt-4 sm:pt-0">
          {/* Campus: MH (Mohali) */}
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

          {/* Campus: LKO (Lucknow) */}
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

          {/* Open Slicers Button (Navy blue pill from Image 1) */}
          <button
            type="button"
            onClick={() => {
              onReset();
              resetDateRange();
              setSelectedCampus('all');
            }}
            className="px-3.5 py-1.5 rounded-md bg-[#0d1740] hover:bg-[#14225d] text-white text-xs font-serif italic tracking-wide transition-all shadow-md hover:scale-[1.02] cursor-pointer flex items-center gap-1.5 border border-indigo-900/60"
            title="Reset all filters and slicers"
          >
            <span>Open Slicers</span>
            {activeCount > 0 && (
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
