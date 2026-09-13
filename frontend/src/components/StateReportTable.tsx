'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getStateHierarchyChildren } from '@/lib/api/states';
import { useAppContext } from '@/context/AppContext';
import dashboardCache from '@/lib/cache/dashboardCache';
import type {
  StateReportRow,
  StateHierarchyParams,
  PeriodSummary,
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
      <span className="relative flex h-2.5 w-2.5 shrink-0" title="Performance increased YoY">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-xs shadow-emerald-500/50"></span>
      </span>
    );
  }
  if (status === 'negative') {
    return (
      <span className="relative flex h-2.5 w-2.5 shrink-0" title="Performance decreased YoY">
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

// ── Rate Transition Badge ─────────────────────────────────────────────────────

function RateTransitionBadge({
  py,
  cy,
  isDark = true,
}: {
  py: number;
  cy: number;
  isDark?: boolean;
}) {
  const diff = cy - py;
  const isNeg = diff < -0.05;
  const isPos = diff > 0.05;
  const sign = diff >= 0 ? '+' : '';

  if (isNeg) {
    return (
      <span
        className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-semibold tabular-nums ${
          isDark
            ? 'bg-rose-950/70 text-rose-300 border border-rose-800/40'
            : 'bg-[#ffdcd0] text-[#991b1b] border border-[#fca5a5]'
        }`}
      >
        {py.toFixed(1)}% → {cy.toFixed(1)}% ({sign}{diff.toFixed(1)}%)
      </span>
    );
  }

  return (
    <span className="text-[11px] tabular-nums whitespace-nowrap">
      <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>{py.toFixed(1)}%</span>
      <span className="mx-1 text-slate-400">→</span>
      <span className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-800'}`}>{cy.toFixed(1)}%</span>{' '}
      <span className={isPos ? (isDark ? 'text-emerald-400 font-semibold' : 'text-emerald-600 font-semibold') : 'text-slate-400'}>
        ({sign}{diff.toFixed(1)}%)
      </span>
    </span>
  );
}

// ── Mobile Detection Hook ─────────────────────────────────────────────────────

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);
  return isMobile;
}

// ── Mobile State Card ─────────────────────────────────────────────────────────

