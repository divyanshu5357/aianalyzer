import logging
import threading

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError, TimeoutError
from app.api.cleaning import router as cleaning_router
from app.api.health import router as health_router
from app.api.upload import router as upload_router
from app.api.semantic import router as semantic_router
from app.api.schema import router as schema_router
from app.api.physical import router as physical_router
from app.api.relationships import router as relationships_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.periods import router as periods_router
from app.api.data_management import router as data_management_router
from app.api.audit import router as audit_router
from app.api.ml_predictions import router as ml_predictions_router
from app.api.graph import router as graph_router
from app.api.mapping import router as mapping_router
from app.api.targets import router as targets_router
from app.api.counsellor import router as counsellor_router
from app.api.conversations import router as conversations_router
from app.api.programs import router as programs_router
from app.api.states import router as states_router
from app.database.connection import SessionLocal, get_db
from app.database.ai_audit import ensure_ai_audit_tables, seed_initial_golden_cases
from app.database.schema_init import ensure_all_database_tables

from app.config.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-powered organizational "
        "data and analytics agent"
    ),
    version="0.1.0",
)


def _is_db_initialized() -> bool:
    try:
        with SessionLocal() as db:
            row = db.execute(text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'system' AND table_name = 'datasets' LIMIT 1;")).scalar()
            return bool(row)
    except Exception as e:
        logger.warning("Could not check if DB is initialized: %s", e)
        return False


def _run_background_warmup():
    """Asynchronously warm up core analytics, route endpoints, and filter caches on server startup."""
    import time
    time.sleep(1.0)
    logger.info("[WARMUP] Starting comprehensive background analytics cache pre-warming...")
    try:
        with SessionLocal() as db:
            # 1. Filter options
            try:
                from app.analytics.dashboard import get_dashboard_filter_options
                get_dashboard_filter_options(db)
                get_dashboard_filter_options(db, years=[2026])
                get_dashboard_filter_options(db, campus="Mohali", years=[2026])
                logger.info("[WARMUP] Filter options pre-warmed for default scopes.")
            except Exception as e:
                logger.warning("[WARMUP] Filter options warmup notice: %s", e)

            # 2. Scope years (2026, 2025)
            try:
                from app.analytics.period_helper import get_active_or_max_academic_year
                active_ay = get_active_or_max_academic_year(db) or 2026
                warmup_years = [active_ay]
                if active_ay - 1 >= 2025:
                    warmup_years.append(active_ay - 1)

                from app.api.dashboard import (
                    get_overview,
                    get_dashboard_insights,
                    get_dashboard_monthly_trend,
                    get_gender_admissions,
                    get_india_state_admissions,
                    get_outside_india_admissions,
                )
                from app.analytics.program_service import (
                    get_program_report_top_level,
                    get_program_insights,
                )
                from app.analytics.state_service import (
                    get_state_report_top_level,
                    get_state_hierarchy_children,
                )
                from app.analytics.counsellor_service import get_counsellors_list

                for ay in warmup_years:
                    # Overview & Insights (both with and without years param)
                    try:
                        get_overview(academic_year=ay, db=db)
                        get_overview(years=str(ay), academic_year=ay, db=db)
                        get_dashboard_insights(academic_year=ay, db=db)
                        get_dashboard_insights(years=str(ay), academic_year=ay, db=db)
                    except Exception as e:
                        logger.debug("[WARMUP] Overview/Insights AY=%s notice: %s", ay, e)

                    # Monthly Trends
                    for m in ("leads", "admissions", "cucet", "conversion_rate"):
                        try:
                            get_dashboard_monthly_trend(academic_year=ay, metric=m, db=db)
                            get_dashboard_monthly_trend(years=str(ay), academic_year=ay, metric=m, db=db)
                        except Exception:
                            pass

                    # State, Gender & International
                    try:
                        get_india_state_admissions(academic_year=ay, db=db)
                        get_india_state_admissions(years=str(ay), academic_year=ay, db=db)
                        get_gender_admissions(academic_year=ay, db=db)
                        get_gender_admissions(years=str(ay), academic_year=ay, db=db)
                        get_outside_india_admissions(academic_year=ay, db=db)
                        get_outside_india_admissions(years=str(ay), academic_year=ay, db=db)
                    except Exception as e:
                        logger.debug("[WARMUP] Geo/Gender AY=%s notice: %s", ay, e)

                    # Program Performance Report
                    try:
                        get_program_report_top_level(db, academic_year=ay)
                        get_program_insights(db, program_group="CSE", academic_year=ay)
                        get_program_insights(db, program_group="MBA", academic_year=ay)
                    except Exception as e:
                        logger.debug("[WARMUP] Program report AY=%s notice: %s", ay, e)

                    # State Report
                    try:
                        get_state_report_top_level(db, academic_year=ay)
                        get_state_hierarchy_children(db, level="source_category", state="PUNJAB", academic_year=ay)
                    except Exception as e:
                        logger.debug("[WARMUP] State report AY=%s notice: %s", ay, e)

                    # Counsellors
                    try:
                        get_counsellors_list(db, academic_year=ay)
                    except Exception as e:
                        logger.debug("[WARMUP] Counsellors AY=%s notice: %s", ay, e)

                    logger.info("[WARMUP] Full analytics stack pre-warmed for AY=%s.", ay)

            except Exception as e:
                logger.warning("[WARMUP] Analytics pre-warming notice: %s", e)

        logger.info("[WARMUP] Background cache pre-warming completed successfully! All pages ready for sub-10ms response.")
    except Exception as e:
        logger.error("[WARMUP] Background warmup error: %s", e)


@app.on_event("startup")
def on_startup():
    try:
        if not _is_db_initialized():
            logger.info("Initializing database tables for first-time setup...")
            with SessionLocal() as db:
                ensure_all_database_tables(db)
                ensure_ai_audit_tables(db)
                seed_initial_golden_cases(db)
    except Exception as e:
        logger.warning(f"Startup database initialization warning: {e}")

    # Launch warmup in daemon thread so port 8000 binds immediately!
    threading.Thread(target=_run_background_warmup, daemon=True).start()


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


@app.exception_handler(TimeoutError)
@app.exception_handler(DisconnectionError)
@app.exception_handler(InterfaceError)
@app.exception_handler(OperationalError)
async def database_unavailable_handler(request: Request, exc: Exception):
    """Return a safe, actionable response when PostgreSQL cannot be reached."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Database is unavailable. Start PostgreSQL and verify DATABASE_URL, "
                "then retry the request."
            )
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Avoid exposing internal exception details to API clients."""
    logger.exception("Unhandled request error for %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected server error. Check the backend logs for details."},
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
app.include_router(
    ml_predictions_router
)
app.include_router(
    graph_router
)
app.include_router(
    mapping_router
)
app.include_router(
    targets_router
)
app.include_router(
    counsellor_router
)
app.include_router(
    conversations_router
)
app.include_router(
    programs_router
)
app.include_router(
    states_router
)
@app.get("/")
def root():

    return {
        "application": settings.app_name,
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/api/data-control/history", tags=["Data Control"])
def legacy_data_control_history(db: Session = Depends(get_db)):
    """Convenience alias for /api/dashboard/data-control."""
    from app.api.dashboard import get_data_control_history
    return get_data_control_history(db=db)

