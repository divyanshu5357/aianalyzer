"use client";

import React from "react";
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

interface AnalyticsRendererProps {
  response: any;
}

export const AnalyticsRenderer: React.FC<AnalyticsRendererProps> = ({ response }) => {
  const { theme } = useApp();
  const isDark = theme === "dark";

  if (!response) return null;

  const data = response.data || response.result_set || [];
  const columns = response.columns || response.result_columns || [];
  const chartType = response.chart_type;

  if (!data || data.length === 0) return null;

  const primaryCol = columns[0] || Object.keys(data[0])[0];
  const numericCols = columns.slice(1).filter((col: string) => typeof data[0][col] === "number");

  return (
    <div className="space-y-4 mt-3 pt-3 border-t border-slate-200/50">
      {/* Chart Visualization */}
      {chartType === "bar" && numericCols.length > 0 && (
        <div className={`p-4 rounded-xl border h-64 ${isDark ? "bg-[#0B0F19] border-slate-800" : "bg-slate-50 border-slate-200"}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#1E293B" : "#E2E8F0"} />
              <XAxis dataKey={primaryCol} tick={{ fontSize: 10, fill: isDark ? "#94A3B8" : "#64748B" }} />
              <YAxis tick={{ fontSize: 10, fill: isDark ? "#94A3B8" : "#64748B" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? "#1E293B" : "#FFFFFF",
                  borderColor: isDark ? "#334155" : "#E2E8F0",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px" }} />
              {numericCols.map((col: string, idx: number) => (
                <Bar key={col} dataKey={col} fill={idx % 2 === 0 ? "#3B82F6" : "#10B981"} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table Visualization */}
      <div className={`overflow-x-auto rounded-xl border ${isDark ? "bg-[#0B0F19] border-slate-800" : "bg-slate-50 border-slate-200"}`}>
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className={`border-b text-[10px] font-extrabold uppercase tracking-wider ${isDark ? "border-slate-800 text-slate-400" : "border-slate-200 text-slate-600"}`}>
              {columns.map((col: string) => (
                <th key={col} className="py-2 px-3">{col.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody className={`divide-y ${isDark ? "divide-slate-800/60" : "divide-slate-200"}`}>
            {data.slice(0, 10).map((row: any, rIdx: number) => (
              <tr key={rIdx} className={isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-100"}>
                {columns.map((col: string) => (
                  <td key={col} className="py-2 px-3 font-medium">
                    {row[col] !== undefined && row[col] !== null ? String(row[col]) : "-"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
