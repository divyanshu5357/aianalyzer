"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
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
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { useApp } from "../context/AppContext";
import {
  getDashboardOverview,
  getDashboardInsights,
  getEntityDetail,
  getDashboardMonthlyTrend,
  getDashboardPerformanceRankings,
  getDashboardFilterOptions,
  DashboardFilters,
  DashboardFilterOptionsResponse,
  OverviewResponse,
  InsightItem,
  EntityDetailResponse,
  MonthlyTrendItem,
  PerformanceRankingsResponse,
  ActiveDatasetInfo,
} from "../lib/api";
import { NavTab } from "./Sidebar";

interface ExecutiveDashboardProps {
  activeDataset: ActiveDatasetInfo | null;
  onNavigateToTab: (tab: NavTab) => void;
  onSeedChatPrompt: (prompt: string) => void;
}

export const ExecutiveDashboard: React.FC<ExecutiveDashboardProps> = ({
  activeDataset,
  onNavigateToTab,
  onSeedChatPrompt,
}) => {
  const { theme, activePeriodLabel } = useApp();
  const isDark = theme === "dark";

  // Filter State - Campus Filter
  const [selectedCampus, setSelectedCampus] = useState<string>("all");
  const [selectedSession, setSelectedSession] = useState<string>("all");

  // Options & Data State
  const [filterOptions, setFilterOptions] = useState<DashboardFilterOptionsResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [insights, setInsights] = useState<InsightItem[]>([]);
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrendItem[]>([]);
  const [rankings, setRankings] = useState<PerformanceRankingsResponse | null>(null);
  const [rankingsDimension, setRankingsDimension] = useState<string>("program");
  const [mainMetric, setMainMetric] = useState<"admissions" | "leads" | "cucet" | "conversion_rate">("admissions");

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer State
  const [selectedEntity, setSelectedEntity] = useState<{ dimension: string; value: string } | null>(null);
  const [entityDetail, setEntityDetail] = useState<EntityDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Sync selected session default with active period label
  useEffect(() => {
    if (activePeriodLabel && selectedSession === "all") {
      setSelectedSession(activePeriodLabel);
    }
  }, [activePeriodLabel, selectedSession]);

  // Active filters object
  const currentFilters: DashboardFilters = useMemo(() => {
    return {
      academic_session: selectedSession !== "all" ? selectedSession : undefined,
      campus: selectedCampus !== "all" ? selectedCampus : undefined,
    };
  }, [selectedSession, selectedCampus]);

  // Load dynamic filter options
  const loadFilterOptions = useCallback(async () => {
    if (!activeDataset) return;
    try {
      const opts = await getDashboardFilterOptions(selectedSession !== "all" ? selectedSession : undefined);
      setFilterOptions(opts);
    } catch (err) {
      console.error("Failed to load filter options:", err);
    }
  }, [activeDataset, selectedSession]);

  // Load rankings for dimension
  const loadRankings = useCallback(async (dim: string) => {
    if (!activeDataset) return;
    try {
      const res = await getDashboardPerformanceRankings(dim, currentFilters);
      setRankings(res);
    } catch (err) {
      console.error("Failed to load rankings for dimension:", dim, err);
    }
  }, [activeDataset, currentFilters]);

  // Main data load function
  const loadData = useCallback(async () => {
    if (!activeDataset) return;
    setIsLoading(true);
    setError(null);
    try {
      await loadFilterOptions();
      const [overviewData, insightsData, trendData] = await Promise.all([
        getDashboardOverview(currentFilters),
        getDashboardInsights(currentFilters),
        getDashboardMonthlyTrend(currentFilters),
      ]);
      setOverview(overviewData);
      setInsights(insightsData);
      setMonthlyTrend(trendData);
      await loadRankings(rankingsDimension);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setIsLoading(false);
    }
  }, [activeDataset, currentFilters, rankingsDimension, loadFilterOptions, loadRankings]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  const handleDimensionChange = async (dim: string) => {
    setRankingsDimension(dim);
    await loadRankings(dim);
  };

  const handleEntityClick = (dimension: string, value: string) => {
    let bDim = dimension.toLowerCase().trim();
    if (bDim === "counsellor") bDim = "owner";
    if (bDim === "program") bDim = "program_name";
    if (bDim === "campus") bDim = "campus_name";

    setSelectedEntity({ dimension: bDim, value });
    setDetailLoading(true);
    setDetailError(null);
    setEntityDetail(null);

    getEntityDetail(bDim, value)
      .then((res) => {
        setEntityDetail(res);
      })
      .catch((err) => {
        setDetailError(err instanceof Error ? err.message : "Failed to load details.");
      })
      .finally(() => {
        setDetailLoading(false);
      });
  };

  const handleAskAIAboutEntity = (dim: string, val: string) => {
    const dimName =
      dim === "program_name"
        ? "program"
        : dim === "campus_name"
        ? "campus"
        : dim === "owner"
        ? "counsellor"
        : dim;
    onSeedChatPrompt(`Analyze the performance of ${dimName} "${val}"`);
    onNavigateToTab("chat");
  };

  // Helper for displaying diff badge formatted clearly
  const renderMetricDiff = (
    change: number,
    growthPct: number | null,
    isRate: boolean = false
  ) => {
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
      const formattedNum = `${isPositive ? "+" : ""}${change.toLocaleString()}`;
      const formattedPct = growthPct !== null ? `${isPositive ? "+" : ""}${growthPct}%` : "N/A";
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

  if (!activeDataset) {
    return (
      <div
        className={`flex flex-col items-center justify-center p-12 border rounded-3xl text-center space-y-6 max-w-2xl mx-auto my-12 shadow-md ${
          isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
        }`}
      >
        <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-500">
          <Database className="w-8 h-8" />
        </div>
        <div className="space-y-2">
          <h2 className={`text-xl font-extrabold ${isDark ? "text-white" : "text-slate-900"}`}>
            No Active Dataset Selected
          </h2>
          <p className={`text-sm max-w-sm ${isDark ? "text-slate-400" : "text-slate-600"}`}>
            To view the Executive Dashboard, you must first upload and select a dataset.
          </p>
        </div>
        <button
          onClick={() => onNavigateToTab("upload")}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm rounded-xl transition-all shadow-md"
        >
          Go to Ingestion Center
        </button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-24 space-y-4">
        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
        <p className={`text-xs font-medium ${isDark ? "text-slate-400" : "text-slate-600"}`}>
          Aggregating executive metrics...
        </p>
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
          onClick={loadData}
          className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-lg transition-colors"
        >
          Retry Aggregation
        </button>
      </div>
    );
  }

  const cyYear = overview?.current_year || 2026;
  const pyYear = overview?.previous_year || 2025;
  const sessionLabel = selectedSession !== "all" ? selectedSession : activeDataset.academic_label || `${pyYear}-${cyYear.toString().slice(-2)}`;

  return (
    <div className="space-y-6 pb-12">
      {/* Top Header & Campus Filter Control */}
      <div className={`p-6 rounded-2xl border flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all shadow-xs ${
        isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200"
      }`}>
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span className={`text-[10px] font-extrabold uppercase tracking-wider ${
              isDark ? "text-blue-400" : "text-blue-600"
            }`}>
              Executive Analytics
            </span>
            <span className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
              • Academic Session: <strong className={isDark ? "text-slate-200" : "text-slate-800"}>{sessionLabel}</strong> (PY {pyYear} vs CY {cyYear})
            </span>
          </div>
          <h1 className={`text-2xl font-extrabold tracking-tight mt-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Executive Management Dashboard
          </h1>
        </div>

        {/* Campus Global Filter Option */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Building2 className={`w-4 h-4 ${isDark ? "text-blue-400" : "text-blue-600"}`} />
            <label className={`text-xs font-bold ${isDark ? "text-slate-300" : "text-slate-700"}`}>
              Campus Filter:
            </label>
          </div>
          <select
            value={selectedCampus}
            onChange={(e) => setSelectedCampus(e.target.value)}
            className={`text-xs font-bold py-2 px-3 rounded-xl border outline-none transition-colors shadow-xs ${
              isDark
                ? "bg-[#0B0F19] border-[#1E293B] text-white focus:border-blue-500"
                : "bg-slate-50 border-slate-300 text-slate-800 focus:border-blue-500"
            }`}
          >
            <option value="all">All Campuses</option>
            {filterOptions?.campuses.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {selectedCampus !== "all" && (
            <button
              onClick={() => setSelectedCampus("all")}
              className={`p-2 rounded-xl text-xs font-bold transition-all ${
                isDark
                  ? "bg-slate-800 hover:bg-slate-700 text-slate-300"
                  : "bg-slate-100 hover:bg-slate-200 text-slate-700"
              }`}
              title="Clear Campus Filter"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* 4 Primary KPI Cards */}
      {overview && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Admissions Card */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className={`text-xs font-extrabold uppercase tracking-wider ${
                isDark ? "text-slate-400" : "text-slate-500"
              }`}>
                Admissions
              </span>
              <div className="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center">
                <Target className="w-4 h-4" />
              </div>
            </div>
            <div className="space-y-1">
              <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                {overview.kpis.admissions.cy.toLocaleString()}
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                  PY: {overview.kpis.admissions.py.toLocaleString()}
                </span>
                {renderMetricDiff(overview.kpis.admissions.change, overview.kpis.admissions.growth_pct)}
              </div>
            </div>
          </div>

          {/* Leads Card */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className={`text-xs font-extrabold uppercase tracking-wider ${
                isDark ? "text-slate-400" : "text-slate-500"
              }`}>
                Leads
              </span>
              <div className="w-8 h-8 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="space-y-1">
              <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                {overview.kpis.leads.cy.toLocaleString()}
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                  PY: {overview.kpis.leads.py.toLocaleString()}
                </span>
                {renderMetricDiff(overview.kpis.leads.change, overview.kpis.leads.growth_pct)}
              </div>
            </div>
          </div>

          {/* CUCET Card (if available) */}
          {overview.has_cucet && overview.kpis.cucet ? (
            <div
              className={`p-5 rounded-2xl border transition-all ${
                isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className={`text-xs font-extrabold uppercase tracking-wider ${
                  isDark ? "text-slate-400" : "text-slate-500"
                }`}>
                  CUCET Registrations
                </span>
                <div className="w-8 h-8 rounded-xl bg-violet-500/10 text-violet-500 flex items-center justify-center">
                  <Award className="w-4 h-4" />
                </div>
              </div>
              <div className="space-y-1">
                <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                  {overview.kpis.cucet.cy.toLocaleString()}
                </div>
                <div className="flex items-center justify-between text-xs pt-1">
                  <span className={isDark ? "text-slate-400" : "text-slate-500"}>
                    PY: {overview.kpis.cucet.py.toLocaleString()}
                  </span>
                  {renderMetricDiff(overview.kpis.cucet.change, overview.kpis.cucet.growth_pct)}
                </div>
              </div>
            </div>
          ) : null}

          {/* Conversion Rate Card */}
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
                  PY: {overview.kpis.conversion_rate.py}%
                </span>
                {renderMetricDiff(overview.kpis.conversion_rate.change, overview.kpis.conversion_rate.growth_pct, true)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Monthly Performance Progression Chart */}
      <div
        className={`p-6 rounded-3xl border transition-all ${
          isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
        }`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h3 className={`text-lg font-extrabold ${isDark ? "text-white" : "text-slate-900"}`}>
              Monthly Performance Progression
            </h3>
            <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
              Comparing CY {cyYear} vs PY {pyYear} monthly trajectory {selectedCampus !== "all" ? `(Filtered: ${selectedCampus})` : ""}
            </p>
          </div>

          {/* Metric Selector Tabs */}
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
            <button
              onClick={() => setMainMetric("conversion_rate")}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                mainMetric === "conversion_rate"
                  ? "bg-blue-600 text-white shadow-xs"
                  : isDark
                  ? "text-slate-400 hover:text-white"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Conversion %
            </button>
          </div>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monthlyTrend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#1E293B" : "#E2E8F0"} />
              <XAxis dataKey="month" stroke={isDark ? "#64748B" : "#64748B"} fontSize={11} />
              <YAxis stroke={isDark ? "#64748B" : "#64748B"} fontSize={11} />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? "#0B0F19" : "#FFFFFF",
                  borderColor: isDark ? "#1E293B" : "#E2E8F0",
                  borderRadius: "12px",
                  color: isDark ? "#FFFFFF" : "#0F172A",
                  boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
                }}
              />
              <Legend />
              <Bar
                dataKey={
                  mainMetric === "admissions"
                    ? "py_admission"
                    : mainMetric === "leads"
                    ? "py_leads"
                    : mainMetric === "cucet"
                    ? "py_cucet"
                    : "py_conversion_rate"
                }
                name={`PY ${pyYear}`}
                fill={isDark ? "#334155" : "#94A3B8"}
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey={
                  mainMetric === "admissions"
                    ? "cy_admission"
                    : mainMetric === "leads"
                    ? "cy_leads"
                    : mainMetric === "cucet"
                    ? "cy_cucet"
                    : "cy_conversion_rate"
                }
                name={`CY ${cyYear}`}
                fill="#2563EB"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
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
                  onClick={() => handleDimensionChange(d)}
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

          {rankings && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Top Improvements */}
              <div>
                <h4 className="text-xs font-extrabold uppercase tracking-wider text-emerald-500 mb-3 flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4" /> Top Improvement Drivers
                </h4>
                <div className="space-y-2">
                  {rankings.improvements.slice(0, 5).map((item) => (
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
                          CY: {item.cy_admission.toLocaleString()} | PY: {item.py_admission.toLocaleString()}
                        </div>
                      </div>
                      <span className="text-xs font-bold text-emerald-500 flex items-center gap-1">
                        +{item.admission_change.toLocaleString()}
                        <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Top Declines */}
              <div>
                <h4 className="text-xs font-extrabold uppercase tracking-wider text-rose-500 mb-3 flex items-center gap-1.5">
                  <TrendingDown className="w-4 h-4" /> Decline Areas
                </h4>
                <div className="space-y-2">
                  {rankings.declines.slice(0, 5).map((item) => (
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
                          CY: {item.cy_admission.toLocaleString()} | PY: {item.py_admission.toLocaleString()}
                        </div>
                      </div>
                      <span className="text-xs font-bold text-rose-500 flex items-center gap-1">
                        {item.admission_change.toLocaleString()}
                        <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </span>
                    </div>
                  ))}
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
                        {entityDetail.overview.admissions.cy.toLocaleString()}
                      </div>
                    </div>
                    <div className={`p-3 rounded-xl border ${isDark ? "bg-[#1E293B]/50 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                      <div className={`text-[10px] font-bold ${isDark ? "text-slate-400" : "text-slate-500"}`}>CY Leads</div>
                      <div className="text-base font-extrabold text-indigo-500">
                        {entityDetail.overview.leads.cy.toLocaleString()}
                      </div>
                    </div>
                    <div className={`p-3 rounded-xl border ${isDark ? "bg-[#1E293B]/50 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                      <div className={`text-[10px] font-bold ${isDark ? "text-slate-400" : "text-slate-500"}`}>Conv %</div>
                      <div className="text-base font-extrabold text-emerald-500">
                        {entityDetail.overview.conversion_rate.cy}%
                      </div>
                    </div>
                  </div>

                  {/* Cross Breakdowns */}
                  {Object.entries(entityDetail.breakdowns).map(([bDim, items]) => (
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
    </div>
  );
};
