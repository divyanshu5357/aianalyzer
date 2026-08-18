"use client";

import React from "react";
import { ArrowRight, Filter, Target, Award, Users } from "lucide-react";
import { FunnelResponse } from "../lib/api";

interface FunnelCardProps {
  funnelData: FunnelResponse | null;
  isLoading?: boolean;
}

export const FunnelCard: React.FC<FunnelCardProps> = ({
  funnelData,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs animate-pulse">
        <div className="h-4 bg-slate-200 rounded w-1/4 mb-4"></div>
        <div className="h-32 bg-slate-100 rounded-xl mb-4"></div>
        <div className="h-10 bg-slate-200 rounded"></div>
      </div>
    );
  }

  if (!funnelData) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-6 text-center text-slate-500 text-sm">
        No funnel analytics available.
      </div>
    );
  }

  const { current_year, current_year_funnel, conversion_rates } = funnelData;
  const leads = current_year_funnel.leads;
  const cucet = current_year_funnel.cucet;
  const admission = current_year_funnel.admission;

  const leadToCucet = conversion_rates.lead_cucet_percent;
  const cucetToAdmission = conversion_rates.cucet_admission_percent;
  const leadToAdmission = conversion_rates.lead_admission_percent;

  const stages = [
    {
      name: "Leads",
      count: leads,
      percent: 100,
      icon: <Users className="w-5 h-5 text-blue-600" />,
      color: "bg-blue-600",
      lightBg: "bg-blue-50 border-blue-100",
    },
    {
      name: "CUCET Registrations",
      count: cucet,
      percent: leadToCucet,
      icon: <Target className="w-5 h-5 text-indigo-600" />,
      color: "bg-indigo-600",
      lightBg: "bg-indigo-50 border-indigo-100",
    },
    {
      name: "Admissions",
      count: admission,
      percent: leadToAdmission,
      icon: <Award className="w-5 h-5 text-emerald-600" />,
      color: "bg-emerald-600",
      lightBg: "bg-emerald-50 border-emerald-100",
    },
  ];

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-bold uppercase tracking-wider text-blue-600">
              ADMISSION FUNNEL
            </span>
          </div>
          <h2 className="text-lg font-extrabold text-slate-900 tracking-tight mt-0.5">
            Year {current_year} Conversion Journey
          </h2>
        </div>
        <span className="px-3 py-1 text-xs font-bold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
          Live Dataset
        </span>
      </div>

      {/* Visual Funnel Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
        {stages.map((stage, idx) => (
          <div key={stage.name} className="relative group">
            <div
              className={`p-5 rounded-2xl border ${stage.lightBg} transition-all duration-200 space-y-3`}
            >
              <div className="flex items-center justify-between">
                <div className="p-2.5 rounded-xl bg-white shadow-2xs">
                  {stage.icon}
                </div>
                <span className="text-xs font-bold text-slate-500">
                  Step {idx + 1}
                </span>
              </div>

              <div>
                <p className="text-2xl font-extrabold text-slate-900 tracking-tight">
                  {stage.count.toLocaleString()}
                </p>
                <p className="text-xs font-semibold text-slate-600 mt-0.5">
                  {stage.name}
                </p>
              </div>

              {/* Progress bar */}
              <div className="space-y-1 pt-1">
                <div className="flex justify-between text-[11px] font-bold text-slate-500">
                  <span>Share of Leads</span>
                  <span>{stage.percent}%</span>
                </div>
                <div className="w-full h-2 bg-slate-200/80 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${stage.color} rounded-full transition-all duration-500`}
                    style={{ width: `${Math.min(100, Math.max(0, stage.percent))}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* Connecting Arrow for Desktop */}
            {idx < stages.length - 1 && (
              <div className="hidden md:flex absolute -right-3.5 top-1/2 -translate-y-1/2 z-10 w-7 h-7 rounded-full bg-white border border-slate-200 text-slate-400 items-center justify-center shadow-2xs">
                <ArrowRight className="w-3.5 h-3.5" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Funnel Conversion Rates Breakdown */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-4 border-t border-slate-100 text-xs">
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 flex flex-col justify-between">
          <span className="text-slate-500 font-semibold">Lead → CUCET</span>
          <span className="text-base font-bold text-slate-900 mt-1">
            {leadToCucet}%
          </span>
        </div>

        <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 flex flex-col justify-between">
          <span className="text-slate-500 font-semibold">CUCET → Admission</span>
          <span className="text-base font-bold text-slate-900 mt-1">
            {cucetToAdmission}%
          </span>
        </div>

        <div className="p-3 rounded-xl bg-blue-50/60 border border-blue-100 flex flex-col justify-between">
          <span className="text-blue-600 font-semibold">Overall Lead → Admission</span>
          <span className="text-base font-extrabold text-blue-700 mt-1">
            {leadToAdmission}%
          </span>
        </div>
      </div>
    </div>
  );
};
