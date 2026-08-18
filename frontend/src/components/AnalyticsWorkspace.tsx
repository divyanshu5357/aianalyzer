"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Filter,
  LoaderCircle,
  TableProperties,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import {
  AnalyticsDisplay,
  AnalyticsMetric,
  AnalyticsPerformance,
  AnalyticsWorkspaceFilters,
  AnalyticsWorkspaceKind,
  AnalyticsWorkspaceResponse,
  getAnalyticsWorkspace,
  getAnalyticsWorkspaceOptions,
  parseApiError,
} from "../lib/api";

type WorkspaceProps = {
  workspace: AnalyticsWorkspaceKind;
};

type SortOption = {
  value: string;
  label: string;
};

const EMPTY_FILTERS: AnalyticsWorkspaceFilters = {
  state: "",
  source: "",
  campus: "",
  owner: "",
  program: "",
  specialization: "",
};

const PAGE_SIZE = 50;

const commonSortOptions: SortOption[] = [
  { value: "absolute_change", label: "Selected metric change" },
  { value: "growth_percent", label: "Growth %" },
  { value: "lead_change", label: "Lead change" },
  { value: "lead_change_percent", label: "Lead change %" },
  { value: "admission_change", label: "Admission change" },
  { value: "admission_change_percent", label: "Admission change %" },
  { value: "conversion_change", label: "Conversion change (pp)" },
];

function fieldLabel(field: keyof AnalyticsWorkspaceFilters) {
  return {
    state: "State",
    source: "Source",
    campus: "Campus",
    owner: "Owner",
    program: "Program",
    specialization: "Specialization / Branch",
  }[field];
}

function metricLabel(metric: AnalyticsMetric) {
  return metric === "conversion_rate"
    ? "Conversion"
    : metric === "admissions"
      ? "Admissions"
      : "Leads";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(value);
}

function formatPercent(value: number | null) {
  return value === null ? "—" : `${value.toFixed(2)}%`;
}

function formatPp(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} pp`;
}

function trendClass(value: number | null) {
  if (value === null || value === 0) return "text-slate-400";
  return value > 0 ? "text-emerald-400" : "text-rose-400";
}

function TrendValue({ value, children }: { value: number | null; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center justify-end gap-1 font-semibold ${trendClass(value)}`}>
      {value !== null && value > 0 ? <ArrowUp className="h-3 w-3" /> : null}
      {value !== null && value < 0 ? <ArrowDown className="h-3 w-3" /> : null}
      {children}
    </span>
  );
}

