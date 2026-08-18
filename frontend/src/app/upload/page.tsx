"use client";

import React from "react";
import { UploadCloud } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { FileUpload } from "../../components/FileUpload";
import { DatasetManager } from "../../components/DatasetManager";

export default function UploadPage() {
  const { activeDataset, fetchActiveDataset, fetchPeriods, theme } = useApp();
  const isDark = theme === "dark";

  const handleDataChange = () => {
    fetchActiveDataset();
    fetchPeriods();
  };

  return (
    <div className="space-y-6">
      {/* Banner Card */}
      <div className={`p-6 rounded-2xl shadow-sm flex items-center justify-between border transition-all duration-200 ${
        isDark
          ? "bg-gradient-to-r from-blue-600/20 to-indigo-600/20 border-blue-500/20 text-white"
          : "bg-gradient-to-r from-blue-600 to-indigo-600 text-white border-transparent"
      }`}>
        <div>
          <h2 className="text-xl font-extrabold tracking-tight">Dataset Ingestion Center</h2>
          <p className={`text-xs mt-1 ${isDark ? "text-slate-300" : "text-blue-100"}`}>
            Upload CSV, XLSX, XLS, or XLSB files to build staged analytics datasets.
          </p>
        </div>
        <div className={`hidden sm:flex p-3 rounded-2xl ${isDark ? "bg-[#1E293B]" : "bg-white/10 backdrop-blur-xs"}`}>
          <UploadCloud className="w-8 h-8 text-white" />
        </div>
      </div>

      <FileUpload onUploadSuccess={handleDataChange} activeDataset={activeDataset} />

      {/* Dataset Management Section */}
      <DatasetManager onDatasetChange={handleDataChange} />
    </div>
  );
}
