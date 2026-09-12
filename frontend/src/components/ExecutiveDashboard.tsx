"use client";

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Users,
  Target,
  Award,
  ChevronRight,
  Database,
  AlertCircle,
  MessageSquare,
  Sparkles,
  RotateCcw,
  Building2,
  Loader2,
  X,
  FileText,
  Globe,
  MapPin,
  Calendar,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LabelList,
} from "recharts";
import { useApp } from "../context/AppContext";
import {
  getDashboardOverview,
  getDashboardInsights,
  getEntityDetail,
  getDashboardMonthlyTrend,
  getDashboardPerformanceRankings,
  getDashboardFilterOptions,
  getAdmissionsByGender,
  getAdmissionsByState,
  DashboardFilters,
  DashboardFilterOptionsResponse,
  OverviewResponse,
  InsightItem,
  EntityDetailResponse,
  MonthlyTrendItem,
  PerformanceRankingsResponse,
  GenderAdmissionsResponse,
  StateAdmissionsResponse,
  ActiveDatasetInfo,
  GenderMonthItem,
  StateAdmissionItem,
  API_BASE_URL,
} from "../lib/api";
import dashboardCache from "../lib/cache/dashboardCache";
import { prefetchAdjacentPages } from "../lib/cache/prefetch";
import IndiaStateMap from "./maps/IndiaStateMap";

export type NavTab = "dashboard" | "upload" | "analytics" | "sources" | "chat";

interface ExecutiveDashboardProps {
  activeDataset: ActiveDatasetInfo | null;
  onNavigateToTab: (tab: NavTab) => void;
  onSeedChatPrompt: (prompt: string) => void;
}

const buildDashKey = (metricName: string, filters: DashboardFilters, extra?: string) => {
  return dashboardCache.buildKey(`dashboard:${metricName}`, {
    campus: filters.campus || "all",
    year: filters.years?.[0] || "all",
    from_date: filters.from_date || "",
    to_date: filters.to_date || "",
    extra: extra || "",
  });
};

