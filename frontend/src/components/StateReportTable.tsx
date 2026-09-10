'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getStateHierarchyChildren } from '@/lib/api/states';
import dashboardCache from '@/lib/cache/dashboardCache';
import type {
  StateReportRow,
  StateHierarchyParams,
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

// ── Status Indicator Dot ──────────────────────────────────────────────────────

function StatusDot({ status }: { status?: 'positive' | 'negative' | 'neutral' }) {
  if (status === 'positive') {
    return (
      <span className="relative flex h-2.5 w-2.5 shrink-0" title="Performance increased vs PY">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-xs shadow-emerald-500/50"></span>
      </span>
    );
  }
  if (status === 'negative') {
    return (
      <span className="relative flex h-2.5 w-2.5 shrink-0" title="Performance decreased vs PY">
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500 shadow-xs shadow-rose-500/50"></span>
      </span>
    );
  }
  return (
    <span className="relative inline-flex rounded-full h-2 w-2 bg-slate-400 shrink-0 opacity-60" title="No change / Baseline" />
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
  if (py === 0 && cy === 0 && diff === 0) {
    return <span className="text-gray-500 text-xs">—</span>;
  }
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
  row: StateReportRow;
  state: ExpandState;
  children: StateReportRow[];
}

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

interface StateReportTableProps {
  topRows: StateReportRow[];
  totalRow: StateReportRow;
  filters: ScopeFilters;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  onSortChange: (col: string, order: 'asc' | 'desc') => void;
  loading?: boolean;
  isDark?: boolean;
}

const INDENT = 20; // px per hierarchy level

export default function StateReportTable({
  topRows,
  totalRow,
  filters,
  sortBy,
  sortOrder,
  onSortChange,
  loading = false,
  isDark = true,
}: StateReportTableProps) {
  // Scope-aware child cache: Map<nodeId, StateReportRow[]>
  const childCache = useRef<Map<string, StateReportRow[]>>(new Map());
  const prevScopeKey = useRef<string>('');

  // Node state map: nodeId → RowNode
  const [nodes, setNodes] = useState<Map<string, RowNode>>(() => {
    const m = new Map<string, RowNode>();
    topRows.forEach((r) => m.set(r.id, { row: r, state: 'collapsed', children: [] }));
    return m;
  });

  // Invalidate and reset child caches when filters or scope changes
  useEffect(() => {
    const currentKey = buildScopeKey(filters);
    if (currentKey !== prevScopeKey.current) {
      childCache.current.clear();
      prevScopeKey.current = currentKey;
    }
    const m = new Map<string, RowNode>();
    topRows.forEach((r) => m.set(r.id, { row: r, state: 'collapsed', children: [] }));
    setNodes(m);
  }, [topRows, filters]);

  // Build the flat list of visible rows in DFS order
  const buildFlatRows = useCallback(
    (nodeMap: Map<string, RowNode>, topList: StateReportRow[]): StateReportRow[] => {
      const result: StateReportRow[] = [];
      function visit(rows: StateReportRow[]) {
        rows.forEach((r) => {
          result.push(r);
          const node = nodeMap.get(r.id);
          if (node && node.state === 'expanded' && node.children.length > 0) {
            visit(node.children);
          }
        });
      }
      visit(topList);
      return result;
    },
    []
  );

  const flatRows = buildFlatRows(nodes, topRows);

  // Resolve hierarchy parameters for lazy loading
  function getChildParams(row: StateReportRow): StateHierarchyParams | null {
    if (row.level === 1) {
      // Expanding State -> fetch Source Categories
      return {
        level: 'source_category',
        state: row.state_key || row.name,
        academic_year: filters.academic_year,
        campus: filters.campus,
        from_date: filters.from_date,
        to_date: filters.to_date,
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
      };
    }
    if (row.level === 2) {
      // Expanding Source Category -> fetch Sub-Sources
      return {
        level: 'sub_source',
        state: row.state_key || (row as any).state || '',
        source_category: row.source_category || row.name,
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

  // Handle row expansion / collapsing
  async function handleToggle(row: StateReportRow) {
    if (!row.has_children) return;

    const current = nodes.get(row.id);
    const currentState = current ? current.state : 'collapsed';

    if (currentState === 'expanded') {
      setNodes((prev) => {
        const next = new Map(prev);
        const existing = next.get(row.id);
        if (existing) {
          next.set(row.id, { ...existing, state: 'collapsed' });
        }
        return next;
      });
      return;
    }

    // Check memory cache first (both local ref and shared cache)
    const cacheKey = `${buildScopeKey(filters)}|${row.id}`;
    const cached = childCache.current.get(row.id) || dashboardCache.getTreeChildren<StateReportRow>(cacheKey);
    if (cached) {
      childCache.current.set(row.id, cached);
      setNodes((prev) => {
        const next = new Map(prev);
        const existing = next.get(row.id) || { row, state: 'collapsed', children: [] };
        cached.forEach((child) => {
          if (!next.has(child.id)) {
            next.set(child.id, { row: child, state: 'collapsed', children: [] });
          }
        });
        next.set(row.id, { ...existing, state: 'expanded', children: cached });
        return next;
      });
      return;
    }

    const params = getChildParams(row);
    if (!params) return;

    setNodes((prev) => {
      const next = new Map(prev);
      const existing = next.get(row.id) || { row, state: 'collapsed', children: [] };
      next.set(row.id, { ...existing, state: 'loading' });
      return next;
    });

    try {
      const res = await getStateHierarchyChildren(params);
      const children = res.rows;
      childCache.current.set(row.id, children);
      dashboardCache.setTreeChildren(cacheKey, children);

      setNodes((prev) => {
        const next = new Map(prev);
        children.forEach((child) => {
          if (!next.has(child.id)) {
            next.set(child.id, { row: child, state: 'collapsed', children: [] });
          }
        });
        next.set(row.id, { row, state: 'expanded', children });
        return next;
      });
    } catch {
      setNodes((prev) => {
        const next = new Map(prev);
        const existing = next.get(row.id) || { row, state: 'collapsed', children: [] };
        next.set(row.id, { ...existing, state: 'collapsed' });
        return next;
      });
    }
  }

  // Column sort click handler
  function handleHeaderClick(col: string) {
    if (sortBy === col) {
      onSortChange(col, sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      const defaultOrder = col === 'state' || col === 'name' ? 'asc' : 'desc';
      onSortChange(col, defaultOrder);
    }
  }

  function renderSortIndicator(col: string) {
    const isActive = sortBy === col;
    if (!isActive) {
      return (
        <span className={`text-[10px] ml-1 select-none opacity-30 ${isDark ? 'text-gray-400' : 'text-slate-400'}`}>
          ↑↓
        </span>
      );
    }
    return (
      <span className="text-[10px] ml-1 select-none font-bold text-indigo-400">
        {sortOrder === 'asc' ? '↑' : '↓'}
      </span>
    );
  }

  // Row styling by hierarchy level
  function getLevelBadge(row: StateReportRow) {
    if (row.level === 1) {
      return (
        <div className="flex items-center gap-1.5 shrink-0">
          <StatusDot status={row.status_indicator} />
          {row.state_code && (
            <span className={`text-[9px] px-1 py-0.2 rounded font-mono font-bold ${
              isDark ? 'bg-indigo-500/20 text-indigo-300' : 'bg-indigo-50 text-indigo-600'
            }`}>
              {row.state_code}
            </span>
          )}
        </div>
      );
    }
    if (row.level === 2) {
      return (
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
      );
    }
    return (
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
    );
  }

  function getRowBg(row: StateReportRow) {
    if (row.level === 1) return isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-slate-100/70';
    if (row.level === 2) return isDark ? 'bg-white/[0.015] hover:bg-white/[0.05]' : 'bg-slate-50/50 hover:bg-slate-100/60';
    return isDark ? 'bg-white/[0.025] hover:bg-white/[0.06]' : 'bg-slate-100/30 hover:bg-slate-100/70';
  }

  function getTextColor(row: StateReportRow) {
    if (row.level === 1) return isDark ? 'text-white font-bold' : 'text-slate-900 font-bold';
    if (row.level === 2) return isDark ? 'text-emerald-300 font-medium' : 'text-emerald-700 font-medium';
    return isDark ? 'text-amber-200/90 font-normal' : 'text-amber-800 font-normal';
  }

  const thBase = `px-3 py-2.5 text-[11px] font-semibold tracking-wider uppercase whitespace-nowrap cursor-pointer select-none transition-colors border-b ${
    isDark
      ? 'text-gray-400 hover:text-white border-white/10'
      : 'text-slate-500 hover:text-slate-900 border-slate-200'
  }`;
  const tdBase = 'px-3 py-2 text-xs whitespace-nowrap border-b border-transparent';

  return (
    <div className={`flex flex-col h-full rounded-xl border overflow-hidden shadow-sm transition-colors ${
      isDark ? 'bg-[#0f1117] border-white/10' : 'bg-white border-slate-200'
    }`}>
      {/* Scrollable table container */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left border-collapse text-xs">
          {/* Sticky Header */}
          <thead className={`sticky top-0 z-20 ${isDark ? 'bg-[#0d0f1a]' : 'bg-white'}`}>
            <tr>
              {/* Frozen Column: State Name */}
              <th
                onClick={() => handleHeaderClick('state')}
                className={`sticky left-0 z-30 min-w-[240px] ${thBase} ${isDark ? 'bg-[#0d0f1a]' : 'bg-white'}`}
              >
                <div className="flex items-center gap-1">
                  <span>STATE GROUP</span>
                  {renderSortIndicator('state')}
                </div>
              </th>

              <th onClick={() => handleHeaderClick('py_leads')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">PY LEADS {renderSortIndicator('py_leads')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cy_leads')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">CY LEADS {renderSortIndicator('cy_leads')}</div>
              </th>
              <th onClick={() => handleHeaderClick('var_leads')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">VAR (LEADS) {renderSortIndicator('var_leads')}</div>
              </th>
              <th onClick={() => handleHeaderClick('py_cucet')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">PY CUCET {renderSortIndicator('py_cucet')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cy_cucet')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">CY CUCET {renderSortIndicator('cy_cucet')}</div>
              </th>
              <th onClick={() => handleHeaderClick('var_cucet')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">VAR (CUCET) {renderSortIndicator('var_cucet')}</div>
              </th>
              <th onClick={() => handleHeaderClick('lead_cucet_pct')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">LEAD-CUCET % {renderSortIndicator('lead_cucet_pct')}</div>
              </th>
              <th onClick={() => handleHeaderClick('py_adm')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">PY ADM {renderSortIndicator('py_adm')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cy_adm')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">CY ADM {renderSortIndicator('cy_adm')}</div>
              </th>
              <th onClick={() => handleHeaderClick('var_adm')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">VAR (ADM) {renderSortIndicator('var_adm')}</div>
              </th>
              <th onClick={() => handleHeaderClick('lead_adm_pct')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">LEAD-ADM % {renderSortIndicator('lead_adm_pct')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cucet_adm_pct')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">CUCET-ADM % {renderSortIndicator('cucet_adm_pct')}</div>
              </th>
              <th className={`${thBase} text-center`}>LEAD TREND</th>
              <th onClick={() => handleHeaderClick('net_admissions')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">NET ADMISSIONS {renderSortIndicator('net_admissions')}</div>
              </th>
              <th className={`${thBase} text-right`}>REFUND PY VS CY</th>
              <th className={`${thBase} text-right`}>REFUND % PY VS CY</th>
              <th className={`${thBase} text-center`}>FEE PAID</th>
              <th className={`${thBase} text-center`}>NET - FEE PAID %</th>
            </tr>
          </thead>

          {/* Table Body */}
          <tbody className={`divide-y ${isDark ? 'divide-white/5' : 'divide-slate-100'}`}>
            {loading ? (
              Array.from({ length: 8 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="px-3 py-3">
                    <div className={`h-3.5 rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} style={{ width: `${90 + (idx % 4) * 25}px` }} />
                  </td>
                  {Array.from({ length: 18 }).map((_, cIdx) => (
                    <td key={cIdx} className="px-3 py-3 text-right">
                      <div className={`h-3 w-12 rounded ml-auto ${isDark ? 'bg-white/5' : 'bg-slate-100'}`} />
                    </td>
                  ))}
                </tr>
              ))
            ) : flatRows.length === 0 ? (
              <tr>
                <td colSpan={19} className="py-16 text-center">
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>
                    No state records found for the selected scope.
                  </p>
                </td>
              </tr>
            ) : (
              flatRows.map((row) => {
                const nodeState = nodes.get(row.id)?.state || 'collapsed';
                const isExpanded = nodeState === 'expanded';
                const isLoading = nodeState === 'loading';
                const indentPx = (row.level - 1) * INDENT;

                return (
                  <tr
                    key={row.id}
                    className={`transition-colors border-b ${
                      isDark ? 'border-white/[0.04]' : 'border-slate-100'
                    } ${getRowBg(row)}`}
                  >
                    {/* Frozen State Column */}
                    <td
                      style={{ paddingLeft: `${indentPx + 12}px` }}
                      className={`sticky left-0 z-10 ${tdBase} ${
                        isDark ? 'bg-[#0f1117]' : 'bg-white'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {/* Expand / Collapse Button */}
                        {row.has_children ? (
                          <button
                            onClick={() => handleToggle(row)}
                            disabled={isLoading}
                            className={`w-4 h-4 flex items-center justify-center rounded text-[10px] transition-colors ${
                              isDark ? 'text-gray-400 hover:text-white' : 'text-slate-400 hover:text-slate-900'
                            }`}
                            title={isExpanded ? 'Collapse' : 'Expand'}
                          >
                            {isLoading ? (
                              <span className="inline-block w-2.5 h-2.5 rounded-full border border-indigo-400 border-t-transparent animate-spin" />
                            ) : isExpanded ? (
                              '▾'
                            ) : (
                              '▸'
                            )}
                          </button>
                        ) : (
                          <span className="w-4" />
                        )}

                        {getLevelBadge(row)}

                        <span
                          className={`truncate max-w-[210px] text-xs ${getTextColor(row)}`}
                          title={row.name}
                        >
                          {row.name}
                        </span>
                      </div>
                    </td>

                    {/* Numeric Columns */}
                    <td className={`${tdBase} text-right font-mono ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>
                      {row.py_leads > 0 ? row.py_leads.toLocaleString() : '—'}
                    </td>
                    <td className={`${tdBase} text-right font-mono font-bold ${isDark ? 'text-gray-100' : 'text-slate-800'}`}>
                      {row.cy_leads.toLocaleString()}
                    </td>
                    <td className={`${tdBase} text-right`}>
                      <VarBadge value={row.var_leads} pct={row.var_leads_pct} />
                    </td>
                    <td className={`${tdBase} text-right font-mono ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>
                      {row.py_cucet > 0 ? row.py_cucet.toLocaleString() : '—'}
                    </td>
                    <td className={`${tdBase} text-right font-mono ${isDark ? 'text-gray-200' : 'text-slate-700'}`}>
                      {row.cy_cucet.toLocaleString()}
                    </td>
                    <td className={`${tdBase} text-right`}>
                      <VarBadge value={row.var_cucet} pct={row.var_cucet_pct} />
                    </td>
                    <td className={`${tdBase} text-right font-semibold ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                      {row.lead_cucet_pct.toFixed(1)}%
                    </td>
                    <td className={`${tdBase} text-right font-mono ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>
                      {row.py_adm > 0 ? row.py_adm.toLocaleString() : '—'}
                    </td>
                    <td className={`${tdBase} text-right font-mono font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                      {row.cy_adm.toLocaleString()}
                    </td>
                    <td className={`${tdBase} text-right`}>
                      <VarBadge value={row.var_adm} pct={row.var_adm_pct} />
                    </td>
                    <td className={`${tdBase} text-right font-semibold ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}>
                      {row.lead_adm_pct.toFixed(1)}%
                    </td>
                    <td className={`${tdBase} text-right font-semibold ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
                      {row.cucet_adm_pct.toFixed(1)}%
                    </td>
                    <td className={`${tdBase} text-center`}>
                      <Sparkline
                        data={row.lead_trend}
                        color={row.level === 1 ? '#6366f1' : row.level === 2 ? '#10b981' : '#f59e0b'}
                      />
                    </td>
                    <td className={`${tdBase} text-right font-mono font-bold ${isDark ? 'text-sky-400' : 'text-sky-600'}`}>
                      {row.net_admissions.toLocaleString()}
                    </td>
                    <td className={`${tdBase} text-right font-mono`}>
                      <RefundCell
                        py={row.refund_py_vs_cy.py}
                        cy={row.refund_py_vs_cy.cy}
                        diff={row.refund_py_vs_cy.diff}
                      />
                    </td>
                    <td className={`${tdBase} text-right text-[11px] ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>
                      {row.refund_pct_py_vs_cy.cy_pct.toFixed(1)}%
                    </td>
                    <td className={`${tdBase} text-center ${isDark ? 'text-gray-500' : 'text-slate-400'}`}>
                      {row.fee_paid}
                    </td>
                    <td className={`${tdBase} text-center ${isDark ? 'text-gray-500' : 'text-slate-400'}`}>
                      {row.net_fee_paid_pct}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>

          {/* Sticky Total Row */}
          {totalRow && (
            <tfoot className={`sticky bottom-0 z-20 font-bold border-t-2 ${
              isDark
                ? 'bg-[#0d1030] border-indigo-500/40 text-white'
                : 'bg-[#eef2ff] border-indigo-200 text-slate-900'
            }`}>
              <tr>
                {/* Frozen Total label */}
                <td className={`sticky left-0 z-30 px-3 py-3 text-xs uppercase tracking-wider ${
                  isDark ? 'bg-[#0d1030] text-indigo-300' : 'bg-[#eef2ff] text-indigo-700'
                }`}>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 shrink-0 shadow-xs shadow-indigo-500/50" />
                    <span>TOTAL ({topRows.length} STATE GROUPS)</span>
                  </div>
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs opacity-75">
                  {totalRow.py_leads.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs font-extrabold">
                  {totalRow.cy_leads.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right">
                  <VarBadge value={totalRow.var_leads} pct={totalRow.var_leads_pct} />
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs opacity-75">
                  {totalRow.py_cucet.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs">
                  {totalRow.cy_cucet.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right">
                  <VarBadge value={totalRow.var_cucet} pct={totalRow.var_cucet_pct} />
                </td>
                <td className="px-3 py-3 text-right text-xs text-amber-400 font-bold">
                  {totalRow.lead_cucet_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs opacity-75">
                  {totalRow.py_adm.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs text-emerald-400 font-bold">
                  {totalRow.cy_adm.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right">
                  <VarBadge value={totalRow.var_adm} pct={totalRow.var_adm_pct} />
                </td>
                <td className="px-3 py-3 text-right text-xs text-indigo-400 font-bold">
                  {totalRow.lead_adm_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-right text-xs text-purple-400 font-bold">
                  {totalRow.cucet_adm_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-center">
                  <Sparkline data={totalRow.lead_trend} color="#818cf8" />
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs text-sky-400 font-bold">
                  {totalRow.net_admissions.toLocaleString()}
                </td>
                <td className="px-3 py-3 text-right font-mono text-xs">
                  <RefundCell
                    py={totalRow.refund_py_vs_cy.py}
                    cy={totalRow.refund_py_vs_cy.cy}
                    diff={totalRow.refund_py_vs_cy.diff}
                  />
                </td>
                <td className="px-3 py-3 text-right text-xs opacity-75">
                  {totalRow.refund_pct_py_vs_cy.cy_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-center text-xs opacity-60">N/A</td>
                <td className="px-3 py-3 text-center text-xs opacity-60">N/A</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
