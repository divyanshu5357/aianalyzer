"use client";

import React, { useState } from "react";
import {
  Check,
  X,
  AlertTriangle,
  FileSpreadsheet,
  CheckCircle2,
  HelpCircle,
  BarChart2,
  Table,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";
import {
  ColumnMappingItem,
  DataQualityReport,
  MappingDecisionPayload,
  executeMappingForDataset,
} from "../lib/api";

export interface MappingSuggestionItem {
  id?: string;
  source_file?: string;
  source_sheet?: string;
  source_column: string;
  target_file?: string;
  target_sheet?: string;
  target_entity: string;
  target_column: string;
  confidence: number;
  confidence_rating?: "HIGH" | "MEDIUM" | "LOW";
  value_overlap_pct?: number;
  value_overlap_label?: string;
  match_type: string;
  status: string;
  requires_confirmation: boolean;
  is_ambiguous?: boolean;
  competing_candidates?: string[];
}

interface MappingReviewModalProps {
  datasetId: string;
  filename: string;
  sheetName?: string;
  totalRows: number;
  suggestions: MappingSuggestionItem[];
  qualityPreview?: DataQualityReport | null;
  onComplete: (result: any) => void;
  onCancel: () => void;
}

export const MappingReviewModal: React.FC<MappingReviewModalProps> = ({
  datasetId,
  filename,
  sheetName = "Sheet1",
  totalRows,
  suggestions: initialSuggestions,
  qualityPreview,
  onComplete,
  onCancel,
}) => {
  const [suggestions, setSuggestions] = useState<MappingSuggestionItem[]>(initialSuggestions);
  const [decisions, setDecisions] = useState<Record<string, "approve" | "reject" | "edit">>({});
  const [editedTargets, setEditedTargets] = useState<Record<string, { entity: string; column: string }>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleActionChange = (colName: string, action: "approve" | "reject") => {
    setDecisions((prev) => ({ ...prev, [colName]: action }));
  };

  const highConfCount = suggestions.filter(
    (s) => s.confidence >= 0.85 && !s.is_ambiguous
  ).length;
  const requiresConfirmCount = suggestions.filter((s) => s.requires_confirmation).length;
  const coveragePct = Math.round(
    ((suggestions.length - requiresConfirmCount) / Math.max(1, suggestions.length)) * 100
  );

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      const decisionPayloads: MappingDecisionPayload[] = suggestions.map((s) => {
        const action = decisions[s.source_column] || "approve";
        const edited = editedTargets[s.source_column];

        return {
          id: s.id,
          action,
          source_file: filename,
          source_sheet: sheetName,
          source_column: s.source_column,
          target_entity: edited?.entity || s.target_entity,
          target_column: edited?.column || s.target_column,
          confidence: s.confidence,
        };
      });

      const res = await executeMappingForDataset(datasetId, decisionPayloads, filename, sheetName);
      onComplete(res);
    } catch (err: any) {
      setError(err.message || "Failed to submit mapping approvals.");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-5xl w-full overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="px-6 py-4 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600/20 text-blue-400 rounded-lg">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-100 flex items-center gap-2">
                Business Relationship & Schema Mapping Review
              </h3>
              <p className="text-xs text-slate-400">
                Workbook: <span className="font-mono text-slate-200">{filename}</span> • Sheet:{" "}
                <span className="font-mono text-slate-200">{sheetName}</span> • Rows:{" "}
                <span className="font-mono text-slate-200">{totalRows.toLocaleString()}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Quality Metrics Banner */}
        <div className="bg-slate-50 border-b border-slate-200 p-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-slate-500 block text-[11px] font-medium">Mapping Coverage</span>
            <span className="text-lg font-extrabold text-blue-600 font-mono">{coveragePct}%</span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-slate-500 block text-[11px] font-medium">High Confidence</span>
            <span className="text-lg font-extrabold text-emerald-600 font-mono">
              {highConfCount} / {suggestions.length}
            </span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-slate-500 block text-[11px] font-medium">Requires Review</span>
            <span className="text-lg font-extrabold text-amber-600 font-mono">
              {requiresConfirmCount}
            </span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-slate-500 block text-[11px] font-medium">Blank Program Codes</span>
            <span className="text-lg font-extrabold text-slate-700 font-mono">
              {qualityPreview?.blank_program_code !== undefined
                ? qualityPreview.blank_program_code.toLocaleString()
                : "—"}
            </span>
          </div>
        </div>

        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-red-500 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Mappings Table */}
        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-bold text-slate-800 text-xs uppercase font-mono tracking-wider">
              Discovered Business Relationships
            </h4>
            <span className="text-[11px] text-slate-500">
              Confirm relationships between RAW Data, Dimension Masters, and Target Benchmarks
            </span>
          </div>

          <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 text-slate-600 font-bold border-b border-slate-200 text-[11px]">
                <tr>
                  <th className="py-2.5 px-4">Source Field / Sheet</th>
                  <th className="py-2.5 px-4">Business Destination / Entity</th>
                  <th className="py-2.5 px-4 text-center">Confidence</th>
                  <th className="py-2.5 px-4 text-center">Value Match</th>
                  <th className="py-2.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {suggestions.map((item, idx) => {
                  const currentDecision = decisions[item.source_column] || "approve";
                  const edited = editedTargets[item.source_column];
                  const rating = item.confidence_rating || (item.confidence >= 0.85 ? "HIGH" : item.confidence >= 0.5 ? "MEDIUM" : "LOW");

                  let overlapDisplay = item.value_overlap_label || "Not evaluated";
                  if (!item.value_overlap_label && item.value_overlap_pct && item.value_overlap_pct > 0) {
                    overlapDisplay = `${item.value_overlap_pct}% match`;
                  }

                  return (
                    <tr
                      key={idx}
                      className={
                        rating === "MEDIUM" || item.requires_confirmation
                          ? "bg-amber-50/40 hover:bg-amber-50 transition-colors"
                          : "hover:bg-slate-50/80 transition-colors"
                      }
                    >
                      <td className="py-3 px-4">
                        <span className="font-bold text-slate-900 block truncate max-w-[200px]">
                          {item.source_column}
                        </span>
                        <span className="text-[10px] text-slate-400 block font-mono">
                          {item.source_file || filename} • {item.source_sheet || sheetName}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5 font-mono text-indigo-700 font-bold">
                          <span>{edited?.entity || item.target_entity}</span>
                          <ArrowRight className="w-3 h-3 text-indigo-400" />
                          <span>{edited?.column || item.target_column}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 block font-mono mt-0.5">
                          {item.target_sheet && item.target_sheet !== "default" ? `Sheet: ${item.target_sheet}` : `Canonical entity mapping`}
                        </span>
                        {item.is_ambiguous && item.competing_candidates && item.competing_candidates.length > 0 && (
                          <span className="text-[10px] text-amber-700 block mt-0.5">
                            Ambiguous with: {item.competing_candidates.join(", ")}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-extrabold font-mono ${
                            rating === "HIGH"
                              ? "bg-emerald-100 text-emerald-800"
                              : rating === "MEDIUM"
                              ? "bg-amber-100 text-amber-800"
                              : "bg-rose-100 text-rose-800"
                          }`}
                        >
                          {Math.round(item.confidence * 100)}% ({rating})
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="text-[11px] text-slate-500 font-medium font-mono">
                          {overlapDisplay}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleActionChange(item.source_column, "approve")}
                            className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all ${
                              currentDecision === "approve"
                                ? "bg-emerald-600 text-white shadow-sm"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => handleActionChange(item.source_column, "reject")}
                            className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all ${
                              currentDecision === "reject"
                                ? "bg-red-600 text-white shadow-sm"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
          <button
            onClick={onCancel}
            disabled={isSubmitting}
            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 transition-colors"
          >
            Cancel
          </button>

          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-md hover:shadow-lg transition-all flex items-center gap-2 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Executing Ingestion...
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                Confirm & Process Dataset
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
