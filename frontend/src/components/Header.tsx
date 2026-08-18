"use client";

import React from "react";
import { RefreshCw, Calendar, Menu, Sparkles, Layers } from "lucide-react";
import { PeriodSummary } from "../lib/api";

interface HeaderProps {
  year: number;
  onYearChange: (year: number) => void;
  onRefresh: () => void;
  isLoading: boolean;
  onToggleMobileSidebar?: () => void;
  // Period-aware props
  periods?: PeriodSummary[];
  activePeriodLabel?: string | null;
  onPeriodChange?: (label: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  year,
  onYearChange,
  onRefresh,
  isLoading,
  onToggleMobileSidebar,
  periods = [],
  activePeriodLabel,
  onPeriodChange,
}) => {
  const hasPeriods = periods.length > 0;

  const handlePeriodSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const label = e.target.value;
    const period = periods.find((p) => p.academic_label === label);
    if (period) {
      onPeriodChange?.(label);
      // Also update the numeric year for backward compat
      if (period.period_end_year) {
        onYearChange(period.period_end_year);
      }
    }
  };

  return (
    <header className="sticky top-0 z-20 bg-white/90 backdrop-blur-md border-b border-slate-200 px-6 py-4 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        {onToggleMobileSidebar && (
          <button
            onClick={onToggleMobileSidebar}
            className="md:hidden p-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
            aria-label="Toggle Navigation"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-600 border border-blue-100">
              <Sparkles className="w-3 h-3" /> ORGANIZATION ANALYTICS
            </span>
          </div>
          <h1 className="text-xl font-extrabold text-slate-900 tracking-tight mt-1">
            Admissions Intelligence
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Academic Period Selector — dynamic from API */}
        {hasPeriods ? (
          <div className="relative flex items-center" title="Academic Period">
            <Layers className="w-4 h-4 text-slate-400 absolute left-3 pointer-events-none" />
            <select
              id="period-selector"
              value={activePeriodLabel ?? ""}
              onChange={handlePeriodSelect}
              className="pl-9 pr-8 py-2 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all appearance-none cursor-pointer hover:bg-slate-50"
              aria-label="Select academic period"
            >
              {periods.map((p) => (
                <option key={p.academic_label} value={p.academic_label}>
                  {p.academic_label}
                  {p.active_dataset_id ? " ✓" : ""}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute right-3 text-slate-400 text-xs">▼</div>
          </div>
        ) : (
          /* Fallback: static year selector for when no periods are loaded yet */
          <div className="relative flex items-center" title="Year">
            <Calendar className="w-4 h-4 text-slate-400 absolute left-3 pointer-events-none" />
            <select
              id="year-selector"
              value={year}
              onChange={(e) => onYearChange(Number(e.target.value))}
              className="pl-9 pr-8 py-2 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all appearance-none cursor-pointer hover:bg-slate-50"
            >
              <option value={new Date().getFullYear()}>{new Date().getFullYear()}</option>
              <option value={new Date().getFullYear() - 1}>{new Date().getFullYear() - 1}</option>
              <option value={new Date().getFullYear() - 2}>{new Date().getFullYear() - 2}</option>
            </select>
            <div className="pointer-events-none absolute right-3 text-slate-400 text-xs">▼</div>
          </div>
        )}

        {/* Refresh Action */}
        <button
          id="refresh-button"
          onClick={onRefresh}
          disabled={isLoading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-bold text-white bg-blue-600 rounded-xl hover:bg-blue-700 focus:ring-2 focus:ring-blue-500/20 disabled:opacity-60 transition-all shadow-sm shadow-blue-600/20"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          <span>{isLoading ? "Refreshing..." : "Refresh"}</span>
        </button>
      </div>
    </header>
  );
};
