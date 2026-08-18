"use client";

import React from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  yoyPercent?: number | null;
  highlight?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  yoyPercent,
  highlight = false,
}) => {
  const renderGrowthPill = () => {
    if (yoyPercent === undefined || yoyPercent === null) return null;

    const isPositive = yoyPercent > 0;
    const isZero = yoyPercent === 0;

    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${
          isZero
            ? "bg-slate-100 text-slate-600"
            : isPositive
            ? "bg-emerald-50 text-emerald-700 border border-emerald-200/80"
            : "bg-rose-50 text-rose-700 border border-rose-200/80"
        }`}
      >
        {isZero ? (
          <Minus className="w-3 h-3" />
        ) : isPositive ? (
          <TrendingUp className="w-3 h-3" />
        ) : (
          <TrendingDown className="w-3 h-3" />
        )}
        <span>
          {isPositive ? "+" : ""}
          {yoyPercent.toFixed(1)}% YoY
        </span>
      </span>
    );
  };

  return (
    <div
      className={`p-6 rounded-2xl border transition-all duration-200 ${
        highlight
          ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white border-blue-600 shadow-md shadow-blue-500/20"
          : "bg-white border-slate-200 text-slate-900 shadow-xs hover:border-slate-300"
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <span
          className={`text-xs font-bold uppercase tracking-wider ${
            highlight ? "text-blue-100" : "text-slate-500"
          }`}
        >
          {title}
        </span>
        {icon && (
          <div
            className={`w-9 h-9 rounded-xl flex items-center justify-center ${
              highlight
                ? "bg-white/10 text-white"
                : "bg-slate-100 text-blue-600"
            }`}
          >
            {icon}
          </div>
        )}
      </div>

      <div className="flex items-baseline justify-between gap-2">
        <span className="text-3xl font-extrabold tracking-tight">{value}</span>
        {renderGrowthPill()}
      </div>

      {subtitle && (
        <p
          className={`text-xs mt-2 font-medium ${
            highlight ? "text-blue-100/90" : "text-slate-500"
          }`}
        >
          {subtitle}
        </p>
      )}
    </div>
  );
};
