"use client";

import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { ChatResponse } from "../lib/api";

const COLORS = [
  "#2563eb", // blue-600
  "#4f46e5", // indigo-600
  "#0d9488", // teal-600
  "#d97706", // amber-600
  "#e11d48", // rose-600
  "#7c3aed", // violet-600
  "#0284c7", // sky-600
  "#059669", // emerald-600
];

interface AnalyticsRendererProps {
  response: ChatResponse;
}

export const AnalyticsRenderer: React.FC<AnalyticsRendererProps> = ({
  response,
}) => {
  const responseType = response.response_type || "text";
  const chartType = response.chart_type || "bar";
  const columns = (response.columns as string[]) || [];
  const data = (response.data as Record<string, unknown>[]) || [];
  const sections = response.sections || [];

  // Render structured analysis sections if provided
  if (sections && sections.length > 0) {
    return (
      <div className="mt-3 space-y-4">
        {sections.map((section, sIdx) => {
          if (section.type === "metric_table" || section.type === "driver_table") {
            const secCols = section.columns || [];
            const secData = section.data || [];
            if (!secData.length) return null;
            return (
              <div
                key={sIdx}
                className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-2xs"
              >
                {section.title && (
                  <div className="px-4 py-2.5 bg-slate-50/80 border-b border-slate-200/80 font-bold text-xs text-slate-800 flex items-center justify-between">
                    <span>{section.title}</span>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                      {secData.length} records
                    </span>
                  </div>
                )}
                <div className="max-h-60 overflow-y-auto overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-50 border-b border-slate-200/60 sticky top-0">
                      <tr>
                        {secCols.map((col) => (
                          <th
                            key={col}
                            className="px-3 py-2 text-[11px] font-bold text-slate-600 uppercase tracking-wider"
                          >
                            {col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {secData.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-50/60 transition-colors">
                          {secCols.map((col) => {
                            const val = row[col];
                            return (
                              <td
                                key={col}
                                className="px-3 py-2 text-slate-700 font-medium text-xs"
                              >
                                {val !== null && val !== undefined ? String(val) : "-"}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          }

          if (section.type === "observation_list") {
            const items = section.items || [];
            if (!items.length) return null;
            return (
              <div
                key={sIdx}
                className="p-4 bg-blue-50/40 border border-blue-100 rounded-xl space-y-2"
              >
                {section.title && (
                  <h4 className="font-bold text-xs text-blue-900 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600"></span>
                    {section.title}
                  </h4>
                )}
                <ul className="space-y-1.5 text-xs text-slate-700">
                  {items.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-2 leading-relaxed">
                      <span className="text-blue-500 font-bold">•</span>
                      <span
                        dangerouslySetInnerHTML={{
                          __html: item.replace(
                            /\*\*(.*?)\*\*/g,
                            '<strong class="font-bold text-slate-900">$1</strong>'
                          ),
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            );
          }

          if (section.type === "text_block" && section.content) {
            return (
              <div
                key={sIdx}
                className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-[11px] text-slate-500 italic leading-relaxed"
              >
                {section.content}
              </div>
            );
          }

          return null;
        })}
      </div>
    );
  }

  if (
    (responseType !== "table" && responseType !== "chart") ||
    !columns.length ||
    !data.length
  ) {
    // Render funnel fallback if available
    if (response.funnel) {
      const cy = response.funnel.current_year_funnel;
      return (
        <div className="mt-3 p-3 bg-white rounded-xl border border-slate-200 text-slate-700 space-y-1">
          <p className="font-bold text-xs text-blue-600">
            Funnel Summary ({response.funnel.current_year})
          </p>
          <div className="grid grid-cols-3 gap-2 pt-1 text-[11px]">
            <div>
              Leads: <strong>{cy.leads}</strong>
            </div>
            <div>
              CUCET: <strong>{cy.cucet}</strong>
            </div>
            <div>
              Adm: <strong>{cy.admission}</strong>
            </div>
          </div>
        </div>
      );
    }
    return null;
  }

  // Derive dimension/name key and metric/value key
  const nameKey = columns[0];
  let valueKey = columns[1] || columns[0];

  if (data[0]) {
    const keys = Object.keys(data[0]);
    const numKey = keys.find(
      (k) => k !== nameKey && typeof data[0][k] === "number"
    );
    if (numKey) valueKey = numKey;
  }

  // Format header name for display
  const formatHeader = (key: string) => {
    return key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  // Render Table
  if (responseType === "table") {
    return (
      <div className="mt-3 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        <div className="max-h-60 overflow-y-auto overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200 sticky top-0">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="px-3 py-2 text-[11px] font-bold text-slate-600 uppercase tracking-wider"
                  >
                    {formatHeader(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                  {columns.map((col) => {
                    const val = row[col];
                    const isNum = typeof val === "number";
                    return (
                      <td
                        key={col}
                        className={`px-3 py-2 text-slate-700 font-medium ${
                          isNum ? "tabular-nums font-semibold" : ""
                        }`}
                      >
                        {val !== null && val !== undefined
                          ? String(val)
                          : "-"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Render Chart
  return (
    <div className="mt-3 bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chartType === "pie" ? (
            <PieChart>
              <Tooltip
                contentStyle={{
                  backgroundColor: "#ffffff",
                  borderColor: "#e2e8f0",
                  borderRadius: "0.75rem",
                  fontSize: "12px",
                  boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1)",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
              <Pie
                data={data}
                dataKey={valueKey}
                nameKey={nameKey}
                cx="50%"
                cy="50%"
                outerRadius={75}
                innerRadius={30}
                paddingAngle={2}
                label={({ name, percent }) =>
                  `${name}: ${((percent || 0) * 100).toFixed(0)}%`
                }
                labelLine={false}
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Pie>
            </PieChart>
          ) : chartType === "line" ? (
            <LineChart
              data={data}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey={nameKey}
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#cbd5e1"
              />
              <YAxis tick={{ fontSize: 10, fill: "#64748b" }} stroke="#cbd5e1" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#ffffff",
                  borderColor: "#e2e8f0",
                  borderRadius: "0.75rem",
                  fontSize: "12px",
                  boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1)",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px" }} />
              <Line
                type="monotone"
                dataKey={valueKey}
                name={formatHeader(valueKey)}
                stroke="#2563eb"
                strokeWidth={2.5}
                dot={{ r: 4, fill: "#2563eb" }}
              />
            </LineChart>
          ) : (
            <BarChart
              data={data}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey={nameKey}
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#cbd5e1"
              />
              <YAxis tick={{ fontSize: 10, fill: "#64748b" }} stroke="#cbd5e1" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#ffffff",
                  borderColor: "#e2e8f0",
                  borderRadius: "0.75rem",
                  fontSize: "12px",
                  boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1)",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px" }} />
              <Bar
                dataKey={valueKey}
                name={formatHeader(valueKey)}
                fill="#2563eb"
                radius={[4, 4, 0, 0]}
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
