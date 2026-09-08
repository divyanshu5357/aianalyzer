"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "../context/AppContext";
import { ExecutiveDashboard } from "../components/ExecutiveDashboard";
import { UploadCloud, ArrowRight, Loader2 } from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const { activeDataset, isLoadingDataset, periods, setSeededPrompt, theme } = useApp();
  const isDark = theme === "dark";

  const hasNoData = !isLoadingDataset && !activeDataset && (!periods || periods.length === 0);

  useEffect(() => {
    if (hasNoData) {
      const timer = setTimeout(() => {
        router.push("/upload");
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [hasNoData, router]);

  const handleNavigate = (tab: string) => {
    if (tab === "chat") {
      router.push("/ai-analyst");
    } else if (tab === "dashboard") {
      router.push("/");
    } else {
      router.push(`/${tab}`);
    }
  };

  if (hasNoData) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-8 space-y-5">
        <div className={`p-5 rounded-3xl border shadow-lg ${
          isDark ? "bg-blue-950/40 border-blue-800 text-blue-400" : "bg-blue-50 border-blue-200 text-blue-600"
        }`}>
          <UploadCloud className="w-14 h-14 animate-bounce" />
        </div>
        <div className="max-w-md space-y-2">
          <h2 className={`text-2xl font-black ${isDark ? "text-white" : "text-slate-900"}`}>
            No Datasets in Database
          </h2>
          <p className={`text-xs leading-relaxed ${isDark ? "text-slate-400" : "text-slate-600"}`}>
            Dimension Master, Target Master, and RAW CRM data are required before analytics can be generated. Redirecting you to the Data Ingestion Center...
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/upload")}
            className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs flex items-center gap-2 shadow-lg shadow-blue-500/25 transition-all cursor-pointer"
          >
            <span>Go to Upload Wizard</span>
            <ArrowRight className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
            <span>Redirecting...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <ExecutiveDashboard
      activeDataset={activeDataset}
      onNavigateToTab={handleNavigate}
      onSeedChatPrompt={setSeededPrompt}
    />
  );
}