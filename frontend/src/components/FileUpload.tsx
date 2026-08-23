"use client";

import React, { useState, useRef } from "react";
import {
  UploadCloud,
  FileSpreadsheet,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Table,
  FileText,
  Check,
  Database,
  BarChart2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Calendar,
} from "lucide-react";
import {
  uploadFiles,
  getIngestionJobStatus,
  IngestionJobStatus,
  FileUploadResponse,
  ActiveDatasetInfo,
  UploadedFileItemExtended,
  FileUploadResponseExtended,
} from "../lib/api";
import { PeriodConfirmationModal } from "./PeriodConfirmationModal";


const ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls", ".xlsb"];

export type UploadStep = "idle" | "uploading" | "staging" | "normalizing" | "success" | "error";

interface FileUploadProps {
  onUploadSuccess?: (result: FileUploadResponse) => void;
  activeDataset?: ActiveDatasetInfo | null;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onUploadSuccess,
  activeDataset,
}) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadStep, setUploadStep] = useState<UploadStep>("idle");
  const [uploadResult, setUploadResult] = useState<FileUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedMappings, setExpandedMappings] = useState<Record<string, boolean>>({});
  // Period confirmation modal state
  const [pendingPeriodFile, setPendingPeriodFile] = useState<UploadedFileItemExtended | null>(null);

  // Real-time backend progress state
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<IngestionJobStatus | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // On mount: Check if there was an active ingestion job stored in localStorage
  React.useEffect(() => {
    const savedJobId = localStorage.getItem("active_ingestion_job_id");
    if (!savedJobId) return;

    let isMounted = true;

    getIngestionJobStatus(savedJobId)
      .then((status) => {
        if (!isMounted) return;
        if (status.status === "processing") {
          setActiveJobId(savedJobId);
          setJobStatus(status);
          setUploadStep("normalizing");
        } else if (status.status === "completed") {
          localStorage.removeItem("active_ingestion_job_id");
        } else if (status.status === "failed") {
          localStorage.removeItem("active_ingestion_job_id");
          setError(status.error || status.message || "Previous ingestion job failed.");
        }
      })
      .catch(() => {
        localStorage.removeItem("active_ingestion_job_id");
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Polling effect while activeJobId is set and status is processing
  React.useEffect(() => {
    if (!activeJobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const status = await getIngestionJobStatus(activeJobId);
        setJobStatus(status);

        if (status.status === "completed") {
          localStorage.removeItem("active_ingestion_job_id");
          setActiveJobId(null);

          const resData = (status.result_data || uploadResult) as FileUploadResponseExtended | null;
          if (resData) {
            setUploadResult(resData);
            setSelectedFiles([]);
            setUploadStep("success");

            const needsConfirmation = resData.files?.find(
              (f) =>
                f.upload_status === "pending_confirmation" ||
                f.upload_status === "period_unknown" ||
                f.upload_status === "conflict"
            ) as UploadedFileItemExtended | undefined;

            if (needsConfirmation) {
              setPendingPeriodFile(needsConfirmation);
            } else if (onUploadSuccess) {
              onUploadSuccess(resData);
            }
          } else {
            setUploadStep("success");
          }
        } else if (status.status === "failed") {
          localStorage.removeItem("active_ingestion_job_id");
          setActiveJobId(null);
          setUploadStep("error");
          setError(status.error || status.message || "Ingestion failed.");
        }
      } catch (err) {
        console.warn("Failed polling ingestion status:", err);
      }
    }, 600);

    return () => clearInterval(pollInterval);
  }, [activeJobId, uploadResult, onUploadSuccess]);


  const validateFiles = (files: File[]): File[] => {
    const valid: File[] = [];
    let invalidCount = 0;

    files.forEach((file) => {
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (ALLOWED_EXTENSIONS.includes(ext)) {
        if (!selectedFiles.some((f) => f.name === file.name)) {
          valid.push(file);
        }
      } else {
        invalidCount++;
      }
    });

    if (invalidCount > 0) {
      setError(
        `Only CSV, XLSX, XLS, and XLSB files are supported. ${invalidCount} invalid file(s) ignored.`
      );
    } else {
      setError(null);
    }

    return valid;
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      const valid = validateFiles(newFiles);
      setSelectedFiles((prev) => [...prev, ...valid]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFiles = Array.from(e.dataTransfer.files);
      const valid = validateFiles(droppedFiles);
      setSelectedFiles((prev) => [...prev, ...valid]);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    if (selectedFiles.length === 1) {
      setError(null);
    }
  };

  const clearAll = () => {
    setSelectedFiles([]);
    setUploadResult(null);
    setError(null);
    setUploadStep("idle");
    setActiveJobId(null);
    setJobStatus(null);
    localStorage.removeItem("active_ingestion_job_id");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    const newJobId = `job_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    localStorage.setItem("active_ingestion_job_id", newJobId);
    setActiveJobId(newJobId);

    setUploadStep("uploading");
    setError(null);
    setUploadResult(null);

    try {
      setUploadStep("uploading");
      const result = await uploadFiles(selectedFiles, newJobId) as FileUploadResponseExtended;
      
      if (result.status !== "processing") {
        setUploadStep("success");
        setUploadResult(result);
        setSelectedFiles([]); // clear queue on success
        localStorage.removeItem("active_ingestion_job_id");
        setActiveJobId(null);

        // Check if any file needs period confirmation
        const needsConfirmation = result.files?.find(
          (f) =>
            f.upload_status === "pending_confirmation" ||
            f.upload_status === "period_unknown" ||
            f.upload_status === "conflict"
        ) as UploadedFileItemExtended | undefined;

        if (needsConfirmation) {
          setPendingPeriodFile(needsConfirmation);
        } else if (onUploadSuccess) {
          onUploadSuccess(result);
        }
      }
      // If processing in background, do nothing here. The useEffect polling handles completion.
    } catch (err) {
      localStorage.removeItem("active_ingestion_job_id");
      setActiveJobId(null);
      setUploadStep("error");
      setError(
        err instanceof Error
          ? err.message
          : "An unexpected error occurred during upload."
      );
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isProcessing =
    uploadStep === "uploading" ||
    uploadStep === "staging" ||
    uploadStep === "normalizing" ||
    !!activeJobId;

  return (
    <div className="space-y-6">
      {/* Period Confirmation Modal — shown when backend needs user input */}
      {pendingPeriodFile && (
        <PeriodConfirmationModal
          file={pendingPeriodFile}
          onClose={() => setPendingPeriodFile(null)}
          onConfirmed={() => {
            setPendingPeriodFile(null);
            if (uploadResult && onUploadSuccess) {
              onUploadSuccess(uploadResult);
            }
          }}
        />
      )}

      {/* Active Dataset Status Card */}
      {activeDataset && (
        <div className="bg-gradient-to-r from-slate-900 to-indigo-950 text-white rounded-2xl p-5 shadow-sm border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-400/30 flex items-center justify-center shrink-0">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-blue-400">
                  Active AI Dataset
                </span>
                <span className="px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  ACTIVE
                </span>
                {activeDataset.academic_label && (
                  <span className="px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/40">
                    {activeDataset.academic_label}
                  </span>
                )}
              </div>
              <h3 className="text-base font-bold text-white tracking-tight mt-0.5">
                {activeDataset.dataset_name || activeDataset.original_filename}
              </h3>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-300 bg-white/5 border border-white/10 px-4 py-2.5 rounded-xl w-full md:w-auto">
            <div>
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Total Rows</span>
              <strong className="text-white font-mono text-sm">{activeDataset.row_count.toLocaleString()}</strong>
            </div>
            <div className="h-6 w-px bg-white/10" />
            <div>
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Columns</span>
              <strong className="text-white font-mono text-sm">{activeDataset.column_count}</strong>
            </div>
            <div className="h-6 w-px bg-white/10" />
            <div>
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Quality Score</span>
              <strong className="text-emerald-400 font-mono text-sm">
                {activeDataset.quality_score !== null ? `${activeDataset.quality_score}%` : "100.0%"}
              </strong>
            </div>
            <div className="h-6 w-px bg-white/10" />
            <div>
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Status</span>
              <strong className="text-indigo-300 font-mono text-xs uppercase">{activeDataset.status}</strong>
            </div>
          </div>
        </div>
      )}

      {/* Upload Card Container */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
        <div className="mb-4">
          <h2 className="text-lg font-bold text-slate-900 tracking-tight">
            Data Source Ingestion
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Upload one or multiple CSV or Excel dataset files to stage and process admissions analytics.
          </p>
        </div>

        {/* Drag & Drop Box */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !isProcessing && fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all duration-200 flex flex-col items-center justify-center ${
            isDragging
              ? "border-blue-500 bg-blue-50/50 scale-[0.99]"
              : isProcessing
              ? "border-slate-200 bg-slate-50 opacity-75 cursor-not-allowed"
              : "border-slate-200 bg-slate-50/60 hover:bg-slate-100/50 hover:border-slate-300"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".csv, .xlsx, .xls, .xlsb"
            onChange={handleFileSelect}
            disabled={isProcessing}
            className="hidden"
          />

          <div className="w-12 h-12 rounded-full bg-blue-100/80 text-blue-600 flex items-center justify-center mb-3">
            {isProcessing ? (
              <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
            ) : (
              <UploadCloud className="w-6 h-6" />
            )}
          </div>

          <p className="text-sm font-semibold text-slate-800">
            {isProcessing ? (
              <span>Processing dataset files...</span>
            ) : (
              <>
                Drag & drop dataset files here, or{" "}
                <span className="text-blue-600 underline font-bold">browse</span>
              </>
            )}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Supports multiple CSV, XLSX, XLS, and XLSB files
          </p>

          {/* Formats badges */}
          <div className="flex items-center justify-center gap-2 mt-4">
            {["CSV", "XLSX", "XLS", "XLSB"].map((fmt) => (
              <span
                key={fmt}
                className="px-2 py-0.5 text-[10px] font-bold rounded-md bg-white text-slate-600 border border-slate-200 shadow-2xs"
              >
                {fmt}
              </span>
            ))}
          </div>
        </div>

        {/* Upload Progress State Banner with Real-time Backend Percent & Row Metrics */}
        {isProcessing && (
          <div className="mt-4 p-5 bg-gradient-to-r from-blue-50 to-indigo-50/70 border border-blue-200 rounded-2xl space-y-3 shadow-xs">
            <div className="flex items-center justify-between text-xs font-bold text-slate-900">
              <span className="flex items-center gap-2.5">
                <Loader2 className="w-4 h-4 animate-spin text-blue-600 shrink-0" />
                <span className="text-slate-800 font-semibold">
                  {jobStatus?.message ||
                    (uploadStep === "uploading"
                      ? "Uploading files to server..."
                      : uploadStep === "staging"
                      ? "Staging records into database..."
                      : "Processing & normalizing metrics...")}
                </span>
              </span>
              <span className="text-blue-700 font-extrabold text-sm font-mono">
                {jobStatus ? `${jobStatus.progress_percent.toFixed(0)}%` : "0%"}
              </span>
            </div>

            <div className="w-full bg-slate-200/80 rounded-full h-2.5 overflow-hidden p-0.5">
              <div
                className="h-full bg-gradient-to-r from-blue-600 to-indigo-600 rounded-full transition-all duration-300 shadow-xs"
                style={{
                  width: `${Math.max(5, Math.min(100, jobStatus?.progress_percent || 5))}%`,
                }}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5 font-medium">
              <span className="uppercase tracking-wider font-bold text-blue-800/80 text-[10px]">
                Stage: {jobStatus?.stage ? jobStatus.stage.toUpperCase() : uploadStep.toUpperCase()}
              </span>
              {jobStatus && jobStatus.total_rows > 0 && (
                <span className="font-mono text-slate-700 font-semibold">
                  {jobStatus.processed_rows.toLocaleString()} / {jobStatus.total_rows.toLocaleString()} rows
                </span>
              )}
            </div>
          </div>
        )}


        {/* Error Alert */}
        {error && (
          <div className="mt-4 p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold">Upload Failed</p>
              <p className="mt-0.5 text-rose-600">{error}</p>
            </div>
          </div>
        )}

        {/* Selected Files List Queue */}
        {selectedFiles.length > 0 && !isProcessing && (
          <div className="mt-6 border-t border-slate-100 pt-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                Selected Files ({selectedFiles.length})
              </span>
              <button
                onClick={clearAll}
                className="text-xs text-slate-500 hover:text-slate-700 font-semibold"
              >
                Clear all
              </button>
            </div>

            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {selectedFiles.map((file, idx) => (
                <div
                  key={`${file.name}-${idx}`}
                  className="flex items-center justify-between p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-xs"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <FileSpreadsheet className="w-4 h-4 text-blue-600 shrink-0" />
                    <span className="font-semibold text-slate-800 truncate">
                      {file.name}
                    </span>
                    <span className="text-[11px] text-slate-400 shrink-0">
                      ({formatFileSize(file.size)})
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(idx);
                    }}
                    className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-5 flex justify-end">
              <button
                onClick={handleUpload}
                disabled={isProcessing}
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm transition-all disabled:opacity-60"
              >
                <UploadCloud className="w-4 h-4" />
                <span>Upload & Process {selectedFiles.length} File(s)</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Upload Success Report */}
      {uploadResult && (
        <div className="bg-emerald-50/70 border border-emerald-200 rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              <div>
                <h3 className="font-bold text-emerald-900 text-sm">
                  Upload & Ingestion Complete ({uploadResult.file_count ?? uploadResult.files?.length ?? 1} File(s))
                </h3>
                <p className="text-xs text-emerald-700 font-semibold">
                  Dataset uploaded successfully.{" "}
                  {(uploadResult.files || [])
                    .reduce((sum, f) => sum + (f?.normalized_rows ?? f?.staged_rows ?? 0), 0)
                    .toLocaleString()}{" "}
                  rows are ready for analysis.
                </p>
              </div>
            </div>
            <span className="px-3 py-1 text-[11px] font-bold rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
              ACTIVE INGESTION
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 pt-2">
            {(uploadResult.files || []).map((file) => {
              const rowsCount = file.profile?.rows ?? file.staged_rows;
              const colsCount = file.profile?.columns ?? "N/A";
              const normalizedCount = file.normalized_rows ?? file.staged_rows;
              const qualityScore =
                file.profile?.quality_score !== undefined && file.profile?.quality_score !== null
                  ? file.profile?.quality_score
                  : 100;
              const isExpanded = !!expandedMappings[file.dataset_id];
              const mappings = file.column_mappings || [];

              return (
                <div
                  key={file.dataset_id}
                  className="bg-white border border-emerald-200 rounded-xl p-4 shadow-2xs space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800 text-xs flex items-center gap-2">
                      <FileText className="w-3.5 h-3.5 text-emerald-600" />
                      {file.filename}
                    </span>
                    <span className="px-2 py-0.5 text-[10px] uppercase font-mono font-bold bg-slate-100 text-slate-600 rounded">
                      {file.file_type}
                    </span>
                  </div>

                  {/* Detailed Metric Badges */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-100 text-xs text-slate-600">
                    <div className="flex items-center gap-1.5">
                      <Table className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>
                        Rows: <strong className="text-slate-900 font-mono">{rowsCount.toLocaleString()}</strong>
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Check className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>
                        Cols: <strong className="text-slate-900 font-mono">{colsCount}</strong>
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <BarChart2 className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                      <span>
                        Normalized: <strong className="text-blue-900 font-mono">{normalizedCount.toLocaleString()}</strong>
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      <span>
                        Quality: <strong className="text-emerald-700 font-mono">{qualityScore}%</strong>
                      </span>
                    </div>
                  </div>

                  {/* Expandable Column Mappings Section */}
                  {mappings.length > 0 && (
                    <div className="pt-2 border-t border-slate-100">
                      <button
                        onClick={() =>
                          setExpandedMappings((prev) => ({
                            ...prev,
                            [file.dataset_id]: !prev[file.dataset_id],
                          }))
                        }
                        className="flex items-center justify-between w-full text-xs font-semibold text-slate-700 hover:text-blue-600 transition-colors py-1"
                      >
                        <span className="flex items-center gap-1.5">
                          <Table className="w-3.5 h-3.5 text-blue-500" />
                          Detected columns ({mappings.length})
                        </span>
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        )}
                      </button>

                      {isExpanded && (
                        <div className="mt-2 bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs space-y-1 max-h-52 overflow-y-auto">
                          <div className="grid grid-cols-2 font-bold text-slate-500 pb-1.5 border-b border-slate-200 text-[11px]">
                            <span>Original column</span>
                            <span className="text-right">Canonical field</span>
                          </div>
                          {mappings.map((m, idx) => (
                            <div
                              key={idx}
                              className="grid grid-cols-2 items-center py-1 text-slate-700 border-b border-slate-100 last:border-0"
                            >
                              <span className="font-medium text-slate-900 truncate pr-2">
                                {m.original_column}
                              </span>
                              <span className="flex items-center justify-end gap-1 font-mono text-blue-700 font-bold">
                                <ArrowRight className="w-3 h-3 text-blue-400" />
                                {m.canonical_field}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px]">
                    <span className="text-slate-500">Processing Status:</span>
                    <span className="font-bold text-emerald-700 uppercase font-mono">{file.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
};

