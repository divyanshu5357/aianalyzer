from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import get_db


router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    value = result.scalar()

    return {
        "status": "healthy",
        "database": "connected",
        "test": value,
    }