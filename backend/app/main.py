from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.cleaning import router as cleaning_router
from app.api.health import router as health_router
from app.api.upload import router as upload_router
from app.api.semantic import router as semantic_router
from app.api.schema import router as schema_router
from app.api.physical import router as physical_router
from app.api.relationships import router as relationships_router
from app.api.chat import router as chat_router
from app.api.analytics import router as analytics_router
from app.api.source_insights import (router as source_insights_router,)
from app.api.source_hierarchy import (router as source_hierarchy_router,)
from app.api.dashboard import router as dashboard_router
from app.api.periods import router as periods_router
from app.api.data_management import router as data_management_router
from app.api.audit import router as audit_router
from app.database.connection import SessionLocal
from app.database.ai_audit import ensure_ai_audit_tables, seed_initial_golden_cases
from app.database.schema_init import ensure_all_database_tables

from app.config.settings import settings

app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-powered organizational "
        "data and analytics agent"
    ),
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    try:
        with SessionLocal() as db:
            ensure_all_database_tables(db)
            ensure_ai_audit_tables(db)
            seed_initial_golden_cases(db)
    except Exception as e:
        print(f"Startup database initialization warning: {e}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://aianalyzer-nine.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin")
    headers = {}
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=headers,
    )




app.include_router(
    health_router
)

app.include_router(
    upload_router
)

app.include_router(
    cleaning_router
)

app.include_router(
    semantic_router
)

app.include_router(
    schema_router
)

app.include_router(
    physical_router
)

app.include_router(
    relationships_router
)

app.include_router(
    chat_router
)

app.include_router(
    analytics_router
)
app.include_router(
    source_insights_router
)
app.include_router(
    source_hierarchy_router
)
app.include_router(
    dashboard_router
)
app.include_router(
    periods_router
)
app.include_router(
    data_management_router
)
app.include_router(
    audit_router
)
@app.get("/")
def root():

    return {
        "application": settings.app_name,
        "status": "running",
        "version": "0.1.0",
    }