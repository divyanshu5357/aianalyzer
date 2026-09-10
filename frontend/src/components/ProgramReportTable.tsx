'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getProgramHierarchyChildren } from '@/lib/api/programs';
import dashboardCache from '@/lib/cache/dashboardCache';
import type {
  ProgramReportRow,
  ProgramHierarchyParams,
} from '@/lib/api/types';

// ── Sparkline Component ──────────────────────────────────────────────────────

function Sparkline({ data, color = '#6366f1' }: { data: number[]; color?: string }) {
  if (!data || data.length < 2) return <span className="text-gray-500 text-xs">—</span>;

  const max = Math.max(...data, 1);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 72;
  const h = 28;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`sg-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── Variance Badge ────────────────────────────────────────────────────────────

function VarBadge({ value, pct }: { value: number; pct: number }) {
  if (value === 0 && pct === 0) return <span className="text-gray-500 text-xs">—</span>;
  const isPos = value >= 0;
  const cls = isPos
    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
    : 'bg-red-500/15 text-red-400 border border-red-500/25';
  const sign = isPos ? '+' : '';
  return (
    <span className={`inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap ${cls}`}>
      {sign}{value.toLocaleString()} ({sign}{pct.toFixed(1)}%)
    </span>
  );
}

// ── Refund Cell ───────────────────────────────────────────────────────────────

function RefundCell({ py, cy, diff }: { py: number; cy: number; diff: number }) {
  const isPos = diff > 0;
  const sign = isPos ? '+' : '';
  const cls = isPos ? 'text-red-400' : diff < 0 ? 'text-emerald-400' : 'text-gray-500';
  return (
    <span className="text-xs whitespace-nowrap">
      <span className="text-gray-300">{py} → {cy}</span>{' '}
      <span className={cls}>({sign}{diff})</span>
    </span>
  );
}

// ── Row expand/collapse helpers ───────────────────────────────────────────────

type ExpandState = 'collapsed' | 'loading' | 'expanded';

interface RowNode {
  row: ProgramReportRow;
  state: ExpandState;
  children: ProgramReportRow[];
}

// ── Cache key builder ─────────────────────────────────────────────────────────

function buildScopeKey(filters: ScopeFilters) {
  return `${filters.academic_year}|${filters.campus || ''}|${filters.from_date || ''}|${filters.to_date || ''}|${filters.sort_by}|${filters.sort_order}`;
}

interface ScopeFilters {
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
  sort_by: string;
  sort_order: string;
}

// ── Main Component ────────────────────────────────────────────────────────────

interface ProgramReportTableProps {
  topRows: ProgramReportRow[];
  totalRow: ProgramReportRow;
  filters: ScopeFilters;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  onSortChange: (col: string, order: 'asc' | 'desc') => void;
  loading?: boolean;
  isDark?: boolean;
}

const INDENT = 22; // px per hierarchy level

export default function ProgramReportTable({
  topRows,
  totalRow,
  filters,
  sortBy,
  sortOrder,
  onSortChange,
  loading = false,
  isDark = true,
}: ProgramReportTableProps) {
  // Scope-aware child cache: Map<nodeId, ProgramReportRow[]>
  const childCache = useRef<Map<string, ProgramReportRow[]>>(new Map());
  const prevScopeKey = useRef<string>('');

  // Node state map: nodeId → RowNode
  const [nodes, setNodes] = useState<Map<string, RowNode>>(() => {
    const m = new Map<string, RowNode>();
    topRows.forEach((r) => m.set(r.id, { row: r, state: 'collapsed', children: [] }));
    return m;
  });

  // Re-init nodes when top rows or scope changes (filter invalidation)
  useEffect(() => {
    const currentKey = buildScopeKey(filters);
    if (currentKey !== prevScopeKey.current) {
      // Scope changed → invalidate child caches
      childCache.current.clear();
      prevScopeKey.current = currentKey;
    }
    const m = new Map<string, RowNode>();
    topRows.forEach((r) => m.set(r.id, { row: r, state: 'collapsed', children: [] }));
    setNodes(m);
  }, [topRows, filters]);

  // Build the flat list of visible rows (DFS order)
  const buildFlatRows = useCallback(
    (nodeMap: Map<string, RowNode>, topRows: ProgramReportRow[]): ProgramReportRow[] => {
      const result: ProgramReportRow[] = [];
      function visit(rows: ProgramReportRow[]) {
        rows.forEach((r) => {
          result.push(r);
          const node = nodeMap.get(r.id);
          if (node && node.state === 'expanded' && node.children.length > 0) {
            visit(node.children);
          }
        });
      }
      visit(topRows);
      return result;
    },
    []
  );

  const flatRows = buildFlatRows(nodes, topRows);

  // Resolve child level and params for lazy loading (5-level hierarchy)
  function getChildParams(row: ProgramReportRow): ProgramHierarchyParams | null {
    if (row.level === 1) {
      return {
        level: 'program',
        program_group: row.program_group || row.program,
        academic_year: filters.academic_year,
        campus: filters.campus,
        from_date: filters.from_date,
        to_date: filters.to_date,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
      };
    }
    if (row.level === 2) {
      const pCode = row.program_code || row.program;
      return {
        level: 'lead_type',
        program_code: pCode,
        program: pCode,
        program_group: row.program_group,
        academic_year: filters.academic_year,
        campus: filters.campus,
        from_date: filters.from_date,
        to_date: filters.to_date,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
      };
    }
    if (row.level === 3) {
      const pCode = row.program_code || row.program;
      const lt = row.lead_type || row.source_category || row.program;
      return {
        level: 'main_source',
        program_code: pCode,
        program: pCode,
        lead_type: lt,
        source_category: lt,
        program_group: row.program_group,
        academic_year: filters.academic_year,
        campus: filters.campus,
        from_date: filters.from_date,
        to_date: filters.to_date,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
      };
    }
    if (row.level === 4) {
      const pCode = row.program_code || row.program;
      const lt = row.lead_type || row.source_category;
      const ms = row.main_source || row.sub_source || row.program;
      return {
        level: 'report_source',
        program_code: pCode,
        program: pCode,
        lead_type: lt,
        source_category: lt,
        main_source: ms,
        sub_source: ms,
        program_group: row.program_group,
        academic_year: filters.academic_year,
        campus: filters.campus,
        from_date: filters.from_date,
        to_date: filters.to_date,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
      };
    }
    return null;
  }

  async function handleToggle(row: ProgramReportRow) {
    if (!row.has_children) return;
    const nodeId = row.id;
    const currentNode = nodes.get(nodeId);

    if (currentNode?.state === 'expanded') {
      // Collapse
      setNodes((prev) => {
        const next = new Map(prev);
        const n = next.get(nodeId);
        if (n) next.set(nodeId, { ...n, state: 'collapsed' });
        return next;
      });
      return;
    }

    // Check cache first (both local ref and persistent shared cache)
    const cacheKey = `${buildScopeKey(filters)}|${nodeId}`;
    const cached = childCache.current.get(cacheKey) || dashboardCache.getTreeChildren<ProgramReportRow>(cacheKey);
    if (cached) {
      childCache.current.set(cacheKey, cached);
      setNodes((prev) => {
        const next = new Map(prev);
        const n = next.get(nodeId);
        if (n) next.set(nodeId, { ...n, state: 'expanded', children: cached });
        cached.forEach((c) => {
          if (!next.has(c.id)) next.set(c.id, { row: c, state: 'collapsed', children: [] });
        });
        return next;
      });
      return;
    }

    // Set loading
    setNodes((prev) => {
      const next = new Map(prev);
      const n = next.get(nodeId);
      if (n) next.set(nodeId, { ...n, state: 'loading' });
      return next;
    });

    const params = getChildParams(row);
    if (!params) return;

    try {
      const resp = await getProgramHierarchyChildren(params);
      const children = resp.rows;
      childCache.current.set(cacheKey, children);
      dashboardCache.setTreeChildren(cacheKey, children);
      setNodes((prev) => {
        const next = new Map(prev);
        const n = next.get(nodeId);
        if (n) next.set(nodeId, { ...n, state: 'expanded', children });
        children.forEach((c) => {
          if (!next.has(c.id)) next.set(c.id, { row: c, state: 'collapsed', children: [] });
        });
        return next;
      });
    } catch (err) {
      console.error('Failed to load children for', nodeId, err);
      setNodes((prev) => {
        const next = new Map(prev);
        const n = next.get(nodeId);
        if (n) next.set(nodeId, { ...n, state: 'collapsed' });
        return next;
      });
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const sparklineColor = (level: number) => {
    const colors = ['#818cf8', '#818cf8', '#38bdf8', '#34d399', '#f59e0b'];
    return colors[(level - 1) % colors.length];
  };

  // Row background per level (theme-aware)
  const levelBg = (level: number) => {
    if (isDark) {
      const bgs = ['', 'bg-[#1a1d2e]/60', 'bg-[#15172b]/40', 'bg-[#111320]/30', 'bg-[#0e101d]/40'];
      return bgs[level - 1] || '';
    } else {
      const bgs = ['', 'bg-slate-50', 'bg-slate-100/60', 'bg-slate-100/40', 'bg-slate-100/20'];
      return bgs[level - 1] || '';
    }
  };

  const getLevelTextColor = (level: number) => {
    if (level === 1) return isDark ? '#e2e8f0' : '#1e293b';
    if (level === 2) return isDark ? '#c4b5fd' : '#6366f1';
    if (level === 3) return isDark ? '#38bdf8' : '#0284c7';
    if (level === 4) return isDark ? '#34d399' : '#059669';
    return isDark ? '#fbbf24' : '#d97706';
  };

  // Frozen col background (solid, no opacity)
  const frozenBg = isDark ? '#0f1117' : '#ffffff';
  const frozenBgTotal = isDark ? '#0d1030' : '#eef2ff';

  function renderRow(row: ProgramReportRow) {
    const indent = (row.level - 1) * INDENT;
    const node = nodes.get(row.id);
    const isExpanded = node?.state === 'expanded';
    const isLoading = node?.state === 'loading';
    const expandable = row.has_children;

    const refund = row.refund_py_vs_cy;
    const refundPct = row.refund_pct_py_vs_cy;

    const rowHoverCls = isDark ? 'hover:bg-white/[0.03]' : 'hover:bg-slate-50';
    const borderCls = isDark ? 'border-white/5' : 'border-slate-100';

    return (
      <tr
        key={row.id}
        className={`border-b transition-colors duration-100 ${rowHoverCls} ${borderCls} ${levelBg(row.level)}`}
      >
        {/* Col 1: Program (frozen) */}
        <td
          className={`sticky left-0 z-10 border-b border-r ${isDark ? 'border-white/5 border-white/10' : 'border-slate-100 border-slate-200'}`}
          style={{ minWidth: 260, maxWidth: 320, background: frozenBg }}
        >
          <div
            className="flex items-center gap-1.5 pr-2"
            style={{ paddingLeft: `${indent + 12}px`, paddingTop: 7, paddingBottom: 7 }}
          >
            {expandable ? (
              <button
                onClick={() => handleToggle(row)}
                className="flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:text-indigo-400 hover:bg-indigo-500/10 transition-all"
              >
                {isLoading ? (
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                ) : isExpanded ? (
                  <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd"/>
                  </svg>
                ) : (
                  <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.17 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd"/>
                  </svg>
                )}
              </button>
            ) : (
              <span className="w-5 h-5 flex-shrink-0" />
            )}
            <span
              className="text-xs font-medium truncate"
              style={{ color: getLevelTextColor(row.level) }}
              title={row.program}
            >
              {row.program}
            </span>
          </div>
        </td>

        {/* Col 2-4: PY/CY Leads + Var */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-400'}`}>{row.py_leads.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right tabular-nums font-medium ${isDark ? 'text-gray-100' : 'text-slate-800'}`}>{row.cy_leads.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_leads} pct={row.var_leads_pct} /></td>

        {/* Col 5-7: PY/CY CUCET + Var */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-400'}`}>{row.py_cucet.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-100' : 'text-slate-800'}`}>{row.cy_cucet.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_cucet} pct={row.var_cucet_pct} /></td>

        {/* Col 8: Lead-CUCET % */}
        <td className="px-3 py-2 text-xs text-right text-amber-400 tabular-nums">{row.lead_cucet_pct.toFixed(1)}%</td>

        {/* Col 9-11: PY/CY Adm + Var */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-400'}`}>{row.py_adm.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right text-emerald-400 tabular-nums font-medium">{row.cy_adm.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_adm} pct={row.var_adm_pct} /></td>

        {/* Col 12: Lead-Adm % */}
        <td className="px-3 py-2 text-xs text-right text-sky-400 tabular-nums">{row.lead_adm_pct.toFixed(1)}%</td>

        {/* Col 13: Cucet-Adm % */}
        <td className="px-3 py-2 text-xs text-right text-violet-400 tabular-nums">{row.cucet_adm_pct.toFixed(1)}%</td>

        {/* Col 14: Lead Trend sparkline */}
        <td className="px-3 py-2">
          <Sparkline data={row.lead_trend} color={sparklineColor(row.level)} />
        </td>

        {/* Col 15: Net Admissions */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums font-medium ${isDark ? 'text-gray-200' : 'text-slate-700'}`}>{row.net_admissions.toLocaleString()}</td>

        {/* Col 16: Refund Py vs Cy */}
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refund ? <RefundCell py={refund.py} cy={refund.cy} diff={refund.diff} /> : '—'}
        </td>

        {/* Col 17: Refund % Py vs Cy */}
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refundPct ? (
            <span className="text-xs">
              <span className="text-gray-400">{refundPct.py_pct.toFixed(0)}% → {refundPct.cy_pct.toFixed(0)}%</span>{' '}
              <span className={refundPct.diff_pct <= 0 ? 'text-emerald-400' : 'text-red-400'}>
                ({refundPct.diff_pct >= 0 ? '+' : ''}{refundPct.diff_pct.toFixed(0)}%)
              </span>
            </span>
          ) : '—'}
        </td>

        {/* Col 18-19: Fee Paid / Net-Fee % (N/A) */}
        <td className={`px-3 py-2 text-xs text-right ${isDark ? 'text-gray-600' : 'text-slate-400'}`} title="Fee payment data not present in uploaded CRM dataset">N/A</td>
        <td className={`px-3 py-2 text-xs text-right ${isDark ? 'text-gray-600' : 'text-slate-400'}`} title="Fee payment data not present in uploaded CRM dataset">N/A</td>
      </tr>
    );
  }

  function renderTotalRow(row: ProgramReportRow) {
    const refund = row.refund_py_vs_cy;
    const refundPct = row.refund_pct_py_vs_cy;
    const totalBorderTop = isDark ? 'border-indigo-500/40' : 'border-indigo-400';
    return (
      <tr
        key="__total__"
        style={{ position: 'sticky', bottom: 0, zIndex: 20, background: frozenBgTotal }}
        className={`border-t-2 ${totalBorderTop}`}
      >
        <td className={`sticky left-0 z-10 border-r pl-4 pr-2 py-2.5 ${isDark ? 'border-white/10' : 'border-indigo-200'}`}
            style={{ background: frozenBgTotal }}>
          <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>⬛ Total</span>
        </td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{row.py_leads.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right font-bold tabular-nums ${isDark ? 'text-white' : 'text-slate-900'}`}>{row.cy_leads.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_leads} pct={row.var_leads_pct} /></td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{row.py_cucet.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-white' : 'text-slate-900'}`}>{row.cy_cucet.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_cucet} pct={row.var_cucet_pct} /></td>
        <td className="px-3 py-2 text-xs text-right text-amber-300 font-semibold tabular-nums">{row.lead_cucet_pct.toFixed(1)}%</td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{row.py_adm.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right text-emerald-300 font-bold tabular-nums">{row.cy_adm.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_adm} pct={row.var_adm_pct} /></td>
        <td className="px-3 py-2 text-xs text-right text-sky-300 font-semibold tabular-nums">{row.lead_adm_pct.toFixed(1)}%</td>
        <td className="px-3 py-2 text-xs text-right text-violet-300 font-semibold tabular-nums">{row.cucet_adm_pct.toFixed(1)}%</td>
        <td className="px-3 py-2">
          <Sparkline data={row.lead_trend} color="#818cf8" />
        </td>
        <td className={`px-3 py-2 text-xs text-right font-bold tabular-nums ${isDark ? 'text-white' : 'text-slate-900'}`}>{row.net_admissions.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refund ? <RefundCell py={refund.py} cy={refund.cy} diff={refund.diff} /> : '—'}
        </td>
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refundPct ? (
            <span className="text-xs">
              <span className="text-gray-400">{refundPct.py_pct.toFixed(0)}% → {refundPct.cy_pct.toFixed(0)}%</span>{' '}
              <span className={refundPct.diff_pct <= 0 ? 'text-emerald-400' : 'text-red-400'}>
                ({refundPct.diff_pct >= 0 ? '+' : ''}{refundPct.diff_pct.toFixed(0)}%)
              </span>
            </span>
          ) : '—'}
        </td>
        <td className={`px-3 py-2 text-xs text-right ${isDark ? 'text-gray-600' : 'text-slate-400'}`}>N/A</td>
        <td className={`px-3 py-2 text-xs text-right ${isDark ? 'text-gray-600' : 'text-slate-400'}`}>N/A</td>
      </tr>
    );
  }

  // Sortable column definitions
  // sortKey: the backend sort param name, undefined = not sortable
  const headers: { label: string; sortKey?: string; frozen?: boolean }[] = [
    { label: 'Program', frozen: true, sortKey: 'program' },
    { label: 'PY Leads' },
    { label: 'CY Leads', sortKey: 'cy_leads' },
    { label: 'VAR (Leads)', sortKey: 'var_leads' },
    { label: 'PY CUCET' },
    { label: 'CY CUCET', sortKey: 'cy_cucet' },
    { label: 'VAR (CUCET)', sortKey: 'var_cucet' },
    { label: 'Lead–CUCET %', sortKey: 'lead_cucet_pct' },
    { label: 'PY Adm' },
    { label: 'CY Adm', sortKey: 'cy_adm' },
    { label: 'VAR (Adm)', sortKey: 'var_adm' },
    { label: 'Lead–Adm %', sortKey: 'lead_adm_pct' },
    { label: 'CUCET–Adm %', sortKey: 'cucet_adm_pct' },
    { label: 'Lead Trend' },
    { label: 'Net Adm.', sortKey: 'net_admissions' },
    { label: 'Refund PY→CY' },
    { label: 'Refund % PY→CY' },
    { label: 'Fee Paid' },
    { label: 'Net–Fee %' },
  ];

  function handleHeaderClick(sortKey?: string) {
    if (!sortKey) return;
    if (sortBy === sortKey) {
      // Toggle direction
      onSortChange(sortKey, sortOrder === 'desc' ? 'asc' : 'desc');
    } else {
      // New column: start desc
      onSortChange(sortKey, 'desc');
    }
  }

  function SortArrow({ col }: { col?: string }) {
    if (!col) return null;
    const isActive = sortBy === col;
    if (isActive) {
      return (
        <span className="ml-1 text-indigo-400">
          {sortOrder === 'desc' ? '↓' : '↑'}
        </span>
      );
    }
    return <span className="ml-1 text-gray-600 group-hover:text-gray-400">↕</span>;
  }

  if (loading) {
    return (
      <div
        className={`relative overflow-auto rounded-xl border ${isDark ? 'border-white/10 bg-[#0d0f1a]/40' : 'border-slate-200 bg-white'}`}
        style={{ maxHeight: 'calc(100vh - 190px)' }}
      >
        <div className="p-4 space-y-3 animate-pulse">
          <div className="flex gap-4 border-b pb-3 border-white/5">
            <div className={`h-4 w-48 rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} />
            <div className={`h-4 w-24 rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} />
            <div className={`h-4 w-24 rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} />
            <div className={`h-4 w-24 rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} />
          </div>
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex gap-4 py-2.5 border-b border-white/5">
              <div className={`h-3.5 rounded ${isDark ? 'bg-white/5' : 'bg-slate-100'}`} style={{ width: `${140 + (i % 4) * 35}px` }} />
              <div className={`h-3.5 w-16 rounded ml-auto ${isDark ? 'bg-white/5' : 'bg-slate-100'}`} />
              <div className={`h-3.5 w-16 rounded ${isDark ? 'bg-white/5' : 'bg-slate-100'}`} />
              <div className={`h-3.5 w-20 rounded ${isDark ? 'bg-white/5' : 'bg-slate-100'}`} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className="relative overflow-auto rounded-xl border border-white/10"
      style={{ maxHeight: 'calc(100vh - 190px)', scrollbarWidth: 'thin' }}
    >
      <table className="w-full border-collapse text-xs" style={{ minWidth: 1600 }}>
        <thead className="sticky top-0 z-30">
          <tr className={`border-b ${isDark ? 'bg-[#0d0f1a] border-white/10' : 'bg-white border-slate-200'}`}>
            {headers.map((h, i) => (
              <th
                key={i}
                onClick={() => handleHeaderClick(h.sortKey)}
                className={[
                  'px-3 py-3 text-left font-semibold uppercase tracking-wider text-[10px] whitespace-nowrap border-b select-none',
                  isDark ? 'border-white/10' : 'border-slate-200',
                  h.sortKey ? 'cursor-pointer group' : 'cursor-default',
                  sortBy === h.sortKey
                    ? (isDark ? 'text-indigo-300' : 'text-indigo-600')
                    : (isDark ? 'text-gray-400' : 'text-slate-500'),
                  h.frozen
                    ? `sticky left-0 z-20 border-r ${isDark ? 'bg-[#0d0f1a] border-r-white/10' : 'bg-white border-r-slate-200'}`
                    : '',
                ].join(' ')}
                style={h.frozen ? { minWidth: 260 } : {}}
              >
                {h.label}<SortArrow col={h.sortKey} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {flatRows.map((row) => renderRow(row))}
          {totalRow && renderTotalRow(totalRow)}
        </tbody>
      </table>
    </div>
  );
}
