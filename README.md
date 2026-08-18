                    ┌─────────────────────┐
                    │      Next.js        │
                    │   Chat + Dashboard  │
                    │   Voice Interface   │
                    └──────────┬──────────┘
                               │
                            REST API
                               │
                               ▼
                    ┌─────────────────────┐
                    │      FastAPI        │
                    │   Backend / API     │
                    └──────────┬──────────┘
                               │
                         ┌─────┴─────┐
                         │ AI AGENT  │
                         └─────┬─────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
       SQL ANALYST          RAG AGENT         ML ENGINE
            │                  │                  │
            │                  │            ┌─────┴─────┐
            │                  │            │ XGBoost   │
            │                  │            │ SHAP      │
            │                  │            │ Forecast  │
            │                  │            └───────────┘
            │                  │
            ▼                  ▼
       PostgreSQL          pgvector
            │
            │
     ┌──────┴────────┐
     │               │
     ▼               ▼
 RAW DATA       CLEAN DATA

 ✅ Data ingestion
✅ Profiling
✅ Staging
✅ Cleaning
✅ Semantic inference
✅ Semantic registry

| Component                  | Status now                   | What remains                                             |
| -------------------------- | ---------------------------- | -------------------------------------------------------- |
| Metric definitions         | 🟡 Partial                   | Central metric registry + consistent definitions         |
| Time-context understanding | 🟢 **Done for 2-year model** | Must extend to arbitrary historical periods              |
| Business aliases           | 🟡 Partial                   | Better fuzzy/entity aliases: `B.E CSE` → actual program  |
| Canonical entities         | 🟢 Mostly done               | Strengthen cross-year/entity resolution                  |
| SQL planner                | 🟢 **Done**                  | Local + Gemini fallback                                  |
| SQL generation             | 🟢 **Done**                  | Tool-based                                               |
| SQL safety/validation      | 🟢 **Done**                  | Canonical validation                                     |
| Result interpretation      | 🟢 **Done**                  | Grounded results                                         |
| Chat agent                 | 🟢 Mostly done               | Driver analysis + better clarification/entity resolution |
| Voice input                | 🔴 Not started               | Later                                                    |
| Voice output               | 🔴 Not started               | Later                                                    |
| Prediction                 | 🔴 Not started               | Later                                                    |
| SHAP/XGBoost               | 🔴 Not started               | After prediction                                         |
| Frontend                   | 🟡 **In progress**           | Workspace separation, stability, historical UI           |
| Client SQL connector       | 🔴 Not started               | Later                                                    |
✅ Agent hardening
🟡 Metric Registry + Entity Resolution
⬜ Historical multi-year data model        ← NEXT
⬜ Upload period detection
⬜ Year/version/conflict management
⬜ Multi-year analytics
⬜ 5M/10M+ historical benchmark
⬜ Analytics workspace refinement
⬜ Comparison workspace
⬜ Driver/reason analysis
⬜ Multi-year Dashboard trends
⬜ Program/Specialization hierarchy
⬜ Detail views
⬜ Prediction / ML
⬜ SHAP/XGBoost
⬜ Voice
⬜ Client SQL connector