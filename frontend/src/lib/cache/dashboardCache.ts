/**
 * Client-Side In-Memory Cache for AI Analytics
 * 
 * Provides:
 * - Query-key-based caching (academic_year, campus, date range, etc.)
 * - In-flight Promise deduplication (prevents duplicate simultaneous API calls)
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
   * Invalidate cache entries matching a prefix, or all entries if no prefix given.
   */
  public invalidate(prefix?: string): void {
    if (!prefix) {
      this.store.clear();
      this.inFlight.clear();
      return;
    }
    for (const key of Array.from(this.store.keys())) {
      if (key.startsWith(prefix) || key.includes(prefix)) {
        this.store.delete(key);
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
   * Current number of cached items.
   */
  public size(): number {
    return this.store.size;
  }
}

export const dashboardCache = new MemoryCache();
export default dashboardCache;
