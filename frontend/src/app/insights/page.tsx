"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  TrendingUp,
  TrendingDown,
  Layers,
  MapPin,
  Compass,
  Briefcase,
  ChevronRight,
  ArrowRight,
  X,
  MessageSquare,
} from "lucide-react";
import { useApp } from "../../context/AppContext";
import {
  getDashboardInsights,
  getEntityDetail,
  InsightItem,
  EntityDetailResponse,
} from "../../lib/api";

export default function InsightsPage() {
  const router = useRouter();
  const { activeDataset, theme, setSeededPrompt, refreshTrigger } = useApp();
  const isDark = theme === "dark";

  // Data State
  const [insights, setInsights] = useState<InsightItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer State
  const [selectedEntity, setSelectedEntity] = useState<{ dimension: string; value: string } | null>(null);
  const [entityDetail, setEntityDetail] = useState<EntityDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!activeDataset) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await getDashboardInsights();
      setInsights(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate analytical insights.");
    } finally {
      setIsLoading(false);
    }
  }, [activeDataset]);

  useEffect(() => {
    setTimeout(() => {
      loadData();
    }, 0);
  }, [loadData, refreshTrigger]);

  const handleEntityClick = (dimension: string, value: string) => {
    setSelectedEntity({ dimension, value });
    setDetailLoading(true);
    setDetailError(null);
    setEntityDetail(null);

    getEntityDetail(dimension, value)
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
    setSeededPrompt(`Analyze the performance of ${dimName} "${val}"`);
    router.push("/ai-analyst");
  };

  // Group insights by focus area
  const improvements = insights.filter((x) => x.id.includes("improvement") || x.id.includes("best"));
  const declines = insights.filter((x) => x.id.includes("decline") || x.id.includes("worst"));
  const channels = insights.filter((x) => x.dimension === "source");
  const geography = insights.filter((x) => x.dimension === "state");
  const programs = insights.filter((x) => x.dimension === "program_name" && !x.id.includes("improvement") && !x.id.includes("decline"));
  const counsellors = insights.filter((x) => x.dimension === "owner");

  const renderInsightSection = (title: string, icon: React.ReactNode, list: InsightItem[]) => {
    if (list.length === 0) return null;
    return (
      <div className="space-y-3">
        <h4 className={`text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 ${
          isDark ? "text-slate-400" : "text-slate-600"
        }`}>
          {icon}
          <span>{title}</span>
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {list.map((ins, idx) => (
            <div
              key={idx}
              onClick={() => handleEntityClick(ins.dimension, ins.value)}
              className={`p-4 rounded-xl border cursor-pointer hover:scale-[1.01] transition-all flex flex-col justify-between group ${
                isDark
                  ? "bg-[#131B2E] border-[#1E293B] hover:border-blue-500/40"
                  : "bg-white border-slate-200 shadow-sm hover:border-blue-400"
              }`}
            >
              <div>
                <p className={`text-[10px] font-extrabold uppercase tracking-wider ${
                  isDark ? "text-blue-400" : "text-blue-600"
                }`}>
                  {ins.title}
                </p>
                <p className={`text-xs mt-2.5 leading-relaxed font-medium ${
                  isDark ? "text-slate-200" : "text-slate-700"
                }`}>
                  {ins.text}
                </p>
              </div>
              <div className={`flex items-center gap-1 text-[10px] font-bold mt-4 transition-colors ${
                isDark ? "text-blue-400 group-hover:text-blue-300" : "text-blue-600 group-hover:text-blue-700"
              }`}>
                <span>View Details & Breakdowns</span>
                <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  if (!activeDataset) {
    return (
      <div className={`p-12 text-center border rounded-3xl max-w-xl mx-auto my-12 ${
        isDark ? "bg-slate-900 border-slate-800 text-slate-400" : "bg-white border-slate-200 text-slate-600 shadow-xs"
      }`}>
        <p className={`font-extrabold text-lg ${isDark ? "text-white" : "text-slate-900"}`}>
          No Active Dataset Selected
        </p>
        <p className="text-xs mt-2">Please upload a dataset in the Ingestion Center first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Overview Banner */}
      <div className={`p-6 rounded-2xl border flex items-center justify-between transition-all duration-200 ${
        isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
      }`}>
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span className={`text-[10px] font-extrabold uppercase tracking-wider ${
              isDark ? "text-blue-400" : "text-blue-600"
            }`}>
              Admissions Intelligence Insights
            </span>
          </div>
          <h2 className={`text-xl font-extrabold tracking-tight mt-1 ${
            isDark ? "text-white" : "text-slate-900"
          }`}>
            Automated Performance Insights
          </h2>
          <p className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-600"}`}>
            Click any card to explore full dimension details and view local breakdowns.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>Mining database statistics...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs rounded-xl font-semibold">
          {error}
        </div>
      ) : (
        <div className="space-y-8">
          {renderInsightSection("Performance Improvements", <TrendingUp className="w-4.5 h-4.5 text-emerald-500" />, improvements)}
          {renderInsightSection("Performance Declines", <TrendingDown className="w-4.5 h-4.5 text-rose-500" />, declines)}
          {renderInsightSection("Source & Channel Insights", <Layers className="w-4.5 h-4.5 text-indigo-500" />, channels)}
          {renderInsightSection("Geographic Insights", <MapPin className="w-4.5 h-4.5 text-amber-500" />, geography)}
          {renderInsightSection("Academic Program Demand", <Compass className="w-4.5 h-4.5 text-blue-500" />, programs)}
          {renderInsightSection("Counsellor Performance", <Briefcase className="w-4.5 h-4.5 text-purple-500" />, counsellors)}
        </div>
      )}

      {/* Drawer Panel */}
      {selectedEntity && (
        <>
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40"
            onClick={() => setSelectedEntity(null)}
          ></div>
          <div className={`fixed top-0 right-0 w-full sm:w-[500px] h-full border-l shadow-2xl z-50 overflow-y-auto flex flex-col ${
            isDark ? "bg-[#0E1322] border-[#1E293B] text-white" : "bg-white border-slate-200 text-slate-900"
          }`}>
            {/* Drawer Header */}
            <div className={`p-5 border-b flex items-center justify-between ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-slate-50 border-slate-200"
            }`}>
              <div>
                <p className="text-[10px] font-extrabold text-blue-500 uppercase tracking-wider">
                  Exploratory Details
                </p>
                <h3 className={`text-base font-extrabold mt-1 truncate max-w-[320px] ${
                  isDark ? "text-white" : "text-slate-900"
                }`}>
                  {selectedEntity.value}
                </h3>
              </div>
              <button
                onClick={() => setSelectedEntity(null)}
                className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                  isDark ? "bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white" : "bg-slate-200 hover:bg-slate-300 text-slate-600 hover:text-slate-900"
                }`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 p-5 space-y-6">
              {detailLoading && (
                <div className="flex flex-col items-center justify-center py-16 space-y-3">
                  <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                  <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>Loading breakdown details...</p>
                </div>
              )}

              {detailError && (
                <div className="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs rounded-xl font-semibold">
                  {detailError}
                </div>
              )}

              {entityDetail && (
                <div className="space-y-6">
                  {/* Overview Cards */}
                  <div className={`border rounded-xl p-4 divide-y ${
                    isDark ? "bg-[#131B2E] border-[#1E293B] divide-[#1E293B]/70" : "bg-slate-50 border-slate-200 divide-slate-200"
                  }`}>
                    {/* Leads Row */}
                    <div className="py-2.5 flex justify-between items-center text-xs">
                      <div>
                        <p className={`font-semibold ${isDark ? "text-slate-300" : "text-slate-700"}`}>Leads</p>
                        <p className={`text-[10px] ${isDark ? "text-slate-500" : "text-slate-400"}`}>PY: {entityDetail.overview.leads.py.toLocaleString()}</p>
                      </div>
                      <div className="text-right">
                        <p className={`font-bold ${isDark ? "text-white" : "text-slate-900"}`}>{entityDetail.overview.leads.cy.toLocaleString()}</p>
                        <span className={`text-[10px] font-bold ${entityDetail.overview.leads.change >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                          {entityDetail.overview.leads.change >= 0 ? "+" : ""}{entityDetail.overview.leads.change.toLocaleString()}
                        </span>
                      </div>
                    </div>

                    {/* Admissions Row */}
                    <div className="py-2.5 flex justify-between items-center text-xs">
                      <div>
                        <p className={`font-semibold ${isDark ? "text-slate-300" : "text-slate-700"}`}>Admissions</p>
                        <p className={`text-[10px] ${isDark ? "text-slate-500" : "text-slate-400"}`}>PY: {entityDetail.overview.admissions.py.toLocaleString()}</p>
                      </div>
                      <div className="text-right">
                        <p className={`font-bold ${isDark ? "text-white" : "text-slate-900"}`}>{entityDetail.overview.admissions.cy.toLocaleString()}</p>
                        <span className={`text-[10px] font-bold ${entityDetail.overview.admissions.change >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                          {entityDetail.overview.admissions.change >= 0 ? "+" : ""}{entityDetail.overview.admissions.change.toLocaleString()}
                        </span>
                      </div>
                    </div>

                    {/* Rate Row */}
                    <div className="py-2.5 flex justify-between items-center text-xs">
                      <div>
                        <p className={`font-semibold ${isDark ? "text-slate-300" : "text-slate-700"}`}>Conversion Rate</p>
                        <p className={`text-[10px] ${isDark ? "text-slate-500" : "text-slate-400"}`}>PY: {entityDetail.overview.conversion_rate.py}%</p>
                      </div>
                      <div className="text-right">
                        <p className={`font-bold ${isDark ? "text-white" : "text-slate-900"}`}>{entityDetail.overview.conversion_rate.cy}%</p>
                        <span className={`text-[10px] font-bold ${entityDetail.overview.conversion_rate.change >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                          {entityDetail.overview.conversion_rate.change >= 0 ? "+" : ""}{entityDetail.overview.conversion_rate.change}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Causal AI Agent link */}
                  <div className={`p-3 border rounded-xl flex items-center justify-between text-xs ${
                    isDark ? "bg-[#131B2E] border-blue-500/20" : "bg-blue-50/50 border-blue-200"
                  }`}>
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4 text-blue-500" />
                      <span className={`font-bold ${isDark ? "text-slate-300" : "text-slate-800"}`}>Investigate in AI analyst?</span>
                    </div>
                    <button
                      onClick={() => handleAskAIAboutEntity(selectedEntity.dimension, selectedEntity.value)}
                      className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg text-[10px] transition-colors flex items-center gap-1 shadow-xs"
                    >
                      <span>Launch AI Chat</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Available breakdowns */}
                  <div className="space-y-4">
                    <h4 className={`text-[10px] font-extrabold uppercase tracking-wider ${
                      isDark ? "text-slate-400" : "text-slate-500"
                    }`}>
                      Target breakdowns
                    </h4>

                    {Object.entries(entityDetail.breakdowns).map(([bDim, rows]) => (
                      <div key={bDim} className="space-y-2">
                        <p className={`text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5 ${
                          isDark ? "text-slate-400" : "text-slate-600"
                        }`}>
                          {bDim === "campus_name" ? (
                            <Compass className="w-3.5 h-3.5 text-blue-500" />
                          ) : bDim === "state" ? (
                            <MapPin className="w-3.5 h-3.5 text-blue-500" />
                          ) : (
                            <Layers className="w-3.5 h-3.5 text-blue-500" />
                          )}
                          <span>By {bDim.replace("_name", "").toUpperCase()}</span>
                        </p>
                        <div className={`border rounded-xl overflow-hidden text-xs ${
                          isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-xs"
                        }`}>
                          <table className={`w-full text-left ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                            <thead>
                              <tr className={`text-[9px] font-bold uppercase border-b ${
                                isDark ? "bg-[#192237] text-slate-400 border-[#1E293B]" : "bg-slate-50 text-slate-500 border-slate-200"
                              }`}>
                                <th className="p-2">Name</th>
                                <th className="p-2 text-right">Leads</th>
                                <th className="p-2 text-right">Admissions</th>
                                <th className="p-2 text-right">Conv.</th>
                              </tr>
                            </thead>
                            <tbody className={`divide-y ${isDark ? "divide-[#1E293B]/75" : "divide-slate-100"}`}>
                              {rows && rows.map((r, idx) => (
                                <tr key={idx} className={`transition-colors ${isDark ? "hover:bg-[#0B0F19]/50" : "hover:bg-slate-50"}`}>
                                  <td className="p-2 font-semibold truncate max-w-[150px]">{r.entity}</td>
                                  <td className="p-2 text-right font-mono">{r.leads.toLocaleString()}</td>
                                  <td className="p-2 text-right font-mono">{r.admissions.toLocaleString()}</td>
                                  <td className="p-2 text-right font-mono font-bold text-blue-500">{r.conversion_rate}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
