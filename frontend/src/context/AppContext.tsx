"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { getActiveDataset, getAllPeriods, ActiveDatasetInfo, PeriodSummary } from "../lib/api";

/**
 * Guard: only accept labels matching the academic period pattern YYYY-YY.
 * Rejects UUIDs, checksums, numeric-only, or empty strings.
 */
function isValidPeriodLabel(label: string | null | undefined): boolean {
  if (!label) return false;
  return /^\d{4}-\d{2}$/.test(label.trim());
}

export type ThemeType = "light" | "dark";

interface AppContextType {
  theme: ThemeType;
  toggleTheme: () => void;
  activeDataset: ActiveDatasetInfo | null;
  isLoadingDataset: boolean;
  fetchActiveDataset: () => Promise<void>;
  // Period-aware year tracking
  year: number;
  setYear: (y: number) => void;
  // All available academic periods from the server
  periods: PeriodSummary[];
  analyticalYears: number[];
  isLoadingPeriods: boolean;
  fetchPeriods: () => Promise<void>;
  // Currently selected academic period label (e.g. "2025-26")
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

  const fetchActiveDataset = useCallback(async () => {
    setIsLoadingDataset(true);
    try {
      const res = await getActiveDataset();
      if (res.active && res.dataset) {
        setActiveDataset(res.dataset);
        // Use the dataset's own academic_label as the source of truth
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
  }, []);

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

  useEffect(() => {
    setTimeout(() => {
      fetchActiveDataset();
      fetchPeriods();
    }, 0);
  }, [fetchActiveDataset, fetchPeriods]);

  const setYear = (y: number) => {
    setYearState(y);
    // When year changes, update activePeriodLabel to match
    const matchingPeriod = periods.find((p) => p.period_end_year === y);
    if (matchingPeriod) {
      setActivePeriodLabel(matchingPeriod.academic_label);
    }
  };

  const triggerRefresh = () => {
    setRefreshTrigger((prev) => prev + 1);
    fetchActiveDataset();
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
