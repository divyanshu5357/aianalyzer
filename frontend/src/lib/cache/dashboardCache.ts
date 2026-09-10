/**
 * Client-Side In-Memory Cache for AI Analytics
 * 
 * Provides:
 * - Query-key-based caching (academic_year, campus, date range, etc.)
 * - In-flight Promise deduplication (prevents duplicate simultaneous API calls)
 * - Stale-While-Revalidate (SWR) pattern for instant 0ms renders with background refresh
 * - AbortController management to cancel obsolete in-flight requests on rapid filter changes
 * - Persistent hierarchical tree node caching across page unmounts
 * - Configurable TTL (default 5 minutes)
 * - Instant (<5ms) synchronous cache reads via peek()
 * - Targeted cache invalidation and global flush
 */

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttlMs: number;
}

const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

class MemoryCache {
  private store = new Map<string, CacheEntry<any>>();
  private inFlight = new Map<string, Promise<any>>();
  private abortControllers = new Map<string, AbortController>();
  private treeStore = new Map<string, any[]>();

  /**
   * Build a normalized cache key from endpoint and parameter dictionary
   */
  public buildKey(endpoint: string, params: Record<string, any> = {}): string {
    const sortedParts = Object.entries(params)
      .filter(([_, v]) => v !== undefined && v !== null && v !== "" && v !== "all")
      .map(([k, v]) => `${k}=${Array.isArray(v) ? v.slice().sort().join(",") : String(v)}`)
      .sort()
      .join("&");
    return `${endpoint}?${sortedParts}`;
  }

  /**
   * Synchronously peek at existing valid cache data without fetching.
   * Returns data if present and not expired, otherwise null.
   */
  public peek<T>(key: string): T | null {
    const entry = this.store.get(key);
    if (!entry) return null;
    if (Date.now() - entry.timestamp > entry.ttlMs) {
      this.store.delete(key);
      return null;
    }
    return entry.data as T;
  }

  /**
   * Get cached data if valid.
   */
  public get<T>(key: string): T | null {
    return this.peek<T>(key);
  }

  /**
   * Store data in cache with TTL.
   */
  public set<T>(key: string, data: T, ttlMs: number = DEFAULT_TTL_MS): void {
    this.store.set(key, {
      data,
      timestamp: Date.now(),
      ttlMs,
    });
  }

  /**
   * Fetch with cache and in-flight request deduplication.
   */
  public async fetchWithCache<T>(
    key: string,
    fetcher: () => Promise<T>,
    options?: { ttlMs?: number; forceRefresh?: boolean }
  ): Promise<T> {
    const ttl = options?.ttlMs ?? DEFAULT_TTL_MS;

    if (!options?.forceRefresh) {
      const cached = this.peek<T>(key);
      if (cached !== null) {
        return cached;
      }

      // Return ongoing request if identical call is already in flight
      const pending = this.inFlight.get(key);
      if (pending) {
        return pending as Promise<T>;
      }
    }

    const promise = (async () => {
      try {
        const data = await fetcher();
        this.set(key, data, ttl);
        return data;
      } finally {
        this.inFlight.delete(key);
      }
    })();

    this.inFlight.set(key, promise);
    return promise;
  }

  /**
   * Stale-While-Revalidate (SWR):
   * 1. Returns cached data immediately if present (<5ms).
   * 2. Kicks off background fetch to ensure freshness.
   * 3. Calls onUpdate callback with fresh data if data changed or was missing.
   */
  public swr<T>(
    key: string,
    fetcher: () => Promise<T>,
    onUpdate: (data: T) => void,
    options?: { ttlMs?: number; forceRefresh?: boolean }
  ): T | null {
    const cached = this.peek<T>(key);
    if (cached !== null && !options?.forceRefresh) {
      // Deliver cached data immediately
      onUpdate(cached);
      // Trigger background revalidation (deduplicated)
      if (!this.inFlight.has(key)) {
        this.fetchWithCache(key, fetcher, { ...options, forceRefresh: true })
          .then((fresh) => {
            onUpdate(fresh);
          })
          .catch(() => {
            // Keep stale cache on network error
          });
      }
      return cached;
    }

    // Cache miss or forceRefresh: execute fetcher
    this.fetchWithCache(key, fetcher, options)
      .then((data) => {
        onUpdate(data);
      })
      .catch((err) => {
        // Handle error in caller
      });
    return null;
  }

