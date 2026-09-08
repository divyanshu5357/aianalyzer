"use client";

import React, { useEffect, useState, useMemo } from "react";
import { StateAdmissionItem } from "@/lib/api";

interface IndiaStateMapProps {
  statesData: StateAdmissionItem[];
  totalAdmissions: number;
  hasPyData?: boolean;
  comparisonYear?: number | null;
  currentYear?: number;
}

interface GeoFeature {
  type: string;
  properties: {
    state_name?: string;
    NAME_1?: string;
    [key: string]: any;
  };
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: any;
  };
}

export default function IndiaStateMap({
  statesData,
  totalAdmissions,
  hasPyData = true,
  comparisonYear = null,
  currentYear = new Date().getFullYear(),
}: IndiaStateMapProps) {
  const [geoFeatures, setGeoFeatures] = useState<GeoFeature[]>([]);
  const [hoveredState, setHoveredState] = useState<{
    name: string;
    cy_admissions: number;
    py_admissions: number | null;
    variance: number | null;
    variance_pct: number | null;
    direction: "increase" | "decline" | "no_change" | "no_comparison";
    cy_leads: number;
    share_pct: number;
    x: number;
    y: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/maps/india-states.json")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load map data");
        return res.json();
      })
      .then((data) => {
        if (data && data.features) {
          setGeoFeatures(data.features);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error loading India states GeoJSON:", err);
        setLoading(false);
      });
  }, []);

  // Map state names to admission stats
  const stateStatsMap = useMemo(() => {
    const map = new Map<string, StateAdmissionItem>();
    statesData.forEach((st) => {
      const key = st.state_name.toLowerCase().trim();
      map.set(key, st);
      // Also map aliases
      if (key === "odisha") map.set("orissa", st);
      if (key === "uttarakhand") map.set("uttaranchal", st);
      if (key === "jammu & kashmir") map.set("jammu and kashmir", st);
      if (key === "delhi") map.set("nct of delhi", st);
    });
    return map;
  }, [statesData]);

  // Calculate maximum admissions to normalize shades
  const maxAdmissions = useMemo(() => {
    let max = 0;
    statesData.forEach((st) => {
      const val = st.cy_admissions ?? st.admissions ?? 0;
      if (val > max) max = val;
    });
    return max > 0 ? max : 1;
  }, [statesData]);

  // Color generator: Blue gradient shades based on CY admission volume
  const getStateColor = (st?: StateAdmissionItem) => {
    if (!st) return "#f1f5f9";
    const val = st.cy_admissions ?? st.admissions ?? 0;
    if (val === 0) return "#f1f5f9";

    const ratio = Math.pow(val / maxAdmissions, 0.42);

    if (ratio >= 0.85) return "#0f3b75"; // Deep navy blue (Punjab, highest)
    if (ratio >= 0.70) return "#1d4ed8"; // Dark royal blue (Haryana)
    if (ratio >= 0.55) return "#2563eb"; // Bold blue (UP)
    if (ratio >= 0.42) return "#3b82f6"; // Medium blue (Bihar, HP)
    if (ratio >= 0.30) return "#60a5fa"; // Medium-light blue (Rajasthan, Delhi)
    if (ratio >= 0.18) return "#93c5fd"; // Soft blue (MP, WB)
    if (ratio >= 0.08) return "#bfdbfe"; // Light blue (Maharashtra, Odisha)
    return "#dbeafe"; // Very light blue (<100)
  };

  // Convert Lon/Lat coordinates to SVG path string
  // India bounds: Lon 68.0 to 97.5, Lat 6.5 to 37.0
  const width = 560;
  const height = 620;
  const pad = 24;

  const project = (pt: [number, number]): [number, number] => {
    const [lon, lat] = pt;
    const x = pad + ((lon - 68.0) / (98.0 - 68.0)) * (width - 2 * pad);
    const y = pad + ((37.0 - lat) / (37.0 - 6.5)) * (height - 2 * pad);
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
  };

  const renderPath = (geom: GeoFeature["geometry"]): string => {
    if (geom.type === "Polygon") {
      return geom.coordinates
        .map((ring: [number, number][]) => {
          return ring
            .map((pt, i) => {
              const [px, py] = project(pt);
              return `${i === 0 ? "M" : "L"}${px},${py}`;
            })
            .join(" ") + "Z";
        })
        .join(" ");
    } else if (geom.type === "MultiPolygon") {
      return geom.coordinates
        .map((poly: [number, number][][]) => {
          return poly
            .map((ring: [number, number][]) => {
              return ring
                .map((pt, i) => {
                  const [px, py] = project(pt);
                  return `${i === 0 ? "M" : "L"}${px},${py}`;
                })
                .join(" ") + "Z";
            })
            .join(" ");
        })
        .join(" ");
    }
    return "";
  };

  return (
    <div className="relative flex flex-col items-center w-full">
      {loading ? (
        <div className="flex flex-col items-center justify-center h-[420px] text-slate-400">
          <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3"></div>
          <p className="text-sm">Loading India Geographic Map...</p>
        </div>
      ) : (
        <div className="relative w-full max-w-[560px] overflow-visible">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto drop-shadow-sm select-none"
            aria-label="India State-wise Admissions Map"
          >
            <g className="india-states">
              {geoFeatures.map((feat, idx) => {
                const rawName = feat.properties.state_name || feat.properties.NAME_1 || "";
                const matched = stateStatsMap.get(rawName.toLowerCase().trim());
                const cyAdmissions = matched ? (matched.cy_admissions ?? matched.admissions ?? 0) : 0;
                const pyAdmissions = matched ? (matched.py_admissions ?? null) : null;
                const variance = matched ? (matched.variance ?? null) : null;
                const variancePct = matched ? (matched.variance_pct ?? null) : null;
                const direction = matched ? matched.direction : "no_comparison";
                const cyLeads = matched ? (matched.cy_leads ?? matched.leads ?? 0) : 0;
                const share = matched ? matched.share_pct : 0.0;
                const fillColor = getStateColor(matched);

                return (
                  <path
                    key={`state-${idx}`}
                    d={renderPath(feat.geometry)}
                    fill={fillColor}
                    stroke="#ffffff"
                    strokeWidth="0.8"
                    strokeLinejoin="round"
                    className="transition-colors duration-150 cursor-pointer hover:opacity-95 hover:stroke-slate-900 dark:hover:stroke-white hover:stroke-[1.8]"
                    onMouseEnter={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      setHoveredState({
                        name: rawName,
                        cy_admissions: cyAdmissions,
                        py_admissions: pyAdmissions,
                        variance: variance,
                        variance_pct: variancePct,
                        direction: direction,
                        cy_leads: cyLeads,
                        share_pct: share,
                        x: rect.left + rect.width / 2,
                        y: rect.top - 10,
                      });
                    }}
                    onMouseLeave={() => setHoveredState(null)}
                  />
                );
              })}
            </g>
          </svg>

          {/* Floating Hover Tooltip: Structured 2-Column Card with Trend Pill */}
          {hoveredState && (
            <div
              className="fixed z-50 pointer-events-none transform -translate-x-1/2 -translate-y-full bg-white dark:bg-slate-900 text-slate-900 dark:text-white px-3.5 py-3 rounded-xl shadow-2xl text-xs border border-slate-200 dark:border-slate-700/80 transition-all duration-75 min-w-[280px]"
              style={{ left: hoveredState.x, top: hoveredState.y }}
            >
              {/* Header: State Name and YoY Trend Badge */}
              <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="font-extrabold text-slate-900 dark:text-white text-sm">
                  {hoveredState.name}
                </span>

                {hoveredState.direction === "increase" && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 dark:bg-emerald-950/80 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                    <span className="text-emerald-600 dark:text-emerald-400">↑</span>
                    <span>Increased (vs PY)</span>
                    {hoveredState.variance !== null && (
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                        ({hoveredState.variance > 0 ? `+${hoveredState.variance.toLocaleString()}` : hoveredState.variance}, {hoveredState.variance_pct !== null && hoveredState.variance_pct > 0 ? `+${hoveredState.variance_pct}%` : `${hoveredState.variance_pct}%`})
                      </span>
                    )}
                  </span>
                )}

                {hoveredState.direction === "decline" && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 dark:bg-rose-950/80 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                    <span className="text-rose-600 dark:text-rose-400">↓</span>
                    <span>Decreased (vs PY)</span>
                    {hoveredState.variance !== null && (
                      <span className="font-semibold text-rose-600 dark:text-rose-400">
                        ({hoveredState.variance.toLocaleString()}, {hoveredState.variance_pct !== null ? `${hoveredState.variance_pct}%` : "N/A"})
                      </span>
                    )}
                  </span>
                )}

                {hoveredState.direction === "no_change" && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                    <span>→</span>
                    <span>No Change (vs PY)</span>
                  </span>
                )}

                {hoveredState.direction === "no_comparison" && (
                  <span className="inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                    No PY comparison
                  </span>
                )}
              </div>

              {/* Clean 2-Column Grid Data Representation (Not all data vertically) */}
              <div className="rounded-lg border border-slate-200 dark:border-slate-700/80 overflow-hidden text-xs">
                {/* Header Row: CY vs PY Admissions with subtle background tint */}
                <div className="grid grid-cols-2 bg-slate-100/90 dark:bg-slate-800/90 border-b border-slate-200 dark:border-slate-700/80 divide-x divide-slate-200 dark:divide-slate-700/80">
                  <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                    <span className="text-slate-600 dark:text-slate-400 font-medium">CY Adms:</span>
                    <span className="font-bold text-slate-900 dark:text-white text-sm">
                      {hoveredState.cy_admissions.toLocaleString()}
                    </span>
                  </div>
                  <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                    <span className="text-slate-600 dark:text-slate-400 font-medium">PY Adms:</span>
                    <span className="font-bold text-slate-800 dark:text-slate-200 text-sm">
                      {hoveredState.py_admissions !== null ? hoveredState.py_admissions.toLocaleString() : "N/A"}
                    </span>
                  </div>
                </div>

                {/* Middle Row: Abs Change vs CY Leads */}
                <div className="grid grid-cols-2 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700/80 divide-x divide-slate-200 dark:divide-slate-700/80">
                  <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                    <span className="text-slate-500 dark:text-slate-400">Abs. Change:</span>
                    <span
                      className={`font-bold ${
                        hoveredState.variance === null
                          ? "text-slate-400"
                          : hoveredState.variance > 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : hoveredState.variance < 0
                          ? "text-rose-600 dark:text-rose-400"
                          : "text-slate-600 dark:text-slate-300"
                      }`}
                    >
                      {hoveredState.variance !== null
                        ? hoveredState.variance > 0
                          ? `+${hoveredState.variance.toLocaleString()}`
                          : hoveredState.variance.toLocaleString()
                        : "N/A"}
                    </span>
                  </div>
                  <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                    <span className="text-slate-500 dark:text-slate-400">CY Leads:</span>
                    <span className="font-semibold text-sky-600 dark:text-sky-400">
                      {hoveredState.cy_leads.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Bottom Row: % Change vs India Share */}
                <div className="grid grid-cols-2 bg-slate-50/70 dark:bg-slate-900/60 divide-x divide-slate-200 dark:divide-slate-700/80">
                  <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                    <span className="text-slate-500 dark:text-slate-400">% Change:</span>
                    <span
                      className={`font-bold ${
                        hoveredState.variance_pct === null
                          ? "text-slate-400"
                          : hoveredState.variance_pct > 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : hoveredState.variance_pct < 0
                          ? "text-rose-600 dark:text-rose-400"
                          : "text-slate-600 dark:text-slate-300"
                      }`}
                    >
                      {hoveredState.variance_pct !== null
                        ? hoveredState.variance_pct > 0
                          ? `+${hoveredState.variance_pct}%`
                          : `${hoveredState.variance_pct}%`
                        : "N/A"}
                    </span>
                  </div>
                  <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                    <span className="text-slate-500 dark:text-slate-400">India Share:</span>
                    <span className="font-medium text-slate-700 dark:text-slate-300">
                      {hoveredState.share_pct}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Blue Volume Gradient Legend */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs font-semibold text-slate-600 dark:text-slate-300">
            <span className="text-[11px] text-slate-500 dark:text-slate-400">Low Volume (Light Blue)</span>
            <div className="h-2.5 w-40 rounded-full bg-gradient-to-r from-[#dbeafe] via-[#3b82f6] to-[#0f3b75] shadow-inner border border-slate-200 dark:border-slate-700"></div>
            <span className="text-[11px] text-slate-500 dark:text-slate-400">High Volume (Dark Blue)</span>
          </div>

          {/* Top 5 States Leaderboard Badges */}
          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-300 mr-1">Top States:</span>
            {statesData.slice(0, 5).map((st, i) => {
              const adm = st.cy_admissions ?? st.admissions ?? 0;
              const isInc = st.direction === "increase";
              const isDec = st.direction === "decline";

              return (
                <span
                  key={st.state_code || i}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 text-slate-800 dark:text-slate-200 font-medium"
                >
                  <span className="w-4 h-4 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px] font-bold">
                    {i + 1}
                  </span>
                  <span>{st.state_name}</span>
                  <span className="font-bold text-slate-900 dark:text-white ml-0.5">
                    {adm.toLocaleString()}
                  </span>
                  {hasPyData && st.variance_pct !== null && (
                    <span
                      className={`text-[10px] font-bold ${
                        isInc ? "text-emerald-600 dark:text-emerald-400" : isDec ? "text-rose-600 dark:text-rose-400" : "text-slate-400"
                      }`}
                    >
                      {st.variance_pct > 0 ? `+${st.variance_pct}%` : `${st.variance_pct}%`}
                    </span>
                  )}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
