"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  Users,
  Award,
  ArrowLeft,
  Search,
  Filter,
  RefreshCw,
  ChevronRight,
  CheckCircle2,
  Calendar,
  FileSpreadsheet,
  FileText,
  Loader2,
  TrendingUp,
  PhoneCall,
  ChevronLeft,
  Layers,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import {
  getCounsellorsList,
  getCounsellorReport,
  getLeadActivityReport,
  getCounsellorExportUrl,
  CounsellorListItem,
  CounsellorDetailReport,
} from "../lib/api";
import dashboardCache from "../lib/cache/dashboardCache";

export const CounsellorOperations: React.FC = () => {
  const { theme, activePeriodLabel, periods, availableCampuses, analyticalYears } = useApp();
  const isDark = theme === "dark";

  // Level selection state: null = Level 1 (List), non-null = Level 2 (Detail Report)
  const [selectedCounsellor, setSelectedCounsellor] = useState<CounsellorListItem | null>(null);

  // Filter state
  const defaultYear = useMemo(() => {
    if (activePeriodLabel && /^\d{4}/.test(activePeriodLabel)) {
      return activePeriodLabel.slice(0, 4);
    }
    if (periods && periods.length > 0) {
      return String(periods[0].period_start_year || periods[0].period_end_year || new Date().getFullYear());
    }
    return String(new Date().getFullYear());
  }, [activePeriodLabel, periods]);

  const [selectedYear, setSelectedYear] = useState<string>(defaultYear);
  const [selectedCampus, setSelectedCampus] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const initialListKey = dashboardCache.buildKey("counsellors:list", {
    academic_year: selectedYear,
    campus: selectedCampus,
    search: searchQuery,
  });
  const cachedInitialList = dashboardCache.peek<any>(initialListKey);

  // Level 1 Data state
  const [listData, setListData] = useState<{
    counsellors: CounsellorListItem[];
    total_counsellors: number;
    summary: {
      total_leads_assigned: number;
      total_admissions: number;
      overall_conversion_rate: number;
      conversion_rate_display: string;
    };
  } | null>(() => cachedInitialList);
  const [isLoadingList, setIsLoadingList] = useState<boolean>(() => !cachedInitialList);

  // Level 2 Data state
  const [reportData, setReportData] = useState<CounsellorDetailReport | null>(null);
  const [isLoadingReport, setIsLoadingReport] = useState<boolean>(false);

  // Optional Scoped Lead Activity state
  const [showLeadActivity, setShowLeadActivity] = useState<boolean>(false);
  const [leadsData, setLeadsData] = useState<any>(null);
  const [isLoadingLeads, setIsLoadingLeads] = useState<boolean>(false);
  const [leadPage, setLeadPage] = useState<number>(1);
  const [leadSearch, setLeadSearch] = useState<string>("");

  const [isExporting, setIsExporting] = useState<boolean>(false);

  // ----------------------------------------------------
  // Level 1: Fetch Counsellors Summary List
  // ----------------------------------------------------
  const fetchCounsellorsList = useCallback(async () => {
    const key = dashboardCache.buildKey("counsellors:list", {
      academic_year: selectedYear,
      campus: selectedCampus,
      search: searchQuery,
    });
    const cached = dashboardCache.peek<any>(key);
    if (cached) {
      setListData(cached);
      setIsLoadingList(false);
    } else {
      setIsLoadingList(true);
    }

    try {
      const res = await dashboardCache.fetchWithCache(
        key,
        () =>
          getCounsellorsList({
            academic_year: selectedYear,
            campus: selectedCampus,
            search: searchQuery,
          })
      );
      setListData(res);
    } catch (err) {
      console.error("Failed to fetch counsellors list:", err);
    } finally {
      setIsLoadingList(false);
    }
  }, [selectedYear, selectedCampus, searchQuery]);

  useEffect(() => {
    fetchCounsellorsList();
  }, [fetchCounsellorsList]);

  // ----------------------------------------------------
  // Level 2: Fetch Selected Counsellor Detail Report
  // ----------------------------------------------------
  const fetchDetailReport = useCallback(async (counsellor: CounsellorListItem) => {
    const targetId = counsellor.raw_counsellor || counsellor.owner_id || counsellor.counsellor;
    const key = dashboardCache.buildKey(`counsellors:detail:${targetId}`, {
      academic_year: selectedYear,
      campus: selectedCampus,
    });
    const cached = dashboardCache.peek<CounsellorDetailReport>(key);
    if (cached) {
      setReportData(cached);
      setIsLoadingReport(false);
    } else {
      setIsLoadingReport(true);
    }

    try {
      const res = await dashboardCache.fetchWithCache(
        key,
        () =>
          getCounsellorReport(targetId, {
            academic_year: selectedYear,
            campus: selectedCampus,
          })
      );
      setReportData(res);
    } catch (err) {
      console.error("Failed to fetch counsellor detail report:", err);
    } finally {
      setIsLoadingReport(false);
    }
  }, [selectedYear, selectedCampus]);

  useEffect(() => {
    if (selectedCounsellor) {
      fetchDetailReport(selectedCounsellor);
      // Reset lead activity when switching counsellor
      setShowLeadActivity(false);
      setLeadsData(null);
      setLeadPage(1);
    } else {
      setReportData(null);
    }
  }, [selectedCounsellor, fetchDetailReport]);

  // ----------------------------------------------------
  // Level 2: Fetch Scoped Lead Activity on demand
  // ----------------------------------------------------
  const fetchScopedLeads = useCallback(async () => {
    if (!selectedCounsellor || !showLeadActivity) return;
    setIsLoadingLeads(true);
    try {
      const res = await getLeadActivityReport({
        academic_year: selectedYear,
        campus: selectedCampus,
        counsellor: selectedCounsellor.raw_counsellor,
        search: leadSearch,
        page: leadPage,
        page_size: 20,
      });
      setLeadsData(res);
    } catch (err) {
      console.error("Failed to fetch scoped lead activity:", err);
    } finally {
      setIsLoadingLeads(false);
    }
  }, [selectedCounsellor, showLeadActivity, selectedYear, selectedCampus, leadSearch, leadPage]);

  useEffect(() => {
    if (showLeadActivity && selectedCounsellor) {
      fetchScopedLeads();
    }
  }, [showLeadActivity, selectedCounsellor, fetchScopedLeads]);

  // Handle Export
  const handleExport = (format: "csv" | "xlsx") => {
    setIsExporting(true);
    const counsellorParam = selectedCounsellor ? selectedCounsellor.raw_counsellor : undefined;
    const url = getCounsellorExportUrl(format, "counsellor_performance", {
      academic_year: selectedYear,
      campus: selectedCampus,
      counsellor: counsellorParam,
    });
    window.open(url, "_blank");
    setTimeout(() => setIsExporting(false), 1500);
  };

  // Client-side search filtering over Level 1 counsellors for instant snappy response
  const filteredCounsellors = useMemo(() => {
    if (!listData?.counsellors) return [];
    if (!searchQuery.trim()) return listData.counsellors;
    const q = searchQuery.toLowerCase().trim();
    return listData.counsellors.filter(
      (c) =>
        (c.counsellor_name && c.counsellor_name.toLowerCase().includes(q)) ||
        (c.owner_id && c.owner_id.toLowerCase().includes(q)) ||
        (c.raw_counsellor && c.raw_counsellor.toLowerCase().includes(q))
    );
  }, [listData, searchQuery]);

  // Academic years options
  const yearOptions = useMemo(() => {
    const list: string[] = ["all"];
    if (analyticalYears && analyticalYears.length > 0) {
      analyticalYears.forEach((y) => {
        const yStr = String(y);
        if (!list.includes(yStr)) list.push(yStr);
      });
    } else if (periods && periods.length > 0) {
      periods.forEach((p) => {
        if (p.period_end_year && !list.includes(String(p.period_end_year))) {
          list.push(String(p.period_end_year));
        }
        if (p.period_start_year && !list.includes(String(p.period_start_year))) {
          list.push(String(p.period_start_year));
        }
      });
    }
    if (list.length === 1) {
      list.push(String(new Date().getFullYear()));
    }
    return list;
  }, [analyticalYears, periods]);

  // =========================================================================
  // LEVEL 2 — COUNSELLOR PERFORMANCE REPORT VIEW
  // =========================================================================
  if (selectedCounsellor) {
    const counsellorInfo = reportData?.counsellor || {
      counsellor_name: selectedCounsellor.counsellor_name,
      owner_id: selectedCounsellor.owner_id,
      raw_counsellor: selectedCounsellor.raw_counsellor,
    };
    const summary = reportData?.summary;
    const categories = reportData?.categories || [];

    return (
      <div className="space-y-6 pb-16 animate-in fade-in duration-200">
        {/* Level 2 Top Header */}
        <div
          className={`p-6 rounded-2xl border flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm ${
            isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200"
          }`}
        >
          <div className="space-y-2">
            <button
              onClick={() => setSelectedCounsellor(null)}
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                isDark
                  ? "bg-[#0B0F19] border border-[#1E293B] text-slate-300 hover:text-white hover:border-blue-500"
                  : "bg-slate-100 border border-slate-200 text-slate-700 hover:text-blue-600 hover:border-blue-300"
              }`}
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back to Counsellors List
            </button>

            <div>
              <div className="flex items-center gap-2 mt-1">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className={`text-[10px] font-extrabold uppercase tracking-wider ${isDark ? "text-emerald-400" : "text-emerald-600"}`}>
                  Counsellor Performance Detail
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-3 mt-1">
                <h1 className={`text-2xl font-black tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
                  {counsellorInfo.counsellor_name || selectedCounsellor.counsellor_name}
                </h1>
                {counsellorInfo.owner_id && (
                  <span className="px-2.5 py-1 rounded-lg font-mono text-xs font-bold bg-blue-500/10 text-blue-500 border border-blue-500/20">
                    ID: {counsellorInfo.owner_id}
                  </span>
                )}
                <span className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  ({counsellorInfo.raw_counsellor})
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => handleExport("csv")}
              disabled={isExporting}
              className={`px-4 py-2 rounded-xl border font-bold text-xs flex items-center gap-2 transition-all ${
                isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200 hover:border-blue-500" : "bg-slate-100 border-slate-200 text-slate-800 hover:border-blue-400"
              }`}
            >
              <FileText className="w-4 h-4 text-blue-500" /> Export CSV
            </button>
            <button
              onClick={() => handleExport("xlsx")}
              disabled={isExporting}
              className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs flex items-center gap-2 shadow-md transition-all"
            >
              <FileSpreadsheet className="w-4 h-4" /> Export XLSX
            </button>
          </div>
        </div>

        {/* Level 2: 4 KPI Cards */}
        {isLoadingReport ? (
          <div className="flex items-center justify-center py-16 gap-3 text-xs font-bold text-blue-500">
            <Loader2 className="w-6 h-6 animate-spin" /> Loading counsellor performance metrics...
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* KPI 1: Total Leads Assigned */}
              <div className={`p-5 rounded-2xl border ${isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-extrabold uppercase tracking-wider ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Total Leads Assigned
                  </span>
                  <Users className="w-4 h-4 text-blue-500" />
                </div>
                <div className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
                  {summary?.total_leads_assigned?.toLocaleString() ?? selectedCounsellor.leads_assigned?.toLocaleString()}
                </div>
                <div className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Distinct ProspectIDs
                </div>
              </div>

              {/* KPI 2: Total Admissions */}
              <div className={`p-5 rounded-2xl border ${isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-extrabold uppercase tracking-wider ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Total Admissions
                  </span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-2xl font-black text-emerald-500">
                  {summary?.total_admissions?.toLocaleString() ?? selectedCounsellor.admissions?.toLocaleString()}
                </div>
                <div className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Confirmed enrolled students
                </div>
              </div>

              {/* KPI 3: Conversion Rate */}
              <div className={`p-5 rounded-2xl border ${isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-extrabold uppercase tracking-wider ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Conversion Rate
                  </span>
                  <TrendingUp className="w-4 h-4 text-purple-500" />
                </div>
                <div className="text-2xl font-black text-purple-500">
                  {summary?.conversion_rate_display ?? selectedCounsellor.conversion_rate_display}
                </div>
                <div className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Admissions / Assigned Leads
                </div>
              </div>

              {/* KPI 4: Best Performing Source Category */}
              <div className={`p-5 rounded-2xl border ${isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-extrabold uppercase tracking-wider ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Best Source Category
                  </span>
                  <Award className="w-4 h-4 text-amber-500" />
                </div>
                <div className={`text-2xl font-black truncate ${isDark ? "text-amber-400" : "text-amber-600"}`}>
                  {summary?.best_source_category || "N/A"}
                </div>
                <div className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Highest valid conversion rate
                </div>
              </div>
            </div>

            {/* Source Category Performance Table */}
            <div className={`p-6 rounded-3xl border ${isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"}`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
                <div>
                  <h2 className={`text-base font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
                    <Layers className="w-4 h-4 text-blue-500" />
                    Source Category Performance
                  </h2>
                  <p className={`text-xs mt-0.5 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Ranked by conversion rate descending. Dynamically populated from organization source master.
                  </p>
                </div>
                {summary?.best_source_category && summary.best_source_category !== "N/A" && (
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/20 text-xs font-bold w-fit">
                    <Sparkles className="w-3.5 h-3.5" /> Best: {summary.best_source_category}
                  </div>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr
                      className={`border-b text-[11px] font-extrabold uppercase tracking-wider ${
                        isDark ? "border-slate-800 text-slate-400" : "border-slate-200 text-slate-500"
                      }`}
                    >
                      <th className="py-3.5 px-4">Source Category</th>
                      <th className="py-3.5 px-4 text-right">Leads Assigned</th>
                      <th className="py-3.5 px-4 text-right">Admissions</th>
                      <th className="py-3.5 px-4 text-right">Conversion %</th>
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? "divide-slate-800/60" : "divide-slate-200"}`}>
                    {categories.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-8 text-center text-slate-500 italic">
                          No category performance data found for this counsellor.
                        </td>
                      </tr>
                    ) : (
                      categories.map((cat, idx) => {
                        const isBest = cat.category === summary?.best_source_category && cat.conversion_rate !== null && cat.leads_assigned > 0;
                        const isZeroLeads = cat.leads_assigned === 0;

                        return (
                          <tr
                            key={cat.category}
                            className={`transition-colors ${
                              isBest
                                ? isDark
                                  ? "bg-amber-500/5 hover:bg-amber-500/10"
                                  : "bg-amber-50/60 hover:bg-amber-100/50"
                                : isDark
                                ? "hover:bg-slate-800/30"
                                : "hover:bg-slate-50"
                            }`}
                          >
                            <td className="py-3.5 px-4 font-bold flex items-center gap-2">
                              <span>{cat.category}</span>
                              {isBest && (
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-amber-500 text-slate-950 flex items-center gap-1">
                                  <Award className="w-3 h-3" /> BEST
                                </span>
                              )}
                            </td>
                            <td className="py-3.5 px-4 text-right font-extrabold text-sm">
                              {cat.leads_assigned.toLocaleString()}
                            </td>
                            <td className="py-3.5 px-4 text-right font-extrabold text-sm text-emerald-500">
                              {cat.admissions.toLocaleString()}
                            </td>
                            <td className="py-3.5 px-4 text-right">
                              {isZeroLeads ? (
                                <span className={`font-mono text-xs font-bold px-2 py-0.5 rounded ${
                                  isDark ? "bg-slate-800 text-slate-400" : "bg-slate-100 text-slate-500"
                                }`}>
                                  N/A
                                </span>
                              ) : (
                                <span className="font-extrabold text-sm text-purple-500">
                                  {cat.conversion_rate_display}
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Optional Scoped Lead Activity Drawer/Section */}
            <div className={`p-6 rounded-3xl border transition-all ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className={`text-base font-extrabold flex items-center gap-2 ${isDark ? "text-white" : "text-slate-900"}`}>
                    <PhoneCall className="w-4 h-4 text-blue-500" />
                    Detailed Lead Activity Records
                  </h3>
                  <p className={`text-xs mt-0.5 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    Server-side paginated enquiry audit scoped strictly to this counsellor.
                  </p>
                </div>

                <button
                  onClick={() => setShowLeadActivity(!showLeadActivity)}
                  className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all border ${
                    showLeadActivity
                      ? isDark
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "bg-blue-600 border-blue-600 text-white"
                      : isDark
                      ? "bg-[#0B0F19] border-[#1E293B] text-slate-300 hover:border-blue-500 hover:text-white"
                      : "bg-slate-100 border-slate-200 text-slate-700 hover:border-blue-400"
                  }`}
                >
                  {showLeadActivity ? "Hide Lead Activity" : "View Lead Activity"}
                </button>
              </div>

              {showLeadActivity && (
                <div className="mt-6 pt-6 border-t border-slate-800/60 space-y-4 animate-in fade-in duration-200">
                  {/* Scoped Search */}
                  <div className="flex items-center gap-3">
                    <div className="relative flex-1 max-w-md">
                      <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                      <input
                        type="text"
                        placeholder="Search ProspectID or Lead Name..."
                        value={leadSearch}
                        onChange={(e) => {
                          setLeadSearch(e.target.value);
                          setLeadPage(1);
                        }}
                        className={`w-full pl-9 pr-3 py-1.5 rounded-xl border text-xs font-medium ${
                          isDark ? "bg-[#0B0F19] border-[#1E293B] text-white" : "bg-slate-50 border-slate-200 text-slate-900"
                        }`}
                      />
                    </div>
                    {leadsData && (
                      <span className={`text-xs font-bold ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                        {leadsData.total_leads?.toLocaleString()} records found
                      </span>
                    )}
                  </div>

                  {isLoadingLeads ? (
                    <div className="flex items-center justify-center py-12 gap-3 text-xs font-bold text-blue-500">
                      <Loader2 className="w-5 h-5 animate-spin" /> Fetching paginated lead records...
                    </div>
                  ) : !leadsData || leadsData.leads?.length === 0 ? (
                    <div className="py-8 text-center text-xs italic text-slate-500">
                      No lead activity records found matching the query.
                    </div>
                  ) : (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs border-collapse">
                          <thead>
                            <tr
                              className={`border-b text-[11px] font-extrabold uppercase tracking-wider ${
                                isDark ? "border-slate-800 text-slate-400" : "border-slate-200 text-slate-500"
                              }`}
                            >
                              <th className="py-3 px-3">Prospect ID</th>
                              <th className="py-3 px-3">Program</th>
                              <th className="py-3 px-3">Cluster</th>
                              <th className="py-3 px-3 text-center">Total Calls</th>
                              <th className="py-3 px-3">First Disposition</th>
                              <th className="py-3 px-3">Follow-up</th>
                              <th className="py-3 px-3">Admission</th>
                            </tr>
                          </thead>
                          <tbody className={`divide-y ${isDark ? "divide-slate-800/60" : "divide-slate-200"}`}>
                            {leadsData.leads.map((l: any) => (
                              <tr key={l.prospect_id} className={isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50"}>
                                <td className="py-2.5 px-3 font-mono text-[11px] text-blue-500 font-bold">
                                  {l.prospect_id}
                                </td>
                                <td className="py-2.5 px-3 max-w-[200px] truncate">{l.program_name}</td>
                                <td className="py-2.5 px-3 text-slate-400">{l.course_cluster || "—"}</td>
                                <td className="py-2.5 px-3 text-center font-bold">{l.total_call_attempts}</td>
                                <td className="py-2.5 px-3">{l.first_call_disposition || "N/A"}</td>
                                <td className="py-2.5 px-3">
                                  <span
                                    className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                                      l.followup_status === "Overdue"
                                        ? "bg-rose-500/10 text-rose-500"
                                        : l.followup_status === "Due Today"
                                        ? "bg-amber-500/10 text-amber-500"
                                        : "bg-emerald-500/10 text-emerald-500"
                                    }`}
                                  >
                                    {l.followup_status}
                                  </span>
                                </td>
                                <td className="py-2.5 px-3">
                                  {l.is_admitted ? (
                                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-500 rounded-full font-bold text-[10px] flex items-center gap-1 w-fit">
                                      <CheckCircle2 className="w-3 h-3" /> Enrolled
                                    </span>
                                  ) : (
                                    <span className="text-slate-400 font-semibold text-[10px]">Pending</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Pagination Controls */}
                      {leadsData.total_pages > 1 && (
                        <div className="flex items-center justify-between pt-4 border-t border-slate-800/60">
                          <span className={`text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                            Page {leadPage} of {leadsData.total_pages} ({leadsData.total_leads} leads)
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              disabled={leadPage <= 1}
                              onClick={() => setLeadPage((p) => Math.max(1, p - 1))}
                              className="px-3 py-1 rounded-lg border text-xs font-bold disabled:opacity-40"
                            >
                              Previous
                            </button>
                            <button
                              disabled={leadPage >= leadsData.total_pages}
                              onClick={() => setLeadPage((p) => p + 1)}
                              className="px-3 py-1 rounded-lg border text-xs font-bold disabled:opacity-40"
                            >
                              Next
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    );
  }

  // =========================================================================
  // LEVEL 1 — COUNSELLOR LIST VIEW
  // =========================================================================
  const summaryKpis = listData?.summary;

  return (
    <div className="space-y-6 pb-16 animate-in fade-in duration-200">
      {/* Top Header */}
      <div
        className={`p-6 rounded-2xl border flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm ${
          isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200"
        }`}
      >
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span className={`text-[10px] font-extrabold uppercase tracking-wider ${isDark ? "text-blue-400" : "text-blue-600"}`}>
              Counsellor Operations
            </span>
          </div>
          <h1 className={`text-2xl font-black tracking-tight mt-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Counsellor Performance Directory
          </h1>
          <p className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-600"}`}>
            Click any counsellor row to open their dedicated performance and source category breakdown report.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => handleExport("csv")}
            disabled={isExporting}
            className={`px-4 py-2 rounded-xl border font-bold text-xs flex items-center gap-2 transition-all ${
              isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200 hover:border-blue-500" : "bg-slate-100 border-slate-200 text-slate-800 hover:border-blue-400"
            }`}
          >
            <FileText className="w-4 h-4 text-blue-500" /> Export CSV
          </button>
          <button
            onClick={() => handleExport("xlsx")}
            disabled={isExporting}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs flex items-center gap-2 shadow-md transition-all"
          >
            <FileSpreadsheet className="w-4 h-4" /> Export XLSX
          </button>
        </div>
      </div>

      {/* Clean Minimal Filters */}
      <div
        className={`p-4 rounded-2xl border flex flex-wrap items-center gap-3 ${
          isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
        }`}
      >
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-blue-500" />
          <span className={`text-xs font-extrabold uppercase tracking-wider ${isDark ? "text-slate-300" : "text-slate-700"}`}>
            Filters:
          </span>
        </div>

        {/* Academic Year */}
        <div className="flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(e.target.value)}
            className={`px-3 py-1.5 rounded-xl border text-xs font-bold transition-all ${
              isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200" : "bg-slate-50 border-slate-200 text-slate-800"
            }`}
          >
            {yearOptions.map((y) => (
              <option key={y} value={y}>
                {y === "all" ? "All Academic Years" : `Academic Year ${y}`}
              </option>
            ))}
          </select>
        </div>

        {/* Campus */}
        <select
          value={selectedCampus}
          onChange={(e) => setSelectedCampus(e.target.value)}
          className={`px-3 py-1.5 rounded-xl border text-xs font-bold transition-all ${
            isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-200" : "bg-slate-50 border-slate-200 text-slate-800"
          }`}
        >
          <option value="all">All Campuses</option>
          {availableCampuses && availableCampuses.map((c) => (
            <option key={c} value={c}>
              {c} Campus
            </option>
          ))}
        </select>

        {/* Search Counsellor */}
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search counsellor by name or owner ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={`w-full pl-9 pr-3 py-1.5 rounded-xl border text-xs font-medium transition-all ${
              isDark ? "bg-[#0B0F19] border-[#1E293B] text-white" : "bg-slate-50 border-slate-200 text-slate-900"
            }`}
          />
        </div>

        {/* Refresh Button */}
        <button
          onClick={fetchCounsellorsList}
          className={`p-2 rounded-xl border transition-all ${
            isDark ? "bg-[#0B0F19] border-[#1E293B] text-slate-400 hover:text-white hover:border-blue-500" : "bg-slate-50 border-slate-200 text-slate-600 hover:border-blue-400"
          }`}
          title="Refresh List"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoadingList ? "animate-spin text-blue-500" : ""}`} />
        </button>
      </div>

      {/* Summary KPI Banner */}
      {summaryKpis && (
        <div className={`px-6 py-4 rounded-2xl border flex flex-wrap items-center justify-between gap-4 text-xs font-semibold ${
          isDark ? "bg-[#131B2E]/70 border-[#1E293B] text-slate-300" : "bg-slate-50 border-slate-200 text-slate-700"
        }`}>
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-500" />
            <span>Total Counsellors: <strong className="text-blue-500 font-extrabold">{filteredCounsellors.length}</strong></span>
          </div>
          <div>
            <span>Assigned Leads: <strong className="font-extrabold">{summaryKpis.total_leads_assigned.toLocaleString()}</strong></span>
          </div>
          <div>
            <span>Total Admissions: <strong className="font-extrabold text-emerald-500">{summaryKpis.total_admissions.toLocaleString()}</strong></span>
          </div>
          <div>
            <span>Overall Conversion: <strong className="font-extrabold text-purple-500">{summaryKpis.conversion_rate_display}</strong></span>
          </div>
        </div>
      )}

      {/* Clean Counsellor List Table */}
      <div className={`p-6 rounded-3xl border ${isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className={`text-base font-extrabold ${isDark ? "text-white" : "text-slate-900"}`}>
            All Counsellors ({filteredCounsellors.length})
          </h2>
          <span className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Click any row to open detailed report
          </span>
        </div>

        {isLoadingList ? (
          <div className="flex items-center justify-center py-16 gap-3 text-xs font-bold text-blue-500">
            <Loader2 className="w-6 h-6 animate-spin" /> Loading counsellors directory...
          </div>
        ) : filteredCounsellors.length === 0 ? (
          <div className="py-16 text-center text-xs italic text-slate-500">
            No counsellors match the search filter.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr
                  className={`border-b text-[11px] font-extrabold uppercase tracking-wider ${
                    isDark ? "border-slate-800 text-slate-400" : "border-slate-200 text-slate-500"
                  }`}
                >
                  <th className="py-3.5 px-4">Counsellor</th>
                  <th className="py-3.5 px-4">Owner ID</th>
                  <th className="py-3.5 px-4 text-right">Leads Assigned</th>
                  <th className="py-3.5 px-4 text-right">Total Admissions</th>
                  <th className="py-3.5 px-4 text-right">Overall Conversion %</th>
                  <th className="py-3.5 px-4 text-center">Action</th>
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? "divide-slate-800/60" : "divide-slate-200"}`}>
                {filteredCounsellors.map((c) => (
                  <tr
                    key={c.raw_counsellor}
                    onClick={() => setSelectedCounsellor(c)}
                    className={`cursor-pointer transition-all ${
                      isDark ? "hover:bg-slate-800/50" : "hover:bg-blue-50/50"
                    }`}
                  >
                    <td className="py-3.5 px-4 font-bold text-sm">
                      <div className="flex items-center gap-2">
                        <span>{c.counsellor_name}</span>
                        {c.raw_counsellor !== c.counsellor_name && (
                          <span className={`text-[10px] hidden sm:inline ${isDark ? "text-slate-500" : "text-slate-400"}`}>
                            ({c.raw_counsellor})
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      {c.owner_id ? (
                        <span className="px-2 py-0.5 rounded font-mono text-xs font-bold bg-blue-500/10 text-blue-500 border border-blue-500/20">
                          {c.owner_id}
                        </span>
                      ) : (
                        <span className="text-slate-400 font-mono text-xs">—</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-right font-extrabold text-sm">
                      {c.leads_assigned.toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4 text-right font-extrabold text-sm text-emerald-500">
                      {c.admissions.toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4 text-right font-extrabold text-sm text-purple-500">
                      {c.conversion_rate_display}
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCounsellor(c);
                        }}
                        className={`inline-flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                          isDark
                            ? "bg-[#0B0F19] text-blue-400 border border-blue-500/30 hover:bg-blue-600 hover:text-white"
                            : "bg-blue-50 text-blue-600 border border-blue-200 hover:bg-blue-600 hover:text-white"
                        }`}
                      >
                        View Report <ChevronRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
