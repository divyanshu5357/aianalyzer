🔴 Phase A — Dynamic/Data Audit
Scan entire frontend for hardcoded business/data values
Scan backend for hardcoded years/campuses/states/sources
Remove them
Verify all metrics originate from PostgreSQL
Verify target uses current year
Verify one target master
Verify one dimension master
🔴 Phase B — Performance
Fix 404
Fix infinite/loading requests
Implement lazy Program hierarchy
Implement lazy State hierarchy
Simplify Counsellor page
Audit duplicate API calls
Split api.ts
Check PostgreSQL query plans
Clean Docker storage safely
🟠 Phase C — Dashboard Completion
Global From/To date
Dynamic Gender monthly chart
Dynamic India state map
Verify every dashboard number changes with data
🟠 Phase D — ML
Keep 2026_canonical_v2
Collect more historical data
Build canonical training dataset pipeline
Retrain when sufficient historical data exists
Compare candidate vs production
Promote only if governance thresholds pass
🟢 Phase E — Final Client QA
Fresh database/data test
Upload 2025
Upload 2026
Replace 2026
Delete 2026
Re-upload
Change dates
Change campus
Test Programs
Test States
Test Counsellors
Test AI
Test Reports
Test exports
Test ML
Test with large dataset
Final security check
Client demo