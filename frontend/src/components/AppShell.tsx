"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "../context/AppContext";
import {
  LayoutDashboard,
  UploadCloud,
  BarChart3,
  Layers,
  Bot,
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Sun,
  Moon,
  RefreshCw,
  Database,
  Menu,
  X,
  User,
  Calendar,
  RotateCcw,
  AlertCircle,
  Building2,
  GraduationCap,
  MapPin,
} from "lucide-react";

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname();
  const {
    theme,
    toggleTheme,
    activeDataset,
    selectedCampus,
    setSelectedCampus,
    availableCampuses,
    year,
    setYear,
    triggerRefresh,
    isLoadingDataset,
    periods,
    activePeriodLabel,
    setActivePeriodLabel,
    fromDate,
    setFromDate,
    toDate,
    setToDate,
    appliedFromDate,
    appliedToDate,
    dateRangeLimits,
    dateRangeError,
    applyDateRange,
    resetDateRange,
  } = useApp();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const isDark = theme === "dark";

  const getPageTitle = () => {
    switch (pathname) {
      case "/":
      case "/dashboard":
        return "Executive Dashboard";
      case "/upload":
        return "Data Ingestion Center";
      case "/counsellor-operations":
        return "Counsellor & Lead Operations";
      case "/ai-analyst":
        return "AI Agent Analyst Desk";
      case "/programs":
        return "Program Performance Report";
      case "/state-analysis":
        return "State Wise Analysis";
      default:
        return "Admissions Intelligence Engine";
    }
  };

  const navItems = [
    {
      path: "/",
      label: "Dashboard",
      icon: <LayoutDashboard className="w-5 h-5" />,
    },
    {
      path: "/programs",
      label: "Programs",
      icon: <GraduationCap className="w-5 h-5" />,
      badge: "NEW",
    },
    {
      path: "/state-analysis",
      label: "State Wise Analysis",
      icon: <MapPin className="w-5 h-5" />,
    },
    {
      path: "/upload",
      label: "Data Ingestion",
      icon: <UploadCloud className="w-5 h-5" />,
    },
    {
      path: "/counsellor-operations",
      label: "Counsellor Ops",
      icon: <User className="w-5 h-5" />,
    },
    {
      path: "/ai-analyst",
      label: "AI Analyst Desk",
      icon: <Bot className="w-5 h-5" />,
      badge: "AI",
    },
  ];

  const sidebarClass = `w-64 border-r shrink-0 flex flex-col justify-between transition-all duration-300 ${
    isDark
      ? "bg-[#0E1322] border-[#1E293B] text-slate-200"
      : "bg-white border-slate-200 text-slate-700"
  }`;

  const renderSidebar = () => (
    <div className="flex flex-col h-full justify-between">
      <div>
        {/* Brand Logo */}
        <div className={`p-6 border-b flex items-center gap-3 ${isDark ? "border-[#1E293B]" : "border-slate-100"}`}>
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h1 className={`font-bold text-base leading-snug tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
              AI Analytics
            </h1>
            <p className={`text-[10px] font-semibold tracking-wide uppercase ${isDark ? "text-blue-400" : "text-blue-600"}`}>
              Admissions Engine
            </p>
          </div>
        </div>

        {/* Navigation Items */}
        <div className="px-4 py-6">
          <p className={`px-3 mb-3 text-[10px] font-extrabold uppercase tracking-wider ${isDark ? "text-slate-500" : "text-slate-400"}`}>
            Workspaces
          </p>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive = pathname === item.path;
              return (
                <Link
                  key={item.path}
                  href={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150 border ${
                    isActive
                      ? isDark
                        ? "bg-blue-600/10 text-blue-400 border-blue-500/30 shadow-md shadow-blue-500/5"
                        : "bg-blue-50 text-blue-600 border-blue-100/85 shadow-2xs"
                      : isDark
                      ? "text-slate-400 hover:text-white hover:bg-slate-900 border-transparent"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-50 border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className={isActive ? (isDark ? "text-blue-400" : "text-blue-600") : "text-slate-400"}>
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>

                  {item.badge ? (
                    <span className="px-2 py-0.5 text-[9px] font-extrabold rounded-full bg-blue-600 text-white tracking-wider">
                      {item.badge}
                    </span>
                  ) : isActive ? (
                    <ChevronRight className="w-4 h-4 text-blue-500 animate-pulse" />
                  ) : null}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Persistent System Status indicator */}
      <div className={`p-4 m-4 rounded-xl border text-xs space-y-2.5 ${isDark ? "bg-[#131B2E] border-[#1E293B] text-slate-400" : "bg-slate-50 border-slate-100 text-slate-500"}`}>
        <div className="flex items-center gap-2 font-bold text-slate-300">
          <ShieldCheck className="w-4 h-4 text-emerald-500 animate-pulse" />
          <span className={isDark ? "text-slate-200" : "text-slate-700"}>System Status</span>
        </div>
        <div className="space-y-1.5 font-medium">
          <div className="flex items-center justify-between">
            <span>API Server</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Online
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Database</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Connected
            </span>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className={`flex h-screen overflow-hidden font-sans transition-colors duration-200 ${isDark ? "bg-[#0B0F19] text-slate-100" : "bg-slate-50 text-slate-900"}`}>
      {/* Desktop Persistent Sidebar */}
      <div className={`hidden lg:flex shrink-0 ${sidebarClass}`}>
        {renderSidebar()}
      </div>

      {/* Mobile Sidebar Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 bg-[#0B0F19]/60 backdrop-blur-xs flex lg:hidden">
          <div className={`w-64 h-full relative flex flex-col ${sidebarClass}`}>
            {renderSidebar()}
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="absolute top-4 right-[-44px] w-9 h-9 bg-slate-800 hover:bg-slate-700 text-white rounded-lg flex items-center justify-center transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="flex-1" onClick={() => setMobileMenuOpen(false)} />
        </div>
      )}

      {/* Main Workspace Frame */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Global Shared Top Bar */}
        <header className={`p-4 border-b flex items-center justify-between relative z-10 shrink-0 ${isDark ? "bg-[#0E1322] border-[#1E293B]" : "bg-white border-slate-200"}`}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className={`p-1.5 rounded-lg lg:hidden border ${isDark ? "bg-slate-900 border-[#1E293B] text-slate-400 hover:text-white" : "bg-slate-50 border-slate-200 text-slate-500 hover:text-slate-900"}`}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <h2 className={`text-base font-extrabold tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
                {getPageTitle()}
              </h2>
              {/* Dynamic dataset details in header */}
              {activeDataset ? (
                <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-medium mt-0.5">
                  <Database className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                  <span className={`truncate max-w-[150px] font-bold ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                    {activeDataset.dataset_name || activeDataset.original_filename}
                  </span>
                  {(activeDataset.academic_label || activePeriodLabel) && (
                    <>
                      <span className="text-slate-400">•</span>
                      <span className="text-blue-500 font-extrabold">
                        {activeDataset.academic_label || activePeriodLabel}
                      </span>
                    </>
                  )}
                  <span className="text-slate-400">•</span>
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded-md font-bold ${
                    isDark
                      ? "bg-slate-800/90 border border-slate-700/60 text-slate-300"
                      : "bg-slate-100 border border-slate-200 text-slate-700"
                  }`}>
                    {activeDataset.row_count.toLocaleString()} rows
                  </span>
                </div>
              ) : (
                <p className="text-[10px] text-slate-500 font-medium mt-0.5">No active dataset selected</p>
              )}
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center gap-2">
            {/* Global Academic Year Selector */}
            <div className="relative">
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border transition-all ${
                isDark 
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-200 hover:border-blue-500/50" 
                  : "bg-white border-slate-200 text-slate-700 hover:border-blue-400 shadow-xs"
              }`}>
                <Calendar className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                <select
                  id="appshell-year-selector"
                  value={year}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!isNaN(val)) setYear(val);
                  }}
                  className="bg-transparent text-xs font-bold focus:outline-none cursor-pointer pr-4 appearance-none"
                >
                  {periods && periods.length > 0 ? (
                    periods.map((p) => {
                      const yr = p.period_end_year || p.period_start_year || 0;
                      return (
                        <option key={p.academic_label || yr} value={yr} className={isDark ? "bg-[#131B2E] text-white" : "bg-white text-slate-800"}>
                          Session {p.academic_label || yr}
                        </option>
                      );
                    })
                  ) : (
                    <option value={year} className={isDark ? "bg-[#131B2E] text-white" : "bg-white text-slate-800"}>
                      Session {year}
                    </option>
                  )}
                </select>
                <ChevronRight className="w-3 h-3 rotate-90 text-slate-400 pointer-events-none -ml-3" />
              </div>
            </div>

            {/* Global Campus Selector */}
            <div className="relative">
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border transition-all ${
                isDark 
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-200 hover:border-indigo-500/50" 
                  : "bg-white border-slate-200 text-slate-700 hover:border-indigo-400 shadow-xs"
              }`}>
                <Building2 className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                <select
                  id="appshell-campus-selector"
                  value={selectedCampus}
                  onChange={(e) => setSelectedCampus(e.target.value)}
                  className="bg-transparent text-xs font-bold focus:outline-none cursor-pointer pr-4 appearance-none"
                >
                  <option value="all" className={isDark ? "bg-[#131B2E] text-white" : "bg-white text-slate-800"}>
                    All Campuses
                  </option>
                  {availableCampuses.map((c) => (
                    <option key={c} value={c} className={isDark ? "bg-[#131B2E] text-white" : "bg-white text-slate-800"}>
                      {c} Campus
                    </option>
                  ))}
                </select>
                <ChevronRight className="w-3 h-3 rotate-90 text-slate-400 pointer-events-none -ml-3" />
              </div>
            </div>

            {/* Global Date Range Filter */}
            <div className="relative flex items-center">
              <div
                className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border transition-all ${
                  dateRangeError
                    ? "border-rose-500/80 bg-rose-500/10 text-rose-300"
                    : (appliedFromDate || appliedToDate)
                    ? isDark
                      ? "bg-indigo-950/40 border-indigo-500/50 shadow-xs shadow-indigo-500/10"
                      : "bg-indigo-50/80 border-indigo-200 shadow-xs shadow-indigo-500/10"
                    : isDark
                    ? "bg-[#131B2E] border-[#1E293B] hover:border-slate-700"
                    : "bg-white border-slate-200 hover:border-slate-300 shadow-xs"
                }`}
              >
                <Calendar className={`w-3.5 h-3.5 shrink-0 ${(appliedFromDate || appliedToDate) ? "text-indigo-500" : "text-slate-400"}`} />
                
                {/* From Date Input */}
                <input
                  type="date"
                  id="global-from-date"
                  value={fromDate}
                  min={dateRangeLimits?.min_date}
                  max={dateRangeLimits?.max_date}
                  onChange={(e) => setFromDate(e.target.value)}
                  className={`px-1 py-0.5 text-xs font-semibold rounded bg-transparent focus:outline-none cursor-pointer ${
                    isDark ? "text-slate-200" : "text-slate-800"
                  }`}
                  title="From Date"
                />
                
                <span className="text-slate-400 text-xs font-bold select-none">→</span>
                
                {/* To Date Input */}
                <input
                  type="date"
                  id="global-to-date"
                  value={toDate}
                  min={dateRangeLimits?.min_date}
                  max={dateRangeLimits?.max_date}
                  onChange={(e) => setToDate(e.target.value)}
                  className={`px-1 py-0.5 text-xs font-semibold rounded bg-transparent focus:outline-none cursor-pointer ${
                    isDark ? "text-slate-200" : "text-slate-800"
                  }`}
                  title="To Date"
                />

                {/* Apply Button */}
                <button
                  id="global-date-apply-btn"
                  onClick={() => applyDateRange()}
                  className="px-3 py-1 text-xs font-bold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs transition-all cursor-pointer flex items-center gap-1 active:scale-95"
                  title="Apply date range filter"
                >
                  Apply
                </button>

                {/* Reset / Clear Button */}
                {(appliedFromDate || appliedToDate || fromDate || toDate) && (
                  <button
                    id="global-date-reset-btn"
                    onClick={() => resetDateRange()}
                    className="p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                    title="Reset to full period"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Validation Error Tooltip */}
              {dateRangeError && (
                <div className="absolute top-full left-0 mt-1.5 z-50 px-2.5 py-1 text-[11px] font-semibold text-rose-300 bg-slate-900 border border-rose-500/50 rounded-lg shadow-xl flex items-center gap-1.5 whitespace-nowrap animate-in fade-in slide-in-from-top-1">
                  <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                  <span>{dateRangeError}</span>
                </div>
              )}
            </div>

            {/* Refresh Trigger */}
            <button
              onClick={triggerRefresh}
              className={`p-2 rounded-xl border transition-all ${
                isDark
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-300 hover:text-white hover:border-indigo-500/40"
                  : "bg-white border-slate-200 text-slate-600 hover:text-slate-900 hover:border-indigo-300 shadow-xs"
              }`}
              title="Refresh database aggregation"
            >
              <RefreshCw className={`w-4 h-4 ${isLoadingDataset ? "animate-spin text-indigo-500" : ""}`} />
            </button>

            {/* Day / Night Theme Toggle */}
            <button
              id="theme-toggle-btn"
              onClick={toggleTheme}
              className={`p-2 rounded-xl border transition-all ${
                isDark
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-300 hover:text-amber-400 hover:border-indigo-500/40"
                  : "bg-white border-slate-200 text-slate-600 hover:text-indigo-600 hover:border-indigo-300 shadow-xs"
              }`}
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-600" />}
            </button>

            {/* Profile widget */}
            <div className={`hidden sm:flex items-center gap-2 pl-2 border-l ${isDark ? "border-[#1E293B]" : "border-slate-200"}`}>
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-blue-500 text-white flex items-center justify-center font-bold text-xs shadow-xs">
                <User className="w-4 h-4" />
              </div>
            </div>
          </div>
        </header>

        {/* Content Box */}
        <main className="p-6 max-w-7xl mx-auto w-full flex-1">
          {children}
        </main>
      </div>
    </div>
  );
};
