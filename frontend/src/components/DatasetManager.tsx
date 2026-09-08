"use client";

/**
 * DatasetManager — Uploaded datasets inventory with multi-dataset analytics control,
 * period/campus editing, benchmark cleanup, dataset deletion, and full reset.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useApp } from "../context/AppContext";
import {
  Database,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Beaker,
  FileSpreadsheet,
  ChevronDown,
  ChevronUp,
  Zap,
  X,
  Edit2,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import {
  listAllDatasets,
  enableDatasetAnalytics,
  disableDatasetAnalytics,
  updateDatasetMetadata,
  deleteDataset,
  getAdminConfig,
  getBenchmarkSummary,
  clearBenchmarkData,
  resetAllData,
  AdminDatasetItem,
} from "../lib/api";

interface DatasetManagerProps {
  onDatasetChange?: () => void;
}

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  typedConfirmation?: string;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  message,
  confirmLabel,
  danger,
  typedConfirmation,
  onConfirm,
  onCancel,
  isLoading,
}) => {
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  if (!open) return null;

  const canConfirm = !typedConfirmation || typed === typedConfirmation;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${danger ? "bg-red-50" : "bg-amber-50"}`}>
              {danger ? (
                <ShieldAlert className="w-5 h-5 text-red-500" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-amber-500" />
              )}
            </div>
            <h3 className="text-base font-bold text-slate-900">{title}</h3>
          </div>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 space-y-3 text-sm text-slate-600">{message}</div>
        {typedConfirmation && (
          <div className="px-5 pb-4">
            <label className="block text-xs font-semibold text-slate-500 mb-1.5">
              Type <span className="font-mono text-red-600">{typedConfirmation}</span> to confirm
            </label>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
              placeholder={typedConfirmation}
            />
          </div>
        )}
        <div className="flex gap-2 p-5 pt-0">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="flex-1 py-2 px-4 rounded-xl text-sm font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm || isLoading}
            className={`flex-1 py-2 px-4 rounded-xl text-sm font-semibold transition-colors disabled:opacity-50 ${
              danger
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-amber-600 text-white hover:bg-amber-700"
            }`}
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export const DatasetManager: React.FC<DatasetManagerProps> = ({ onDatasetChange }) => {
  const { availableCampuses: contextCampuses, periods } = useApp();

  const availableYears = useMemo(() => {
    const current = new Date().getFullYear();
    const years = new Set<number>();
    if (periods && periods.length > 0) {
      periods.forEach((p) => {
        if (p.period_start_year) years.add(p.period_start_year);
        if (p.period_end_year) years.add(p.period_end_year);
      });
    }
    for (let y = current - 3; y <= current + 4; y++) {
      years.add(y);
    }
    return Array.from(years).sort((a, b) => a - b);
  }, [periods]);

  const availableCampuses = useMemo(() => {
    const set = new Set<string>();
    if (contextCampuses && contextCampuses.length > 0) {
      contextCampuses.forEach((c) => set.add(c));
    }
    set.add("All Campuses");
    return Array.from(set);
  }, [contextCampuses]);

  const [datasets, setDatasets] = useState<AdminDatasetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [allowReset, setAllowReset] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [filterCategory, setFilterCategory] = useState<"RAW" | "DIMENSION" | "TARGET">("RAW");

  // Edit metadata modal state
  const [editingDataset, setEditingDataset] = useState<AdminDatasetItem | null>(null);
  const [editYear, setEditYear] = useState<number>(() => {
    if (periods && periods.length > 0 && (periods[0].period_end_year || periods[0].period_start_year)) {
      return periods[0].period_end_year || periods[0].period_start_year!;
    }
    return new Date().getFullYear();
  });
  const [editCampus, setEditCampus] = useState<string>(() => {
    if (contextCampuses && contextCampuses.length > 0) return contextCampuses[0];
    return "All Campuses";
  });
  const [editName, setEditName] = useState<string>("");

  // Conflict warning modal state
  const [conflictWarning, setConflictWarning] = useState<{ id: string; name: string; message: string } | null>(null);

  // Confirmation dialogs
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string; period: string | null; rowCount: number } | null>(null);
  const [benchmarkConfirm, setBenchmarkConfirm] = useState<{ count: number; totalRows: number } | null>(null);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dsData, configData] = await Promise.all([
        listAllDatasets(),
        getAdminConfig(),
      ]);
      setDatasets(dsData.datasets);
      setAllowReset(configData.allow_data_reset);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load datasets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 4000);
  };

  const handleToggleAnalytics = async (id: string, currentlyEnabled: boolean, force: boolean = false) => {
    setActionLoading(id);
    try {
      if (currentlyEnabled) {
        await disableDatasetAnalytics(id);
        showSuccess("Analytics disabled for dataset.");
      } else {
        const res = await enableDatasetAnalytics(id, force);
        if (res.warning) {
          setConflictWarning({ id, name: res.conflict_name || "Existing Dataset", message: res.message || "" });
          return;
        }
        showSuccess("Analytics enabled for dataset.");
      }
      setConflictWarning(null);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle analytics state");
    } finally {
      setActionLoading(null);
    }
  };

  const handleSaveMetadata = async () => {
    if (!editingDataset) return;
    setActionLoading(editingDataset.id);
    try {
      await updateDatasetMetadata(editingDataset.id, editYear, editCampus, editName);
      showSuccess("Dataset metadata updated successfully.");
      setEditingDataset(null);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update metadata");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    setActionLoading(deleteConfirm.id);
    try {
      const res = await deleteDataset(deleteConfirm.id);
      showSuccess(`Deleted ${res.dataset_name}. ${res.deleted_staging_rows + res.deleted_analytics_rows} rows removed.`);
      setDeleteConfirm(null);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deletion failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleClearBenchmark = async () => {
    setActionLoading("benchmark");
    try {
      const res = await clearBenchmarkData(false);
      showSuccess(`Cleared ${res.deleted_datasets} test/benchmark datasets.`);
      setBenchmarkConfirm(null);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Benchmark cleanup failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResetAll = async () => {
    setActionLoading("reset");
    try {
      const res = await resetAllData("DELETE ALL UPLOADED DATA");
      showSuccess(`Full reset complete. ${res.deleted_datasets} datasets removed.`);
      setResetConfirm(false);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setActionLoading(null);
    }
  };

  const productionDatasets = datasets.filter((d) => d.category === "production");
  const testDatasets = datasets.filter((d) => d.category === "test_benchmark");

  return (
    <>
      {/* Edit Metadata Modal */}
      {editingDataset && (() => {
        const editingWbType = (editingDataset.workbook_type || "RAW").toUpperCase();
        const isEditingDim = editingWbType === "DIMENSION";
        const isEditingTgt = editingWbType === "TARGET";

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">Edit Dataset Metadata</h3>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase border ${
                    isEditingDim
                      ? "bg-purple-50 text-purple-700 border-purple-200"
                      : isEditingTgt
                      ? "bg-amber-50 text-amber-700 border-amber-200"
                      : "bg-blue-50 text-blue-700 border-blue-200"
                  }`}>
                    {editingWbType}
                  </span>
                </div>
                <button onClick={() => setEditingDataset(null)} className="text-slate-400 hover:text-slate-600">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="space-y-4 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Dataset Name</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-900 bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 font-medium"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Academic Year</label>
                    {isEditingDim ? (
                      <input
                        type="text"
                        disabled
                        value="Reference (Universal)"
                        className="w-full px-3 py-2 border border-purple-200 rounded-lg text-purple-800 bg-purple-50/60 font-bold"
                      />
                    ) : isEditingTgt ? (
                      <input
                        type="text"
                        disabled
                        value="Target Master (Row Scope)"
                        className="w-full px-3 py-2 border border-amber-200 rounded-lg text-amber-800 bg-amber-50/60 font-bold"
                      />
                    ) : (
                      <select
                        value={editYear}
                        onChange={(e) => setEditYear(Number(e.target.value))}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-900 bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 font-bold"
                      >
                        {availableYears.map((yr) => (
                          <option key={yr} value={yr}>
                            {yr}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Campus Scope</label>
                    {isEditingDim ? (
                      <input
                        type="text"
                        disabled
                        value="Universal / Reference"
                        className="w-full px-3 py-2 border border-purple-200 rounded-lg text-purple-800 bg-purple-50/60 font-bold"
                      />
                    ) : isEditingTgt ? (
                      <input
                        type="text"
                        disabled
                        value="Multi-campus (Row Scope)"
                        className="w-full px-3 py-2 border border-amber-200 rounded-lg text-amber-800 bg-amber-50/60 font-bold"
                      />
                    ) : (
                      <select
                        value={editCampus}
                        onChange={(e) => setEditCampus(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-900 bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 font-bold"
                      >
                        {availableCampuses.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {isEditingDim ? (
                  <div className="p-3 bg-purple-50 border border-purple-200 rounded-xl text-[11px] text-purple-800 space-y-1">
                    <p className="font-bold">ℹ️ Universal Reference Master</p>
                    <p className="text-purple-700">
                      Dimension lookup tables (Source_ms, Program, State) automatically apply across all academic years and campuses.
                    </p>
                  </div>
                ) : isEditingTgt ? (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-[11px] text-amber-800 space-y-1">
                    <p className="font-bold">ℹ️ Target Allocation Master</p>
                    <p className="text-amber-700">
                      Target boundaries are derived directly from row-level Date, Month, Campus, and Target For dimensions.
                    </p>
                  </div>
                ) : (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-[11px] text-blue-800 space-y-1">
                    <p className="font-bold">ℹ️ Actual Leads & Admissions Boundary</p>
                    <p className="text-blue-700">
                      RAW dataset metadata specifies the explicit academic year and campus for actual lead and admission metrics.
                    </p>
                  </div>
                )}
              </div>
              <div className="flex gap-2 mt-6">
                <button
                  onClick={() => setEditingDataset(null)}
                  className="flex-1 py-2 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveMetadata}
                  disabled={actionLoading === editingDataset.id}
                  className="flex-1 py-2 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {actionLoading === editingDataset.id ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : "Save Metadata"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Conflict Warning Modal */}
      {conflictWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 text-amber-600 mb-3">
              <AlertTriangle className="w-6 h-6 shrink-0" />
              <h3 className="text-base font-bold text-slate-900">Duplicate Active Dataset Warning</h3>
            </div>
            <p className="text-xs text-slate-600 mb-4">{conflictWarning.message}</p>
            <p className="text-[11px] text-slate-500 mb-6">
              Enabling multiple datasets for the exact same campus and year may merge analytical totals. Do you wish to enable both?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setConflictWarning(null)}
                className="flex-1 py-2 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={() => handleToggleAnalytics(conflictWarning.id, false, true)}
                className="flex-1 py-2 rounded-xl text-xs font-semibold bg-amber-600 text-white hover:bg-amber-700"
              >
                Enable Both
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modals */}
      <ConfirmDialog
        open={!!deleteConfirm}
        title="Delete this dataset?"
        danger
        message={
          <div className="space-y-3">
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5 space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Dataset</span>
                <span className="font-bold text-slate-800">{deleteConfirm?.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Rows</span>
                <span className="font-mono font-semibold text-slate-700">{deleteConfirm?.rowCount?.toLocaleString()}</span>
              </div>
            </div>
          </div>
        }
        confirmLabel="Delete Dataset"
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(null)}
        isLoading={actionLoading === deleteConfirm?.id}
      />

      <ConfirmDialog
        open={!!benchmarkConfirm}
        title="Clear Test Data"
        message={<p className="text-xs text-slate-600">Clear test and benchmark datasets safely?</p>}
        confirmLabel="Clear Test Data"
        onConfirm={handleClearBenchmark}
        onCancel={() => setBenchmarkConfirm(null)}
        isLoading={actionLoading === "benchmark"}
      />

      <ConfirmDialog
        open={resetConfirm}
        title="Reset All Uploaded Data"
        danger
        typedConfirmation="DELETE ALL UPLOADED DATA"
        message={<p className="text-xs text-red-600 font-semibold">⚠️ Permanently delete all uploaded datasets?</p>}
        confirmLabel="Reset All Data"
        onConfirm={handleResetAll}
        onCancel={() => setResetConfirm(false)}
        isLoading={actionLoading === "reset"}
      />

      {/* Main Section */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs">
        <div
          role="button"
          tabIndex={0}
          onClick={() => setExpanded(!expanded)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setExpanded(!expanded); } }}
          className="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50/50 rounded-t-2xl transition-colors cursor-pointer select-none"
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center">
              <Database className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Dataset Management</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {datasets.length} dataset{datasets.length !== 1 ? "s" : ""} · Multi-Year & Multi-Campus Analytics
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); fetchData(); }}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </div>
        </div>

        {expanded && (
          <div className="border-t border-slate-100">
            {successMsg && (
              <div className="mx-5 mt-4 p-3 bg-emerald-50 border border-emerald-100 rounded-xl text-xs text-emerald-700 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                {successMsg}
              </div>
            )}
            {error && (
              <div className="mx-5 mt-4 p-3 bg-red-50 border border-red-100 rounded-xl text-xs text-red-700 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
                {error}
                <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-12 text-slate-400 text-sm gap-2">
                <Loader2 className="w-5 h-5 animate-spin" />
                Loading datasets…
              </div>
            ) : datasets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                <Database className="w-10 h-10 mb-2 text-slate-300" />
                <p className="text-sm font-semibold">No datasets uploaded</p>
              </div>
            ) : (() => {
              const rawCount = datasets.filter(d => (d.workbook_type || "RAW").toUpperCase() === "RAW").length;
              const dimCount = datasets.filter(d => (d.workbook_type || "").toUpperCase() === "DIMENSION").length;
              const tgtCount = datasets.filter(d => (d.workbook_type || "").toUpperCase() === "TARGET").length;

              const visibleDatasets = datasets.filter(d => {
                return (d.workbook_type || "RAW").toUpperCase() === filterCategory;
              });

              return (
                <>
                  <div className="px-5 py-3 flex flex-wrap gap-2 border-b border-slate-100 bg-slate-50/50">
                    <button
                      onClick={() => setFilterCategory("RAW")}
                      className={`px-3 py-1 rounded-lg text-xs font-extrabold transition-all flex items-center gap-1.5 ${
                        filterCategory === "RAW"
                          ? "bg-blue-600 text-white shadow-xs"
                          : "bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${filterCategory === "RAW" ? "bg-white" : "bg-blue-500"}`}></span>
                      Raw Data ({rawCount})
                    </button>
                    <button
                      onClick={() => setFilterCategory("DIMENSION")}
                      className={`px-3 py-1 rounded-lg text-xs font-extrabold transition-all flex items-center gap-1.5 ${
                        filterCategory === "DIMENSION"
                          ? "bg-purple-600 text-white shadow-xs"
                          : "bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${filterCategory === "DIMENSION" ? "bg-white" : "bg-purple-500"}`}></span>
                      Dimension Data ({dimCount})
                    </button>
                    <button
                      onClick={() => setFilterCategory("TARGET")}
                      className={`px-3 py-1 rounded-lg text-xs font-extrabold transition-all flex items-center gap-1.5 ${
                        filterCategory === "TARGET"
                          ? "bg-amber-600 text-white shadow-xs"
                          : "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${filterCategory === "TARGET" ? "bg-white" : "bg-amber-500"}`}></span>
                      Target Data ({tgtCount})
                    </button>
                  </div>

                  {filterCategory === "TARGET" && (
                    <div className="px-5 py-2.5 bg-amber-50/70 border-b border-amber-100/80 flex items-center justify-between text-[11px] text-amber-900">
                      <div className="flex items-center gap-2">
                        <span className="font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] uppercase tracking-wide">
                          Target Master Rule
                        </span>
                        <span>Strictly <strong>ONE active Target master file</strong> (multi-sheet: Admission, Lead, CUCET targets). Row-level target matching by Date, Month, Campus, and Target For.</span>
                      </div>
                    </div>
                  )}
                  {filterCategory === "DIMENSION" && (
                    <div className="px-5 py-2.5 bg-purple-50/70 border-b border-purple-100/80 flex items-center justify-between text-[11px] text-purple-900">
                      <div className="flex items-center gap-2">
                        <span className="font-bold px-2 py-0.5 rounded bg-purple-100 text-purple-800 text-[10px] uppercase tracking-wide">
                          Dimension Master Rule
                        </span>
                        <span>Strictly <strong>ONE active Dimension master file</strong>. Multi-sheet reference tables applied universally across all reporting periods.</span>
                      </div>
                    </div>
                  )}
                  {filterCategory === "RAW" && (
                    <div className="px-5 py-2.5 bg-blue-50/70 border-b border-blue-100/80 flex items-center justify-between text-[11px] text-blue-900">
                      <div className="flex items-center gap-2">
                        <span className="font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-[10px] uppercase tracking-wide">
                          RAW CRM Multi-Dataset Rule
                        </span>
                        <span>Multiple RAW datasets <strong>coexist across Academic Years and Campuses</strong>. Replacement occurs only for matching (Academic Year, Campus).</span>
                      </div>
                    </div>
                  )}

                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-slate-50 text-slate-500 border-b border-slate-100">
                          <th className="text-left py-2.5 px-5 font-semibold uppercase tracking-wider">Dataset Name</th>
                          <th className="text-left py-2.5 px-3 font-semibold uppercase tracking-wider">Type</th>
                          <th className="text-left py-2.5 px-3 font-semibold uppercase tracking-wider">Campus</th>
                          <th className="text-left py-2.5 px-3 font-semibold uppercase tracking-wider">Period</th>
                          <th className="text-right py-2.5 px-3 font-semibold uppercase tracking-wider">Rows</th>
                          <th className="text-center py-2.5 px-3 font-semibold uppercase tracking-wider">Analytics</th>
                          <th className="text-right py-2.5 px-5 font-semibold uppercase tracking-wider">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {visibleDatasets.map((ds) => {
                          const isEnabled = bool(ds.is_analytics_enabled || ds.is_active);
                          const wbType = (ds.workbook_type || "RAW").toUpperCase();
                          const isDimension = wbType === "DIMENSION";
                          const isTarget = wbType === "TARGET";
                          
                          const campusDisplay = isDimension ? "Universal" : isTarget ? "Multi-campus" : (ds.campus_name || "All Campuses");
                          const periodDisplay = isDimension ? "Reference" : isTarget ? "Target Master" : String(ds.academic_year || ds.academic_label || "Unspecified");

                        return (
                          <tr key={ds.id} className={`transition-colors ${isEnabled ? "bg-indigo-50/20" : "hover:bg-slate-50/50"}`}>
                            <td className="py-3 px-5 font-semibold text-slate-800 truncate max-w-[220px]">
                              {ds.dataset_name || ds.original_filename}
                            </td>
                            <td className="py-3 px-3">
                              <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase border ${
                                isDimension
                                  ? "bg-purple-50 text-purple-700 border-purple-200"
                                  : isTarget
                                  ? "bg-amber-50 text-amber-700 border-amber-200"
                                  : "bg-blue-50 text-blue-700 border-blue-200"
                              }`}>
                                {wbType}
                              </span>
                            </td>
                            <td className="py-3 px-3">
                              <span className="px-2 py-0.5 rounded-md text-[11px] font-bold bg-slate-100 text-slate-700">
                                {campusDisplay}
                              </span>
                            </td>
                            <td className="py-3 px-3 font-semibold text-indigo-700">
                              {periodDisplay}
                            </td>
                            <td className="py-3 px-3 text-right font-mono font-semibold text-slate-700">
                              {(ds.row_count ?? 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 text-center">
                              <button
                                onClick={() => handleToggleAnalytics(ds.id, isEnabled)}
                                disabled={actionLoading === ds.id}
                                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-extrabold transition-all ${
                                  isEnabled
                                    ? "bg-emerald-100 text-emerald-800 border border-emerald-300 hover:bg-emerald-200"
                                    : "bg-slate-100 text-slate-500 border border-slate-200 hover:bg-slate-200"
                                }`}
                              >
                                {isEnabled ? <CheckCircle2 className="w-3 h-3 text-emerald-600" /> : <ToggleLeft className="w-3 h-3 text-slate-400" />}
                                {isEnabled ? "ENABLED" : "DISABLED"}
                              </button>
                            </td>
                            <td className="py-3 px-5 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => {
                                    setEditingDataset(ds);
                                    setEditYear(ds.academic_year || (periods && (periods[0]?.period_end_year || periods[0]?.period_start_year)) || new Date().getFullYear());
                                    setEditCampus(ds.campus_name || availableCampuses[0] || "All Campuses");
                                    setEditName(ds.dataset_name || ds.original_filename);
                                  }}
                                  className="p-1 rounded-lg text-slate-600 hover:bg-slate-100 border border-slate-200"
                                  title="Edit metadata"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => setDeleteConfirm({ id: ds.id, name: ds.dataset_name, period: ds.academic_label, rowCount: ds.row_count })}
                                  className="px-2 py-1 rounded-lg text-[11px] font-semibold text-red-600 bg-red-50 border border-red-200 hover:bg-red-100"
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="border-t border-slate-100 p-5 flex flex-wrap items-center gap-2">
                  {allowReset && (
                    <button
                      onClick={() => setResetConfirm(true)}
                      className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-red-50 text-red-700 border border-red-200 hover:bg-red-100"
                    >
                      <ShieldAlert className="w-3.5 h-3.5" />
                      Reset All Uploaded Data
                    </button>
                  )}
                </div>
              </>
            );
          })()}
          </div>
        )}
      </div>
    </>
  );
};

function bool(val: any): boolean {
  return Boolean(val);
}
