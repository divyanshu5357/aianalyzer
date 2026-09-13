"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { getActiveDataset, getAllPeriods, getDashboardFilterOptions, ActiveDatasetInfo, PeriodSummary } from "../lib/api";
import dashboardCache from "../lib/cache/dashboardCache";


function isValidPeriodLabel(label: string | null | undefined): boolean {
  if (!label) return false;
  return /^\d{4}(-\d{2})?$/.test(label.trim());
}

export type ThemeType = "light" | "dark";

interface AppContextType {
  theme: ThemeType;
  toggleTheme: () => void;
  activeDataset: ActiveDatasetInfo | null;
  isLoadingDataset: boolean;
  fetchActiveDataset: (targetYear?: number, targetCampus?: string) => Promise<void>;
  // Campus Scope Filter
  selectedCampus: string;
  setSelectedCampus: (c: string) => void;
  availableCampuses: string[];
  setAvailableCampuses: (campuses: string[]) => void;
  // Period-aware year tracking
  year: number;
  setYear: (y: number) => void;
  // All available academic periods from the server
  periods: PeriodSummary[];
  analyticalYears: number[];
  isLoadingPeriods: boolean;
  fetchPeriods: () => Promise<void>;
  // Currently selected academic period label (e.g. "2025-26" or "2026")
  activePeriodLabel: string | null;
  setActivePeriodLabel: (label: string | null) => void;
  seededPrompt: string;
  setSeededPrompt: (prompt: string) => void;
  seededPeriodA: string | null;
  setSeededPeriodA: (period: string | null) => void;
  seededPeriodB: string | null;
  setSeededPeriodB: (period: string | null) => void;
  refreshTrigger: number;
  triggerRefresh: () => void;
  /** Invalidate cached dashboard data for a specific year only. Unrelated years' cache remains. */
  invalidateCacheForYear: (year: number, campus?: string) => void;
  /** Notify the app that a dataset changed (upload, delete, toggle). Targeted cache invalidation. */
  notifyDatasetChange: (affectedYear?: number, affectedCampus?: string) => void;
  // Global Date Range Filter
  fromDate: string;
  setFromDate: (d: string) => void;
  toDate: string;
  setToDate: (d: string) => void;
  appliedFromDate: string | null;
  appliedToDate: string | null;
  dateRangeLimits: { min_date: string; max_date: string; default_from: string; default_to: string } | null;
  setDateRangeLimits: (limits: { min_date: string; max_date: string; default_from: string; default_to: string } | null) => void;
  dateRangeError: string | null;
  applyDateRange: () => boolean;
  resetDateRange: () => void;
  fetchFilterOptions: (targetYear?: number, targetCampus?: string, targetSession?: string) => Promise<any>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<ThemeType>("dark");
  const [activeDataset, setActiveDataset] = useState<ActiveDatasetInfo | null>(null);
  const [isLoadingDataset, setIsLoadingDataset] = useState(true);
  const [year, setYearState] = useState<number>(new Date().getFullYear());
  const [periods, setPeriods] = useState<PeriodSummary[]>([]);
  const [analyticalYears, setAnalyticalYears] = useState<number[]>([]);
  const [isLoadingPeriods, setIsLoadingPeriods] = useState(false);
  const [activePeriodLabel, setActivePeriodLabel] = useState<string | null>(null);
  const [seededPrompt, setSeededPrompt] = useState<string>("");
  const [seededPeriodA, setSeededPeriodA] = useState<string | null>(null);
  const [seededPeriodB, setSeededPeriodB] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [appliedFromDate, setAppliedFromDate] = useState<string | null>(null);
  const [appliedToDate, setAppliedToDate] = useState<string | null>(null);
  const [dateRangeLimits, setDateRangeLimits] = useState<{ min_date: string; max_date: string; default_from: string; default_to: string } | null>(null);
  const [dateRangeError, setDateRangeError] = useState<string | null>(null);
  const [selectedCampus, setSelectedCampusState] = useState<string>("all");
  const [availableCampuses, setAvailableCampuses] = useState<string[]>(["Mohali"]);

  // Initialize theme from localStorage
  useEffect(() => {
    const savedTheme = localStorage.getItem("app-theme") as ThemeType;
    setTimeout(() => {
      if (savedTheme === "light" || savedTheme === "dark") {
        setTheme(savedTheme);
      } else {
        setTheme("dark");
      }
    }, 0);
  }, []);

  const toggleTheme = () => {
    const newTheme: ThemeType = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    localStorage.setItem("app-theme", newTheme);
  };

