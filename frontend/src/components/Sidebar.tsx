"use client";

import React from "react";
import {
  LayoutDashboard,
  UploadCloud,
  BarChart3,
  TrendingUp,
  Layers,
  Bot,
  Sparkles,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";

export type NavTab = "dashboard" | "upload" | "analytics" | "historical" | "sources" | "chat";

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  className?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  className = "",
}) => {
  const navItems: {
    id: NavTab;
    label: string;
    icon: React.ReactNode;
    badge?: string;
  }[] = [
    {
      id: "dashboard",
      label: "Dashboard",
      icon: <LayoutDashboard className="w-5 h-5" />,
    },
    {
      id: "upload",
      label: "Data Upload",
      icon: <UploadCloud className="w-5 h-5" />,
    },
    {
      id: "analytics",
      label: "Analytics",
      icon: <BarChart3 className="w-5 h-5" />,
    },
    {
      id: "historical",
      label: "Historical Trends",
      icon: <TrendingUp className="w-5 h-5" />,
    },
    {
      id: "sources",
      label: "Source Performance",
      icon: <Layers className="w-5 h-5" />,
    },
    {
      id: "chat",
      label: "AI Analyst",
      icon: <Bot className="w-5 h-5" />,
      badge: "AI",
    },
  ];

  return (
    <aside
      className={`w-64 bg-white border-r border-slate-200 flex flex-col justify-between shrink-0 min-h-screen ${className}`}
    >
      <div>
        {/* Brand Header */}
        <div className="p-6 border-b border-slate-100 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-slate-900 text-base leading-snug tracking-tight">
              AI Analytics
            </h1>
            <p className="text-xs text-slate-500 font-medium">Admissions Engine</p>
          </div>
        </div>

        {/* Navigation Section */}
        <div className="px-4 py-6">
          <p className="px-3 mb-3 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
            Navigation
          </p>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onSelectTab(item.id)}
                  className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150 ${
                    isActive
                      ? "bg-blue-50 text-blue-600 border border-blue-100/80 shadow-xs"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`${
                        isActive ? "text-blue-600" : "text-slate-400"
                      }`}
                    >
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>

                  {item.badge ? (
                    <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-blue-600 text-white">
                      {item.badge}
                    </span>
                  ) : isActive ? (
                    <ChevronRight className="w-4 h-4 text-blue-500" />
                  ) : null}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer Info */}
      <div className="p-4 m-4 rounded-xl bg-slate-50 border border-slate-100 text-xs text-slate-500 space-y-2">
        <div className="flex items-center gap-2 text-slate-700 font-medium">
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          <span>System Status</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          FastAPI Engine connected at <span className="font-mono text-[10px] bg-slate-200/60 px-1 py-0.5 rounded">127.0.0.1:8000</span>
        </p>
      </div>
    </aside>
  );
};
