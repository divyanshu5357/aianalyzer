"use client";

import React from "react";
import { UploadCloud } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { UploadWizard } from "../../components/UploadWizard";
import { DatasetManager } from "../../components/DatasetManager";

export default function UploadPage() {
  const { activeDataset, fetchActiveDataset, fetchPeriods, theme, year, notifyDatasetChange } = useApp();
  const isDark = theme === "dark";
  const [wizardType, setWizardType] = React.useState<"raw_data" | "dimension" | "target">("raw_data");

  const handleDataChange = (uploadResult?: any) => {
    // Dynamically extract affected year and campus from upload result if available.
    // Falls back to currently selected year. Unrelated years' cache is preserved.
    const affectedYear =
      uploadResult?.academic_year ||
      uploadResult?.result_data?.academic_year ||
      uploadResult?.year ||
      year;
    const affectedCampus =
      uploadResult?.campus_name ||
      uploadResult?.result_data?.campus_name ||
      uploadResult?.campus;

    notifyDatasetChange(
      affectedYear ? Number(affectedYear) : undefined,
      affectedCampus ? String(affectedCampus) : undefined
    );
  };

  const handleSelectUploadType = (type: "raw_data" | "dimension" | "target") => {
    setWizardType(type);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  return (
    <div className="space-y-8">
      {/* Banner Card */}
      <div className={`p-6 rounded-2xl shadow-sm flex items-center justify-between border transition-all duration-200 ${
        isDark
          ? "bg-gradient-to-r from-blue-600/20 to-indigo-600/20 border-blue-500/20 text-white"
          : "bg-gradient-to-r from-blue-600 to-indigo-600 text-white border-transparent"
      }`}>
        <div>
          <h2 className="text-xl font-extrabold tracking-tight">Dataset Ingestion Center</h2>
          <p className={`text-xs mt-1 ${isDark ? "text-slate-300" : "text-blue-100"}`}>
            Production Upload Wizard for Raw CRM Data, Dimension Masters, and Target Workbooks.
          </p>
        </div>
        <div className={`hidden sm:flex p-3 rounded-2xl ${isDark ? "bg-[#1E293B]" : "bg-white/10 backdrop-blur-xs"}`}>
          <UploadCloud className="w-8 h-8 text-white" />
        </div>
      </div>

      {/* Production Upload Wizard */}
      <UploadWizard onComplete={handleDataChange} isDark={isDark} initialType={wizardType} />

      {/* Dataset Management Section */}
      <DatasetManager onDatasetChange={handleDataChange} onSelectUploadType={handleSelectUploadType} />
    </div>
  );
}
