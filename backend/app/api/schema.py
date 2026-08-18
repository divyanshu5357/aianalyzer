from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.schema_discovery import (
    discover_schema,
)


router = APIRouter(
    prefix="/api/schema",
    tags=["Schema Discovery"],
)


@router.get("/organization")
def get_organization_schema(
    db: Session = Depends(get_db),
):
    return discover_schema(db)