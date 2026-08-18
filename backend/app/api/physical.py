from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.schema_discovery import (
    discover_schema,
)
from app.semantic.physical_mapper import (
    discover_physical_candidates,
)


router = APIRouter(
    prefix="/api/physical",
    tags=["Physical Mapping"],
)


@router.get("/discover")
def discover_physical_mapping(
    db: Session = Depends(get_db),
):

    schema_info = discover_schema(
        db
    )

    concepts = [
        "leads",
        "cucet",
        "admission",
        "program",
        "campus",
        "state",
    ]

    mappings = (
        discover_physical_candidates(
            schema_info,
            concepts,
        )
    )

    return {
        "schema": "organization",
        "concepts": concepts,
        "mappings": mappings,
    }