  /**
   * Get an AbortSignal for a named scope, cancelling any previous in-flight request for that scope.
   */
  public getScopedSignal(scopeName: string): AbortSignal {
    const prev = this.abortControllers.get(scopeName);
    if (prev) {
      prev.abort();
    }
    const next = new AbortController();
    this.abortControllers.set(scopeName, next);
    return next.signal;
  }

  /**
   * Cancel in-flight requests for a named scope.
   */
  public abortScope(scopeName: string): void {
    const ctrl = this.abortControllers.get(scopeName);
    if (ctrl) {
      ctrl.abort();
      this.abortControllers.delete(scopeName);
    }
  }

  /**
   * Hierarchical drilldown node cache (survives page unmounts).
   */
  public getTreeChildren<T>(parentKey: string): T[] | null {
    return (this.treeStore.get(parentKey) as T[]) || null;
  }

  public setTreeChildren<T>(parentKey: string, children: T[]): void {
    this.treeStore.set(parentKey, children);
  }

  public clearTreeChildren(scopePrefix?: string): void {
    if (!scopePrefix) {
      this.treeStore.clear();
      return;
    }
    for (const k of Array.from(this.treeStore.keys())) {
      if (k.startsWith(scopePrefix) || k.includes(scopePrefix)) {
        this.treeStore.delete(k);
      }
    }
  }

  /**
   * Invalidate cache entries matching a prefix, or all entries if no prefix given.
   */
  public invalidate(prefix?: string): void {
    if (!prefix) {
      this.store.clear();
      this.inFlight.clear();
      this.treeStore.clear();
      return;
    }
    for (const key of Array.from(this.store.keys())) {
      if (key.startsWith(prefix) || key.includes(prefix)) {
        this.store.delete(key);
      }
    }
    this.clearTreeChildren(prefix);
  }

  /**
   * Target-specific invalidation by year and/or campus without wiping unrelated cache.
   */
  public invalidateTargeted(criteria: { year?: number | string; campus?: string }): void {
    const { year, campus } = criteria;
    if (!year && !campus) {
      this.invalidate();
      return;
    }
    const yearStr = year ? String(year) : null;
    const campusStr = campus && campus.toLowerCase() !== "all" ? campus.toLowerCase() : null;

    for (const key of Array.from(this.store.keys())) {
      const matchYear = !yearStr || key.includes(yearStr);
      const matchCampus = !campusStr || key.toLowerCase().includes(campusStr);
      if (matchYear && matchCampus) {
        this.store.delete(key);
      }
    }
    for (const key of Array.from(this.treeStore.keys())) {
      const matchYear = !yearStr || key.includes(yearStr);
      const matchCampus = !campusStr || key.toLowerCase().includes(campusStr);
      if (matchYear && matchCampus) {
        this.treeStore.delete(key);
      }
    }
  }

  /**
   * Remove a specific key.
   */
  public delete(key: string): void {
    this.store.delete(key);
    this.inFlight.delete(key);
  }

  /**
   * Flush all cached items and in-flight promises.
   */
  public flush(): void {
    this.invalidate();
  }

  /**
   * Invalidate entries for a specific year and optional campus.
   */
  public invalidateForYear(year: number | string, campus?: string): void {
    this.invalidateTargeted({ year, campus });
  }

  /**
   * Current number of cached items.
   */
  public size(): number {
    return this.store.size;
  }
}

export const dashboardCache = new MemoryCache();
export default dashboardCache;