function MobileStateCard({
  row,
  isDark,
  onSelect,
}: {
  row: StateReportRow;
  isDark: boolean;
  onSelect: () => void;
}) {
  const admUp = row.var_adm >= 0;
  const leadsUp = row.var_leads >= 0;

  const greenColor = isDark ? '#10b981' : '#059669';
  const redColor = isDark ? '#ef4444' : '#dc2626';
  const borderColor = admUp ? greenColor : redColor;
  const admColor = admUp ? greenColor : redColor;
  const leadsColor = leadsUp ? greenColor : redColor;

  const cardBg = isDark
    ? admUp ? 'rgba(16,185,129,0.04)' : 'rgba(239,68,68,0.04)'
    : admUp ? 'rgba(16,185,129,0.03)' : 'rgba(239,68,68,0.03)';

  return (
    <div
      onClick={onSelect}
      className="active:scale-[0.98] transition-transform duration-100 cursor-pointer"
      style={{
        borderLeft: `3px solid ${borderColor}`,
        borderRadius: 10,
        background: isDark ? '#111827' : '#ffffff',
        marginBottom: 8,
        padding: '12px 14px',
        boxShadow: isDark
          ? '0 1px 3px rgba(0,0,0,0.4)'
          : '0 1px 3px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.04)',
        border: isDark ? 'none' : '1px solid #e2e8f0',
        borderLeftWidth: 3,
        borderLeftStyle: 'solid' as const,
        borderLeftColor: borderColor,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div style={{ position: 'absolute', inset: 0, background: cardBg, pointerEvents: 'none' }} />

      {/* Row 1: State name + Admission badge */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <StatusDot status={row.status_indicator} />
          <span style={{
            fontSize: 13,
            fontWeight: 700,
            color: isDark ? '#e2e8f0' : '#1e293b',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {row.name || row.state}
          </span>
        </div>

        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 3,
          fontSize: 11,
          fontWeight: 700,
          padding: '3px 8px',
          borderRadius: 6,
          background: admUp ? (isDark ? 'rgba(16,185,129,0.15)' : 'rgba(5,150,105,0.12)') : (isDark ? 'rgba(239,68,68,0.15)' : 'rgba(220,38,38,0.12)'),
          color: admColor,
          border: `1px solid ${admUp ? (isDark ? 'rgba(16,185,129,0.25)' : 'rgba(5,150,105,0.2)') : (isDark ? 'rgba(239,68,68,0.25)' : 'rgba(220,38,38,0.2)')}`,
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 12 }}>{admUp ? '▲' : '▼'}</span>
          {admUp ? '+' : ''}{row.var_adm} Adm
        </span>
      </div>

      {/* Row 2: 3-column metric grid */}
      <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
        {/* Leads */}
        <div style={{
          background: isDark ? 'rgba(255,255,255,0.04)' : '#f8fafc',
          borderRadius: 7,
          padding: '7px 8px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 9, fontWeight: 500, color: isDark ? '#9ca3af' : '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>Leads</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: isDark ? '#f1f5f9' : '#1e293b' }}>{row.cy_leads.toLocaleString()}</div>
          <div style={{
            fontSize: 10,
            fontWeight: 600,
            color: leadsColor,
            marginTop: 1,
          }}>
            {leadsUp ? '↑' : '↓'} {leadsUp ? '+' : ''}{row.var_leads_pct.toFixed(0)}%
          </div>
        </div>

        {/* CUCET */}
        <div style={{
          background: isDark ? 'rgba(255,255,255,0.04)' : '#f8fafc',
          borderRadius: 7,
          padding: '7px 8px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 9, fontWeight: 500, color: isDark ? '#9ca3af' : '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>CUCET</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: isDark ? '#f1f5f9' : '#1e293b' }}>{row.cy_cucet.toLocaleString()}</div>
          <div style={{
            fontSize: 10,
            fontWeight: 600,
            color: row.var_cucet >= 0 ? greenColor : redColor,
            marginTop: 1,
          }}>
            {row.var_cucet >= 0 ? '↑' : '↓'} {row.var_cucet >= 0 ? '+' : ''}{row.var_cucet_pct.toFixed(0)}%
          </div>
        </div>

        {/* Admissions */}
        <div style={{
          background: isDark ? 'rgba(255,255,255,0.04)' : '#f8fafc',
          borderRadius: 7,
          padding: '7px 8px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 9, fontWeight: 500, color: isDark ? '#9ca3af' : '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>Admissions</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: isDark ? '#f1f5f9' : '#1e293b' }}>{row.cy_adm.toLocaleString()}</div>
          <div style={{
            fontSize: 10,
            fontWeight: 600,
            color: admColor,
            marginTop: 1,
          }}>
            {admUp ? '↑' : '↓'} {admUp ? '+' : ''}{row.var_adm_pct.toFixed(0)}%
          </div>
        </div>
      </div>

      {/* Row 3: Conversion rates */}
      <div style={{
        position: 'relative',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: 8,
        paddingTop: 8,
        borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : '#f1f5f9'}`,
        fontSize: 11,
      }}>
        <span style={{ color: isDark ? '#9ca3af' : '#64748b' }}>
          Lead-Adm: <span style={{ fontWeight: 600, color: isDark ? '#38bdf8' : '#0284c7' }}>{row.lead_adm_pct.toFixed(1)}%</span>
        </span>
        <span style={{ color: isDark ? '#9ca3af' : '#64748b' }}>
          CUCET-Adm: <span style={{ fontWeight: 600, color: isDark ? '#c084fc' : '#9333ea' }}>{row.cucet_adm_pct.toFixed(1)}%</span>
        </span>
      </div>
    </div>
  );
}

// ── Mobile Total Card ─────────────────────────────────────────────────────────

function MobileTotalCard({ row, isDark }: { row: StateReportRow; isDark: boolean }) {
  return (
    <div style={{
      borderRadius: 10,
      background: isDark ? 'linear-gradient(135deg, #1e1b4b, #312e81)' : 'linear-gradient(135deg, #eef2ff, #e0e7ff)',
      padding: '14px 16px',
      marginBottom: 8,
      border: `1px solid ${isDark ? 'rgba(99,102,241,0.3)' : 'rgba(99,102,241,0.2)'}`,
    }}>
      <div style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '1px', color: isDark ? '#a5b4fc' : '#4f46e5', marginBottom: 10 }}>
        ⬛ Total
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: isDark ? '#94a3b8' : '#6b7280', textTransform: 'uppercase', marginBottom: 2 }}>Leads</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: isDark ? '#ffffff' : '#1e293b' }}>{row.cy_leads.toLocaleString()}</div>
          <VarBadge value={row.var_leads} pct={row.var_leads_pct} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: isDark ? '#94a3b8' : '#6b7280', textTransform: 'uppercase', marginBottom: 2 }}>CUCET</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: isDark ? '#ffffff' : '#1e293b' }}>{row.cy_cucet.toLocaleString()}</div>
          <VarBadge value={row.var_cucet} pct={row.var_cucet_pct} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: isDark ? '#94a3b8' : '#6b7280', textTransform: 'uppercase', marginBottom: 2 }}>Adm</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: isDark ? '#10b981' : '#059669' }}>{row.cy_adm.toLocaleString()}</div>
          <VarBadge value={row.var_adm} pct={row.var_adm_pct} />
        </div>
      </div>
    </div>
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
  selectedState?: string | null;
  onSelectState?: (state: string) => void;
  loading?: boolean;
  isDark?: boolean;
  sourceFilter?: string;
  activeMetric?: 'lead_cucet_pct' | 'lead_adm_pct' | 'cucet_adm_pct' | null;
}

const INDENT = 20; // px per hierarchy level

export default function StateReportTable({
  topRows,
  totalRow,
  filters,
  sortBy,
  sortOrder,
  onSortChange,
  selectedState = null,
  onSelectState,
  loading = false,
  isDark = true,
  sourceFilter = 'All',
  activeMetric = null,
}: StateReportTableProps) {
  const isMobile = useIsMobile();
  const { year: contextYear, periods } = useAppContext();
  const activeYear = filters.academic_year || contextYear || 2026;
  const activePeriod = periods?.find((p: PeriodSummary) => (p.period_end_year || p.period_start_year) === activeYear);
  const cyYear = activePeriod?.period_end_year || activeYear;
  const pyYear = activePeriod?.period_start_year || (cyYear - 1);
  const cyShort = `'${String(cyYear).slice(-2)}`;
  const pyShort = `'${String(pyYear).slice(-2)}`;

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
          // If level 2 (source category) or level 3 (sub-source) and sourceFilter is active
          if ((r.level === 2 || r.level === 3) && sourceFilter && sourceFilter !== 'All') {
            const sName = (r.source_category || r.sub_source || r.name || '').toLowerCase();
            if (!sName.includes(sourceFilter.toLowerCase())) return;
          }
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
    [sourceFilter]
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

  // ── Mobile Card View ────────────────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{ maxHeight: 'calc(100vh - 190px)', overflowY: 'auto', padding: '4px 0', WebkitOverflowScrolling: 'touch' }}>
        {/* Total card at top */}
        {totalRow && <MobileTotalCard row={totalRow} isDark={isDark} />}

        {/* State cards */}
        {topRows.map((row) => (
          <MobileStateCard
            key={row.id || row.state || row.name}
            row={row}
            isDark={isDark}
            onSelect={() => onSelectState && onSelectState(row.state_key || row.state || row.name)}
          />
        ))}

        {topRows.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px 16px', color: isDark ? '#6b7280' : '#9ca3af', fontSize: 13 }}>
            No states found
          </div>
        )}
      </div>
    );
  }

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
                <div className="flex items-center justify-end">{pyShort} LEADS {renderSortIndicator('py_leads')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cy_leads')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">{cyShort} LEADS {renderSortIndicator('cy_leads')}</div>
              </th>
              <th onClick={() => handleHeaderClick('var_leads')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">VAR (LEADS) {renderSortIndicator('var_leads')}</div>
              </th>
              <th onClick={() => handleHeaderClick('py_cucet')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">{pyShort} CUCET {renderSortIndicator('py_cucet')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cy_cucet')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">{cyShort} CUCET {renderSortIndicator('cy_cucet')}</div>
              </th>
              <th onClick={() => handleHeaderClick('var_cucet')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">VAR (CUCET) {renderSortIndicator('var_cucet')}</div>
              </th>
              <th onClick={() => handleHeaderClick('lead_cucet_pct')} className={`${thBase} text-right ${activeMetric === 'lead_cucet_pct' ? (isDark ? 'bg-blue-600/25 text-white ring-1 ring-blue-400' : 'bg-blue-100 text-blue-900 ring-1 ring-blue-400') : ''}`}>
                <div className="flex items-center justify-end">LEAD-CUCET % {renderSortIndicator('lead_cucet_pct')}</div>
              </th>
              <th onClick={() => handleHeaderClick('py_adm')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">{pyShort} ADM {renderSortIndicator('py_adm')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cy_adm')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">{cyShort} ADM {renderSortIndicator('cy_adm')}</div>
              </th>
              <th onClick={() => handleHeaderClick('var_adm')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">VAR (ADM) {renderSortIndicator('var_adm')}</div>
              </th>
              <th onClick={() => handleHeaderClick('lead_adm_pct')} className={`${thBase} text-right ${activeMetric === 'lead_adm_pct' ? (isDark ? 'bg-blue-600/25 text-white ring-1 ring-blue-400' : 'bg-blue-100 text-blue-900 ring-1 ring-blue-400') : ''}`}>
                <div className="flex items-center justify-end">LEAD-ADM % {renderSortIndicator('lead_adm_pct')}</div>
              </th>
              <th onClick={() => handleHeaderClick('cucet_adm_pct')} className={`${thBase} text-right ${activeMetric === 'cucet_adm_pct' ? (isDark ? 'bg-blue-600/25 text-white ring-1 ring-blue-400' : 'bg-blue-100 text-blue-900 ring-1 ring-blue-400') : ''}`}>
                <div className="flex items-center justify-end">CUCET-ADM % {renderSortIndicator('cucet_adm_pct')}</div>
              </th>
              <th className={`${thBase} text-center`}>LEAD TREND</th>
              <th onClick={() => handleHeaderClick('net_admissions')} className={`${thBase} text-right`}>
                <div className="flex items-center justify-end">NET ADMISSIONS {renderSortIndicator('net_admissions')}</div>
              </th>
              <th className={`${thBase} text-right`}>REFUND {pyShort} VS {cyShort}</th>
              <th className={`${thBase} text-right`}>REFUND % {pyShort} VS {cyShort}</th>
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
                const stateKey = row.state_key || (row as any).state || row.name;
                const isSelected = row.level === 1 && selectedState === stateKey;

                const selectedCls = isSelected
                  ? isDark
                    ? 'bg-indigo-950/40 border-l-2 border-l-indigo-500'
                    : 'bg-indigo-50/70 border-l-2 border-l-indigo-600'
                  : '';
                const frozenBg = isSelected
                  ? isDark
                    ? '#141A33'
                    : '#EEF2FF'
                  : isDark
                  ? '#0f1117'
                  : '#ffffff';

                const handleRowClick = () => {
                  if (row.level === 1 && onSelectState) {
                    onSelectState(stateKey);
                  }
                };

                return (
                  <tr
                    key={row.id}
                    onClick={handleRowClick}
                    className={`transition-colors border-b ${
                      isDark ? 'border-white/[0.04]' : 'border-slate-100'
                    } ${selectedCls || getRowBg(row)} ${row.level === 1 ? 'cursor-pointer' : ''}`}
                  >
                    {/* Frozen State Column */}
                    <td
                      style={{ paddingLeft: `${indentPx + 12}px`, background: frozenBg }}
                      className={`sticky left-0 z-10 ${tdBase}`}
                    >
                      <div className="flex items-center gap-2">
                        {/* Expand / Collapse Button */}
                        {row.has_children ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggle(row);
                            }}
                            disabled={isLoading}
                            className={`w-4 h-4 flex items-center justify-center rounded text-[10px] transition-colors cursor-pointer ${
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
                          className={`truncate max-w-[240px] text-xs ${getTextColor(row)}`}
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
                    <td className={`${tdBase} text-right whitespace-nowrap ${
                      activeMetric === 'lead_cucet_pct' ? (isDark ? 'bg-amber-950/30' : 'bg-amber-50/80') : ''
                    }`}>
                      <RateTransitionBadge
                        py={row.py_leads > 0 ? (row.py_cucet / row.py_leads) * 100 : 0}
                        cy={row.cy_leads > 0 ? (row.cy_cucet / row.cy_leads) * 100 : row.lead_cucet_pct}
                        isDark={isDark}
                      />
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
                    <td className={`${tdBase} text-right whitespace-nowrap ${
                      activeMetric === 'lead_adm_pct' ? (isDark ? 'bg-indigo-950/30' : 'bg-indigo-50/80') : ''
                    }`}>
                      <RateTransitionBadge
                        py={row.py_leads > 0 ? (row.py_adm / row.py_leads) * 100 : 0}
                        cy={row.cy_leads > 0 ? (row.cy_adm / row.cy_leads) * 100 : row.lead_adm_pct}
                        isDark={isDark}
                      />
                    </td>
                    <td className={`${tdBase} text-right whitespace-nowrap ${
                      activeMetric === 'cucet_adm_pct' ? (isDark ? 'bg-purple-950/30' : 'bg-purple-50/80') : ''
                    }`}>
                      <RateTransitionBadge
                        py={row.py_cucet > 0 ? (row.py_adm / row.py_cucet) * 100 : 0}
                        cy={row.cy_cucet > 0 ? (row.cy_adm / row.cy_cucet) * 100 : row.cucet_adm_pct}
                        isDark={isDark}
                      />
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
                <td className={`px-3 py-3 text-right text-xs whitespace-nowrap ${
                  activeMetric === 'lead_cucet_pct' ? (isDark ? 'bg-amber-950/30' : 'bg-amber-50/80') : ''
                }`}>
                  <RateTransitionBadge
                    py={totalRow.py_leads > 0 ? (totalRow.py_cucet / totalRow.py_leads) * 100 : 0}
                    cy={totalRow.cy_leads > 0 ? (totalRow.cy_cucet / totalRow.cy_leads) * 100 : totalRow.lead_cucet_pct}
                    isDark={isDark}
                  />
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
                <td className={`px-3 py-3 text-right text-xs whitespace-nowrap ${
                  activeMetric === 'lead_adm_pct' ? (isDark ? 'bg-indigo-950/30' : 'bg-indigo-50/80') : ''
                }`}>
                  <RateTransitionBadge
                    py={totalRow.py_leads > 0 ? (totalRow.py_adm / totalRow.py_leads) * 100 : 0}
                    cy={totalRow.cy_leads > 0 ? (totalRow.cy_adm / totalRow.cy_leads) * 100 : totalRow.lead_adm_pct}
                    isDark={isDark}
                  />
                </td>
                <td className={`px-3 py-3 text-right text-xs whitespace-nowrap ${
                  activeMetric === 'cucet_adm_pct' ? (isDark ? 'bg-purple-950/30' : 'bg-purple-50/80') : ''
                }`}>
                  <RateTransitionBadge
                    py={totalRow.py_cucet > 0 ? (totalRow.py_adm / totalRow.py_cucet) * 100 : 0}
                    cy={totalRow.cy_cucet > 0 ? (totalRow.cy_adm / totalRow.cy_cucet) * 100 : totalRow.cucet_adm_pct}
                    isDark={isDark}
                  />
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
