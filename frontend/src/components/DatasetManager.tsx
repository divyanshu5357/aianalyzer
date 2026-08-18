"use client";

/**
 * DatasetManager — Uploaded datasets inventory with active-dataset control,
 * benchmark cleanup, single-dataset deletion, and full reset.
 *
 * Displayed on the Data Ingestion page below the FileUpload component.
 */
import React, { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";
import {
  listAllDatasets,
  activateDataset,
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

// ─── Confirm Dialog ────────────────────────────────────────────────────────
interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  /** If set, user must type this exact phrase to confirm */
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
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
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

// ─── Main Component ────────────────────────────────────────────────────────
export const DatasetManager: React.FC<DatasetManagerProps> = ({ onDatasetChange }) => {
  const [datasets, setDatasets] = useState<AdminDatasetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [allowReset, setAllowReset] = useState(false);
  const [expanded, setExpanded] = useState(true);

  // Confirmation dialogs
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string; isActive: boolean; period: string | null; rowCount: number } | null>(null);
  const [benchmarkConfirm, setBenchmarkConfirm] = useState<{
    count: number;
    totalRows: number;
  } | null>(null);
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

  // ── Actions ──────────────────────────────────────────────────────────────

  const handleActivate = async (id: string) => {
    setActionLoading(id);
    try {
      const res = await activateDataset(id);
      showSuccess(`${res.dataset_name} is now active.`);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    setActionLoading(deleteConfirm.id);
    try {
      const res = await deleteDataset(deleteConfirm.id);
      showSuccess(
        `Deleted ${res.dataset_name}. ${res.deleted_staging_rows + res.deleted_analytics_rows} dependent rows removed.`
      );
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
      showSuccess(
        `Cleared ${res.deleted_datasets} test/benchmark datasets (${res.deleted_staging_rows + res.deleted_analytics_rows} dependent rows).`
      );
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
      showSuccess(
        `Full reset complete. ${res.deleted_datasets} datasets and all dependent data removed.`
      );
      setResetConfirm(false);
      await fetchData();
      onDatasetChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setActionLoading(null);
    }
  };

  const startBenchmarkClear = async () => {
    try {
      const summary = await getBenchmarkSummary();
      if (summary.candidate_count === 0) {
        showSuccess("No test/benchmark datasets found to clear.");
        return;
      }
      setBenchmarkConfirm({
        count: summary.candidate_count,
        totalRows: summary.total_rows,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load benchmark summary");
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const productionDatasets = datasets.filter((d) => d.category === "production");
  const testDatasets = datasets.filter((d) => d.category === "test_benchmark");

  return (
    <>
      {/* Confirmation Modals */}
      <ConfirmDialog
        open={!!deleteConfirm}
        title={deleteConfirm?.isActive ? "Delete Active Dataset" : "Delete this dataset?"}
        danger={deleteConfirm?.isActive}
        message={
          <div className="space-y-3">
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5 space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Dataset</span>
                <span className="font-bold text-slate-800">{deleteConfirm?.name}</span>
              </div>
              {deleteConfirm?.period && (
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">Period</span>
                  <span className="font-semibold text-slate-700">{deleteConfirm.period}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Rows</span>
                <span className="font-mono font-semibold text-slate-700">{deleteConfirm?.rowCount?.toLocaleString()}</span>
              </div>
            </div>
            <p className="text-xs text-slate-500">
              This removes the dataset and its dependent staging, analytics,
              mappings, and related dataset records.
            </p>
            {deleteConfirm?.isActive && (
              <div className="bg-red-50 border border-red-100 rounded-lg p-3 text-xs text-red-700">
                <strong>Warning:</strong> This is the currently active dataset.
                After deletion, no dataset will be automatically activated.
                You will need to select another dataset.
              </div>
            )}
          </div>
        }
        confirmLabel="Delete Dataset"
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(null)}
        isLoading={actionLoading === deleteConfirm?.id}
      />

      <ConfirmDialog
        open={!!benchmarkConfirm}
        title="Clear Test / Benchmark Data"
        message={
          <div className="space-y-2">
            <p>
              <strong>{benchmarkConfirm?.count}</strong> test/benchmark
              dataset(s) found with{" "}
              <strong>{benchmarkConfirm?.totalRows?.toLocaleString()}</strong>{" "}
              total rows.
            </p>
            <p className="text-xs text-slate-500">
              This will remove all Bench_*, benchmark_*, test_*, and synthetic_* 
              datasets and their dependent staging, analytics, mappings, and quality
              records. Your production data will not be affected.
            </p>
          </div>
        }
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
        message={
          <div className="space-y-2">
            <p className="font-semibold text-red-700">
              ⚠️ This will permanently delete ALL uploaded datasets.
            </p>
            <p className="text-xs text-slate-500">
              Staging rows, analytics metrics, column mappings, quality reports,
              and conversation contexts will be removed. Database schemas and
              application tables will remain intact.
            </p>
          </div>
        }
        confirmLabel="Reset All Data"
        onConfirm={handleResetAll}
        onCancel={() => setResetConfirm(false)}
        isLoading={actionLoading === "reset"}
      />

      {/* Main Section */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xs">
        {/* Header — uses <div> instead of <button> to avoid nesting the refresh <button> */}
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
              <h3 className="text-sm font-bold text-slate-900">Data Management</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {datasets.length} dataset{datasets.length !== 1 ? "s" : ""} ·{" "}
                {productionDatasets.length} production ·{" "}
                {testDatasets.length} test/benchmark
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
            {expanded ? (
              <ChevronUp className="w-4 h-4 text-slate-400" />
            ) : (
              <ChevronDown className="w-4 h-4 text-slate-400" />
            )}
          </div>
        </div>

        {expanded && (
          <div className="border-t border-slate-100">
            {/* Success / Error messages */}
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
                <p className="text-xs mt-1">Upload a file to get started.</p>
              </div>
            ) : (
              <>
                {/* Dataset Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-50 text-slate-500 border-b border-slate-100">
                        <th className="text-left py-2.5 px-5 font-semibold uppercase tracking-wider">
                          Dataset
                        </th>
                        <th className="text-left py-2.5 px-3 font-semibold uppercase tracking-wider">
                          Period
                        </th>
                        <th className="text-right py-2.5 px-3 font-semibold uppercase tracking-wider">
                          Rows
                        </th>
                        <th className="text-center py-2.5 px-3 font-semibold uppercase tracking-wider">
                          Category
                        </th>
                        <th className="text-center py-2.5 px-3 font-semibold uppercase tracking-wider">
                          Status
                        </th>
                        <th className="text-right py-2.5 px-5 font-semibold uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {datasets.map((ds) => {
                        const isTest = ds.category === "test_benchmark";
                        const isActive = ds.is_active;
                        return (
                          <tr
                            key={ds.id}
                            className={`transition-colors ${
                              isActive
                                ? "bg-blue-50/40"
                                : "hover:bg-slate-50/50"
                            }`}
                          >
                            {/* Name */}
                            <td className="py-3 px-5">
                              <div className="flex items-center gap-2.5">
                                <FileSpreadsheet
                                  className={`w-4 h-4 shrink-0 ${
                                    isActive ? "text-blue-500" : "text-slate-400"
                                  }`}
                                />
                                <div className="min-w-0">
                                  <p className={`font-semibold truncate max-w-[200px] ${isActive ? "text-blue-900" : "text-slate-800"}`}>
                                    {ds.dataset_name || ds.original_filename}
                                  </p>
                                  {ds.original_filename && ds.dataset_name !== ds.original_filename && (
                                    <p className="text-[10px] text-slate-400 truncate max-w-[200px]">
                                      {ds.original_filename}
                                    </p>
                                  )}
                                  {ds.upload_version && ds.upload_version > 1 && (
                                    <span className="text-[9px] font-mono text-slate-400">
                                      v{ds.upload_version}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </td>

                            {/* Period */}
                            <td className="py-3 px-3">
                              {ds.academic_label ? (
                                <span className="font-semibold text-slate-700">
                                  {ds.academic_label}
                                </span>
                              ) : (
                                <span className="text-slate-400 italic">—</span>
                              )}
                            </td>

                            {/* Rows */}
                            <td className="py-3 px-3 text-right">
                              <span className="font-mono font-semibold text-slate-700">
                                {(ds.row_count ?? 0).toLocaleString()}
                              </span>
                            </td>

                            {/* Category */}
                            <td className="py-3 px-3 text-center">
                              {isTest ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                                  <Beaker className="w-3 h-3" />
                                  TEST
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                  <Zap className="w-3 h-3" />
                                  PROD
                                </span>
                              )}
                            </td>

                            {/* Status */}
                            <td className="py-3 px-3 text-center">
                              {isActive ? (
                                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-blue-100 text-blue-700 border border-blue-200">
                                  <CheckCircle2 className="w-3 h-3" />
                                  ACTIVE
                                </span>
                              ) : (
                                <span className="text-[10px] font-semibold text-slate-400 uppercase">
                                  {ds.status}
                                </span>
                              )}
                            </td>

                            {/* Actions */}
                            <td className="py-3 px-5 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                {!isActive && !isTest && (
                                  <button
                                    onClick={() => handleActivate(ds.id)}
                                    disabled={!!actionLoading}
                                    className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
                                  >
                                    {actionLoading === ds.id ? (
                                      <Loader2 className="w-3 h-3 animate-spin" />
                                    ) : (
                                      "Set Active"
                                    )}
                                  </button>
                                )}
                                <button
                                  onClick={() =>
                                    setDeleteConfirm({
                                      id: ds.id,
                                      name: ds.dataset_name || ds.original_filename,
                                      isActive,
                                      period: ds.academic_label || null,
                                      rowCount: ds.row_count ?? 0,
                                    })
                                  }
                                  disabled={!!actionLoading}
                                  className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-red-600 bg-red-50 border border-red-200 hover:bg-red-100 transition-colors disabled:opacity-50"
                                  title="Delete dataset"
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

                {/* Bulk Actions */}
                <div className="border-t border-slate-100 p-5 flex flex-wrap items-center gap-2">
                  {testDatasets.length > 0 && allowReset && (
                    <button
                      onClick={startBenchmarkClear}
                      disabled={!!actionLoading}
                      className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-colors disabled:opacity-50"
                    >
                      <Beaker className="w-3.5 h-3.5" />
                      Clear Test / Benchmark Data
                    </button>
                  )}
                  {allowReset && (
                    <button
                      onClick={() => setResetConfirm(true)}
                      disabled={!!actionLoading}
                      className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 transition-colors disabled:opacity-50"
                    >
                      <ShieldAlert className="w-3.5 h-3.5" />
                      Reset All Uploaded Data
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
};
