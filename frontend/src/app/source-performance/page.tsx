"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useApp } from "../../context/AppContext";
import { SourcePerformanceComponent } from "../../components/SourcePerformance";
import { SourceDetailModal } from "../../components/SourceDetail";
import { getSourceHierarchy, SourceHierarchyNode } from "../../lib/api";

export default function SourcePerformancePage() {
  const { activeDataset, year, refreshTrigger, theme } = useApp();
  const isDark = theme === "dark";

  const [sources, setSources] = useState<SourceHierarchyNode[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedSource, setSelectedSource] = useState<{
    mainSource: string;
    source: string;
  } | null>(null);

  const loadData = useCallback(async () => {
    if (!activeDataset) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await getSourceHierarchy(year);
      setSources(res.sources || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load source performance.");
    } finally {
      setIsLoading(false);
    }
  }, [activeDataset, year]);

  useEffect(() => {
    setTimeout(() => {
      loadData();
    }, 0);
  }, [loadData, refreshTrigger]);

  const handleSelectSource = (mainSource: string, source: string) => {
    setSelectedSource({ mainSource, source });
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
    <div className="space-y-6">
      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs rounded-xl">
          {error}
        </div>
      )}
      <SourcePerformanceComponent
        sources={sources}
        onSelectSource={handleSelectSource}
        isLoading={isLoading}
      />

      {selectedSource && (
        <SourceDetailModal
          year={year}
          mainSource={selectedSource.mainSource}
          source={selectedSource.source}
          onClose={() => setSelectedSource(null)}
        />
      )}
    </div>
  );
}
