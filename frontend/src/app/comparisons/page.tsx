"use client";

import React, { useEffect, useState } from "react";
import {
  Scale,
  Sparkles,
  AlertCircle,
} from "lucide-react";
import { useApp } from "../../context/AppContext";
import {
  getDimensionValues,
  getDashboardCompare,
  CompareResponse,
} from "../../lib/api";

export default function ComparisonsPage() {
  const { activeDataset, theme, refreshTrigger } = useApp();
  const isDark = theme === "dark";

  // Form State
  const [dimension, setDimension] = useState<string>("source");
  const [valueOptions, setValueOptions] = useState<string[]>([]);
  const [valueA, setValueA] = useState<string>("");
  const [valueB, setValueB] = useState<string>("");
  const [metric, setMetric] = useState<string>("admission");

  // Loading / Result States
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load dimension values whenever dimension changes
  useEffect(() => {
    if (!activeDataset) return;
    getDimensionValues(dimension)
      .then((vals) => {
        setValueOptions(vals);
        if (vals.length >= 2) {
          setValueA(vals[0]);
          setValueB(vals[1]);
        } else if (vals.length === 1) {
          setValueA(vals[0]);
          setValueB(vals[0]);
        } else {
          setValueA("");
          setValueB("");
        }
      })
      .catch((err) => {
        console.error("Failed to load options:", err);
      });
  }, [activeDataset, dimension, refreshTrigger]);

  const handleCompare = () => {
    if (!valueA || !valueB) {
      setError("Please select two distinct values to compare.");
      return;
    }
    setIsLoading(true);
    setError(null);
    getDashboardCompare(dimension, valueA, valueB, metric)
      .then((res) => {
        setCompareResult(res);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to run comparison.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const loadPrebuilt = (dim: string, valA: string, valB: string, met: string) => {
    setDimension(dim);
    setMetric(met);
    setIsLoading(true);
    setError(null);

    // Wait slightly for value list to load
    getDimensionValues(dim).then((vals) => {
      setValueOptions(vals);
      setValueA(valA);
      setValueB(valB);
      getDashboardCompare(dim, valA, valB, met)
        .then((res) => {
          setCompareResult(res);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to run prebuilt comparison.");
        })
        .finally(() => {
          setIsLoading(false);
        });
    });
  };


  if (!activeDataset) {
    return (
      <div className={`p-12 text-center border rounded-3xl max-w-xl mx-auto my-12 ${
        isDark ? "bg-slate-900 border-slate-800 text-slate-400" : "bg-white border-slate-200 text-slate-500 shadow-xs"
      }`}>
        <p className="font-extrabold text-white text-lg">No Active Dataset Selected</p>
        <p className="text-xs mt-2">Please upload a dataset in the Ingestion Center first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Prebuilt comparison cards */}
      <div className="space-y-3">
        <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span>Prebuilt Analytical Scenarios</span>
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            onClick={() => loadPrebuilt("source", "Direct", "Indirect", "admission")}
            className={`p-4 rounded-xl border cursor-pointer hover:scale-[1.02] transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B] hover:border-blue-500/30" : "bg-white border-slate-200 shadow-xs hover:border-blue-300"
            }`}
          >
            <p className="text-[10px] font-bold text-blue-400 uppercase tracking-wider">Acquisition Channels</p>
            <p className="text-xs text-slate-300 font-extrabold mt-1">Direct vs Indirect Channels</p>
            <p className="text-[10px] text-slate-500 mt-2 font-medium">Compare leads & admissions</p>
          </div>

          <div
            onClick={() => loadPrebuilt("campus_name", "Main Campus", "Extension Campus", "admission")}
            className={`p-4 rounded-xl border cursor-pointer hover:scale-[1.02] transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B] hover:border-blue-500/30" : "bg-white border-slate-200 shadow-xs hover:border-blue-300"
            }`}
          >
            <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider">Campus Locations</p>
            <p className="text-xs text-slate-300 font-extrabold mt-1">Main vs Extension Campus</p>
            <p className="text-[10px] text-slate-500 mt-2 font-medium">Analyze enrollment efficiency</p>
          </div>

          <div
            onClick={() => loadPrebuilt("program_name", "B.E. CSE : CS201", "B.Tech. CSE : LCS201", "conversion_rate")}
            className={`p-4 rounded-xl border cursor-pointer hover:scale-[1.02] transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B] hover:border-blue-500/30" : "bg-white border-slate-200 shadow-xs hover:border-blue-300"
            }`}
          >
            <p className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">Academic Programs</p>
            <p className="text-xs text-slate-300 font-extrabold mt-1">CSE B.E. vs B.Tech</p>
            <p className="text-[10px] text-slate-500 mt-2 font-medium">Compare conversion rates</p>
          </div>

          <div
            onClick={() => loadPrebuilt("state", "Punjab", "Haryana", "leads")}
            className={`p-4 rounded-xl border cursor-pointer hover:scale-[1.02] transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B] hover:border-blue-500/30" : "bg-white border-slate-200 shadow-xs hover:border-blue-300"
            }`}
          >
            <p className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">Geographic Regions</p>
            <p className="text-xs text-slate-300 font-extrabold mt-1">Punjab vs Haryana</p>
            <p className="text-[10px] text-slate-500 mt-2 font-medium">Compare regional lead demand</p>
          </div>
        </div>
      </div>

      {/* Custom Manual comparison config form */}
      <div className={`p-5 rounded-2xl border ${
        isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
      }`}>
        <div className="flex items-center gap-2 mb-4">
          <Scale className="w-5 h-5 text-blue-400" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Custom Entity Comparison</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 items-end">
          {/* Dimension Selector */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Select Dimension</label>
            <select
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none ${
                isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200" : "bg-slate-50 border-slate-200 text-slate-700"
              }`}
            >
              <option value="source">Lead Source</option>
              <option value="program_name">Course / Program</option>
              <option value="campus_name">Campus Location</option>
              <option value="state">Geographic State</option>
              <option value="owner">Counsellor / Owner</option>
            </select>
          </div>

          {/* Value A */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Value A</label>
            <select
              value={valueA}
              onChange={(e) => setValueA(e.target.value)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none ${
                isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200" : "bg-slate-50 border-slate-200 text-slate-700"
              }`}
            >
              {valueOptions.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>

          {/* Value B */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Value B</label>
            <select
              value={valueB}
              onChange={(e) => setValueB(e.target.value)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border focus:outline-none ${
                isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200" : "bg-slate-50 border-slate-200 text-slate-700"
              }`}
            >
              {valueOptions.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>

          {/* Compare Button */}
          <div>
            <button
              onClick={handleCompare}
              disabled={isLoading || !valueA || !valueB}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold text-xs rounded-lg transition-all"
            >
              {isLoading ? "Running Aggregation..." : "Run Comparison"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs rounded-xl flex items-center gap-2">
            <AlertCircle className="w-4.5 h-4.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Result Section */}
      {compareResult && (
        <div className="space-y-6">
          {/* Side by side stats grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Entity A Panel */}
            <div className={`p-5 rounded-2xl border ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}>
              <div className="flex justify-between items-center pb-3 border-b border-[#1E293B]/70">
                <span className="text-xs font-extrabold text-blue-400 uppercase tracking-wider">Value A</span>
                <span className="text-xs font-bold text-white max-w-[200px] truncate">{compareResult.value_a.entity}</span>
              </div>
              <div className="grid grid-cols-3 gap-4 mt-4 text-center">
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold">Leads</p>
                  <p className="text-base font-extrabold text-white mt-1">{compareResult.value_a.cy_leads.toLocaleString()}</p>
                  <p className="text-[9px] text-slate-500 mt-0.5">PY: {compareResult.value_a.py_leads.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold">Admissions</p>
                  <p className="text-base font-extrabold text-white mt-1">{compareResult.value_a.cy_admission.toLocaleString()}</p>
                  <p className="text-[9px] text-slate-500 mt-0.5">PY: {compareResult.value_a.py_admission.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold">Conv. Rate</p>
                  <p className="text-base font-extrabold text-blue-400 mt-1">{compareResult.value_a.cy_rate}%</p>
                  <p className="text-[9px] text-slate-500 mt-0.5">PY: {compareResult.value_a.py_rate}%</p>
                </div>
              </div>
            </div>

            {/* Entity B Panel */}
            <div className={`p-5 rounded-2xl border ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}>
              <div className="flex justify-between items-center pb-3 border-b border-[#1E293B]/70">
                <span className="text-xs font-extrabold text-indigo-400 uppercase tracking-wider">Value B</span>
                <span className="text-xs font-bold text-white max-w-[200px] truncate">{compareResult.value_b.entity}</span>
              </div>
              <div className="grid grid-cols-3 gap-4 mt-4 text-center">
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold">Leads</p>
                  <p className="text-base font-extrabold text-white mt-1">{compareResult.value_b.cy_leads.toLocaleString()}</p>
                  <p className="text-[9px] text-slate-500 mt-0.5">PY: {compareResult.value_b.py_leads.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold">Admissions</p>
                  <p className="text-base font-extrabold text-white mt-1">{compareResult.value_b.cy_admission.toLocaleString()}</p>
                  <p className="text-[9px] text-slate-500 mt-0.5">PY: {compareResult.value_b.py_admission.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold">Conv. Rate</p>
                  <p className="text-base font-extrabold text-indigo-400 mt-1">{compareResult.value_b.cy_rate}%</p>
                  <p className="text-[9px] text-slate-500 mt-0.5">PY: {compareResult.value_b.py_rate}%</p>
                </div>
              </div>
            </div>
          </div>

          {/* Variance / differences analysis table */}
          <div className={`p-5 rounded-2xl border ${
            isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
          }`}>
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#1E293B]/70">
              <Scale className="w-4.5 h-4.5 text-blue-400" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">Variance Analysis (Value A - Value B)</h3>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-[#1E293B]/50 text-slate-400 font-bold uppercase text-[9px] tracking-wider">
                    <th className="py-2">Metric</th>
                    <th className="py-2 text-right">CY Variance</th>
                    <th className="py-2 text-right">PY Variance</th>
                    <th className="py-2 text-right">Trend Analysis</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1E293B]/50 font-medium">
                  {/* Leads Variance */}
                  <tr>
                    <td className="py-3">Leads</td>
                    <td className={`py-3 text-right font-mono font-bold ${compareResult.differences.cy_leads >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {compareResult.differences.cy_leads >= 0 ? "+" : ""}
                      {compareResult.differences.cy_leads.toLocaleString()}
                    </td>
                    <td className={`py-3 text-right font-mono ${compareResult.differences.py_leads >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {compareResult.differences.py_leads >= 0 ? "+" : ""}
                      {compareResult.differences.py_leads.toLocaleString()}
                    </td>
                    <td className="py-3 text-right">
                      {compareResult.differences.cy_leads > compareResult.differences.py_leads ? (
                        <span className="text-[10px] text-emerald-400 font-bold">Variance widening (A outperforming)</span>
                      ) : (
                        <span className="text-[10px] text-rose-400 font-bold">Variance narrowing (B catching up)</span>
                      )}
                    </td>
                  </tr>

                  {/* Admissions Variance */}
                  <tr>
                    <td className="py-3">Admissions</td>
                    <td className={`py-3 text-right font-mono font-bold ${compareResult.differences.cy_admission >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {compareResult.differences.cy_admission >= 0 ? "+" : ""}
                      {compareResult.differences.cy_admission.toLocaleString()}
                    </td>
                    <td className={`py-3 text-right font-mono ${compareResult.differences.py_admission >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {compareResult.differences.py_admission >= 0 ? "+" : ""}
                      {compareResult.differences.py_admission.toLocaleString()}
                    </td>
                    <td className="py-3 text-right">
                      {compareResult.differences.cy_admission > compareResult.differences.py_admission ? (
                        <span className="text-[10px] text-emerald-400 font-bold">Enrollment gap growing</span>
                      ) : (
                        <span className="text-[10px] text-rose-400 font-bold">Enrollment gap shrinking</span>
                      )}
                    </td>
                  </tr>

                  {/* Conversion rate variance */}
                  <tr>
                    <td className="py-3">Conversion Rate</td>
                    <td className={`py-3 text-right font-mono font-bold ${compareResult.differences.cy_rate >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {compareResult.differences.cy_rate >= 0 ? "+" : ""}
                      {compareResult.differences.cy_rate}%
                    </td>
                    <td className={`py-3 text-right font-mono ${compareResult.differences.py_rate >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {compareResult.differences.py_rate >= 0 ? "+" : ""}
                      {compareResult.differences.py_rate}%
                    </td>
                    <td className="py-3 text-right">
                      {compareResult.differences.cy_rate > compareResult.differences.py_rate ? (
                        <span className="text-[10px] text-emerald-400 font-bold">Efficiency delta increasing</span>
                      ) : (
                        <span className="text-[10px] text-rose-400 font-bold">Efficiency delta decreasing</span>
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
