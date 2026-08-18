"use client";

import React, { useEffect, useState } from "react";
import {
  X,
  AlertTriangle,
  CheckCircle2,
  Layers,
  Loader2,
  Users,
  Target,
  Award,
} from "lucide-react";
import { getSourceDetail, SourceDetailResponse } from "../lib/api";

interface SourceDetailProps {
  year: number;
  mainSource: string | null;
  source: string | null;
  onClose: () => void;
}

export const SourceDetailModal: React.FC<SourceDetailProps> = ({
  year,
  mainSource,
  source,
  onClose,
}) => {
  const [detail, setDetail] = useState<SourceDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mainSource || !source) return;

    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getSourceDetail(year, mainSource, source);
        setDetail(res);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load channel details."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [year, mainSource, source]);

  if (!mainSource || !source) return null;

  const leads = detail?.funnel.leads ?? 0;
  const cucet = detail?.funnel.cucet ?? 0;
  const admission = detail?.funnel.admission ?? 0;
  const isZeroAdmissionWarning = leads > 0 && admission === 0;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex justify-end transition-opacity animate-in fade-in">
      <div className="w-full max-w-lg bg-white h-full shadow-2xl flex flex-col justify-between overflow-y-auto border-l border-slate-200">
        {/* Modal Header */}
        <div>
          <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-100/80 text-blue-600 flex items-center justify-center font-bold">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  {mainSource}
                </span>
                <h3 className="text-lg font-extrabold text-slate-900 leading-tight">
                  {source} Performance
                </h3>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="p-6 space-y-6">
            {loading ? (
              <div className="py-12 text-center text-slate-500 space-y-3">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
                <p className="text-xs font-semibold">
                  Fetching source metrics for {year}...
                </p>
              </div>
            ) : error ? (
              <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{error}</span>
              </div>
            ) : detail ? (
              <>
                {/* Warning Banner if leads exist but admissions are zero */}
                {isZeroAdmissionWarning && (
                  <div className="p-4 bg-amber-50 border border-amber-200 rounded-2xl text-xs text-amber-900 space-y-1 shadow-2xs">
                    <div className="flex items-center gap-2 font-bold text-amber-700">
                      <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                      <span>Zero Admissions Warning</span>
                    </div>
                    <p className="text-amber-800 leading-relaxed">
                      This channel generated <strong>{leads} leads</strong> in {year}, but resulted in <strong>0 admissions</strong>. Immediate conversion pipeline review is recommended.
                    </p>
                  </div>
                )}

                {/* Status Badge Card */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">
                    Performance Status
                  </span>
                  {detail.performance === "high_leads_low_conversion" ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800">
                      <AlertTriangle className="w-3.5 h-3.5" /> High Leads / Low Conv.
                    </span>
                  ) : detail.performance === "strong" ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Strong Channel
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-slate-200 text-slate-700">
                      Normal Performance
                    </span>
                  )}
                </div>

                {/* Funnel Metrics Grid */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    Funnel Volume ({year})
                  </h4>

                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-4 bg-blue-50/60 border border-blue-100 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-blue-600 text-xs font-semibold">
                        <Users className="w-3.5 h-3.5" /> Leads
                      </div>
                      <p className="text-xl font-extrabold text-slate-900">
                        {leads.toLocaleString()}
                      </p>
                    </div>

                    <div className="p-4 bg-indigo-50/60 border border-indigo-100 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-indigo-600 text-xs font-semibold">
                        <Target className="w-3.5 h-3.5" /> CUCET
                      </div>
                      <p className="text-xl font-extrabold text-slate-900">
                        {cucet.toLocaleString()}
                      </p>
                    </div>

                    <div className="p-4 bg-emerald-50/60 border border-emerald-100 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-emerald-600 text-xs font-semibold">
                        <Award className="w-3.5 h-3.5" /> Admissions
                      </div>
                      <p className="text-xl font-extrabold text-slate-900">
                        {admission.toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Conversion Percentages */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    Conversion Efficiencies
                  </h4>

                  <div className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 text-xs">
                    <div className="p-4 flex items-center justify-between">
                      <span className="font-semibold text-slate-600">Lead → CUCET</span>
                      <span className="font-bold text-slate-900 text-sm">
                        {detail.conversion.lead_cucet_percent !== null
                          ? `${detail.conversion.lead_cucet_percent}%`
                          : "—"}
                      </span>
                    </div>

                    <div className="p-4 flex items-center justify-between">
                      <span className="font-semibold text-slate-600">CUCET → Admission</span>
                      <span className="font-bold text-slate-900 text-sm">
                        {detail.conversion.cucet_admission_percent !== null
                          ? `${detail.conversion.cucet_admission_percent}%`
                          : "—"}
                      </span>
                    </div>

                    <div className="p-4 flex items-center justify-between bg-slate-50/50 rounded-b-2xl">
                      <span className="font-bold text-slate-800">Lead → Admission (Overall)</span>
                      <span className="font-extrabold text-blue-600 text-base">
                        {detail.conversion.lead_admission_percent !== null
                          ? `${detail.conversion.lead_admission_percent}%`
                          : "—"}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 text-white font-bold text-xs rounded-xl hover:bg-slate-800 transition-colors"
          >
            Close Panel
          </button>
        </div>
      </div>
    </div>
  );
};