export function AnalyticsWorkspace({ workspace }: WorkspaceProps) {
  const { theme, periods, analyticalYears, isLoadingPeriods, refreshTrigger } = useApp();
  const isDark = theme === "dark";
  const [periodA, setPeriodA] = useState("");
  const [periodB, setPeriodB] = useState("");
  const [metric, setMetric] = useState<AnalyticsMetric>("leads");
  const [performance, setPerformance] = useState<AnalyticsPerformance>("all");
  const [display, setDisplay] = useState<AnalyticsDisplay>("both");
  const [sortField, setSortField] = useState("absolute_change");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [filters, setFilters] = useState<AnalyticsWorkspaceFilters>(EMPTY_FILTERS);
  const [options, setOptions] = useState<Record<keyof AnalyticsWorkspaceFilters, string[]>>({
    state: [], source: [], campus: [], owner: [], program: [], specialization: [],
  });
  const [data, setData] = useState<AnalyticsWorkspaceResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const availableYears = useMemo(() => {
    if (analyticalYears && analyticalYears.length > 0) {
      return analyticalYears;
    }
    const set = new Set<number>();
    periods.forEach((p) => {
      if (p.period_start_year) set.add(p.period_start_year);
      if (p.period_end_year) set.add(p.period_end_year);
    });
    return Array.from(set).sort((a, b) => a - b);
  }, [analyticalYears, periods]);

  const yearSelectOptions = useMemo(() => {
    if (availableYears.length > 0) {
      return availableYears.map((y) => ({ value: String(y), label: String(y) }));
    }
    return periods.map((p) => ({ value: p.academic_label, label: p.academic_label }));
  }, [availableYears, periods]);

  useEffect(() => {
    if (periodA || periodB) return;
    if (availableYears.length >= 2) {
      setPeriodA(String(availableYears[availableYears.length - 2]));
      setPeriodB(String(availableYears[availableYears.length - 1]));
    } else if (availableYears.length === 1) {
      setPeriodA(String(availableYears[0]));
      setPeriodB(String(availableYears[0]));
    } else if (periods.length > 0) {
      const p = periods[0];
      if (p.period_start_year && p.period_end_year) {
        setPeriodA(String(p.period_start_year));
        setPeriodB(String(p.period_end_year));
      }
    }
  }, [availableYears, periods, periodA, periodB]);

  const loadOptions = useCallback(async () => {
    if (!periodA || !periodB) return;
    if (periodA.trim() === periodB.trim()) return;
    try {
      const result = await getAnalyticsWorkspaceOptions(workspace, periodA, periodB);
      setOptions(result.options);
    } catch (loadError) {
      const cleanMsg = parseApiError(
        loadError instanceof Error ? loadError.message : String(loadError),
        "Failed to load filter values."
      );
      setError(cleanMsg);
    }
  }, [periodA, periodB, workspace]);

  const loadWorkspace = useCallback(async () => {
    if (!periodA || !periodB) return;
    if (periodA.trim() === periodB.trim()) {
      setError("Please select two different years for comparison.");
      setData(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await getAnalyticsWorkspace({
        workspace,
        periodA,
        periodB,
        metric,
        performance,
        sortField,
        sortDirection,
        display,
        limit: PAGE_SIZE,
        offset,
        ...filters,
      });
      setData(result);
    } catch (loadError) {
      const cleanMsg = parseApiError(
        loadError instanceof Error ? loadError.message : String(loadError),
        "Failed to load the analytics table."
      );
      setError(cleanMsg);
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [display, filters, metric, offset, performance, periodA, periodB, sortDirection, sortField, workspace]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions, refreshTrigger]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace, refreshTrigger]);

  const setFilter = (field: keyof AnalyticsWorkspaceFilters, value: string) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setOffset(0);
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setPerformance("all");
    setOffset(0);
  };

  const filterFields: (keyof AnalyticsWorkspaceFilters)[] = workspace === "source"
    ? ["state", "source", "campus", "owner"]
    : ["program", "specialization", "state", "campus", "source", "owner"];
  const sortOptions = workspace === "source"
    ? [{ value: "source", label: "Source" }, { value: "state", label: "State" }, ...commonSortOptions]
    : [{ value: "program", label: "Program" }, { value: "specialization", label: "Specialization / Branch" }, ...commonSortOptions];
  const showExact = display !== "percentage";
  const showPercentages = display !== "exact";
  const currentMetric = metricLabel(metric);
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;

  if (isLoadingPeriods) {
    return <WorkspaceLoading isDark={isDark} />;
  }

  if (periods.length === 0 && availableYears.length === 0) {
    return (
      <div className={`rounded-2xl border p-10 text-center ${isDark ? "border-slate-800 bg-[#111827] text-slate-400" : "border-slate-200 bg-white text-slate-500"}`}>
        <TableProperties className="mx-auto mb-3 h-7 w-7 text-blue-400" />
        <p className="font-bold">No historical periods are ready for analysis</p>
        <p className="mt-1 text-sm">Upload and activate at least one period dataset to use this workspace.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-blue-400">Analytics workspace</p>
          <h1 className={`mt-1 text-2xl font-extrabold tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
            {workspace === "source" ? "Source Analytics" : "Program Analytics"}
          </h1>
          <p className={`mt-1 text-sm ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Compare performance across any historical analytical years.
          </p>
        </div>
        <div className={`inline-flex items-center gap-2 self-start rounded-lg border px-3 py-2 text-xs font-semibold sm:self-auto ${isDark ? "border-slate-700 bg-[#111827] text-slate-300" : "border-slate-200 bg-white text-slate-600"}`}>
          <TableProperties className="h-4 w-4 text-blue-400" />
          Server-side table
        </div>
      </section>

      <section className={`rounded-2xl border p-4 shadow-sm ${isDark ? "border-[#25324A] bg-[#111827]" : "border-slate-200 bg-white"}`}>
        <div className="mb-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-blue-400" />
            <h2 className={`text-sm font-bold ${isDark ? "text-slate-100" : "text-slate-800"}`}>Table filters</h2>
          </div>
          <button
            type="button"
            onClick={resetFilters}
            className={`text-xs font-bold ${isDark ? "text-slate-400 hover:text-white" : "text-slate-500 hover:text-slate-800"}`}
          >
            Reset filters
          </button>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SelectField label="Year From" value={periodA} onChange={(value) => { setPeriodA(value); setOffset(0); }} options={yearSelectOptions} isDark={isDark} />
          <SelectField label="Year To" value={periodB} onChange={(value) => { setPeriodB(value); setOffset(0); }} options={yearSelectOptions} isDark={isDark} />
          <SelectField label="Metric" value={metric} onChange={(value) => { setMetric(value as AnalyticsMetric); setOffset(0); }} options={[{ value: "leads", label: "Leads" }, { value: "admissions", label: "Admissions" }, { value: "conversion_rate", label: "Conversion rate" }]} isDark={isDark} />
          <SelectField label="Performance" value={performance} onChange={(value) => { setPerformance(value as AnalyticsPerformance); setOffset(0); }} options={[{ value: "all", label: "All" }, { value: "increased", label: "Increased" }, { value: "decreased", label: "Decreased" }]} isDark={isDark} />
          {filterFields.map((field) => (
            <SelectField
              key={field}
              label={fieldLabel(field)}
              value={filters[field] ?? ""}
              onChange={(value) => setFilter(field, value)}
              options={[{ value: "", label: `All ${fieldLabel(field)}` }, ...(options[field] ?? []).map((value) => ({ value, label: value }))]}
              isDark={isDark}
            />
          ))}
          <SelectField label="Sort field" value={sortField} onChange={(value) => { setSortField(value); setOffset(0); }} options={sortOptions} isDark={isDark} />
          <SelectField label="Sort direction" value={sortDirection} onChange={(value) => { setSortDirection(value as "asc" | "desc"); setOffset(0); }} options={[{ value: "desc", label: "Descending" }, { value: "asc", label: "Ascending" }]} isDark={isDark} />
          <SelectField label="Display" value={display} onChange={(value) => setDisplay(value as AnalyticsDisplay)} options={[{ value: "exact", label: "Exact" }, { value: "percentage", label: "%" }, { value: "both", label: "Both" }]} isDark={isDark} />
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">{error}</div>
      ) : null}

      <section className={`overflow-hidden rounded-2xl border shadow-sm ${isDark ? "border-[#25324A] bg-[#111827]" : "border-slate-200 bg-white"}`}>
        <div className={`flex flex-col gap-2 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${isDark ? "border-[#25324A]" : "border-slate-200"}`}>
          <div>
            <h2 className={`font-bold ${isDark ? "text-white" : "text-slate-900"}`}>
              {workspace === "source" ? "Source performance" : "Program performance"}
            </h2>
            <p className={`mt-0.5 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
              {periodA} baseline → {periodB} comparison · {currentMetric} selected for performance filtering
            </p>
          </div>
          <span className={`w-fit rounded-md px-2 py-1 text-[11px] font-bold ${isDark ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-600"}`}>
            Page {pageNumber}
          </span>
        </div>

        {isLoading ? <WorkspaceLoading isDark={isDark} compact /> : (
          <WorkspaceTable
            workspace={workspace}
            data={data}
            periodA={periodA}
            periodB={periodB}
            showExact={showExact}
            showPercentages={showPercentages}
            isDark={isDark}
          />
        )}

        <div className={`flex items-center justify-between gap-3 border-t px-4 py-3 ${isDark ? "border-[#25324A]" : "border-slate-200"}`}>
          <p className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Up to {PAGE_SIZE} aggregated rows per page.
          </p>
          <div className="flex items-center gap-2">
            <button type="button" disabled={offset === 0 || isLoading} onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))} className={paginationButton(isDark, offset === 0 || isLoading)}>
              <ChevronLeft className="h-4 w-4" /> Previous
            </button>
            <button type="button" disabled={!data?.pagination.has_more || isLoading} onClick={() => setOffset((current) => current + PAGE_SIZE)} className={paginationButton(isDark, !data?.pagination.has_more || isLoading)}>
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function SelectField({ label, value, onChange, options, isDark }: { label: string; value: string; onChange: (value: string) => void; options: SortOption[]; isDark: boolean }) {
  return (
    <label className="min-w-0">
      <span className={`mb-1.5 block text-[11px] font-bold uppercase tracking-wide ${isDark ? "text-slate-500" : "text-slate-500"}`}>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className={`w-full truncate rounded-lg border px-3 py-2 text-sm font-semibold outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 ${isDark ? "border-slate-700 bg-[#0B1220] text-slate-200" : "border-slate-200 bg-slate-50 text-slate-700"}`}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function WorkspaceLoading({ isDark, compact = false }: { isDark: boolean; compact?: boolean }) {
  return (
    <div className={`flex items-center justify-center gap-2 ${compact ? "min-h-64" : "min-h-96"} ${isDark ? "text-slate-400" : "text-slate-500"}`}>
      <LoaderCircle className="h-5 w-5 animate-spin text-blue-400" />
      <span className="text-sm font-medium">Aggregating historical metrics…</span>
    </div>
  );
}

function paginationButton(isDark: boolean, disabled: boolean) {
  return `inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-bold transition ${disabled ? "cursor-not-allowed opacity-40" : "hover:border-blue-500 hover:text-blue-400"} ${isDark ? "border-slate-700 bg-[#0B1220] text-slate-300" : "border-slate-200 bg-white text-slate-600"}`;
}

function WorkspaceTable({ workspace, data, periodA, periodB, showExact, showPercentages, isDark }: { workspace: AnalyticsWorkspaceKind; data: AnalyticsWorkspaceResponse | null; periodA: string; periodB: string; showExact: boolean; showPercentages: boolean; isDark: boolean }) {
  const rows = data?.rows ?? [];
  const headerClass = `whitespace-nowrap px-3 py-3 text-right text-[10px] font-extrabold uppercase tracking-wide ${isDark ? "bg-[#0B1220] text-slate-500" : "bg-slate-50 text-slate-500"}`;
  const cellClass = `whitespace-nowrap px-3 py-3 text-right text-xs tabular-nums ${isDark ? "text-slate-300" : "text-slate-700"}`;

  if (rows.length === 0) {
    return <div className={`p-12 text-center text-sm ${isDark ? "text-slate-400" : "text-slate-500"}`}>No grouped results match the selected filters.</div>;
  }

  return (
    <div className="max-w-full overflow-x-auto">
      <table className="min-w-max w-full border-collapse text-left">
        <thead>
          <tr>
            <th className={`${headerClass} sticky left-0 z-10 text-left ${isDark ? "bg-[#0B1220]" : "bg-slate-50"}`}>{workspace === "source" ? "Source" : "Program"}</th>
            {workspace === "source" ? <th className={`${headerClass} text-left`}>State</th> : <th className={`${headerClass} text-left`}>Specialization / Branch</th>}
            {workspace === "program" && showExact ? <>
              <th className={headerClass}>{periodA} value</th><th className={headerClass}>{periodB} value</th><th className={headerClass}>Absolute change</th>
            </> : null}
            {workspace === "program" && showPercentages ? <th className={headerClass}>Growth %</th> : null}
            {showExact ? <>
              <th className={headerClass}>{periodA} leads</th><th className={headerClass}>{periodB} leads</th><th className={headerClass}>Lead change</th>
            </> : null}
            {showPercentages ? <th className={headerClass}>Lead change %</th> : null}
            {showExact ? <>
              <th className={headerClass}>{periodA} admissions</th><th className={headerClass}>{periodB} admissions</th><th className={headerClass}>Admission change</th>
            </> : null}
            {showPercentages ? <th className={headerClass}>Admission change %</th> : null}
            <th className={headerClass}>{periodA} conversion</th><th className={headerClass}>{periodB} conversion</th><th className={headerClass}>Conversion change</th>
          </tr>
        </thead>
        <tbody className={isDark ? "divide-y divide-slate-800" : "divide-y divide-slate-100"}>
          {rows.map((row, index) => (
            <tr key={`${row.source ?? row.program}-${row.state ?? row.specialization ?? ""}-${index}`} className={isDark ? "hover:bg-slate-800/40" : "hover:bg-slate-50"}>
              <td className={`sticky left-0 z-[1] px-3 py-3 text-sm font-bold ${isDark ? "bg-[#111827] text-slate-100" : "bg-white text-slate-800"}`}>{row.source ?? row.program}</td>
              <td className={`${cellClass} text-left font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}>{row.state ?? row.specialization ?? "—"}</td>
              {workspace === "program" && showExact ? <>
                <td className={cellClass}>{formatNumber(row.period_a_value)}</td><td className={cellClass}>{formatNumber(row.period_b_value)}</td><td className={cellClass}><TrendValue value={row.absolute_change}>{formatNumber(row.absolute_change)}</TrendValue></td>
              </> : null}
              {workspace === "program" && showPercentages ? <td className={cellClass}><TrendValue value={row.growth_percent}>{formatPercent(row.growth_percent)}</TrendValue></td> : null}
              {showExact ? <>
                <td className={cellClass}>{formatNumber(row.period_a_leads)}</td><td className={cellClass}>{formatNumber(row.period_b_leads)}</td><td className={cellClass}><TrendValue value={row.lead_change}>{formatNumber(row.lead_change)}</TrendValue></td>
              </> : null}
              {showPercentages ? <td className={cellClass}><TrendValue value={row.lead_change_percent}>{formatPercent(row.lead_change_percent)}</TrendValue></td> : null}
              {showExact ? <>
                <td className={cellClass}>{formatNumber(row.period_a_admissions)}</td><td className={cellClass}>{formatNumber(row.period_b_admissions)}</td><td className={cellClass}><TrendValue value={row.admission_change}>{formatNumber(row.admission_change)}</TrendValue></td>
              </> : null}
              {showPercentages ? <td className={cellClass}><TrendValue value={row.admission_change_percent}>{formatPercent(row.admission_change_percent)}</TrendValue></td> : null}
              <td className={cellClass}>{formatPercent(row.period_a_conversion)}</td><td className={cellClass}>{formatPercent(row.period_b_conversion)}</td><td className={cellClass}><TrendValue value={row.conversion_change_percentage_points}>{formatPp(row.conversion_change_percentage_points)}</TrendValue></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
