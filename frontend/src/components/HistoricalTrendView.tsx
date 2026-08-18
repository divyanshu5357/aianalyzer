"use client";

import React, { useState, useEffect } from "react";
import {
  TrendingUp,
  BarChart2,
  LineChart as LineChartIcon,
  Layers,
  Calendar,
  Filter,
  RefreshCw,
  Award,
  Sparkles,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { useApp } from "../context/AppContext";
import { getHistoricalTrends } from "../lib/api";

interface TrendRow {
  name: string;
  [key: string]: string | number;
}

interface TrendResponse {
  dimension: string;
  metric: string;
  periods: string[];
  data: TrendRow[];
}

const COLOR_PALETTE = [
  "#3B82F6", // Blue
  "#10B981", // Emerald
  "#F59E0B", // Amber
  "#8B5CF6", // Purple
  "#EC4899", // Pink
  "#06B6D4", // Cyan
  "#F97316", // Orange
  "#6366F1", // Indigo
];

export const HistoricalTrendView: React.FC = () => {
  const { theme, periods, activePeriodLabel } = useApp();
  const isDark = theme === "dark";

  const [metric, setMetric] = useState<string>("admissions");
  const [dimension, setDimension] = useState<string>("program_name");
  const [chartType, setChartType] = useState<"line" | "bar">("line");
  const [trendData, setTrendData] = useState<TrendResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrendData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getHistoricalTrends(metric, dimension);
      setTrendData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTrendData();
  }, [metric, dimension]);

  const activePeriodsList = periods.filter((p) => p.academic_label);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className={`p-6 rounded-2xl border transition-all ${
        isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
      }`}>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-blue-500 uppercase tracking-wider mb-1">
              <Sparkles className="w-4 h-4" /> Multi-Year Analytics Engine
            </div>
            <h1 className={`text-2xl font-black tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
              Historical Trend Explorer
            </h1>
            <p className={`text-sm mt-1 max-w-2xl ${isDark ? "text-slate-400" : "text-slate-600"}`}>
              Analyze metric progression over analytical years derived from active non-overlapping database academic sessions.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* View Mode Toggle */}
            <div className={`p-1 rounded-xl border flex items-center gap-1 ${
              isDark ? "bg-slate-900 border-[#1E293B]" : "bg-slate-100 border-slate-200"
            }`}>
              <button
                onClick={() => setChartType("line")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  chartType === "line"
                    ? "bg-blue-600 text-white shadow-sm"
                    : isDark ? "text-slate-400 hover:text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <LineChartIcon className="w-3.5 h-3.5" /> Line
              </button>
              <button
                onClick={() => setChartType("bar")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  chartType === "bar"
                    ? "bg-blue-600 text-white shadow-sm"
                    : isDark ? "text-slate-400 hover:text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <BarChart2 className="w-3.5 h-3.5" /> Bar
              </button>
            </div>

            <button
              onClick={fetchTrendData}
              className={`p-2.5 rounded-xl border font-semibold text-xs transition-all ${
                isDark
                  ? "bg-[#1E293B] border-slate-700 text-slate-200 hover:bg-slate-700"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
              title="Refresh trends"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin text-blue-500" : ""}`} />
            </button>
          </div>
        </div>

        {/* Controls Bar */}
        <div className={`mt-6 pt-6 border-t flex flex-wrap items-center justify-between gap-4 ${
          isDark ? "border-[#1E293B]" : "border-slate-100"
        }`}>
          <div className="flex flex-wrap items-center gap-4">
            {/* Metric Selector */}
            <div>
              <label className={`block text-[11px] font-bold uppercase tracking-wider mb-1.5 ${
                isDark ? "text-slate-400" : "text-slate-500"
              }`}>
                Metric
              </label>
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
                className={`px-3 py-2 text-xs font-bold rounded-xl border transition-all cursor-pointer ${
                  isDark
                    ? "bg-slate-900 border-[#1E293B] text-slate-200 focus:border-blue-500"
                    : "bg-white border-slate-200 text-slate-800 focus:border-blue-500 shadow-2xs"
                }`}
              >
                <option value="admissions">Admissions</option>
                <option value="leads">Leads / Enquiries</option>
                <option value="cucet">CUCET Registrations</option>
                <option value="conversion_rate">Conversion Rate (%)</option>
              </select>
            </div>

            {/* Dimension Selector */}
            <div>
              <label className={`block text-[11px] font-bold uppercase tracking-wider mb-1.5 ${
                isDark ? "text-slate-400" : "text-slate-500"
              }`}>
                Dimension
              </label>
              <select
                value={dimension}
                onChange={(e) => setDimension(e.target.value)}
                className={`px-3 py-2 text-xs font-bold rounded-xl border transition-all cursor-pointer ${
                  isDark
                    ? "bg-slate-900 border-[#1E293B] text-slate-200 focus:border-blue-500"
                    : "bg-white border-slate-200 text-slate-800 focus:border-blue-500 shadow-2xs"
                }`}
              >
                <option value="program_name">Program Name</option>
                <option value="source">Main Source</option>
                <option value="campus_name">Campus Name</option>
                <option value="state">State</option>
                <option value="owner">Owner / Counselor</option>
              </select>
            </div>
          </div>

          {/* Sessions Badges */}
          <div className="flex items-center gap-2">
            <span className={`text-xs font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}>
              Active Sessions:
            </span>
            {activePeriodsList.length > 0 ? (
              activePeriodsList.map((p) => (
                <span
                  key={p.academic_label}
                  className="px-2.5 py-1 text-xs font-bold rounded-lg bg-blue-500/10 text-blue-500 border border-blue-500/20"
                >
                  {p.academic_label}
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-400">Default dataset sessions</span>
            )}
          </div>
        </div>
      </div>

      {/* Main Visualization Card */}
      <div className={`p-6 rounded-2xl border ${
        isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
      }`}>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-blue-500" />
            <h2 className={`text-base font-bold ${isDark ? "text-white" : "text-slate-900"}`}>
              {metric.toUpperCase()} Trend by {dimension.replace("_", " ").toUpperCase()}
            </h2>
          </div>
          {trendData?.data && (
            <span className="text-xs font-semibold text-slate-400">
              Showing top {trendData.data.length} items
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="h-80 flex items-center justify-center text-slate-400 gap-2 font-medium">
            <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
            Loading historical trends...
          </div>
        ) : error ? (
          <div className="h-64 flex items-center justify-center text-red-500 text-sm font-medium bg-red-500/5 rounded-xl border border-red-500/10">
            {error}
          </div>
        ) : !trendData || !trendData.data || trendData.data.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-400 text-sm font-medium">
            <Layers className="w-8 h-8 mb-2 opacity-50 text-slate-400" />
            No historical trend data found for the selected configuration.
          </div>
        ) : (
          <div className="h-96 w-full">
            <ResponsiveContainer width="100%" height="100%">
              {chartType === "line" ? (
                <LineChart data={trendData.data} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#1E293B" : "#E2E8F0"} />
                  <XAxis
                    dataKey="name"
                    stroke={isDark ? "#94A3B8" : "#64748B"}
                    tick={{ fontSize: 11 }}
                    angle={-20}
                    textAnchor="end"
                  />
                  <YAxis stroke={isDark ? "#94A3B8" : "#64748B"} tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: isDark ? "#0E1322" : "#FFFFFF",
                      borderColor: isDark ? "#1E293B" : "#E2E8F0",
                      borderRadius: "12px",
                      color: isDark ? "#FFFFFF" : "#0F172A",
                    }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "15px" }} />
                  {trendData.periods.map((periodLabel, idx) => (
                    <Line
                      key={periodLabel}
                      type="monotone"
                      dataKey={periodLabel}
                      name={periodLabel.includes("-") ? `Session ${periodLabel}` : `Year ${periodLabel}`}
                      stroke={COLOR_PALETTE[idx % COLOR_PALETTE.length]}
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      activeDot={{ r: 7 }}
                    />
                  ))}
                </LineChart>
              ) : (
                <BarChart data={trendData.data} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#1E293B" : "#E2E8F0"} />
                  <XAxis
                    dataKey="name"
                    stroke={isDark ? "#94A3B8" : "#64748B"}
                    tick={{ fontSize: 11 }}
                    angle={-20}
                    textAnchor="end"
                  />
                  <YAxis stroke={isDark ? "#94A3B8" : "#64748B"} tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: isDark ? "#0E1322" : "#FFFFFF",
                      borderColor: isDark ? "#1E293B" : "#E2E8F0",
                      borderRadius: "12px",
                      color: isDark ? "#FFFFFF" : "#0F172A",
                    }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "15px" }} />
                  {trendData.periods.map((periodLabel, idx) => (
                    <Bar
                      key={periodLabel}
                      dataKey={periodLabel}
                      name={periodLabel.includes("-") ? `Session ${periodLabel}` : `Year ${periodLabel}`}
                      fill={COLOR_PALETTE[idx % COLOR_PALETTE.length]}
                      radius={[6, 6, 0, 0]}
                    />
                  ))}
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Historical Data Table */}
      {trendData && trendData.data && trendData.data.length > 0 && (
        <div className={`rounded-2xl border overflow-hidden ${
          isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
        }`}>
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <h3 className={`text-sm font-bold ${isDark ? "text-white" : "text-slate-900"}`}>
              Historical Breakdown Table
            </h3>
            <span className="text-xs text-slate-400 font-medium">
              Metric: {metric}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className={`border-b ${
                isDark ? "bg-slate-900/60 border-[#1E293B] text-slate-400" : "bg-slate-50 border-slate-200 text-slate-500"
              }`}>
                <tr>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider">
                    {dimension.replace("_", " ")}
                  </th>
                  {trendData.periods.map((period) => (
                    <th key={period} className="py-3 px-4 font-bold text-right uppercase tracking-wider">
                      {period.includes("-") ? period : `Year ${period}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? "divide-[#1E293B]" : "divide-slate-100"}`}>
                {trendData.data.map((row, idx) => (
                  <tr
                    key={row.name || idx}
                    className={`transition-colors ${
                      isDark ? "hover:bg-slate-800/40" : "hover:bg-slate-50"
                    }`}
                  >
                    <td className={`py-3 px-4 font-bold ${isDark ? "text-slate-200" : "text-slate-800"}`}>
                      {row.name}
                    </td>
                    {trendData.periods.map((period) => {
                      const val = Number(row[period] ?? 0);
                      return (
                        <td key={period} className="py-3 px-4 text-right font-mono font-semibold">
                          {metric === "conversion_rate"
                            ? `${val.toFixed(2)}%`
                            : val.toLocaleString()}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
