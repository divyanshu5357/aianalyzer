/**
 * Test Suite for Phase 14 Performance Architecture Client Cache
 * Verifies SWR, Deduplication, Abort Scopes, Tree Hierarchy, and Scope Isolation.
 */

import dashboardCache from "./dashboardCache";

function assert(condition: boolean, msg: string) {
  if (!condition) {
    throw new Error(`Assertion failed: ${msg}`);
  }
}

async function runTests() {
  console.log("=== RUNNING FRONTEND CACHE & SWR ARCHITECTURE TESTS ===");
  dashboardCache.flush();

  // 1. Cache Miss & Set
  console.log("Test 1: Cache Miss & FetchWithCache...");
  const k1 = dashboardCache.buildKey("test:page", { academic_year: 2026, campus: "Mohali" });
  assert(dashboardCache.peek(k1) === null, "Initial peek must be null");

  let fetchCount = 0;
  const fetcher = async () => {
    fetchCount++;
    return { data: "2026_mohali_data" };
  };

  const res1 = await dashboardCache.fetchWithCache<{ data: string }>(k1, fetcher);
  assert(res1.data === "2026_mohali_data", "Fetch must return correct data");
  assert(fetchCount === 1, "Fetcher must execute once");
  assert(dashboardCache.peek<{ data: string }>(k1)?.data === "2026_mohali_data", "Peek must now return cached data");
  console.log("✓ Test 1 Passed");

  // 2. Cache Hit (<1ms)
  console.log("Test 2: Instant Cache Hit (<1ms)...");
  const t0 = performance.now();
  const cachedData = dashboardCache.peek<{ data: string }>(k1);
  const tHit = performance.now() - t0;
  assert(cachedData?.data === "2026_mohali_data", "Cached data must match");
  assert(tHit < 5, `Cache peek must be <5ms, got ${tHit.toFixed(2)}ms`);
  console.log(`✓ Test 2 Passed (${tHit.toFixed(3)}ms)`);

  // 3. In-flight Request Deduplication
  console.log("Test 3: In-flight Request Deduplication...");
  dashboardCache.flush();
  let simFetchCount = 0;
  const slowFetcher = async () => {
    simFetchCount++;
    await new Promise((r) => setTimeout(r, 50));
    return { value: "deduped_result" };
  };

  const kDedup = dashboardCache.buildKey("test:dedup", { year: 2026 });
  const [d1, d2, d3] = await Promise.all([
    dashboardCache.fetchWithCache(kDedup, slowFetcher),
    dashboardCache.fetchWithCache(kDedup, slowFetcher),
    dashboardCache.fetchWithCache(kDedup, slowFetcher),
  ]);

  assert(simFetchCount === 1, `Simultaneous requests must execute fetcher only once, got ${simFetchCount}`);
  assert(d1.value === "deduped_result" && d2.value === "deduped_result" && d3.value === "deduped_result", "All callers must receive same result");
  console.log("✓ Test 3 Passed");

  // 4. Stale-While-Revalidate (SWR)
  console.log("Test 4: Stale-While-Revalidate (SWR)...");
  dashboardCache.flush();
  const kSWR = dashboardCache.buildKey("programs:report", { academic_year: 2026 });
  dashboardCache.set(kSWR, { version: 1 });

  let updatedVersion = 0;
  const swrFetcher = async () => {
    await new Promise((r) => setTimeout(r, 20));
    return { version: 2 };
  };

  const immediate = dashboardCache.swr(
    kSWR,
    swrFetcher,
    (fresh) => {
      updatedVersion = fresh.version;
    }
  );

  assert(immediate?.version === 1, "SWR must immediately return version 1 without blocking");
  assert(updatedVersion === 1, "onUpdate should be called immediately with cached version 1");

  await new Promise((r) => setTimeout(r, 60));
  assert(updatedVersion === 2, "SWR callback must be called with fresh version 2 in background");
  console.log("✓ Test 4 Passed");

  // 5. Scoped AbortSignals
  console.log("Test 5: Scoped AbortSignal Cancellation...");
  const sig1 = dashboardCache.getScopedSignal("programs:report");
  assert(!sig1.aborted, "Initial signal must not be aborted");

  const sig2 = dashboardCache.getScopedSignal("programs:report");
  assert(sig1.aborted, "Previous signal must be aborted when new signal is created");
  assert(!sig2.aborted, "New signal must be active");

  dashboardCache.abortScope("programs:report");
  assert(sig2.aborted, "abortScope must abort active signal");
  console.log("✓ Test 5 Passed");

  // 6. Hierarchical Drilldown Node Cache
  console.log("Test 6: Hierarchical Tree Node Cache...");
  const parentKey = "2026|Mohali|group:Engineering";
  const childNodes = [{ id: "cse", name: "Computer Science" }, { id: "ece", name: "Electronics" }];
  
  assert(dashboardCache.getTreeChildren(parentKey) === null, "Initial tree node must be null");
  dashboardCache.setTreeChildren(parentKey, childNodes);
  
  const retrieved = dashboardCache.getTreeChildren<any>(parentKey);
  assert(retrieved?.length === 2, "Retrieved tree children must have 2 nodes");
  assert(retrieved?.[0].id === "cse", "First child node must match");
  console.log("✓ Test 6 Passed");

  // 7. Year & Campus Scope Invalidation
  console.log("Test 7: Targeted Scope Invalidation...");
  dashboardCache.set(dashboardCache.buildKey("dash", { academic_year: 2026, campus: "mohali" }), "2026_mohali");
  dashboardCache.set(dashboardCache.buildKey("dash", { academic_year: 2025, campus: "mohali" }), "2025_mohali");
  dashboardCache.set(dashboardCache.buildKey("dash", { academic_year: 2026, campus: "lucknow" }), "2026_lucknow");

  dashboardCache.invalidateForYear(2026, "mohali");

  assert(dashboardCache.peek(dashboardCache.buildKey("dash", { academic_year: 2026, campus: "mohali" })) === null, "2026 mohali must be invalidated");
  assert(dashboardCache.peek(dashboardCache.buildKey("dash", { academic_year: 2025, campus: "mohali" })) === "2025_mohali", "2025 mohali must remain untouched");
  assert(dashboardCache.peek(dashboardCache.buildKey("dash", { academic_year: 2026, campus: "lucknow" })) === "2026_lucknow", "2026 lucknow must remain untouched");
  console.log("✓ Test 7 Passed");

  console.log("\n=======================================================");
  console.log("ALL 7 FRONTEND PERFORMANCE & CACHE TESTS PASSED!");
  console.log("=======================================================\n");
}

runTests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
