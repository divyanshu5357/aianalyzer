/**
 * Intelligent Idle Prefetcher
 *
 * Pre-warms client caches during browser idle periods for likely-to-be-visited
 * pages and top drilldown nodes. Uses requestIdleCallback (falling back to setTimeout)
 * so it never degrades main-thread responsiveness or user interactions.
 */

import dashboardCache from "./dashboardCache";
import { getProgramReport, getProgramHierarchyChildren } from "../api/programs";
import { getStateReport, getStateHierarchyChildren } from "../api/states";
import { getCounsellorsList } from "../api";
import type { ProgramReportRow, StateReportRow } from "../api/types";

interface PageScope {
  academic_year?: number;
  campus?: string;
  from_date?: string;
  to_date?: string;
}

const scheduledPrefetches = new Set<string>();

function runWhenIdle(callback: () => void, timeoutMs: number = 2000) {
  if (typeof window !== "undefined" && "requestIdleCallback" in window) {
    (window as any).requestIdleCallback(callback, { timeout: timeoutMs });
  } else if (typeof setTimeout !== "undefined") {
    setTimeout(callback, 150);
  }
}

/**
 * Prefetch top-level aggregate summaries for adjacent pages:
 * - Programs Report (L1)
 * - State Wise Analysis (L1)
 * - Counsellor Operations (L1)
 */
export function prefetchAdjacentPages(scope: PageScope) {
  const scopeKey = `${scope.academic_year || "all"}|${scope.campus || "all"}|${scope.from_date || ""}|${scope.to_date || ""}`;
  if (scheduledPrefetches.has(scopeKey)) return;
  scheduledPrefetches.add(scopeKey);

  runWhenIdle(() => {
    // 1. Prefetch Programs Report (L1 default sort)
    const progKey = dashboardCache.buildKey("programs:report", {
      academic_year: scope.academic_year,
      campus: scope.campus,
      from_date: scope.from_date,
      to_date: scope.to_date,
      sort_by: "cy_leads",
      sort_order: "desc",
    });
    if (!dashboardCache.peek(progKey)) {
      dashboardCache.fetchWithCache(
        progKey,
        () =>
          getProgramReport({
            academic_year: scope.academic_year,
            campus: scope.campus,
            from_date: scope.from_date,
            to_date: scope.to_date,
            sort_by: "cy_leads",
            sort_order: "desc",
          }),
        { ttlMs: 5 * 60 * 1000 }
      ).catch(() => {});
    }

    // 2. Prefetch State Report (L1 default sort)
    const stateKey = dashboardCache.buildKey("states:report", {
      academic_year: scope.academic_year,
      campus: scope.campus,
      from_date: scope.from_date,
      to_date: scope.to_date,
      sort_by: "cy_leads",
      sort_order: "desc",
    });
    if (!dashboardCache.peek(stateKey)) {
      dashboardCache.fetchWithCache(
        stateKey,
        () =>
          getStateReport({
            academic_year: scope.academic_year,
            campus: scope.campus,
            from_date: scope.from_date,
            to_date: scope.to_date,
            sort_by: "cy_leads",
            sort_order: "desc",
          }),
        { ttlMs: 5 * 60 * 1000 }
      ).catch(() => {});
    }

    // 3. Prefetch Counsellor Operations List (L1)
    const counsKey = dashboardCache.buildKey("counsellors:list", {
      academic_year: scope.academic_year ? String(scope.academic_year) : undefined,
      campus: scope.campus,
      search: "",
    });
    if (!dashboardCache.peek(counsKey)) {
      dashboardCache.fetchWithCache(
        counsKey,
        () =>
          getCounsellorsList({
            academic_year: scope.academic_year ? String(scope.academic_year) : undefined,
            campus: scope.campus,
            search: "",
          }),
        { ttlMs: 5 * 60 * 1000 }
      ).catch(() => {});
    }
  });
}

/**
 * Prefetch children for the top 3 items in ProgramReport (e.g. top 3 Program Groups)
 */
export function prefetchTopProgramsChildren(
  topRows: ProgramReportRow[],
  scope: PageScope,
  maxItems: number = 3
) {
  if (!topRows || topRows.length === 0) return;

  runWhenIdle(() => {
    const candidates = topRows.slice(0, maxItems);
    const scopePrefix = `${scope.academic_year || "all"}|${scope.campus || "all"}|${scope.from_date || ""}|${scope.to_date || ""}|cy_leads|desc`;

    for (const row of candidates) {
      if (!row.has_children) continue;
      const cacheKey = `${scopePrefix}|${row.id}`;
      if (dashboardCache.getTreeChildren(cacheKey)) continue;

      getProgramHierarchyChildren({
        level: "program",
        program_group: row.program_group || row.program,
        academic_year: scope.academic_year,
        campus: scope.campus,
        from_date: scope.from_date,
        to_date: scope.to_date,
        sort_by: "cy_leads",
        sort_order: "desc",
      })
        .then((resp) => {
          if (resp?.rows) {
            dashboardCache.setTreeChildren(cacheKey, resp.rows);
          }
        })
        .catch(() => {});
    }
  }, 3000);
}

/**
 * Prefetch children for top 3 States (e.g. top states' source categories)
 */
export function prefetchTopStatesChildren(
  topRows: StateReportRow[],
  scope: PageScope,
  maxItems: number = 3
) {
  if (!topRows || topRows.length === 0) return;

  runWhenIdle(() => {
    const candidates = topRows.slice(0, maxItems);
    const scopePrefix = `${scope.academic_year || "all"}|${scope.campus || "all"}|${scope.from_date || ""}|${scope.to_date || ""}|cy_leads|desc`;

    for (const row of candidates) {
      if (!row.has_children) continue;
      const cacheKey = `${scopePrefix}|${row.id}`;
      if (dashboardCache.getTreeChildren(cacheKey)) continue;

      getStateHierarchyChildren({
        level: "source_category",
        state: row.state_key || row.name,
        academic_year: scope.academic_year,
        campus: scope.campus,
        from_date: scope.from_date,
        to_date: scope.to_date,
        sort_by: "cy_leads",
        sort_order: "desc",
      })
        .then((resp) => {
          if (resp?.rows) {
            dashboardCache.setTreeChildren(cacheKey, resp.rows);
          }
        })
        .catch(() => {});
    }
  }, 3000);
}