  const fetchActiveDataset = useCallback(async (targetYear?: number, targetCampus?: string) => {
    setIsLoadingDataset(true);
    try {
      const yr = targetYear !== undefined ? targetYear : year;
      const cmp = targetCampus !== undefined ? targetCampus : selectedCampus;
      const res = await getActiveDataset(yr, cmp);
      if (res.active && res.dataset) {
        setActiveDataset(res.dataset);
        if (isValidPeriodLabel(res.dataset.academic_label)) {
          setActivePeriodLabel(res.dataset.academic_label!);
        }
      } else {
        setActiveDataset(null);
      }
    } catch {
      setActiveDataset(null);
    } finally {
      setIsLoadingDataset(false);
    }
  }, [year, selectedCampus]);

  const fetchPeriods = useCallback(async () => {
    setIsLoadingPeriods(true);
    try {
      const res = await getAllPeriods();
      const sorted = [...res.periods].sort((a, b) =>
        (b.period_end_year ?? 0) - (a.period_end_year ?? 0)
      );
      setPeriods(sorted);

      let years = res.years || [];
      if (!years || years.length === 0) {
        const yearsSet = new Set<number>();
        sorted.forEach((p) => {
          if (p.period_start_year) yearsSet.add(p.period_start_year);
          if (p.period_end_year) yearsSet.add(p.period_end_year);
        });
        years = Array.from(yearsSet).sort((a, b) => a - b);
      }
      setAnalyticalYears(years);

      const maxAvailableYear = years.length > 0 ? Math.max(...years) : undefined;

      // Auto-select the most recent period with an active dataset
      const activePeriod = sorted.find((p) => p.active_dataset_id);
      if (activePeriod && isValidPeriodLabel(activePeriod.academic_label)) {
        setActivePeriodLabel(activePeriod.academic_label);
        if (activePeriod.period_end_year) {
          setYearState(activePeriod.period_end_year);
        } else if (maxAvailableYear) {
          setYearState(maxAvailableYear);
        }
      } else if (sorted.length > 0 && isValidPeriodLabel(sorted[0].academic_label)) {
        setActivePeriodLabel(sorted[0].academic_label);
        if (sorted[0].period_end_year) {
          setYearState(sorted[0].period_end_year);
        } else if (maxAvailableYear) {
          setYearState(maxAvailableYear);
        }
      } else if (maxAvailableYear) {
        setYearState(maxAvailableYear);
      }
    } catch {
      setPeriods([]);
      setAnalyticalYears([]);
    } finally {
      setIsLoadingPeriods(false);
    }
  }, []);

  const fetchFilterOptions = useCallback(async (targetYear?: number, targetCampus?: string, targetSession?: string) => {
    try {
      const yr = targetYear !== undefined ? targetYear : year;
      const cmp = targetCampus !== undefined ? targetCampus : selectedCampus;
      const sess = targetSession !== undefined ? targetSession : (activePeriodLabel || (yr ? String(yr) : undefined));
      const opts = await getDashboardFilterOptions(
        sess !== "all" ? sess : undefined,
        cmp !== "all" ? cmp : undefined,
        yr ? [yr] : undefined
      );
      if (opts?.campuses && opts.campuses.length > 0) {
        const normalized = Array.from(
          new Set(
            opts.campuses.map(
              (c) => c.charAt(0).toUpperCase() + c.slice(1).toLowerCase()
            )
          )
        ).sort();
        setAvailableCampuses(normalized);
      }
      if (opts?.date_range) {
        let range = opts.date_range;

        // Grounding guard: If remote API returned 2024/2025 dates for Session 2026 due to legacy cache,
        // correctly ground to Session 2026's dataset bounds (2025-05-01 to 2026-09-10).
        if (yr === 2026 && range.max_date < "2026-01-01") {
          range = {
            min_date: "2025-05-01",
            max_date: "2026-09-10",
            default_from: "2025-11-01",
            default_to: "2026-09-10",
          };
        } else if (yr === 2026 && range.max_date > "2026-09-10") {
          range = {
            ...range,
            max_date: "2026-09-10",
            default_to: "2026-09-10",
          };
        } else if (yr === 2025 && range.min_date > "2024-11-01") {
          range = {
            min_date: "2024-07-01",
            max_date: "2025-10-31",
            default_from: "2024-11-01",
            default_to: "2025-10-31",
          };
        }

        setDateRangeLimits(range);

        // Ground date inputs to the session's active academic period (1 Nov to dataset max)
        setFromDate(range.default_from || range.min_date);
        setToDate(range.max_date);

        // Reset applied dates so new session loads its full, authentic scope
        setAppliedFromDate(null);
        setAppliedToDate(null);
      }
      return opts;
    } catch {
      // Keep defaults
    }
  }, [year, selectedCampus, activePeriodLabel]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchActiveDataset();
      fetchPeriods();
      fetchFilterOptions();
    }, 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyDateRange = useCallback(() => {
    if (!fromDate && !toDate) {
      setAppliedFromDate(null);
      setAppliedToDate(null);
      setDateRangeError(null);
      return true;
    }
    if (!fromDate || !toDate) {
      setDateRangeError("Both From Date and To Date are required.");
      return false;
    }
    if (fromDate > toDate) {
      setDateRangeError("From Date cannot be later than To Date.");
      return false;
    }
    // Strict enforcement: cannot query outside dataset bounds
    if (dateRangeLimits?.min_date && fromDate < dateRangeLimits.min_date) {
      setDateRangeError(`Dataset starts on ${dateRangeLimits.min_date}. Please select a date on or after this.`);
      return false;
    }
    if (dateRangeLimits?.max_date && toDate > dateRangeLimits.max_date) {
      setDateRangeError(`Dataset ends on ${dateRangeLimits.max_date}. Please select a date on or before this.`);
      return false;
    }
    setDateRangeError(null);
    setAppliedFromDate(fromDate);
    setAppliedToDate(toDate);
    return true;
  }, [fromDate, toDate, dateRangeLimits]);

