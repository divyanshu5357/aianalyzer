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

      // Auto-select the most recent period with an active dataset
      const activePeriod = sorted.find((p) => p.active_dataset_id);
      if (activePeriod && isValidPeriodLabel(activePeriod.academic_label)) {
        setActivePeriodLabel(activePeriod.academic_label);
        if (activePeriod.period_end_year) {
          setYearState(activePeriod.period_end_year);
        }
      } else if (sorted.length > 0 && isValidPeriodLabel(sorted[0].academic_label)) {
        setActivePeriodLabel(sorted[0].academic_label);
        if (sorted[0].period_end_year) {
          setYearState(sorted[0].period_end_year);
        }
      }
    } catch {
      setPeriods([]);
      setAnalyticalYears([]);
    } finally {
      setIsLoadingPeriods(false);
    }
  }, []);

  const fetchFilterOptions = useCallback(async () => {
    try {
      const opts = await getDashboardFilterOptions();
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
        setDateRangeLimits(opts.date_range);
      }
    } catch {
      // Keep defaults
    }
  }, []);

  useEffect(() => {
    setTimeout(() => {
      fetchActiveDataset();
      fetchPeriods();
      fetchFilterOptions();
    }, 0);
  }, [fetchActiveDataset, fetchPeriods, fetchFilterOptions]);

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
    setDateRangeError(null);
    setAppliedFromDate(fromDate);
    setAppliedToDate(toDate);
    return true;
  }, [fromDate, toDate]);

  const resetDateRange = useCallback(() => {
    setFromDate("");
    setToDate("");
    setAppliedFromDate(null);
    setAppliedToDate(null);
    setDateRangeError(null);
  }, []);

  const setSelectedCampus = (c: string) => {
    setSelectedCampusState(c);
    fetchActiveDataset(year, c);
  };

  const setYear = (y: number) => {
    setYearState(y);
    const matchingPeriod = periods.find((p) => p.period_end_year === y || p.period_start_year === y);
    if (matchingPeriod) {
      setActivePeriodLabel(matchingPeriod.academic_label);
    }
    resetDateRange();
    fetchActiveDataset(y, selectedCampus);
  };

  const triggerRefresh = () => {
    dashboardCache.invalidate();
    setRefreshTrigger((prev) => prev + 1);
    fetchActiveDataset(year, selectedCampus);
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
