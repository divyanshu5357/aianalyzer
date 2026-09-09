from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import get_db


router = APIRouter()


@router.get("/health")
@router.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    value = result.scalar()

    from app.storage.service import get_storage_provider
    from app.storage.s3_r2_provider import S3R2StorageProvider
    from app.database.connection import engine

    provider = get_storage_provider()
    is_s3 = isinstance(provider, S3R2StorageProvider)
    storage_type = "s3" if is_s3 else "local"

    # Safely extract host without exposing credentials, username, or password
    db_host = engine.url.host if engine and hasattr(engine, "url") and engine.url else "unknown"
    db_driver = engine.url.drivername if engine and hasattr(engine, "url") and engine.url else "postgresql"

    return {
        "status": "healthy",
        "database": "connected",
        "database_host": db_host,
        "database_type": db_driver,
        "storage_provider": storage_type,
        "storage_bucket": getattr(provider, "bucket", "local"),
        "test": value,
    }