  const resetDateRange = useCallback(() => {
    if (dateRangeLimits) {
      setFromDate(dateRangeLimits.default_from || dateRangeLimits.min_date);
      setToDate(dateRangeLimits.max_date);
    } else {
      setFromDate("");
      setToDate("");
    }
    setAppliedFromDate(null);
    setAppliedToDate(null);
    setDateRangeError(null);
  }, [dateRangeLimits]);

  const setSelectedCampus = (c: string) => {
    setSelectedCampusState(c);
    fetchActiveDataset(year, c);
    fetchFilterOptions(year, c);
  };

  const setYear = (y: number) => {
    setYearState(y);
    const matchingPeriod = periods.find((p) => p.period_end_year === y || p.period_start_year === y);
    if (matchingPeriod) {
      setActivePeriodLabel(matchingPeriod.academic_label);
    }
    // Cleanly reset applied date range so switching sessions queries full data for the new session
    setAppliedFromDate(null);
    setAppliedToDate(null);
    setDateRangeError(null);
    fetchActiveDataset(y, selectedCampus);
    fetchFilterOptions(y, selectedCampus, matchingPeriod?.academic_label || String(y));
  };

  const triggerRefresh = () => {
    dashboardCache.invalidate();
    setRefreshTrigger((prev) => prev + 1);
    fetchActiveDataset(year, selectedCampus);
    fetchPeriods();
  };

  /**
   * Targeted cache invalidation: only flush cache entries containing the given year/campus.
   * Other years' cached data is preserved for instant navigation.
   */
  const invalidateCacheForYear = (targetYear: number, campus?: string) => {
    dashboardCache.invalidateTargeted({ year: targetYear, campus });
  };

  /**
   * Called after dataset upload/delete/toggle. Performs targeted invalidation
   * for the affected year/campus (if known) and refreshes period metadata.
   * Falls back to global invalidation if no specific year is provided.
   */
  const notifyDatasetChange = (affectedYear?: number, affectedCampus?: string) => {
    if (affectedYear) {
      dashboardCache.invalidateTargeted({ year: affectedYear, campus: affectedCampus });
    } else {
      // Unknown affected year — invalidate all to be safe
      dashboardCache.invalidate();
    }
    setRefreshTrigger((prev) => prev + 1);
    fetchActiveDataset(affectedYear ?? year, affectedCampus ?? selectedCampus);
    fetchPeriods();
  };

  // Sync class name on <html> element for Tailwind mode compatibility
  useEffect(() => {
    const root = window.document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [theme]);

  return (
    <AppContext.Provider
      value={{
        theme,
        toggleTheme,
        activeDataset,
        isLoadingDataset,
        fetchActiveDataset,
        selectedCampus,
        setSelectedCampus,
        availableCampuses,
        setAvailableCampuses,
        year,
        setYear,
        periods,
        analyticalYears,
        isLoadingPeriods,
        fetchPeriods,
        activePeriodLabel,
        setActivePeriodLabel,
        seededPrompt,
        setSeededPrompt,
        seededPeriodA,
        setSeededPeriodA,
        seededPeriodB,
        setSeededPeriodB,
        refreshTrigger,
        triggerRefresh,
        invalidateCacheForYear,
        notifyDatasetChange,
        fromDate,
        setFromDate,
        toDate,
        setToDate,
        appliedFromDate,
        appliedToDate,
        dateRangeLimits,
        setDateRangeLimits,
        dateRangeError,
        applyDateRange,
        resetDateRange,
        fetchFilterOptions,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
};

export const useAppContext = useApp;
