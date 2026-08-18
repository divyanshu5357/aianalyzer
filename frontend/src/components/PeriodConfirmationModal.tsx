"use client";

/**
 * PeriodConfirmationModal
 *
 * Shown after uploading a file when the backend either:
 *   1. Detects a period with low confidence → ask user to confirm or correct it
 *   2. Cannot detect a period at all → ask user to select from available periods
 *   3. Detects a conflict with an existing period → ask user to choose replace/new_version/cancel
 *
 * After the user clicks an action, it calls /api/data/upload/confirm and then
 * triggers a full context refresh.
 */
import React, { useState } from "react";
import { X, AlertTriangle, CheckCircle, Info, Calendar } from "lucide-react";
import { confirmUpload, UploadedFileItemExtended } from "../lib/api";

interface Props {
  file: UploadedFileItemExtended;
  onClose: () => void;
  onConfirmed: () => void;   // called after successful confirmation so parent can refresh
}

export const PeriodConfirmationModal: React.FC<Props> = ({ file, onClose, onConfirmed }) => {
  const uploadStatus = file.upload_status;
  const detection = file.period_detection;
  const conflict = file.conflict;
  const availablePeriods = file.available_periods ?? [];

  const detectedLabel = detection?.academic_label ?? null;

  // Generate 2-year non-overlapping stepping options (e.g. 2025-26, 2023-24, 2021-22, 2019-20)
  const getTwoYearSteppingOptions = (anchor?: string | null, serverList: string[] = []): string[] => {
    let anchorStart = 2025;
    if (anchor) {
      const m = anchor.match(/^(20\d{2})[-_](\d{2}|20\d{2})$/);
      if (m && m[1]) {
        anchorStart = parseInt(m[1], 10);
      }
    }
    const generated: string[] = [];
    for (let i = 0; i < 6; i++) {
      const s = anchorStart - i * 2;
      const e = s + 1;
      generated.push(`${s}-${e.toString().slice(-2)}`);
    }
    const options: string[] = [];
    if (anchor && !options.includes(anchor)) options.push(anchor);
    generated.forEach((g) => {
      if (!options.includes(g)) options.push(g);
    });
    serverList.forEach((sp) => {
      if (sp && !options.includes(sp)) options.push(sp);
    });
    return options;
  };

  const periodOptions = getTwoYearSteppingOptions(detectedLabel, availablePeriods);

  const [selectedLabel, setSelectedLabel] = useState<string>(
    detectedLabel ?? (periodOptions[0] ?? "2025-26")
  );
  const [isCustom, setIsCustom] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(file.error_detail ?? null);

  const handleAction = async (action: "confirm" | "replace" | "new_version" | "cancel") => {
    if (action === "cancel") {
      onClose();
      return;
    }
    if (!selectedLabel) {
      setError("Please select an academic period.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await confirmUpload(file.dataset_id, action, selectedLabel);
      onConfirmed();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // ─── Conflict Mode ───────────────────────────────────────────────────────
  if (uploadStatus === "conflict" && conflict) {
    const existing = conflict.existing_dataset;
    const existingLabel = conflict.academic_label;
    const nextVersion = conflict.next_version;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-amber-500" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900">Period Conflict Detected</h2>
                <p className="text-sm text-slate-500 mt-0.5">
                  Data for <strong>{existingLabel}</strong> already exists
                </p>
              </div>
            </div>
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-4">
            <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
              <p className="text-sm text-amber-800 font-medium">
                Existing dataset: <span className="font-bold">{existing?.original_filename}</span>
              </p>
              <p className="text-xs text-amber-600 mt-1">
                Version {existing?.upload_version} · Uploaded {existing?.created_at?.split("T")[0]}
              </p>
            </div>

            <p className="text-sm text-slate-600">
              Your new file <strong>{file.filename}</strong> will become{" "}
              <strong>version {nextVersion}</strong> for period{" "}
              <strong>{existingLabel}</strong>. Choose how to handle this:
            </p>

            {error && (
              <div className="bg-red-50 border border-red-100 rounded-lg p-3 text-sm text-red-700">
                {error}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-2 p-6 pt-0">
            <button
              id="btn-replace"
              disabled={isSubmitting}
              onClick={() => handleAction("replace")}
              className="w-full py-3 px-4 rounded-xl font-semibold text-sm bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              Replace — Deactivate old version, activate new upload
            </button>
            <button
              id="btn-new-version"
              disabled={isSubmitting}
              onClick={() => handleAction("new_version")}
              className="w-full py-3 px-4 rounded-xl font-semibold text-sm bg-slate-100 text-slate-800 hover:bg-slate-200 transition-colors disabled:opacity-50"
            >
              Keep Both — Save as version {nextVersion} and activate
            </button>
            <button
              id="btn-cancel-conflict"
              disabled={isSubmitting}
              onClick={() => handleAction("cancel")}
              className="w-full py-3 px-4 rounded-xl font-semibold text-sm text-slate-500 hover:text-slate-700 transition-colors"
            >
              Cancel — Do not activate this upload
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ─── Period Selection / Confirmation Mode ────────────────────────────────
  const isUnknown = uploadStatus === "period_unknown";
  const isPending = uploadStatus === "pending_confirmation";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isPending ? "bg-blue-50" : "bg-slate-50"}`}>
              {isPending ? (
                <CheckCircle className="w-5 h-5 text-blue-500" />
              ) : (
                <Info className="w-5 h-5 text-slate-400" />
              )}
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                {isPending ? "Confirm Academic Period" : "Select Academic Period"}
              </h2>
              <p className="text-sm text-slate-500 mt-0.5">{file.filename}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {isPending && detectedLabel && (
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-blue-500" />
                <span className="text-sm font-semibold text-blue-800">
                  Detected: {detectedLabel}
                </span>
                <span className="text-xs text-blue-500 ml-auto">
                  {Math.round((detection?.confidence ?? 0) * 100)}% confidence
                </span>
              </div>
            </div>
          )}

          {isUnknown && (
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-4">
              <p className="text-sm text-slate-600">
                Could not automatically detect the academic period from the filename.
                Please select the correct period below.
              </p>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-semibold text-slate-700" htmlFor="period-select-modal">
                Academic Session
              </label>
              <button
                type="button"
                onClick={() => setIsCustom(!isCustom)}
                className="text-xs text-blue-600 font-semibold hover:underline"
              >
                {isCustom ? "Select from list" : "+ Enter custom session"}
              </button>
            </div>
            <div className="relative">
              <Calendar className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              {isCustom ? (
                <input
                  id="period-select-modal"
                  type="text"
                  placeholder="e.g. 2025-26"
                  value={selectedLabel}
                  onChange={(e) => setSelectedLabel(e.target.value)}
                  className="w-full pl-9 pr-4 py-2.5 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                />
              ) : (
                <>
                  <select
                    id="period-select-modal"
                    value={selectedLabel}
                    onChange={(e) => setSelectedLabel(e.target.value)}
                    className="w-full pl-9 pr-8 py-2.5 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all appearance-none"
                  >
                    {periodOptions.map((label) => (
                      <option key={label} value={label}>{label}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs">▼</div>
                </>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1.5">
              Format: YYYY-YY (e.g. 2025-26 where 2025 is PY and 2026 is CY)
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3.5 text-sm text-red-700 flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <div className="leading-snug">{error}</div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3 p-6 pt-0">
          <button
            id="btn-cancel-period"
            disabled={isSubmitting}
            onClick={onClose}
            className="flex-1 py-2.5 px-4 rounded-xl font-semibold text-sm bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            id="btn-confirm-period"
            disabled={isSubmitting || !selectedLabel}
            onClick={() => handleAction("confirm")}
            className="flex-1 py-2.5 px-4 rounded-xl font-semibold text-sm bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            {isSubmitting ? "Activating..." : "Confirm & Activate"}
          </button>
        </div>
      </div>
    </div>
  );
};
