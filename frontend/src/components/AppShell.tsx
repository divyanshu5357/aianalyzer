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
  TrendingUp,
  User,
} from "lucide-react";

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname();
  const {
    theme,
    toggleTheme,
    activeDataset,
    year,
    setYear,
    triggerRefresh,
    isLoadingDataset,
    periods,
    activePeriodLabel,
    setActivePeriodLabel,
  } = useApp();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const isDark = theme === "dark";

  // Mapping paths to titles
  const getPageTitle = () => {
    switch (pathname) {
      case "/":
      case "/dashboard":
        return "Executive Dashboard";
      case "/upload":
        return "Data Ingestion Center";
      case "/analytics":
        return "Analytical Exploration";
      case "/source-analytics":
        return "Source Analytics";
      case "/program-analytics":
        return "Program Analytics";
      case "/comparisons":
        return "Comparisons Workspace";
      case "/insights":
        return "Automated Data Insights";
      case "/ai-analyst":
        return "AI Agent Analyst";
      case "/historical-trends":
        return "Historical Trends";
      case "/source-performance":
        return "Source Performance";
      default:
        return "Admissions Intelligence";
    }
  };

  const navItems = [
    {
      path: "/",
      label: "Dashboard",
      icon: <LayoutDashboard className="w-5 h-5" />,
    },
    {
      path: "/upload",
      label: "Data Ingestion",
      icon: <UploadCloud className="w-5 h-5" />,
    },
    {
      path: "/analytics",
      label: "Detailed Explore",
      icon: <BarChart3 className="w-5 h-5" />,
    },
    {
      path: "/historical-trends",
      label: "Historical Trends",
      icon: <TrendingUp className="w-5 h-5" />,
    },
    {
      path: "/source-analytics",
      label: "Source Analytics",
      icon: <Layers className="w-5 h-5" />,
    },
    {
      path: "/program-analytics",
      label: "Program Analytics",
      icon: <TrendingUp className="w-5 h-5" />,
    },
    {
      path: "/comparisons",
      label: "Comparisons",
      icon: <TrendingUp className="w-5 h-5" />,
    },
    {
      path: "/insights",
      label: "Insights Engine",
      icon: <Sparkles className="w-5 h-5" />,
    },
    {
      path: "/source-performance",
      label: "Source Performance",
      icon: <Layers className="w-5 h-5" />,
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
                  <span className="truncate max-w-[150px] font-bold text-slate-300">
                    {activeDataset.dataset_name || activeDataset.original_filename}
                  </span>
                  {(activeDataset.academic_label || activePeriodLabel) && (
                    <>
                      <span className="text-slate-500">•</span>
                      <span className="text-blue-400 font-bold">
                        {activeDataset.academic_label || activePeriodLabel}
                      </span>
                    </>
                  )}
                  <span className="text-slate-500">•</span>
                  <span className="font-mono text-[9px] bg-slate-800 px-1 py-0.2 rounded text-slate-400">
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
            {/* Dynamic period/year selector — driven by /api/periods */}
            {activeDataset && (
              <div className="relative">
                <select
                  id="appshell-period-selector"
                  value={activePeriodLabel ?? String(year)}
                  onChange={(e) => {
                    const val = e.target.value;
                    const period = periods.find((p) => p.academic_label === val);
                    if (period) {
                      setActivePeriodLabel(val);
                      if (period.period_end_year) setYear(period.period_end_year);
                    } else {
                      setYear(Number(val));
                    }
                  }}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg border appearance-none pr-8 cursor-pointer focus:outline-none transition-all ${
                    isDark
                      ? "bg-[#131B2E] border-[#1E293B] text-slate-200 focus:border-blue-500/50"
                      : "bg-white border-slate-200 text-slate-700 focus:border-blue-500"
                  }`}
                >
                  {periods.filter(p => /^\d{4}-\d{2}$/.test(p.academic_label ?? "")).length > 0 ? (
                    periods
                      .filter(p => /^\d{4}-\d{2}$/.test(p.academic_label ?? ""))
                      .map((p) => (
                      <option key={p.academic_label} value={p.academic_label}>
                        {p.academic_label}{p.active_dataset_id ? " ✓" : ""}
                      </option>
                    ))
                  ) : (
                    // Fallback while periods are loading
                    [year, year - 1, year - 2].map((y) => (
                      <option key={y} value={y}>Year {y}</option>
                    ))
                  )}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400">
                  <ChevronRight className="w-3 h-3 rotate-90" />
                </div>
              </div>
            )}

            {/* Refresh Trigger */}
            <button
              onClick={triggerRefresh}
              className={`p-2 rounded-lg border transition-all ${
                isDark
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-300 hover:text-white hover:bg-slate-800"
                  : "bg-white border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50"
              }`}
              title="Refresh database aggregation"
            >
              <RefreshCw className={`w-4 h-4 ${isLoadingDataset ? "animate-spin text-blue-400" : ""}`} />
            </button>

            {/* Day / Night Theme Toggle */}
            <button
              onClick={toggleTheme}
              className={`p-2 rounded-lg border transition-all ${
                isDark
                  ? "bg-[#131B2E] border-[#1E293B] text-slate-300 hover:text-white hover:bg-slate-800"
                  : "bg-white border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50"
              }`}
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {isDark ? <Sun className="w-4 h-4 text-amber-400 animate-spin" /> : <Moon className="w-4 h-4 text-indigo-600" />}
            </button>

            {/* Profile widget */}
            <div className={`hidden sm:flex items-center gap-2 pl-2 border-l ${isDark ? "border-[#1E293B]" : "border-slate-200"}`}>
              <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs">
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
