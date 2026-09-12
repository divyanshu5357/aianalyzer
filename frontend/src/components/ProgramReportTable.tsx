'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getProgramHierarchyChildren } from '@/lib/api/programs';
import dashboardCache from '@/lib/cache/dashboardCache';
import ProgramInsightModal from '@/components/ProgramInsightModal';
import type {
  ProgramReportRow,
  ProgramHierarchyParams,
} from '@/lib/api/types';

// ── useIsMobile Hook ─────────────────────────────────────────────────────────

function useIsMobile(breakpoint = 640) {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);
    setIsMobile(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [breakpoint]);
  return isMobile;
}

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

// ── Mini Sparkline (for mobile cards) ─────────────────────────────────────────

function MiniSparkline({ data, color = '#6366f1' }: { data: number[]; color?: string }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 48;
  const h = 18;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ── Variance Badge ────────────────────────────────────────────────────────────

function VarBadge({ value, pct, isDark = true }: { value: number; pct: number; isDark?: boolean }) {
  if (value === 0 && pct === 0) return <span className="text-gray-500 text-xs">—</span>;
  const isPos = value >= 0;
  const cls = isPos
    ? isDark
      ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
      : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
    : isDark
      ? 'bg-red-500/15 text-red-400 border border-red-500/25'
      : 'bg-red-50 text-red-700 border border-red-200';
  const sign = isPos ? '+' : '';
  return (
    <span className={`inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap ${cls}`}>
      {sign}{value.toLocaleString()} ({sign}{pct.toFixed(1)}%)
    </span>
  );
}

// ── Refund Cell ───────────────────────────────────────────────────────────────

function RefundCell({ py, cy, diff, isDark = true }: { py: number; cy: number; diff: number; isDark?: boolean }) {
  const isPos = diff > 0;
  const sign = isPos ? '+' : '';
  const cls = isPos
    ? (isDark ? 'text-red-400' : 'text-red-600')
    : diff < 0
      ? (isDark ? 'text-emerald-400' : 'text-emerald-600')
      : (isDark ? 'text-gray-500' : 'text-slate-400');
  return (
    <span className="text-xs whitespace-nowrap">
      <span className={isDark ? 'text-gray-300' : 'text-slate-500'}>{py} → {cy}</span>{' '}
      <span className={cls}>({sign}{diff})</span>
    </span>
  );
}

// ── Mobile Program Card ───────────────────────────────────────────────────────

function MobileProgramCard({
  row,
  isDark,
  onSelect,
}: {
  row: ProgramReportRow;
  isDark: boolean;
  onSelect: () => void;
}) {
  const admUp = row.var_adm >= 0;
  const leadsUp = row.var_leads >= 0;

  // Card border-left color: green if admissions up, red if down
  const greenColor = isDark ? '#10b981' : '#059669';
  const redColor = isDark ? '#ef4444' : '#dc2626';
  const borderColor = admUp ? greenColor : redColor;
  const admColor = admUp ? greenColor : redColor;
  const leadsColor = leadsUp ? greenColor : redColor;

  // Background tint
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
      {/* Subtle background tint */}
      <div style={{ position: 'absolute', inset: 0, background: cardBg, pointerEvents: 'none' }} />

      {/* Row 1: Program name + Admission badge */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
        <span style={{
          fontSize: 13,
          fontWeight: 600,
          color: isDark ? '#e2e8f0' : '#1e293b',
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {row.program}
        </span>

        {/* Admission change badge */}
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
          background: admUp ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
          borderRadius: 7,
          padding: '7px 8px',
          textAlign: 'center',
          border: `1px solid ${admUp ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
        }}>
          <div style={{ fontSize: 9, fontWeight: 500, color: isDark ? '#9ca3af' : '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>Adm</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: admColor }}>{row.cy_adm.toLocaleString()}</div>
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

      {/* Row 3: Conversion rates + mini sparkline */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, paddingTop: 8, borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}` }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 10, color: isDark ? '#9ca3af' : '#6b7280' }}>
            L→A <span style={{ fontWeight: 600, color: isDark ? '#38bdf8' : '#0284c7' }}>{row.lead_adm_pct.toFixed(1)}%</span>
          </span>
          <span style={{ fontSize: 10, color: isDark ? '#9ca3af' : '#6b7280' }}>
            Net <span style={{ fontWeight: 600, color: isDark ? '#e2e8f0' : '#1e293b' }}>{row.net_admissions.toLocaleString()}</span>
          </span>
          {row.refund_py_vs_cy && (
            <span style={{ fontSize: 10, color: isDark ? '#9ca3af' : '#6b7280' }}>
              Ref <span style={{ fontWeight: 600, color: row.refund_py_vs_cy.diff > 0 ? redColor : greenColor }}>{row.refund_py_vs_cy.diff > 0 ? '+' : ''}{row.refund_py_vs_cy.diff}</span>
            </span>
          )}
        </div>
        <MiniSparkline data={row.lead_trend} color={admColor} />
      </div>
    </div>
  );
}