export const ExecutiveDashboard: React.FC<ExecutiveDashboardProps> = ({
  activeDataset,
  onNavigateToTab,
  onSeedChatPrompt,
}) => {
  const {
    theme,
    selectedCampus,
    setSelectedCampus,
    availableCampuses,
    year,
    refreshTrigger,
    fromDate,
    setFromDate,
    toDate,
    setToDate,
    appliedFromDate,
    appliedToDate,
    setDateRangeLimits,
  } = useApp();
  const isDark = theme === "dark";

  // Active filters object
  const currentFilters: DashboardFilters = useMemo(() => {
    return {
      campus: selectedCampus !== "all" ? selectedCampus : undefined,
      years: year ? [year] : undefined,
      from_date: appliedFromDate || undefined,
      to_date: appliedToDate || undefined,
    };
  }, [selectedCampus, year, appliedFromDate, appliedToDate]);

  const [rankingsDimension, setRankingsDimension] = useState<string>("program");
  const [mainMetric, setMainMetric] = useState<"admissions" | "leads" | "cucet" | "conversion_rate">("leads");

  // Synchronous peek keys for instant render on navigation (<5ms)
  const initialOverviewKey = useMemo(() => buildDashKey("overview", currentFilters), [currentFilters]);
  const initialInsightsKey = useMemo(() => buildDashKey("insights", currentFilters), [currentFilters]);
  const initialGenderKey = useMemo(() => buildDashKey("gender", currentFilters), [currentFilters]);
  const initialStateKey = useMemo(() => buildDashKey("indiaStates", currentFilters), [currentFilters]);
  const initialRankingsKey = useMemo(() => buildDashKey("rankings", currentFilters, rankingsDimension), [currentFilters, rankingsDimension]);
  const initialTrendKey = useMemo(() => buildDashKey("monthlyTrend", currentFilters, mainMetric), [currentFilters, mainMetric]);

  // Options & Data State (initialized from cache if returning from navigation)
  const [filterOptions, setFilterOptions] = useState<DashboardFilterOptionsResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(() => dashboardCache.peek<OverviewResponse>(initialOverviewKey));
  const [insights, setInsights] = useState<InsightItem[]>(() => dashboardCache.peek<InsightItem[]>(initialInsightsKey) || []);
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrendItem[]>(() => dashboardCache.peek<MonthlyTrendItem[]>(initialTrendKey) || []);
  const [rankings, setRankings] = useState<PerformanceRankingsResponse | null>(() => dashboardCache.peek<PerformanceRankingsResponse>(initialRankingsKey));

  const [isLoading, setIsLoading] = useState<boolean>(() => !dashboardCache.peek(initialOverviewKey));
  const [error, setError] = useState<string | null>(null);
  const [loadVersion, setLoadVersion] = useState(0);

  // Sync refresh trigger
  useEffect(() => {
    if (refreshTrigger > 0) {
      setLoadVersion((prev) => prev + 1);
    }
  }, [refreshTrigger]);

  // Detail Drawer State
  const [selectedEntity, setSelectedEntity] = useState<{ dimension: string; value: string } | null>(null);
  const [entityDetail, setEntityDetail] = useState<EntityDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Phase 11.7B: Gender and Geographic Analytics State
  const [genderMonths, setGenderMonths] = useState<GenderMonthItem[]>(() => dashboardCache.peek<GenderAdmissionsResponse>(initialGenderKey)?.months || []);
  const [genderCategories, setGenderCategories] = useState<string[]>(() => dashboardCache.peek<GenderAdmissionsResponse>(initialGenderKey)?.gender_categories || []);
  const [totalGenderAdmissions, setTotalGenderAdmissions] = useState<number>(() => dashboardCache.peek<GenderAdmissionsResponse>(initialGenderKey)?.total_admissions || 0);
  const [genderLoading, setGenderLoading] = useState<boolean>(() => !dashboardCache.peek(initialGenderKey));

  const [indiaStatesData, setIndiaStatesData] = useState<StateAdmissionItem[]>(() => dashboardCache.peek<StateAdmissionsResponse>(initialStateKey)?.states || []);
  const [totalIndiaAdmissions, setTotalIndiaAdmissions] = useState<number>(() => dashboardCache.peek<StateAdmissionsResponse>(initialStateKey)?.total_india_admissions || 0);
  const [hasPyStateData, setHasPyStateData] = useState<boolean>(() => dashboardCache.peek<StateAdmissionsResponse>(initialStateKey)?.has_py_data ?? true);
  const [stateComparisonYear, setStateComparisonYear] = useState<number | null>(() => dashboardCache.peek<StateAdmissionsResponse>(initialStateKey)?.comparison_year ?? null);
  const [indiaStatesLoading, setIndiaStatesLoading] = useState<boolean>(() => !dashboardCache.peek(initialStateKey));

  // Data Control Modal State
  const [showDataControlModal, setShowDataControlModal] = useState(false);
  const [dataControlHistory, setDataControlHistory] = useState<any[]>([]);
  const [dataControlLoading, setDataControlLoading] = useState(false);

  const fetchControlHistory = () => {
    setDataControlLoading(true);
    fetch(`${API_BASE_URL}/api/dashboard/data-control`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (data?.history) {
          setDataControlHistory(data.history);
        }
        setDataControlLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch data control history:", err);
        setDataControlLoading(false);
      });
  };

  const fromDateRef = useRef(fromDate);
  fromDateRef.current = fromDate;
  const toDateRef = useRef(toDate);
  toDateRef.current = toDate;

  // Load dynamic filter options (non-blocking)
  const loadFilterOptions = useCallback(async (signal?: AbortSignal) => {
    try {
      const opts = await getDashboardFilterOptions(
        undefined,
        selectedCampus !== "all" ? selectedCampus : undefined,
        undefined,
        { signal }
      );
      setFilterOptions(opts);
      if (opts?.date_range) {
        setDateRangeLimits(opts.date_range);
        if (!fromDateRef.current && opts.date_range.default_from) {
          setFromDate(opts.date_range.default_from);
        }
        if (!toDateRef.current && opts.date_range.default_to) {
          setToDate(opts.date_range.default_to);
        }
      }
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        console.error("Failed to load filter options:", err);
      }
    }
  }, [selectedCampus, setDateRangeLimits, setFromDate, setToDate]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    const ovKey = buildDashKey("overview", currentFilters);
    const inKey = buildDashKey("insights", currentFilters);
    const genKey = buildDashKey("gender", currentFilters);
    const stKey = buildDashKey("indiaStates", currentFilters);

    const cachedOv = dashboardCache.peek<OverviewResponse>(ovKey);
    if (cachedOv) {
      setOverview(cachedOv);
      setIsLoading(false);
      prefetchAdjacentPages({
        academic_year: currentFilters.years?.[0],
        campus: currentFilters.campus,
        from_date: currentFilters.from_date,
        to_date: currentFilters.to_date,
      });
    } else {
      setIsLoading(true);
    }

    const cachedIn = dashboardCache.peek<InsightItem[]>(inKey);
    if (cachedIn) {
      setInsights(cachedIn);
    }

    const cachedGen = dashboardCache.peek<GenderAdmissionsResponse>(genKey);
    if (cachedGen) {
      setGenderMonths(cachedGen.months || []);
      setGenderCategories(cachedGen.gender_categories || []);
      setTotalGenderAdmissions(cachedGen.total_admissions || 0);
      setGenderLoading(false);
    } else {
      setGenderLoading(true);
    }

    const cachedSt = dashboardCache.peek<StateAdmissionsResponse>(stKey);
    if (cachedSt) {
      setIndiaStatesData(cachedSt.states || []);
      setTotalIndiaAdmissions(cachedSt.total_india_admissions || 0);
      setHasPyStateData(cachedSt.has_py_data ?? true);
      setStateComparisonYear(cachedSt.comparison_year ?? null);
      setIndiaStatesLoading(false);
    } else {
      setIndiaStatesLoading(true);
    }

    setError(null);
    loadFilterOptions(signal);

    const force = loadVersion > 0;

    dashboardCache
      .fetchWithCache(ovKey, () => getDashboardOverview(currentFilters, { signal }), { forceRefresh: force })
      .then((overviewData) => {
        setOverview(overviewData);
        setIsLoading(false);
        prefetchAdjacentPages({
          academic_year: currentFilters.years?.[0],
          campus: currentFilters.campus,
          from_date: currentFilters.from_date,
          to_date: currentFilters.to_date,
        });
      })
      .catch((err) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to load dashboard overview:", err);
          setError(err?.message || "Failed to load executive dashboard aggregation.");
          setIsLoading(false);
        }
      });

    dashboardCache
      .fetchWithCache(inKey, () => getDashboardInsights(currentFilters, { signal }), { forceRefresh: force })
      .then((insightsData) => {
        setInsights(insightsData);
      })
      .catch((err) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to load dashboard insights:", err);
        }
      });

    dashboardCache
      .fetchWithCache(genKey, () => getAdmissionsByGender(currentFilters, { signal }), { forceRefresh: force })
      .then((genderRes) => {
        setGenderMonths(genderRes?.months || []);
        setGenderCategories(genderRes?.gender_categories || []);
        setTotalGenderAdmissions(genderRes?.total_admissions || 0);
        setGenderLoading(false);
      })
      .catch((err) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to load admissions by gender:", err);
          setGenderLoading(false);
        }
      });

    dashboardCache
      .fetchWithCache(stKey, () => getAdmissionsByState(currentFilters, { signal }), { forceRefresh: force })
      .then((stateRes) => {
        setIndiaStatesData(stateRes?.states || []);
        setTotalIndiaAdmissions(stateRes?.total_india_admissions || 0);
        setHasPyStateData(stateRes?.has_py_data ?? true);
        setStateComparisonYear(stateRes?.comparison_year ?? null);
        setIndiaStatesLoading(false);
      })
      .catch((err) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to load admissions by state:", err);
          setIndiaStatesLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [loadVersion, currentFilters, loadFilterOptions]);

  // Refetch performance rankings independently when rankings dimension tab or filters change
  useEffect(() => {
    const controller = new AbortController();
    const rankKey = buildDashKey("rankings", currentFilters, rankingsDimension);
    const cachedRank = dashboardCache.peek<PerformanceRankingsResponse>(rankKey);
    if (cachedRank) {
      setRankings(cachedRank);
    }
    dashboardCache
      .fetchWithCache(
        rankKey,
        () => getDashboardPerformanceRankings(rankingsDimension, currentFilters, { signal: controller.signal }),
        { forceRefresh: loadVersion > 0 }
      )
      .then((rankingsData) => setRankings(rankingsData))
      .catch((err) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to load performance rankings:", err);
        }
      });
    return () => controller.abort();
  }, [rankingsDimension, currentFilters, loadVersion]);

  // Refetch monthly trend when metric tab changes
  useEffect(() => {
    const controller = new AbortController();
    const trendKey = buildDashKey("monthlyTrend", currentFilters, mainMetric);
    const cachedTrend = dashboardCache.peek<MonthlyTrendItem[]>(trendKey);
    if (cachedTrend) {
      setMonthlyTrend(cachedTrend);
    }
    dashboardCache
      .fetchWithCache(
        trendKey,
        () => getDashboardMonthlyTrend(mainMetric, currentFilters, { signal: controller.signal }),
        { forceRefresh: loadVersion > 0 }
      )
      .then((data) => setMonthlyTrend(data))
      .catch((err) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to refresh monthly trend:", err);
        }
      });
    return () => controller.abort();
  }, [mainMetric, currentFilters, loadVersion]);

  // Load entity detail when an entity is clicked
  useEffect(() => {
    if (!selectedEntity) return;

    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError(null);

    getEntityDetail(selectedEntity.dimension, selectedEntity.value, currentFilters, {
      signal: controller.signal,
    })
      .then((res: any) => {
        setEntityDetail(res);
        setDetailLoading(false);
      })
      .catch((err: any) => {
        if (err?.name !== "AbortError") {
          console.error("Failed to load entity detail:", err);
          setDetailError("Failed to fetch entity drilldown analysis.");
          setDetailLoading(false);
        }
      });

    return () => controller.abort();
  }, [selectedEntity, currentFilters]);

  const handleDimensionChange = (dim: "program" | "state" | "source" | "emp" | "campus") => {
    setRankingsDimension(dim);
  };

  const handleEntityClick = (dimension: string, value: string) => {
    setSelectedEntity({ dimension, value });
  };

  const handleAskAIAboutEntity = (dimension: string, value: string) => {
    if (onSeedChatPrompt) {
      onSeedChatPrompt(`Analyze the performance trend and key drivers for ${dimension} '${value}'.`);
    }
  };

  // Helper for displaying diff badge
  const renderMetricDiff = (
    change: number | null | undefined,
    growthPct: number | null | undefined,
    isRate: boolean = false
  ) => {
    if (change === undefined || change === null) return null;

    const isPositive = change > 0;
    const isNegative = change < 0;
    const colorClass = isPositive
      ? "text-emerald-500 font-bold"
      : isNegative
      ? "text-rose-500 font-bold"
      : "text-slate-400 font-medium";

    let textStr = "";
    if (isRate) {
      const formattedPp = `${isPositive ? "+" : ""}${change} pp`;
      textStr = formattedPp;
    } else {
      const formattedNum = `${isPositive ? "+" : ""}${(change ?? 0).toLocaleString()}`;
      const formattedPct = growthPct !== null && growthPct !== undefined ? `${isPositive ? "+" : ""}${growthPct}%` : "N/A";
      textStr = `${formattedNum} (${formattedPct})`;
    }

    return (
      <span className={`inline-flex items-center gap-1 text-xs ${colorClass}`}>
        {isPositive && <TrendingUp className="w-3.5 h-3.5" />}
        {isNegative && <TrendingDown className="w-3.5 h-3.5" />}
        {!isPositive && !isNegative && <Minus className="w-3.5 h-3.5 text-slate-400" />}
        {textStr}
      </span>
    );
  };

  if (isLoading && !overview) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        <span className={`text-xs font-semibold ${isDark ? "text-slate-400" : "text-slate-600"}`}>
          Aggregating multi-campus analytics engine...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-rose-500/10 border border-rose-500/20 rounded-2xl text-rose-500 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-rose-500" />
          <span className="text-xs font-semibold">{error}</span>
        </div>
        <button
          onClick={() => {
            setIsLoading(true);
            setError(null);
            setLoadVersion((version) => version + 1);
          }}
          className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-lg transition-colors"
        >
          Retry Aggregation
        </button>
      </div>
    );
  }

  const cyYear = overview?.current_year;
  const pyYear = overview?.previous_year;
  const campusLabel = selectedCampus === "all" ? "All Campuses" : `${selectedCampus} Campus`;
  const datasetCount = overview?.dataset_count ?? 0;

  return (
    <div className="space-y-6 pb-12">
      {/* Executive Scope Header Banner */}
      <div className={`p-6 rounded-2xl border transition-all ${
        isDark 
          ? "bg-gradient-to-r from-[#111A2E] via-[#10182B] to-[#0D1424] border-[#1E2B45] shadow-lg shadow-black/20" 
          : "bg-gradient-to-r from-white via-slate-50/60 to-white border-slate-200/90 shadow-sm"
      }`}>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                Active Analytics Scope
              </span>
              <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
                isDark ? "bg-slate-800/80 border-slate-700/60 text-slate-300" : "bg-slate-100 border-slate-200 text-slate-700"
              }`}>
                🏢 {campusLabel}
              </span>
              <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
                isDark ? "bg-slate-800/80 border-slate-700/60 text-slate-300" : "bg-slate-100 border-slate-200 text-slate-700"
              }`}>
                📊 {datasetCount} Active Dataset{datasetCount !== 1 ? "s" : ""}
              </span>
              {(appliedFromDate || appliedToDate || overview?.from_date || overview?.to_date) && (
                <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
                  isDark 
                    ? "bg-indigo-950/60 border-indigo-800/80 text-indigo-300" 
                    : "bg-indigo-50 border-indigo-200 text-indigo-700"
                }`}>
                  <Calendar className="w-3.5 h-3.5 text-indigo-500" />
                  <span>
                    {overview?.from_date || appliedFromDate || "Start"} → {overview?.to_date || appliedToDate || "End"}
                  </span>
                  {overview?.py_from_date && overview?.py_to_date && (
                    <span className={`text-[10px] ml-1 font-medium ${isDark ? "text-indigo-400/90" : "text-indigo-600/90"}`}>
                      (PY: {overview.py_from_date} → {overview.py_to_date})
                    </span>
                  )}
                </span>
              )}
            </div>
            <h1 className={`text-2xl lg:text-3xl font-black tracking-tight mt-2 ${isDark ? "text-white" : "text-slate-900"}`}>
              {selectedCampus === "all" ? "University Admissions & Conversion Overview" : `${selectedCampus} Campus Admissions & Conversion`}
            </h1>
            <p className={`text-xs mt-1 font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}>
              {cyYear && pyYear ? `Intake trajectory comparing Academic Year ${cyYear} vs ${pyYear}` : "Comprehensive intake trajectory, lead velocity, and CUCET conversion performance"}
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={() => {
                fetchControlHistory();
                setShowDataControlModal(true);
              }}
              className={`px-3.5 py-2 rounded-xl border text-xs font-bold flex items-center gap-2 transition-all shadow-xs ${
                isDark
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-300 hover:text-white hover:border-indigo-500/50 hover:bg-slate-800/60"
                  : "bg-white border-slate-200 text-slate-700 hover:text-slate-900 hover:border-indigo-400 hover:bg-slate-50"
              }`}
            >
              <Database className="w-3.5 h-3.5 text-indigo-500" />
              <span>Data Control</span>
            </button>
          </div>
        </div>
      </div>

      {/* 4 Primary KPI Cards (Reshuffled: Leads -> CUCET -> Admissions -> Conversion Rate with Interactive Click & Sub-metrics) */}
      {overview && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* 1. Leads Card */}
          <div
            onClick={() => setMainMetric("leads")}
            role="button"
            tabIndex={0}
            className={`p-5 rounded-2xl border transition-all cursor-pointer transform hover:-translate-y-0.5 select-none ${
              mainMetric === "leads"
                ? isDark
                  ? "bg-[#161F38] border-indigo-500/70 ring-2 ring-indigo-500/50 shadow-lg shadow-indigo-500/10"
                  : "bg-indigo-50/60 border-indigo-300 ring-2 ring-indigo-500/40 shadow-md"
                : isDark
                ? "bg-[#131B2E] border-[#1E293B] hover:border-slate-700"
                : "bg-white border-slate-200 shadow-sm hover:border-slate-300"
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-extrabold uppercase tracking-wider ${
                  isDark ? "text-slate-400" : "text-slate-500"
                }`}>
                  Leads
                </span>
                {mainMetric === "leads" && (
                  <span className="px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider rounded-md bg-indigo-500 text-white animate-pulse">
                    Active
                  </span>
                )}
              </div>
              <div className="w-8 h-8 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="space-y-1">
              <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                {(overview?.kpis?.leads?.cy ?? 0).toLocaleString()}
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                  {overview?.kpis?.leads?.py != null ? `PY: ${(overview.kpis.leads.py ?? 0).toLocaleString()}` : "Single Year Scope"}
                </span>
                {renderMetricDiff(overview?.kpis?.leads?.change ?? 0, overview?.kpis?.leads?.growth_pct ?? null)}
              </div>
            </div>
            {/* Sub-metric: Successful Fast Track ID Generation */}
            {overview?.kpis?.leads?.sub_metric && (
              <div className={`mt-3 pt-2.5 border-t flex items-center justify-between text-[11px] ${
                isDark ? "border-[#1E293B]" : "border-slate-100"
              }`}>
                <div className="flex items-center gap-1.5 font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping" />
                  <span className={isDark ? "text-slate-300" : "text-slate-600"}>
                    Fast Track IDs:
                  </span>
                </div>
                <div className="font-extrabold text-indigo-500 dark:text-indigo-400 flex items-center gap-1">
                  <span>{(overview.kpis.leads.sub_metric.cy ?? 0).toLocaleString()}</span>
                  {overview.kpis.leads.sub_metric.py != null && (
                    <span className="text-[10px] font-normal text-slate-400">
                      (PY: {(overview.kpis.leads.sub_metric.py ?? 0).toLocaleString()})
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 2. CUCET Registrations Card */}
          {overview?.has_cucet && overview?.kpis?.cucet ? (
            <div
              onClick={() => setMainMetric("cucet")}
              role="button"
              tabIndex={0}
              className={`p-5 rounded-2xl border transition-all cursor-pointer transform hover:-translate-y-0.5 select-none ${
                mainMetric === "cucet"
                  ? isDark
                    ? "bg-[#181C38] border-violet-500/70 ring-2 ring-violet-500/50 shadow-lg shadow-violet-500/10"
                    : "bg-violet-50/60 border-violet-300 ring-2 ring-violet-500/40 shadow-md"
                  : isDark
                  ? "bg-[#131B2E] border-[#1E293B] hover:border-slate-700"
                  : "bg-white border-slate-200 shadow-sm hover:border-slate-300"
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-extrabold uppercase tracking-wider ${
                    isDark ? "text-slate-400" : "text-slate-500"
                  }`}>
                    CUCET Registrations
                  </span>
                  {mainMetric === "cucet" && (
                    <span className="px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider rounded-md bg-violet-500 text-white animate-pulse">
                      Active
                    </span>
                  )}
                </div>
                <div className="w-8 h-8 rounded-xl bg-violet-500/10 text-violet-500 flex items-center justify-center">
                  <Award className="w-4 h-4" />
                </div>
              </div>
              <div className="space-y-1">
                <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                  {(overview.kpis.cucet.cy ?? 0).toLocaleString()}
                </div>
                <div className="flex items-center justify-between text-xs pt-1">
                  <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                    {overview.kpis.cucet.py != null ? `PY: ${(overview.kpis.cucet.py ?? 0).toLocaleString()}` : "Single Year Scope"}
                  </span>
                  {renderMetricDiff(overview.kpis.cucet.change ?? 0, overview.kpis.cucet.growth_pct ?? null)}
                </div>
              </div>
              {/* Sub-metric: Total Eligible for Scholarship */}
              {overview?.kpis?.cucet?.sub_metric && (
                <div className={`mt-3 pt-2.5 border-t flex items-center justify-between text-[11px] ${
                  isDark ? "border-[#1E293B]" : "border-slate-100"
                }`}>
                  <div className="flex items-center gap-1.5 font-bold">
                    <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-ping" />
                    <span className={isDark ? "text-slate-300" : "text-slate-600"}>
                      Scholarship Eligible:
                    </span>
                  </div>
                  <div className="font-extrabold text-violet-500 dark:text-violet-400 flex items-center gap-1">
                    <span>{(overview.kpis.cucet.sub_metric.cy ?? 0).toLocaleString()}</span>
                    {overview.kpis.cucet.sub_metric.py != null && (
                      <span className="text-[10px] font-normal text-slate-400">
                        (PY: {(overview.kpis.cucet.sub_metric.py ?? 0).toLocaleString()})
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : null}

          {/* 3. Admissions Card */}
          <div
            onClick={() => setMainMetric("admissions")}
            role="button"
            tabIndex={0}
            className={`p-5 rounded-2xl border transition-all cursor-pointer transform hover:-translate-y-0.5 select-none ${
              mainMetric === "admissions"
                ? isDark
                  ? "bg-[#14223E] border-blue-500/70 ring-2 ring-blue-500/50 shadow-lg shadow-blue-500/10"
                  : "bg-blue-50/60 border-blue-300 ring-2 ring-blue-500/40 shadow-md"
                : isDark
                ? "bg-[#131B2E] border-[#1E293B] hover:border-slate-700"
                : "bg-white border-slate-200 shadow-sm hover:border-slate-300"
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-extrabold uppercase tracking-wider ${
                  isDark ? "text-slate-400" : "text-slate-500"
                }`}>
                  Admissions
                </span>
                {mainMetric === "admissions" && (
                  <span className="px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider rounded-md bg-blue-500 text-white animate-pulse">
                    Active
                  </span>
                )}
              </div>
              <div className="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center">
                <Target className="w-4 h-4" />
              </div>
            </div>
            <div className="space-y-1">
              <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                {(overview?.kpis?.admissions?.cy ?? 0).toLocaleString()}
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                  {overview?.kpis?.admissions?.py != null ? `PY: ${(overview.kpis.admissions.py ?? 0).toLocaleString()}` : "Single Year Scope"}
                </span>
                {renderMetricDiff(overview?.kpis?.admissions?.change ?? 0, overview?.kpis?.admissions?.growth_pct ?? null)}
              </div>
            </div>
            {/* Sub-metric: Total Active Admissions (Gross - Refunds) */}
            {overview?.kpis?.admissions?.sub_metric && (
              <div className={`mt-3 pt-2.5 border-t flex items-center justify-between text-[11px] ${
                isDark ? "border-[#1E293B]" : "border-slate-100"
              }`}>
                <div className="flex items-center gap-1.5 font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />
                  <span className={isDark ? "text-slate-300" : "text-slate-600"}>
                    Active Admissions:
                  </span>
                </div>
                <div className="font-extrabold text-blue-500 dark:text-blue-400 flex items-center gap-1">
                  <span>{(overview.kpis.admissions.sub_metric.cy ?? 0).toLocaleString()}</span>
                  {overview.kpis.admissions.sub_metric.py != null && (
                    <span className="text-[10px] font-normal text-slate-400">
                      (PY: {(overview.kpis.admissions.sub_metric.py ?? 0).toLocaleString()})
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 4. Conversion Rate Card */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className={`text-xs font-extrabold uppercase tracking-wider ${
                isDark ? "text-slate-400" : "text-slate-500"
              }`}>
                Conversion Rate
              </span>
              <div className="w-8 h-8 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
                <TrendingUp className="w-4 h-4" />
              </div>
            </div>
            <div className="space-y-1">
              <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                {overview.kpis.conversion_rate.cy}%
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                  {overview.kpis.conversion_rate.py != null ? `PY: ${overview.kpis.conversion_rate.py}%` : "Single Year Scope"}
                </span>
                {renderMetricDiff(overview.kpis.conversion_rate.change, overview.kpis.conversion_rate.growth_pct, true)}
              </div>
            </div>
            {overview?.kpis?.cucet_conversion_rate && (
              <div className={`mt-3 pt-2.5 border-t flex items-center justify-between text-[11px] ${
                isDark ? "border-[#1E293B]" : "border-slate-100"
              }`}>
                <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                  CUCET Conv Rate:
                </span>
                <span className="font-extrabold text-emerald-500">
                  {overview.kpis.cucet_conversion_rate.cy}%
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 2 Interactive Side-by-Side Monthly Trajectory Charts (Target vs Actual & PY vs CY) */}
      <div className="space-y-6">
        {/* Section Header & Shared Metric Selector */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className={`text-lg font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
              Monthly Performance & Trajectory Analysis
            </h3>
            <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
              {pyYear ? `Comparing CY ${cyYear} vs PY ${pyYear} & Targets across monthly intake periods` : `Monthly trajectory for ${cyYear}`} {selectedCampus !== "all" ? `(Filtered: ${selectedCampus})` : ""}
            </p>
          </div>

          {/* Shared Metric Selector Tabs (Admissions, Leads, CUCET) */}
          <div className={`flex items-center p-1 rounded-xl border text-xs ${
            isDark ? "bg-[#0B0F19] border-[#1E293B]" : "bg-slate-100 border-slate-200"
          }`}>
            <button
              onClick={() => setMainMetric("admissions")}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                mainMetric === "admissions"
                  ? "bg-blue-600 text-white shadow-xs"
                  : isDark
                  ? "text-slate-400 hover:text-white"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Admissions
            </button>
            <button
              onClick={() => setMainMetric("leads")}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                mainMetric === "leads"
                  ? "bg-blue-600 text-white shadow-xs"
                  : isDark
                  ? "text-slate-400 hover:text-white"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Leads
            </button>
            {overview?.has_cucet && (
              <button
                onClick={() => setMainMetric("cucet")}
                className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                  mainMetric === "cucet"
                    ? "bg-blue-600 text-white shadow-xs"
                    : isDark
                    ? "text-slate-400 hover:text-white"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                CUCET
              </button>
            )}
          </div>
        </div>

        {/* 2 Side-by-Side Chart Cards Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* CHART 1: Target vs Actual Performance */}
          <div
            className={`p-6 rounded-3xl border transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
              <div>
                <h4 className={`text-base font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
                  <span>{mainMetric === "admissions" ? "🎓" : mainMetric === "leads" ? "🟣" : "🎫"}</span>
                  Target Performance Trajectory
                </h4>
                <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Target vs CY {cyYear} Actual ({mainMetric === "admissions" ? "Admissions" : mainMetric === "leads" ? "Leads" : "CUCET"})
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs font-semibold">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-300 inline-block" /> Target
                </span>
                <span className="flex items-center gap-1.5 text-teal-600 dark:text-teal-400">
                  <span className="w-2.5 h-2.5 rounded-full bg-teal-600 inline-block" /> CY {cyYear} Actual
                </span>
              </div>
            </div>

            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyTrend} margin={{ top: 35, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#1E293B" : "#F1F5F9"} />
                  <XAxis dataKey="month" tickFormatter={(m) => (m ? m.slice(0, 3) : "")} stroke={isDark ? "#64748B" : "#94A3B8"} fontSize={11} />
                  <YAxis stroke={isDark ? "#64748B" : "#94A3B8"} fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: isDark ? "#0B0F19" : "#FFFFFF", borderColor: isDark ? "#1E293B" : "#E2E8F0", borderRadius: "12px", fontSize: "12px" }}
                    formatter={(val: any, name: any) => [typeof val === "number" ? val.toLocaleString() : (val ?? 0), name]}
                  />
                  <Bar
                    dataKey={mainMetric === "admissions" ? "target_admission" : mainMetric === "leads" ? "target_leads" : "target_cucet"}
                    name="Target"
                    fill="#6EE7B7"
                    radius={[4, 4, 0, 0]}
                  >
                    <LabelList
                      dataKey={mainMetric === "admissions" ? "target_admission" : mainMetric === "leads" ? "target_leads" : "target_cucet"}
                      content={(props: any) => {
                        const { x, y, width, value } = props;
                        if (value === undefined || value === null || value <= 0) return null;
                        const valStr = typeof value === "number" ? Math.round(value).toLocaleString() : String(value);
                        const centerX = (x || 0) + (width ? width / 2 : 0);
                        const posY = (y || 0) - 6;
                        return (
                          <text
                            x={centerX}
                            y={posY}
                            fill={isDark ? "#A7F3D0" : "#047857"}
                            fontSize={10}
                            fontWeight={800}
                            textAnchor="start"
                            transform={`rotate(-90 ${centerX} ${posY})`}
                          >
                            {valStr}
                          </text>
                        );
                      }}
                    />
                  </Bar>
                  <Bar
                    dataKey={mainMetric === "admissions" ? "cy_admission" : mainMetric === "leads" ? "cy_leads" : "cy_cucet"}
                    name={`CY ${cyYear}`}
                    fill="#0D9488"
                    radius={[4, 4, 0, 0]}
                  >
                    <LabelList
                      dataKey={mainMetric === "admissions" ? "cy_admission" : mainMetric === "leads" ? "cy_leads" : "cy_cucet"}
                      content={(props: any) => {
                        const { x, y, width, value } = props;
                        if (value === undefined || value === null || value <= 0) return null;
                        const valStr = typeof value === "number" ? Math.round(value).toLocaleString() : String(value);
                        const centerX = (x || 0) + (width ? width / 2 : 0);
                        const posY = (y || 0) - 6;
                        return (
                          <text
                            x={centerX}
                            y={posY}
                            fill={isDark ? "#6EE7B7" : "#0F766E"}
                            fontSize={10}
                            fontWeight={800}
                            textAnchor="start"
                            transform={`rotate(-90 ${centerX} ${posY})`}
                          >
                            {valStr}
                          </text>
                        );
                      }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* CHART 2: PY vs CY Historic Comparison */}
          <div
            className={`p-6 rounded-3xl border transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
              <div>
                <h4 className={`text-base font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
                  <span>{mainMetric === "admissions" ? "🎓" : mainMetric === "leads" ? "🟣" : "🎫"}</span>
                  Historic Trajectory Comparison
                </h4>
                <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Comparing CY {cyYear} vs {pyYear ? `PY ${pyYear}` : "Previous Year"} ({mainMetric === "admissions" ? "Admissions" : mainMetric === "leads" ? "Leads" : "CUCET"})
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs font-semibold">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-300 inline-block" /> PY {pyYear || ""}
                </span>
                <span className="flex items-center gap-1.5 text-indigo-500 dark:text-indigo-400">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 inline-block" /> CY {cyYear}
                </span>
              </div>
            </div>

            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyTrend} margin={{ top: 35, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#1E293B" : "#F1F5F9"} />
                  <XAxis dataKey="month" tickFormatter={(m) => (m ? m.slice(0, 3) : "")} stroke={isDark ? "#64748B" : "#94A3B8"} fontSize={11} />
                  <YAxis stroke={isDark ? "#64748B" : "#94A3B8"} fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: isDark ? "#0B0F19" : "#FFFFFF", borderColor: isDark ? "#1E293B" : "#E2E8F0", borderRadius: "12px", fontSize: "12px" }}
                    formatter={(val: any, name: any) => [typeof val === "number" ? val.toLocaleString() : (val ?? 0), name]}
                  />
                  <Bar
                    dataKey={mainMetric === "admissions" ? "py_admission" : mainMetric === "leads" ? "py_leads" : "py_cucet"}
                    name={`PY ${pyYear || ""}`}
                    fill="#6EE7B7"
                    radius={[4, 4, 0, 0]}
                  >
                    <LabelList
                      dataKey={mainMetric === "admissions" ? "py_admission" : mainMetric === "leads" ? "py_leads" : "py_cucet"}
                      content={(props: any) => {
                        const { x, y, width, value } = props;
                        if (value === undefined || value === null || value <= 0) return null;
                        const valStr = typeof value === "number" ? Math.round(value).toLocaleString() : String(value);
                        const centerX = (x || 0) + (width ? width / 2 : 0);
                        const posY = (y || 0) - 6;
                        return (
                          <text
                            x={centerX}
                            y={posY}
                            fill={isDark ? "#A7F3D0" : "#047857"}
                            fontSize={10}
                            fontWeight={800}
                            textAnchor="start"
                            transform={`rotate(-90 ${centerX} ${posY})`}
                          >
                            {valStr}
                          </text>
                        );
                      }}
                    />
                  </Bar>
                  <Bar
                    dataKey={mainMetric === "admissions" ? "cy_admission" : mainMetric === "leads" ? "cy_leads" : "cy_cucet"}
                    name={`CY ${cyYear}`}
                    fill="#6366F1"
                    radius={[4, 4, 0, 0]}
                  >
                    <LabelList
                      dataKey={mainMetric === "admissions" ? "cy_admission" : mainMetric === "leads" ? "cy_leads" : "cy_cucet"}
                      content={(props: any) => {
                        const { x, y, width, value } = props;
                        if (value === undefined || value === null || value <= 0) return null;
                        const valStr = typeof value === "number" ? Math.round(value).toLocaleString() : String(value);
                        const centerX = (x || 0) + (width ? width / 2 : 0);
                        const posY = (y || 0) - 6;
                        return (
                          <text
                            x={centerX}
                            y={posY}
                            fill={isDark ? "#818CF8" : "#4338CA"}
                            fontSize={10}
                            fontWeight={800}
                            textAnchor="start"
                            transform={`rotate(-90 ${centerX} ${posY})`}
                          >
                            {valStr}
                          </text>
                        );
                      }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* PHASE 11.7: GEOGRAPHY & GENDER ANALYTICS SECTION             */}
      {/* ============================================================ */}
      <div className="space-y-6">
        {/* Gender Breakdown (Left) & India State Admissions CY vs PY (Right) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
          {/* LEFT CARD: Admissions by Gender Monthly Bar Chart (6 cols on lg) */}
          <div
            className={`lg:col-span-6 p-6 rounded-3xl border flex flex-col justify-between transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h4 className={`text-base font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
                    <Users className="w-5 h-5 text-blue-500" />
                    Admissions by Gender
                  </h4>
                  <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Monthly admission mix by gender ({cyYear})
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300">
                    {(totalGenderAdmissions ?? 0).toLocaleString()} Total Admitted
                  </span>
                </div>
              </div>

              {/* Monthly Grouped Bar Chart */}
              {genderLoading ? (
                <div className="h-80 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                </div>
              ) : genderMonths.length === 0 ? (
                <div className="h-80 flex items-center justify-center text-slate-400 text-sm">
                  No monthly gender breakdown data available
                </div>
              ) : (
                <div className="w-full h-80 pt-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={genderMonths} margin={{ top: 15, right: 10, left: -15, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#1E293B" : "#F1F5F9"} />
                      <XAxis
                        dataKey="month"
                        stroke={isDark ? "#64748B" : "#94A3B8"}
                        fontSize={11}
                        tickLine={false}
                      />
                      <YAxis
                        stroke={isDark ? "#64748B" : "#94A3B8"}
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`)}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: isDark ? "#0B0F19" : "#FFFFFF",
                          borderColor: isDark ? "#1E293B" : "#E2E8F0",
                          borderRadius: "12px",
                          fontSize: "12px",
                          boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
                        }}
                        formatter={(val: any, name: any) => [
                          `${Number(val ?? 0).toLocaleString()} admissions`,
                          name,
                        ]}
                        labelFormatter={(label: any, payload: any) => {
                          const item = payload?.[0]?.payload;
                          return item?.month_display || label;
                        }}
                      />
                      <Legend
                        wrapperStyle={{ paddingTop: "12px", fontSize: "12px" }}
                        iconType="circle"
                      />
                      {genderCategories.map((cat, idx) => {
                        const catLower = cat.toLowerCase();
                        let barColor = "#8B5CF6"; // default purple
                        if (catLower.includes("male") && !catLower.includes("female")) barColor = "#3B82F6"; // blue
                        else if (catLower.includes("female")) barColor = "#EC4899"; // pink
                        else if (catLower.includes("unspecified")) barColor = "#94A3B8"; // slate
                        else if (catLower.includes("other")) barColor = "#10B981"; // emerald
                        else {
                          const fallbacks = ["#F59E0B", "#06B6D4", "#6366F1", "#14B8A6"];
                          barColor = fallbacks[idx % fallbacks.length];
                        }

                        return (
                          <Bar
                            key={cat}
                            dataKey={cat}
                            name={cat}
                            fill={barColor}
                            radius={[4, 4, 0, 0]}
                            maxBarSize={28}
                          />
                        );
                      })}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* RIGHT CARD: India State-wise Admissions CY vs PY Map (6 cols on lg) */}
          <div
            className={`lg:col-span-6 p-6 rounded-3xl border flex flex-col justify-between transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h4 className={`text-base font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
                    <MapPin className="w-5 h-5 text-indigo-600" />
                    India Admissions by State
                  </h4>
                  <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    State-wise admissions: CY Admissions (more adms)
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800 text-indigo-800 dark:text-indigo-300">
                    {(totalIndiaAdmissions ?? 0).toLocaleString()} India Total
                  </span>
                </div>
              </div>

              {/* Interactive India Map */}
              {indiaStatesLoading ? (
                <div className="h-80 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
                </div>
              ) : (
                <IndiaStateMap
                  statesData={indiaStatesData}
                  totalAdmissions={totalIndiaAdmissions}
                  hasPyData={hasPyStateData}
                  comparisonYear={stateComparisonYear}
                  currentYear={cyYear}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Performance Rankings & Strategic Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Rankings (2 Cols) */}
        <div
          className={`lg:col-span-2 p-6 rounded-3xl border transition-all ${
            isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
          }`}
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
            <div>
              <h3 className={`text-base font-extrabold ${isDark ? "text-white" : "text-slate-900"}`}>
                Performance Rankings
              </h3>
              <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                Top improvement drivers & decline areas
              </p>
            </div>

            <div className={`flex items-center p-1 rounded-xl border text-xs ${
              isDark ? "bg-[#0B0F19] border-[#1E293B]" : "bg-slate-100 border-slate-200"
            }`}>
              {["program", "state", "campus", "source", "counsellor"].map((d) => (
                <button
                  key={d}
                  onClick={() => handleDimensionChange(d as any)}
                  className={`px-2.5 py-1 rounded-lg font-bold capitalize transition-all ${
                    rankingsDimension === d
                      ? "bg-blue-600 text-white shadow-xs"
                      : isDark
                      ? "text-slate-400 hover:text-white"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          {rankings && rankings.improvements && rankings.declines && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Top Improvements */}
              <div>
                <h4 className="text-xs font-extrabold uppercase tracking-wider text-emerald-500 mb-3 flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4" /> Top Improvement Drivers
                </h4>
                <div className="space-y-2">
                  {(rankings.improvements || []).length > 0 ? (
                    (rankings.improvements || []).slice(0, 5).map((item) => (
                      <div
                        key={item.entity}
                        onClick={() => handleEntityClick(rankingsDimension, item.entity)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between group ${
                          isDark
                            ? "bg-[#0B0F19] border-[#1E293B] hover:border-blue-500/50"
                            : "bg-slate-50 border-slate-200 hover:border-blue-400 shadow-xs"
                        }`}
                      >
                        <div>
                          <div className={`text-xs font-bold ${isDark ? "text-white" : "text-slate-900"}`}>
                            {item.entity}
                          </div>
                          <div className={`text-[10px] ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                            CY: {(item.cy_admission ?? 0).toLocaleString()}
                            {item.py_admission != null ? ` | PY: ${(item.py_admission ?? 0).toLocaleString()}` : ""}
                          </div>
                        </div>
                        <span className="text-xs font-bold text-emerald-500 flex items-center gap-1">
                          {item.admission_change != null
                            ? `${item.admission_change >= 0 ? "+" : ""}${(item.admission_change ?? 0).toLocaleString()}`
                            : `CY: ${(item.cy_admission ?? 0).toLocaleString()}`}
                          <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className={`p-4 rounded-xl text-xs italic ${isDark ? "bg-[#0B0F19] text-slate-500" : "bg-slate-50 text-slate-500"}`}>
                      No positive improvement drivers found for this selection.
                    </div>
                  )}
                </div>
              </div>

              {/* Top Declines */}
              <div>
                <h4 className="text-xs font-extrabold uppercase tracking-wider text-rose-500 mb-3 flex items-center gap-1.5">
                  <TrendingDown className="w-4 h-4" /> Decline Areas
                </h4>
                <div className="space-y-2">
                  {(rankings.declines || []).length > 0 ? (
                    (rankings.declines || []).slice(0, 5).map((item) => (
                      <div
                        key={item.entity}
                        onClick={() => handleEntityClick(rankingsDimension, item.entity)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between group ${
                          isDark
                            ? "bg-[#0B0F19] border-[#1E293B] hover:border-blue-500/50"
                            : "bg-slate-50 border-slate-200 hover:border-blue-400 shadow-xs"
                        }`}
                      >
                        <div>
                          <div className={`text-xs font-bold ${isDark ? "text-white" : "text-slate-900"}`}>
                            {item.entity}
                          </div>
                          <div className={`text-[10px] ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                            CY: {(item.cy_admission ?? 0).toLocaleString()}
                            {item.py_admission != null ? ` | PY: ${(item.py_admission ?? 0).toLocaleString()}` : ""}
                          </div>
                        </div>
                        <span className="text-xs font-bold text-rose-500 flex items-center gap-1">
                          {item.admission_change != null
                            ? (item.admission_change ?? 0).toLocaleString()
                            : `CY: ${(item.cy_admission ?? 0).toLocaleString()}`}
                          <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className={`p-4 rounded-xl text-xs italic ${isDark ? "bg-[#0B0F19] text-slate-500" : "bg-slate-50 text-slate-500"}`}>
                      No decline areas detected for this selection.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Strategic Insights Cards (1 Col) */}
        <div
          className={`p-6 rounded-3xl border transition-all flex flex-col justify-between ${
            isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
          }`}
        >
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Sparkles className="w-5 h-5 text-amber-500" />
              <h3 className={`text-base font-extrabold ${isDark ? "text-white" : "text-slate-900"}`}>
                Strategic Insights
              </h3>
            </div>

            <div className="space-y-3">
              {insights.slice(0, 4).map((ins) => (
                <div
                  key={ins.id}
                  onClick={() => handleEntityClick(ins.dimension, ins.value)}
                  className={`p-3 rounded-xl border transition-all cursor-pointer ${
                    isDark
                      ? "bg-[#0B0F19] border-[#1E293B] hover:border-blue-500/50"
                      : "bg-slate-50 border-slate-200 hover:border-blue-400 shadow-xs"
                  }`}
                >
                  <div className={`text-xs font-extrabold mb-0.5 ${
                    isDark ? "text-blue-400" : "text-blue-600"
                  }`}>
                    {ins.title}
                  </div>
                  <div className={`text-xs leading-relaxed font-medium ${
                    isDark ? "text-slate-200" : "text-slate-700"
                  }`}>
                    {ins.text}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={() => onNavigateToTab("chat")}
            className="mt-4 w-full py-2.5 bg-blue-600/10 hover:bg-blue-600/20 text-blue-600 font-bold text-xs rounded-xl border border-blue-500/20 flex items-center justify-center gap-2 transition-all shadow-xs"
          >
            <MessageSquare className="w-4 h-4" />
            Ask Executive AI Agent
          </button>
        </div>
      </div>

      {/* Slide-over Entity Detail Drawer */}
      {selectedEntity && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs animate-fadeIn">
          <div
            className={`w-full max-w-xl h-full overflow-y-auto p-6 border-l shadow-2xl flex flex-col justify-between ${
              isDark ? "bg-[#0F172A] border-[#1E293B] text-white" : "bg-white border-slate-200 text-slate-900"
            }`}
          >
            <div>
              <div className={`flex items-center justify-between pb-4 border-b ${
                isDark ? "border-slate-800" : "border-slate-200"
              }`}>
                <div>
                  <span className="text-[10px] font-extrabold uppercase tracking-wider text-blue-500">
                    Entity Drilldown ({selectedEntity.dimension})
                  </span>
                  <h2 className="text-xl font-black">{selectedEntity.value}</h2>
                </div>
                <button
                  onClick={() => setSelectedEntity(null)}
                  className={`p-2 rounded-xl transition-colors ${
                    isDark ? "hover:bg-slate-800 text-slate-400" : "hover:bg-slate-100 text-slate-600"
                  }`}
                >
                  Close
                </button>
              </div>

              {detailLoading && (
                <div className={`p-12 text-center text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Loading entity analytics...
                </div>
              )}

              {detailError && (
                <div className="p-4 my-4 bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs rounded-xl font-semibold">
                  {detailError}
                </div>
              )}

              {entityDetail && (
                <div className="space-y-6 pt-4">
                  {/* Overview Stats */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className={`p-3 rounded-xl border ${isDark ? "bg-[#1E293B]/50 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                      <div className={`text-[10px] font-bold ${isDark ? "text-slate-400" : "text-slate-500"}`}>CY Admissions</div>
                      <div className="text-base font-extrabold text-blue-500">
                        {(entityDetail?.overview?.admissions?.cy ?? 0).toLocaleString()}
                      </div>
                    </div>
                    <div className={`p-3 rounded-xl border ${isDark ? "bg-[#1E293B]/50 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                      <div className={`text-[10px] font-bold ${isDark ? "text-slate-400" : "text-slate-500"}`}>CY Leads</div>
                      <div className="text-base font-extrabold text-indigo-500">
                        {(entityDetail?.overview?.leads?.cy ?? 0).toLocaleString()}
                      </div>
                    </div>
                    <div className={`p-3 rounded-xl border ${isDark ? "bg-[#1E293B]/50 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                      <div className={`text-[10px] font-bold ${isDark ? "text-slate-400" : "text-slate-500"}`}>Conv %</div>
                      <div className="text-base font-extrabold text-emerald-500">
                        {entityDetail?.overview?.conversion_rate?.cy ?? 0}%
                      </div>
                    </div>
                  </div>

                  {/* Cross Breakdowns */}
                  {Object.entries(entityDetail.breakdowns || {}).map(([bDim, items]) => (
                    <div key={bDim}>
                      <h4 className={`text-xs font-bold uppercase tracking-wider mb-2 capitalize ${
                        isDark ? "text-slate-400" : "text-slate-600"
                      }`}>
                        Breakdown by {bDim.replace("_name", "")}
                      </h4>
                      <div className="space-y-1.5">
                        {items?.slice(0, 5).map((it) => (
                          <div
                            key={it.entity}
                            className={`p-2.5 rounded-xl border flex items-center justify-between text-xs ${
                              isDark ? "bg-[#1E293B]/30 border-slate-800 text-slate-200" : "bg-slate-50 border-slate-200 text-slate-800"
                            }`}
                          >
                            <span className="font-semibold">{it.entity}</span>
                            <span className="font-bold text-blue-500">{it.admissions} adm ({it.conversion_rate}%)</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className={`pt-4 border-t ${isDark ? "border-slate-800" : "border-slate-200"}`}>
              <button
                onClick={() => handleAskAIAboutEntity(selectedEntity.dimension, selectedEntity.value)}
                className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2"
              >
                <Sparkles className="w-4 h-4" />
                Ask AI Agent About {selectedEntity.value}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Data Control Modal */}
      {showDataControlModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className={`w-full max-w-4xl max-h-[85vh] rounded-3xl border flex flex-col shadow-2xl overflow-hidden ${
            isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200"
          }`}>
            <div className={`p-6 border-b flex items-center justify-between ${isDark ? "border-slate-800" : "border-slate-200"}`}>
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-500">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <h2 className={`text-lg font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                    Data Control & Upload Audit History
                  </h2>
                  <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                    Real dataset records & prospect tracking from PostgreSQL
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowDataControlModal(false)}
                className={`p-2 rounded-xl border transition-all ${
                  isDark ? "bg-slate-800 border-slate-700 text-slate-400 hover:text-white" : "bg-slate-100 border-slate-200 text-slate-600 hover:text-slate-900"
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4">
              {dataControlLoading ? (
                <div className="flex items-center justify-center py-12 gap-3 text-xs font-semibold text-blue-500">
                  <Loader2 className="w-5 h-5 animate-spin" /> Loading upload history from PostgreSQL...
                </div>
              ) : dataControlHistory.length === 0 ? (
                <div className="py-12 text-center text-xs italic text-slate-500">
                  No dataset records found in PostgreSQL.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className={`border-b text-[11px] font-extrabold uppercase tracking-wider ${
                        isDark ? "border-slate-800 text-slate-400" : "border-slate-200 text-slate-500"
                      }`}>
                        <th className="py-3 px-3">File / Dataset</th>
                        <th className="py-3 px-3">Type</th>
                        <th className="py-3 px-3">Academic Year</th>
                        <th className="py-3 px-3">Rows Staged</th>
                        <th className="py-3 px-3">Distinct ProspectIDs</th>
                        <th className="py-3 px-3">Status</th>
                        <th className="py-3 px-3">Upload Time</th>
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? "divide-slate-800/60" : "divide-slate-200"}`}>
                      {dataControlHistory.map((ds) => (
                        <tr key={ds.id} className={isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50"}>
                          <td className="py-3 px-3 font-bold flex items-center gap-2">
                            <FileText className="w-4 h-4 text-blue-500 flex-shrink-0" />
                            <span className={isDark ? "text-white" : "text-slate-900"}>{ds.original_filename}</span>
                          </td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase ${
                              ds.workbook_type === "RAW"
                                ? "bg-blue-500/10 text-blue-500"
                                : ds.workbook_type === "DIMENSION"
                                ? "bg-purple-500/10 text-purple-500"
                                : "bg-amber-500/10 text-amber-500"
                            }`}>
                              {ds.workbook_type}
                            </span>
                          </td>
                          <td className="py-3 px-3 font-semibold">
                            {ds.academic_year || ds.academic_label || "Auto-Detected"}
                          </td>
                          <td className="py-3 px-3 font-extrabold text-blue-500">
                            {ds.row_count?.toLocaleString() ?? 0}
                          </td>
                          <td className="py-3 px-3 font-extrabold text-emerald-500">
                            {ds.distinct_prospect_count?.toLocaleString() ?? ds.row_count?.toLocaleString() ?? 0}
                          </td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              ds.is_active ? "bg-emerald-500/10 text-emerald-500" : "bg-slate-500/10 text-slate-400"
                            }`}>
                              {ds.is_active ? "Active" : ds.status}
                            </span>
                          </td>
                          <td className={`py-3 px-3 text-[11px] ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                            {ds.created_at ? new Date(ds.created_at).toLocaleString() : "N/A"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
