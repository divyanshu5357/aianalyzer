'use client';

import React, { useState, useRef, useEffect } from 'react';
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
    (filters.programName !== 'All' ? 1 : 0);

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

  return (
    <div
      ref={barRef}
      className={`relative z-40 border-b px-3 sm:px-6 py-2.5 transition-colors select-none ${
        isDark ? 'bg-[#0d101d] border-white/10' : 'bg-slate-50/80 border-slate-200'
      }`}
    >
      <div className="flex items-center justify-between gap-2 sm:gap-3 flex-wrap">
        
        {/* Filter Controls Row */}
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap flex-1 min-w-0">
          
          {/* 1. Lead Type */}
          <div className="relative flex flex-col gap-1 min-w-[110px] sm:min-w-[125px] flex-1 sm:flex-none">
            <label className={labelBase}>Lead Type</label>
            <button
              type="button"
              onClick={() => toggleDropdown('leadType')}
              className={`${btnBase} ${
                filters.leadType !== 'All'
                  ? (isDark ? 'border-indigo-500/50 text-indigo-300 bg-indigo-950/30' : 'border-indigo-300 text-indigo-700 bg-indigo-50')
                  : ''
              }`}
            >
              <span className="truncate">{filters.leadType}</span>
              <svg
                className={`w-3.5 h-3.5 shrink-0 transition-transform text-slate-400 ${
                  openDropdown === 'leadType' ? 'rotate-180 text-indigo-500' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'leadType' && (
              <div className={`${popoverBase} w-44`}>
                {LEAD_TYPE_OPTIONS.map((lt) => (
                  <div
                    key={lt}
                    onClick={() => {
                      onChange({ ...filters, leadType: lt });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 rounded-lg cursor-pointer flex items-center justify-between transition-colors ${
                      filters.leadType === lt
                        ? (isDark ? 'bg-indigo-600/20 text-indigo-300 font-bold' : 'bg-indigo-50 text-indigo-700 font-bold')
                        : (isDark ? 'hover:bg-indigo-600/20 hover:text-indigo-300 text-slate-200' : 'hover:bg-indigo-50 hover:text-indigo-700 text-slate-800')
                    }`}
                  >
                    <span>{lt}</span>
                    {filters.leadType === lt && <span className="text-indigo-500">✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 2. Source */}
          <div className="relative flex flex-col gap-1 min-w-[115px] sm:min-w-[130px] flex-1 sm:flex-none">
            <label className={labelBase}>Source</label>
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

          {/* 3. Lee | Gen | ITP (Category Multi-Select) */}
          <div className="relative flex flex-col gap-1 min-w-[125px] sm:min-w-[140px] flex-1 sm:flex-none">
            <label className={labelBase}>Lee | Gen | ITP</label>
            <button
              type="button"
              onClick={() => toggleDropdown('leetToGen')}
              className={`${btnBase} ${
                filters.selectedLeetToGen.length > 0
                  ? (isDark ? 'border-emerald-500/50 text-emerald-300 bg-emerald-950/30' : 'border-emerald-300 text-emerald-700 bg-emerald-50')
                  : ''
              }`}
            >
              <span className="truncate">
                {filters.selectedLeetToGen.length === 0
                  ? 'All'
                  : filters.selectedLeetToGen.length === 1
                  ? filters.selectedLeetToGen[0]
                  : `${filters.selectedLeetToGen.length} selected`}
              </span>
              <svg
                className={`w-3.5 h-3.5 shrink-0 transition-transform text-slate-400 ${
                  openDropdown === 'leetToGen' ? 'rotate-180 text-emerald-500' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'leetToGen' && (
              <div className={`${popoverBase} w-48`}>
                <div className={`flex items-center justify-between pb-1.5 mb-1.5 border-b px-1 text-[10px] font-bold uppercase tracking-wider ${
                  isDark ? 'border-white/10 text-slate-400' : 'border-slate-200 text-slate-600'
                }`}>
                  <span>Categories</span>
                  {filters.selectedLeetToGen.length > 0 && (
                    <button
                      type="button"
                      onClick={() => onChange({ ...filters, selectedLeetToGen: [] })}
                      className={`hover:underline cursor-pointer ${isDark ? 'text-indigo-400 hover:text-indigo-300' : 'text-indigo-600 hover:text-indigo-800'}`}
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="space-y-1">
                  {LEET_TO_GEN_OPTIONS.map((opt) => {
                    const isChecked = filters.selectedLeetToGen.includes(opt);
                    return (
                      <label
                        key={opt}
                        className={`flex items-center gap-2 px-2 py-1 rounded-lg cursor-pointer transition-colors ${
                          isDark ? 'hover:bg-white/5 text-slate-200' : 'hover:bg-slate-100 text-slate-800'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleLeetToggle(opt)}
                          className="w-3.5 h-3.5 rounded border-slate-600 text-indigo-600 focus:ring-indigo-500 cursor-pointer accent-indigo-600"
                        />
                        <span className="font-medium text-xs">{opt}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* 4. Top | Next 15 */}
          <div className="relative flex flex-col gap-1 min-w-[110px] sm:min-w-[125px] flex-1 sm:flex-none">
            <label className={labelBase}>Top | Next 15</label>
            <button
              type="button"
              onClick={() => toggleDropdown('top15')}
              className={`${btnBase} ${
                filters.top15 !== 'All'
                  ? (isDark ? 'border-indigo-500/50 text-indigo-300 bg-indigo-950/30' : 'border-indigo-300 text-indigo-700 bg-indigo-50')
                  : ''
              }`}
            >
              <span className="truncate">{filters.top15}</span>
              <svg
                className={`w-3.5 h-3.5 shrink-0 transition-transform text-slate-400 ${
                  openDropdown === 'top15' ? 'rotate-180 text-indigo-500' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'top15' && (
              <div className={`${popoverBase} w-44`}>
                {TOP_15_OPTIONS.map((t) => (
                  <div
                    key={t}
                    onClick={() => {
                      onChange({ ...filters, top15: t });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 rounded-lg cursor-pointer flex items-center justify-between transition-colors ${
                      filters.top15 === t
                        ? (isDark ? 'bg-indigo-600/20 text-indigo-300 font-bold' : 'bg-indigo-50 text-indigo-700 font-bold')
                        : (isDark ? 'hover:bg-indigo-600/20 hover:text-indigo-300 text-slate-200' : 'hover:bg-indigo-50 hover:text-indigo-700 text-slate-800')
                    }`}
                  >
                    <span>{t}</span>
                    {filters.top15 === t && <span className="text-indigo-500">✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 5. Program Name */}
          <div className="relative flex flex-col gap-1 min-w-[130px] sm:min-w-[160px] flex-1 sm:flex-none">
            <label className={labelBase}>Program Name</label>
            <button
              type="button"
              onClick={() => toggleDropdown('programName')}
              className={`${btnBase} ${
                filters.programName !== 'All'
                  ? (isDark ? 'border-indigo-500/50 text-indigo-300 bg-indigo-950/30' : 'border-indigo-300 text-indigo-700 bg-indigo-50')
                  : ''
              }`}
            >
              <span className="truncate">{filters.programName}</span>
              <svg
                className={`w-3.5 h-3.5 shrink-0 transition-transform text-slate-400 ${
                  openDropdown === 'programName' ? 'rotate-180 text-indigo-500' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {openDropdown === 'programName' && (
              <div className={`${popoverBase} w-72 max-h-72 overflow-y-auto scrollbar-thin`}>
                <div className={`p-1.5 border-b sticky top-0 ${isDark ? 'border-white/10 bg-[#141a29]' : 'border-slate-200 bg-white'}`}>
                  <input
                    type="text"
                    placeholder="Search program..."
                    value={programSearch}
                    onChange={(e) => setProgramSearch(e.target.value)}
                    className={`w-full px-2.5 py-1.5 rounded-lg text-xs border focus:outline-hidden ${
                      isDark
                        ? 'bg-slate-800/90 text-white border-white/10 focus:border-indigo-500'
                        : 'bg-slate-50 text-slate-900 border-slate-300 focus:border-indigo-500'
                    }`}
                    autoFocus
                  />
                </div>
                <div
                  onClick={() => {
                    onChange({ ...filters, programName: 'All' });
                    setOpenDropdown(null);
                  }}
                  className={`px-3 py-1.5 rounded-lg cursor-pointer flex items-center justify-between font-semibold transition-colors ${
                    filters.programName === 'All'
                      ? (isDark ? 'bg-indigo-600/20 text-indigo-300' : 'bg-indigo-50 text-indigo-700')
                      : (isDark ? 'hover:bg-indigo-600/20 hover:text-indigo-300 text-slate-200' : 'hover:bg-indigo-50 hover:text-indigo-700 text-slate-800')
                  }`}
                >
                  <span>All Programs</span>
                  {filters.programName === 'All' && <span>✓</span>}
                </div>
                {filteredPrograms.map((p) => (
                  <div
                    key={p}
                    onClick={() => {
                      onChange({ ...filters, programName: p });
                      setOpenDropdown(null);
                    }}
                    className={`px-3 py-1.5 rounded-lg cursor-pointer flex items-center justify-between transition-colors ${
                      filters.programName === p
                        ? (isDark ? 'bg-indigo-600/20 text-indigo-300 font-bold' : 'bg-indigo-50 text-indigo-700 font-bold')
                        : (isDark ? 'hover:bg-indigo-600/20 hover:text-indigo-300 text-slate-200' : 'hover:bg-indigo-50 hover:text-indigo-700 text-slate-800')
                    }`}
                  >
                    <span className="truncate">{p}</span>
                    {filters.programName === p && <span className="text-indigo-500">✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Clear Filters Button (shown only when filters active) */}
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
