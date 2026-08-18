"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  TrendingUp,
  TrendingDown,
  Info,
  ArrowRight,
  X,
  MessageSquare,
  Layers,
  MapPin,
  Compass,
  BarChart2,
  GitCompare,
} from "lucide-react";
import { useApp } from "../../context/AppContext";
import {
  getAllPeriods,
  getPeriodsCompare,
  getPeriodsTrend,
  PeriodSummary,
  PeriodCompareResponse,
  PeriodTrendResponse,
  parseApiError,
} from "../../lib/api";

export default function AnalyticsPage() {
  const router = useRouter();
  const { theme, setSeededPrompt, setSeededPeriodA, setSeededPeriodB, refreshTrigger } = useApp();
  const isDark = theme === "dark";

  // Available Periods & Analytical Years
  const [availablePeriods, setAvailablePeriods] = useState<PeriodSummary[]>([]);
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [periodsLoading, setPeriodsLoading] = useState(true);

  // View State
  const [viewMode, setViewMode] = useState<"comparison" | "trend">("comparison");

  // Selectors State
  const [periodA, setPeriodA] = useState<string>("");
  const [periodB, setPeriodB] = useState<string>("");
  const [metric, setMetric] = useState<"admission" | "leads" | "conversion_rate">("admission");
  const [dimension, setDimension] = useState<string>("program_name");
  const [limit, setLimit] = useState<number>(10);

  // Data Fetching State
  const [compareData, setCompareData] = useState<PeriodCompareResponse | null>(null);
  const [trendData, setTrendData] = useState<PeriodTrendResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load Periods & Years on Mount
  useEffect(() => {
    async function loadPeriods() {
      setPeriodsLoading(true);
      try {
        const res = await getAllPeriods();
        const activeOnly = res.periods.filter((p) => p.active_dataset_id);
        setAvailablePeriods(activeOnly);
        setAvailableYears(res.years || []);

        if (res.years && res.years.length >= 2) {
          setPeriodA(String(res.years[res.years.length - 2]));
          setPeriodB(String(res.years[res.years.length - 1]));
        } else if (res.years && res.years.length === 1) {
          setPeriodA(String(res.years[0]));
          setPeriodB(String(res.years[0]));
        } else if (activeOnly.length >= 2) {
          setPeriodA(activeOnly[1].academic_label);
          setPeriodB(activeOnly[0].academic_label);
        } else if (activeOnly.length === 1) {
          setPeriodA(activeOnly[0].academic_label);
          setPeriodB(activeOnly[0].academic_label);
        }
      } catch (err) {
        console.error("Failed to load periods", err);
      } finally {
        setPeriodsLoading(false);
      }
    }
    loadPeriods();
  }, []);

  const loadData = useCallback(async () => {
    if (!periodA || !periodB) return;
    if (viewMode === "comparison" && periodA.trim() === periodB.trim()) {
      setError("Please select two different years for comparison.");
      setCompareData(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      if (viewMode === "comparison") {
        const res = await getPeriodsCompare(periodA, periodB, metric, dimension, limit);
        setCompareData(res);
      } else {
        const res = await getPeriodsTrend(metric, dimension);
        setTrendData(res);
      }
    } catch (err) {
      setError(parseApiError(err instanceof Error ? err.message : String(err), "Failed to load analytical data."));
    } finally {
      setIsLoading(false);
    }
  }, [periodA, periodB, metric, dimension, limit, viewMode]);

  useEffect(() => {
    if (!periodsLoading && periodA && periodB) {
      loadData();
    }
  }, [loadData, refreshTrigger, periodsLoading]);

  const handleAskAIAboutEntity = (dim: string, val: string) => {
    const dimName =
      dim === "program_name"
        ? "program"
        : dim === "campus_name"
        ? "campus"
        : dim === "owner"
        ? "counsellor"
        : dim;
    setSeededPrompt(`Analyze the performance of ${dimName} "${val}"`);
    setSeededPeriodA(periodA);
    setSeededPeriodB(periodB);
    router.push("/ai-analyst");
  };

  const getMetricLabel = (m: string) => {
    if (m === "leads") return "Leads";
    if (m === "admission") return "Admissions";
    return "Conversion Rate";
  };

  if (periodsLoading) {
    return (
      <div className="flex justify-center items-center h-full min-h-[500px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const positiveCohort = compareData?.data.filter((item) => (item.absolute_change || 0) > 0) || [];
  const declineCohort = compareData?.data.filter((item) => (item.absolute_change || 0) < 0).sort((a, b) => (a.absolute_change || 0) - (b.absolute_change || 0)) || [];

  return (
    <div className={`p-6 space-y-6 ${isDark ? "text-slate-200" : "text-slate-800"}`}>
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className={`text-2xl font-bold tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
            Arbitrary Year Analytics
          </h1>
          <p className={`text-sm mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Dynamically compare performance cohorts across any historical analytical years.
          </p>
        </div>
        
        <div className={`flex bg-opacity-20 p-1 rounded-lg ${isDark ? "bg-slate-800" : "bg-slate-200"}`}>
          <button
            onClick={() => setViewMode("comparison")}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              viewMode === "comparison"
                ? "bg-blue-600 text-white shadow-sm"
                : `${isDark ? "text-slate-400 hover:text-slate-200" : "text-slate-600 hover:text-slate-900"}`
            }`}
          >
            <GitCompare size={16} /> Comparison
          </button>
          <button
            onClick={() => setViewMode("trend")}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              viewMode === "trend"
                ? "bg-blue-600 text-white shadow-sm"
                : `${isDark ? "text-slate-400 hover:text-slate-200" : "text-slate-600 hover:text-slate-900"}`
            }`}
          >
            <BarChart2 size={16} /> Historical Trend
          </button>
        </div>
      </div>

      <div className={`p-4 rounded-xl border flex flex-wrap gap-4 items-end ${
        isDark ? "bg-slate-800/50 border-slate-700" : "bg-white border-slate-200"
      }`}>
        <div className="flex flex-col gap-1.5 w-full sm:w-auto">
          <label className={`text-xs font-semibold ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Year From
          </label>
          <select
            value={periodA}
            onChange={(e) => setPeriodA(e.target.value)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              isDark
                ? "bg-slate-900 border-slate-700 text-white"
                : "bg-slate-50 border-slate-200 text-slate-900"
            }`}
          >
            {availableYears.length > 0
              ? availableYears.map((y) => (
                  <option key={y} value={String(y)}>{y}</option>
                ))
              : availablePeriods.map((p) => (
                  <option key={p.academic_label} value={p.academic_label}>{p.academic_label}</option>
                ))}
          </select>
        </div>
        
        <div className="flex flex-col gap-1.5 w-full sm:w-auto">
          <label className={`text-xs font-semibold ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Year To
          </label>
          <select
            value={periodB}
            onChange={(e) => setPeriodB(e.target.value)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              isDark
                ? "bg-slate-900 border-slate-700 text-white"
                : "bg-slate-50 border-slate-200 text-slate-900"
            }`}
          >
            {availableYears.length > 0
              ? availableYears.map((y) => (
                  <option key={y} value={String(y)}>{y}</option>
                ))
              : availablePeriods.map((p) => (
                  <option key={p.academic_label} value={p.academic_label}>{p.academic_label}</option>
                ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5 w-full sm:w-auto">
          <label className={`text-xs font-semibold ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Dimension
          </label>
          <select
            value={dimension}
            onChange={(e) => setDimension(e.target.value)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              isDark
                ? "bg-slate-900 border-slate-700 text-white"
                : "bg-slate-50 border-slate-200 text-slate-900"
            }`}
          >
            <option value="program_name">Program / Course</option>
            <option value="source">Source</option>
            <option value="state">State</option>
            <option value="owner">Counsellor (Owner)</option>
            <option value="campus_name">Campus</option>
            <option value="lead_type">Lead Type</option>
          </select>
        </div>

        <div className="flex flex-col gap-1.5 w-full sm:w-auto">
          <label className={`text-xs font-semibold ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Metric
          </label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as any)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              isDark
                ? "bg-slate-900 border-slate-700 text-white"
                : "bg-slate-50 border-slate-200 text-slate-900"
            }`}
          >
            <option value="admission">Admissions</option>
            <option value="leads">Leads</option>
            <option value="conversion_rate">Conversion Rate</option>
          </select>
        </div>

        {viewMode === "comparison" && (
          <div className="flex flex-col gap-1.5 w-full sm:w-auto">
            <label className={`text-xs font-semibold ${isDark ? "text-slate-400" : "text-slate-500"}`}>
              Limit
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                isDark
                  ? "bg-slate-900 border-slate-700 text-white"
                  : "bg-slate-50 border-slate-200 text-slate-900"
              }`}
            >
              <option value="5">Top 5</option>
              <option value="10">Top 10</option>
              <option value="20">Top 20</option>
              <option value="50">Top 50</option>
              <option value="100">All (Top 100)</option>
            </select>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <p className={`text-sm ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Crunching {dimension} metrics...
          </p>
        </div>
      ) : error ? (
        <div className={`p-4 rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-500`}>
          {error}
        </div>
      ) : viewMode === "comparison" && compareData ? (
        positiveCohort.length === 0 && declineCohort.length === 0 ? (
          <div className={`p-8 text-center rounded-xl border text-sm font-semibold ${
            isDark ? "bg-slate-800/40 border-slate-700 text-slate-400" : "bg-white border-slate-200 text-slate-600"
          }`}>
            No positive or negative change between the selected periods.
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <CohortTable 
              title="Positive Growth Cohort" 
              data={positiveCohort} 
              isDark={isDark} 
              periodA={periodA} 
              periodB={periodB} 
              metricLabel={getMetricLabel(metric)}
              isConversion={metric === "conversion_rate"}
              onAskAI={handleAskAIAboutEntity}
              dimension={dimension}
            />
            <CohortTable 
              title="Decline Cohort" 
              data={declineCohort} 
              isDark={isDark} 
              periodA={periodA} 
              periodB={periodB} 
              metricLabel={getMetricLabel(metric)}
              isConversion={metric === "conversion_rate"}
              onAskAI={handleAskAIAboutEntity}
              dimension={dimension}
            />
          </div>
        )
      ) : viewMode === "trend" && trendData ? (
        <TrendTable 
          data={trendData} 
          isDark={isDark} 
          metricLabel={getMetricLabel(metric)}
          isConversion={metric === "conversion_rate"}
        />
      ) : null}
    </div>
  );
}

function CohortTable({ title, data, isDark, periodA, periodB, metricLabel, isConversion, onAskAI, dimension }: any) {
  return (
    <div className={`rounded-xl border overflow-hidden ${isDark ? "bg-slate-900 border-slate-700" : "bg-white border-slate-200 shadow-sm"}`}>
      <div className={`p-4 border-b flex items-center justify-between ${isDark ? "border-slate-700" : "border-slate-100"}`}>
        <h3 className={`font-bold flex items-center gap-2 ${title.includes("Positive") ? "text-emerald-500" : "text-rose-500"}`}>
          {title.includes("Positive") ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          {title}
        </h3>
        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-md ${isDark ? "bg-slate-800 text-slate-400" : "bg-slate-100 text-slate-500"}`}>
          {data.length} Entities
        </span>
      </div>
      
      {data.length === 0 ? (
        <div className="p-8 text-center text-sm opacity-50">No entities found in this cohort.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className={`text-xs uppercase bg-opacity-50 ${isDark ? "bg-slate-800 text-slate-400" : "bg-slate-50 text-slate-500"}`}>
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3 text-right">{periodA}</th>
                <th className="px-4 py-3 text-right">{periodB}</th>
                <th className="px-4 py-3 text-right">Change</th>
                <th className="px-4 py-3 text-right">Growth %</th>
                <th className="px-4 py-3 text-center">AI</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {data.map((item: any, idx: number) => (
                <tr key={idx} className={`hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors`}>
                  <td className="px-4 py-3 font-medium max-w-[200px] truncate" title={item.name}>{item.name}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs">
                    {isConversion ? `${item.period_a_rate}%` : item.period_a_value.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs">
                    {isConversion ? `${item.period_b_rate}%` : item.period_b_value.toLocaleString()}
                  </td>
                  <td className={`px-4 py-3 text-right font-mono text-xs font-bold ${item.absolute_change >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                    {item.absolute_change > 0 ? "+" : ""}{isConversion ? `${item.absolute_change}%` : item.absolute_change.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs">
                    {item.growth_percent !== null ? (
                      <span className={`px-2 py-0.5 rounded-full ${item.growth_percent >= 0 ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}>
                        {item.growth_percent > 0 ? "+" : ""}{item.growth_percent}%
                      </span>
                    ) : "-"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button 
                      onClick={() => onAskAI(dimension, item.name)}
                      className="p-1.5 rounded-md hover:bg-blue-50 dark:hover:bg-blue-900/30 text-blue-500 transition-colors"
                      title={`Ask AI about ${item.name}`}
                    >
                      <MessageSquare size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TrendTable({ data, isDark, metricLabel, isConversion }: any) {
  const periods = data.periods || [];
  
  return (
    <div className={`rounded-xl border overflow-hidden ${isDark ? "bg-slate-900 border-slate-700" : "bg-white border-slate-200 shadow-sm"}`}>
      <div className={`p-4 border-b flex items-center justify-between ${isDark ? "border-slate-700" : "border-slate-100"}`}>
        <h3 className="font-bold flex items-center gap-2">
          <Layers size={18} />
          {metricLabel} Historical Trend
        </h3>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className={`text-xs uppercase bg-opacity-50 ${isDark ? "bg-slate-800 text-slate-400" : "bg-slate-50 text-slate-500"}`}>
            <tr>
              <th className="px-4 py-3">Entity</th>
              {periods.map((p: string) => (
                <th key={p} className="px-4 py-3 text-right">{p}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {data.data.map((item: any, idx: number) => (
              <tr key={idx} className={`hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors`}>
                <td className="px-4 py-3 font-medium max-w-[200px] truncate" title={item.name}>{item.name}</td>
                {periods.map((p: string) => (
                  <td key={p} className="px-4 py-3 text-right font-mono text-xs opacity-80">
                    {isConversion ? `${item[p]}%` : item[p].toLocaleString()}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
