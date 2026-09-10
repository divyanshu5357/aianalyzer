'use client';

import React, { useEffect, useState } from 'react';
import { getProgramInsights } from '@/lib/api/programs';
import type { ProgramInsightData } from '@/lib/api/types';

interface ProgramInsightModalProps {
  programName: string;
  scopeParams: {
    academic_year?: number;
    campus?: string;
    from_date?: string;
    to_date?: string;
  };
  isDark?: boolean;
  onClose: () => void;
}

export default function ProgramInsightModal({
  programName,
  scopeParams,
  isDark = true,
  onClose,
}: ProgramInsightModalProps) {
  const [data, setData] = useState<ProgramInsightData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getProgramInsights({
      program_group: programName,
      academic_year: scopeParams.academic_year,
      campus: scopeParams.campus,
      from_date: scopeParams.from_date,
      to_date: scopeParams.to_date,
    })
      .then((res) => {
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err?.message || 'Failed to load program insights');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [programName, scopeParams]);

  // Handle ESC key to close
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const isGrowing = data?.trajectory === 'GROWING';
  const isDropping = data?.trajectory === 'DROPPING';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/70 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className={`relative w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl overflow-hidden border transition-all duration-200 ${
          isDark
            ? 'bg-[#0F172A] border-slate-700/80 text-slate-100'
            : 'bg-white border-slate-200 text-slate-900'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className={`px-6 py-5 border-b shrink-0 flex items-start justify-between gap-4 ${
            isDark
              ? 'border-slate-800 bg-slate-900/60'
              : 'border-slate-100 bg-slate-50/80'
          }`}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 text-white font-bold text-lg">
              ✨
            </div>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h2 className="text-lg font-bold tracking-tight">
                  {programName} Diagnostic Insights
                </h2>
                {data && (
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                      isGrowing
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : isDropping
                        ? 'bg-red-500/15 text-red-400 border border-red-500/30'
                        : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                    }`}
                  >
                    {isGrowing ? '📈' : isDropping ? '📉' : '⚖️'} {data.trajectory_badge}
                  </span>
                )}
              </div>
              <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Session {scopeParams.academic_year || 2026} · Campus: {scopeParams.campus || 'All Campuses'} · Root Cause Analysis
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
              isDark
                ? 'text-slate-400 hover:text-white hover:bg-white/10'
                : 'text-slate-400 hover:text-slate-800 hover:bg-slate-100'
            }`}
            title="Close (Esc)"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="w-9 h-9 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className={`text-xs font-medium ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Analyzing admissions, lead types & source drivers...
              </p>
            </div>
          ) : error ? (
            <div className="py-12 text-center space-y-3">
              <p className="text-sm text-red-400">{error}</p>
              <button
                onClick={() => onClose()}
                className="px-4 py-1.5 text-xs rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 font-medium"
              >
                Close
              </button>
            </div>
          ) : data ? (
            <>
              {/* 4 Metric Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {/* Admissions Card */}
                <div
                  className={`p-3.5 rounded-xl border ${
                    isDark ? 'bg-slate-900/50 border-slate-800' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    CY Admissions
                  </span>
                  <div className="text-xl font-bold mt-1 text-emerald-400">
                    {data.metrics.cy_admissions.toLocaleString()}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[11px]">
                    <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>
                      PY: {data.metrics.py_admissions.toLocaleString()}
                    </span>
                    <span
                      className={`font-semibold ${
                        data.metrics.var_admissions >= 0 ? 'text-emerald-400' : 'text-red-400'
                      }`}
                    >
                      ({data.metrics.var_admissions >= 0 ? '+' : ''}
                      {data.metrics.var_admissions.toLocaleString()})
                    </span>
                  </div>
                </div>

                {/* Leads Card */}
                <div
                  className={`p-3.5 rounded-xl border ${
                    isDark ? 'bg-slate-900/50 border-slate-800' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    CY Leads
                  </span>
                  <div className="text-xl font-bold mt-1 text-indigo-400">
                    {data.metrics.cy_leads.toLocaleString()}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[11px]">
                    <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>
                      PY: {data.metrics.py_leads.toLocaleString()}
                    </span>
                    <span
                      className={`font-semibold ${
                        data.metrics.var_leads >= 0 ? 'text-indigo-400' : 'text-red-400'
                      }`}
                    >
                      ({data.metrics.var_leads >= 0 ? '+' : ''}
                      {data.metrics.var_leads_pct.toFixed(1)}%)
                    </span>
                  </div>
                </div>

                {/* CUCET Card */}
                <div
                  className={`p-3.5 rounded-xl border ${
                    isDark ? 'bg-slate-900/50 border-slate-800' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    CY CUCET
                  </span>
                  <div className="text-xl font-bold mt-1 text-amber-400">
                    {data.metrics.cy_cucet.toLocaleString()}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[11px]">
                    <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>
                      PY: {data.metrics.py_cucet.toLocaleString()}
                    </span>
                    <span
                      className={`font-semibold ${
                        data.metrics.var_cucet >= 0 ? 'text-amber-400' : 'text-red-400'
                      }`}
                    >
                      ({data.metrics.var_cucet >= 0 ? '+' : ''}
                      {data.metrics.var_cucet_pct.toFixed(1)}%)
                    </span>
                  </div>
                </div>

                {/* Conversion Rate Card */}
                <div
                  className={`p-3.5 rounded-xl border ${
                    isDark ? 'bg-slate-900/50 border-slate-800' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    Lead → Adm Rate
                  </span>
                  <div className="text-xl font-bold mt-1 text-sky-400">
                    {data.metrics.conversion_rate_cy.toFixed(2)}%
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[11px]">
                    <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>
                      PY: {data.metrics.conversion_rate_py.toFixed(2)}%
                    </span>
                    <span
                      className={`font-semibold ${
                        data.metrics.conversion_rate_cy >= data.metrics.conversion_rate_py
                          ? 'text-emerald-400'
                          : 'text-red-400'
                      }`}
                    >
                      ({(data.metrics.conversion_rate_cy - data.metrics.conversion_rate_py >= 0 ? '+' : '')}
                      {(data.metrics.conversion_rate_cy - data.metrics.conversion_rate_py).toFixed(2)} pp)
                    </span>
                  </div>
                </div>
              </div>

              {/* Section 1: Lead Type Performance (Good vs Bad) */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-sky-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider">
                    Lead Type Drivers (Working Good vs Underperforming)
                  </h3>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {data.lead_types.map((lt) => {
                    const isGood = lt.status === 'good';
                    return (
                      <div
                        key={lt.lead_type}
                        className={`p-3.5 rounded-xl border flex flex-col justify-between transition-all ${
                          isGood
                            ? isDark
                              ? 'bg-emerald-950/15 border-emerald-500/30'
                              : 'bg-emerald-50/50 border-emerald-200'
                            : isDark
                            ? 'bg-red-950/15 border-red-500/30'
                            : 'bg-red-50/50 border-red-200'
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <span className="font-bold text-sm tracking-tight">{lt.lead_type}</span>
                            <span
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
                                isGood
                                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                  : 'bg-red-500/20 text-red-400 border border-red-500/30'
                              }`}
                            >
                              {isGood ? '🟢 Working Good' : '🔴 Drag / Drop'}
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-xs mb-2.5">
                            <div>
                              <span className={`text-[10px] block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                Admissions
                              </span>
                              <span className="font-bold text-slate-100">
                                {lt.cy_adm.toLocaleString()}
                              </span>{' '}
                              <span
                                className={`text-[10px] font-semibold ${
                                  lt.var_adm >= 0 ? 'text-emerald-400' : 'text-red-400'
                                }`}
                              >
                                ({lt.var_adm >= 0 ? '+' : ''}{lt.var_adm})
                              </span>
                            </div>
                            <div>
                              <span className={`text-[10px] block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                Conversion
                              </span>
                              <span className="font-bold text-sky-400">{lt.conversion_rate.toFixed(2)}%</span>
                            </div>
                          </div>
                        </div>

                        <p className={`text-[11px] leading-relaxed pt-2 border-t ${
                          isDark ? 'border-white/5 text-slate-300' : 'border-slate-200 text-slate-600'
                        }`}>
                          {lt.reason}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Section 2: Top Source Breakdown (Growth Drivers vs Drops) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Top Positive Sources */}
                <div
                  className={`p-4 rounded-xl border ${
                    isDark ? 'bg-slate-900/40 border-slate-800' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-emerald-400 font-bold text-sm">📈</span>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                      Top Sources Driving Admissions (Good)
                    </h3>
                  </div>

                  <div className="space-y-2">
                    {data.top_growth_sources.length === 0 ? (
                      <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        No significant growth sources recorded.
                      </p>
                    ) : (
                      data.top_growth_sources.map((s, idx) => (
                        <div
                          key={s.source_name + idx}
                          className={`flex items-center justify-between p-2 rounded-lg text-xs border ${
                            isDark ? 'bg-slate-800/40 border-slate-700/50' : 'bg-white border-slate-200'
                          }`}
                        >
                          <div>
                            <span className="font-semibold">{s.source_name}</span>
                            <span className={`text-[10px] ml-1.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                              ({s.lead_type})
                            </span>
                          </div>
                          <div className="text-right tabular-nums">
                            <span className="font-bold text-emerald-400">{s.cy_adm} adm</span>
                            <span className="text-[10px] ml-1 text-emerald-500">
                              (+{s.var_adm})
                            </span>
                            <span className={`text-[10px] block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                              {s.cy_leads.toLocaleString()} leads ({s.conversion_rate.toFixed(1)}%)
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Sources Causing Drop / Drag */}
                <div
                  className={`p-4 rounded-xl border ${
                    isDark ? 'bg-slate-900/40 border-slate-800' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-red-400 font-bold text-sm">📉</span>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-red-400">
                      Sources with Drop / Drag (Underperforming)
                    </h3>
                  </div>

                  <div className="space-y-2">
                    {data.top_drag_sources.length === 0 ? (
                      <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                        No major dropping sources detected.
                      </p>
                    ) : (
                      data.top_drag_sources.map((s, idx) => (
                        <div
                          key={s.source_name + idx}
                          className={`flex items-center justify-between p-2 rounded-lg text-xs border ${
                            isDark ? 'bg-slate-800/40 border-slate-700/50' : 'bg-white border-slate-200'
                          }`}
                        >
                          <div>
                            <span className="font-semibold">{s.source_name}</span>
                            <span className={`text-[10px] ml-1.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                              ({s.lead_type})
                            </span>
                          </div>
                          <div className="text-right tabular-nums">
                            <span className="font-bold text-red-400">{s.cy_adm} adm</span>
                            <span className="text-[10px] ml-1 text-red-400">
                              ({s.var_adm >= 0 ? '+' : ''}{s.var_adm})
                            </span>
                            <span className={`text-[10px] block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                              {s.cy_leads.toLocaleString()} leads ({s.conversion_rate.toFixed(1)}%)
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Section 3: AI Diagnosis & Strategic Recommendations */}
              <div
                className={`p-4 rounded-xl border ${
                  isDark ? 'bg-indigo-950/20 border-indigo-500/30' : 'bg-indigo-50/50 border-indigo-200'
                }`}
              >
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400">
                    AI Diagnostic Summary & Recommendations
                  </h3>
                </div>

                <div className="space-y-2.5">
                  {data.takeaways.map((t, idx) => (
                    <div key={idx} className="flex items-start gap-2.5 text-xs">
                      <span className="mt-0.5 shrink-0 text-sm">
                        {t.type === 'positive'
                          ? '✅'
                          : t.type === 'negative'
                          ? '⚠️'
                          : t.type === 'warning'
                          ? '🔍'
                          : '💡'}
                      </span>
                      <div>
                        <span className="font-bold text-slate-200">{t.title}: </span>
                        <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>
                          {t.description}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div
          className={`px-6 py-3 border-t shrink-0 flex items-center justify-between text-xs ${
            isDark ? 'border-slate-800 bg-slate-900/40 text-slate-400' : 'border-slate-100 bg-slate-50 text-slate-500'
          }`}
        >
          <span>Server-side aggregated diagnostics · AI Analyzer</span>
          <button
            onClick={onClose}
            className={`px-4 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
              isDark
                ? 'bg-white/10 hover:bg-white/15 border-white/10 text-white'
                : 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-800'
            }`}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