// ── Mobile Total Card ─────────────────────────────────────────────────────────

function MobileTotalCard({ row, isDark }: { row: ProgramReportRow; isDark: boolean }) {
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
          <VarBadge value={row.var_leads} pct={row.var_leads_pct} isDark={isDark} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: isDark ? '#94a3b8' : '#6b7280', textTransform: 'uppercase', marginBottom: 2 }}>CUCET</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: isDark ? '#ffffff' : '#1e293b' }}>{row.cy_cucet.toLocaleString()}</div>
          <VarBadge value={row.var_cucet} pct={row.var_cucet_pct} isDark={isDark} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: isDark ? '#94a3b8' : '#6b7280', textTransform: 'uppercase', marginBottom: 2 }}>Adm</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: isDark ? '#10b981' : '#059669' }}>{row.cy_adm.toLocaleString()}</div>
          <VarBadge value={row.var_adm} pct={row.var_adm_pct} isDark={isDark} />
        </div>
      </div>
    </div>
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
  selectedProgram?: string | null;
  onSelectProgram?: (program: string) => void;
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
  selectedProgram,
  onSelectProgram,
  loading = false,
  isDark = true,
}: ProgramReportTableProps) {
  const isMobile = useIsMobile();

  // Scope-aware child cache: Map<nodeId, ProgramReportRow[]>
  const childCache = useRef<Map<string, ProgramReportRow[]>>(new Map());
  const prevScopeKey = useRef<string>('');

  // Node state map: nodeId → RowNode
  const [nodes, setNodes] = useState<Map<string, RowNode>>(() => {
    const savedExpanded = dashboardCache.getProgramUiState().expandedNodeIds;
    const m = new Map<string, RowNode>();
    topRows.forEach((r) =>
      m.set(r.id, {
        row: r,
        state: savedExpanded.has(r.id) ? 'expanded' : 'collapsed',
        children: [],
      })
    );
    return m;
  });

  // Selected program for fallback AI diagnostic modal
  const [selectedInsightProgram, setSelectedInsightProgram] = useState<string | null>(null);

  // Re-init nodes when top rows or scope changes (filter invalidation)
  useEffect(() => {
    const currentKey = buildScopeKey(filters);
    if (currentKey !== prevScopeKey.current) {
      // Scope changed → invalidate child caches
      childCache.current.clear();
      prevScopeKey.current = currentKey;
    }
    const savedExpanded = dashboardCache.getProgramUiState().expandedNodeIds;
    const m = new Map<string, RowNode>();
    topRows.forEach((r) => {
      const isExp = savedExpanded.has(r.id);
      const cachedChildren = childCache.current.get(`${currentKey}|${r.id}`) || [];
      m.set(r.id, {
        row: r,
        state: isExp && cachedChildren.length > 0 ? 'expanded' : 'collapsed',
        children: cachedChildren,
      });
    });
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
      const currentExpanded = new Set(dashboardCache.getProgramUiState().expandedNodeIds);
      currentExpanded.delete(nodeId);
      dashboardCache.setProgramUiState({ expandedNodeIds: currentExpanded });
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
      const currentExpanded = new Set(dashboardCache.getProgramUiState().expandedNodeIds);
      currentExpanded.add(nodeId);
      dashboardCache.setProgramUiState({ expandedNodeIds: currentExpanded });
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
      const currentExpanded = new Set(dashboardCache.getProgramUiState().expandedNodeIds);
      currentExpanded.add(nodeId);
      dashboardCache.setProgramUiState({ expandedNodeIds: currentExpanded });
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

    const isSelected = selectedProgram && (selectedProgram === row.program || selectedProgram === row.program_group);
    const selectedCls = isSelected
      ? isDark
        ? 'bg-indigo-950/40 ring-1 ring-inset ring-indigo-500/40'
        : 'bg-indigo-50/80 ring-1 ring-inset ring-indigo-300'
      : '';
    const rowHoverCls = isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-slate-50';
    const borderCls = isDark ? 'border-white/5' : 'border-slate-100';

    const handleRowClick = () => {
      if (row.level === 1 || row.level === 2) {
        if (onSelectProgram) {
          onSelectProgram(row.program_group || row.program);
        } else {
          setSelectedInsightProgram(row.program_group || row.program);
        }
      }
    };

    return (
      <tr
        key={row.id}
        onClick={handleRowClick}
        className={`border-b transition-colors duration-100 ${selectedCls || levelBg(row.level)} ${rowHoverCls} ${borderCls} ${(row.level === 1 || row.level === 2) ? 'cursor-pointer' : ''}`}
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
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggle(row);
                }}
                className="flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:text-indigo-400 hover:bg-indigo-500/10 transition-all cursor-pointer"
                title={isExpanded ? 'Collapse' : 'Expand hierarchy'}
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
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_leads} pct={row.var_leads_pct} isDark={isDark} /></td>

        {/* Col 5-7: PY/CY CUCET + Var */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-400'}`}>{row.py_cucet.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-100' : 'text-slate-800'}`}>{row.cy_cucet.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_cucet} pct={row.var_cucet_pct} isDark={isDark} /></td>

        {/* Col 8: Lead-CUCET % */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>{row.lead_cucet_pct.toFixed(1)}%</td>

        {/* Col 9-11: PY/CY Adm + Var */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-400'}`}>{row.py_adm.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right tabular-nums font-medium ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{row.cy_adm.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_adm} pct={row.var_adm_pct} isDark={isDark} /></td>

        {/* Col 12: Lead-Adm % */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-sky-400' : 'text-sky-600'}`}>{row.lead_adm_pct.toFixed(1)}%</td>

        {/* Col 13: Cucet-Adm % */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums ${isDark ? 'text-violet-400' : 'text-violet-600'}`}>{row.cucet_adm_pct.toFixed(1)}%</td>

        {/* Col 14: Lead Trend sparkline */}
        <td className="px-3 py-2">
          <Sparkline data={row.lead_trend} color={sparklineColor(row.level)} />
        </td>

        {/* Col 15: Net Admissions */}
        <td className={`px-3 py-2 text-xs text-right tabular-nums font-medium ${isDark ? 'text-gray-200' : 'text-slate-700'}`}>{row.net_admissions.toLocaleString()}</td>

        {/* Col 16: Refund Py vs Cy */}
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refund ? <RefundCell py={refund.py} cy={refund.cy} diff={refund.diff} isDark={isDark} /> : '—'}
        </td>

        {/* Col 17: Refund % Py vs Cy */}
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refundPct ? (
            <span className="text-xs">
              <span className={isDark ? 'text-gray-400' : 'text-slate-500'}>{refundPct.py_pct.toFixed(0)}% → {refundPct.cy_pct.toFixed(0)}%</span>{' '}
              <span className={refundPct.diff_pct <= 0 ? (isDark ? 'text-emerald-400' : 'text-emerald-600') : (isDark ? 'text-red-400' : 'text-red-600')}>
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
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>⬛ Total</span>
          </div>
        </td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{row.py_leads.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right font-bold tabular-nums ${isDark ? 'text-white' : 'text-slate-900'}`}>{row.cy_leads.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_leads} pct={row.var_leads_pct} isDark={isDark} /></td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{row.py_cucet.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-white' : 'text-slate-900'}`}>{row.cy_cucet.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_cucet} pct={row.var_cucet_pct} isDark={isDark} /></td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-amber-300' : 'text-amber-600'}`}>{row.lead_cucet_pct.toFixed(1)}%</td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>{row.py_adm.toLocaleString()}</td>
        <td className={`px-3 py-2 text-xs text-right font-bold tabular-nums ${isDark ? 'text-emerald-300' : 'text-emerald-600'}`}>{row.cy_adm.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right"><VarBadge value={row.var_adm} pct={row.var_adm_pct} isDark={isDark} /></td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-sky-300' : 'text-sky-600'}`}>{row.lead_adm_pct.toFixed(1)}%</td>
        <td className={`px-3 py-2 text-xs text-right font-semibold tabular-nums ${isDark ? 'text-violet-300' : 'text-violet-600'}`}>{row.cucet_adm_pct.toFixed(1)}%</td>
        <td className="px-3 py-2">
          <Sparkline data={row.lead_trend} color="#818cf8" />
        </td>
        <td className={`px-3 py-2 text-xs text-right font-bold tabular-nums ${isDark ? 'text-white' : 'text-slate-900'}`}>{row.net_admissions.toLocaleString()}</td>
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refund ? <RefundCell py={refund.py} cy={refund.cy} diff={refund.diff} isDark={isDark} /> : '—'}
        </td>
        <td className="px-3 py-2 text-xs text-right whitespace-nowrap">
          {refundPct ? (
            <span className="text-xs">
              <span className={isDark ? 'text-gray-400' : 'text-slate-500'}>{refundPct.py_pct.toFixed(0)}% → {refundPct.cy_pct.toFixed(0)}%</span>{' '}
              <span className={refundPct.diff_pct <= 0 ? (isDark ? 'text-emerald-400' : 'text-emerald-600') : (isDark ? 'text-red-400' : 'text-red-600')}>
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
        <span className={`ml-1 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}>
          {sortOrder === 'desc' ? '↓' : '↑'}
        </span>
      );
    }
    return <span className={`ml-1 ${isDark ? 'text-gray-600 group-hover:text-gray-400' : 'text-slate-300 group-hover:text-slate-400'}`}>↕</span>;
  }

  // ── Mobile Loading Skeleton ──────────────────────────────────────────────────
  if (loading && isMobile) {
    return (
      <div style={{ padding: '8px 4px' }}>
        <div className="animate-pulse" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{
              borderRadius: 10,
              background: isDark ? '#111827' : '#ffffff',
              padding: '14px 16px',
              border: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)'}`,
              boxShadow: isDark ? 'none' : '0 1px 2px rgba(0,0,0,0.04)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <div className={`rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} style={{ width: 120, height: 14 }} />
                <div className={`rounded ${isDark ? 'bg-white/10' : 'bg-slate-200'}`} style={{ width: 60, height: 20 }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                {[0,1,2].map(j => (
                  <div key={j} className={`rounded ${isDark ? 'bg-white/5' : 'bg-slate-100'}`} style={{ height: 48, borderRadius: 7 }} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Desktop Loading Skeleton ────────────────────────────────────────────────
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

  // ── Mobile Card View ────────────────────────────────────────────────────────
  if (isMobile) {
    const handleMobileSelect = (row: ProgramReportRow) => {
      if (onSelectProgram) {
        onSelectProgram(row.program_group || row.program);
      } else {
        setSelectedInsightProgram(row.program_group || row.program);
      }
    };

    return (
      <div style={{ maxHeight: 'calc(100vh - 190px)', overflowY: 'auto', padding: '4px 0', WebkitOverflowScrolling: 'touch' }}>
        {/* Total card at top */}
        {totalRow && <MobileTotalCard row={totalRow} isDark={isDark} />}

        {/* Program cards */}
        {topRows.map((row) => (
          <MobileProgramCard
            key={row.id}
            row={row}
            isDark={isDark}
            onSelect={() => handleMobileSelect(row)}
          />
        ))}

        {topRows.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px 16px', color: isDark ? '#6b7280' : '#9ca3af', fontSize: 13 }}>
            No programs found
          </div>
        )}

        {/* Program AI Insight Diagnostic Modal */}
        {selectedInsightProgram && (
          <ProgramInsightModal
            programName={selectedInsightProgram}
            scopeParams={{
              academic_year: filters.academic_year,
              campus: filters.campus,
              from_date: filters.from_date,
              to_date: filters.to_date,
            }}
            isDark={isDark}
            onClose={() => setSelectedInsightProgram(null)}
          />
        )}
      </div>
    );
  }

  // ── Desktop Table View ──────────────────────────────────────────────────────
  return (
    <div
      className={`relative overflow-auto rounded-xl border ${isDark ? 'border-white/10' : 'border-slate-200'}`}
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

      {/* Program AI Insight Diagnostic Modal */}
      {selectedInsightProgram && (
        <ProgramInsightModal
          programName={selectedInsightProgram}
          scopeParams={{
            academic_year: filters.academic_year,
            campus: filters.campus,
            from_date: filters.from_date,
            to_date: filters.to_date,
          }}
          isDark={isDark}
          onClose={() => setSelectedInsightProgram(null)}
        />
      )}
    </div>
  );
}
