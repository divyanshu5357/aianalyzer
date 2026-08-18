from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.schema_discovery import discover_schema
from app.semantic.relationship_discovery import discover_relationships
from app.semantic.relationship_registry import save_relationships


router = APIRouter(
    prefix="/api/relationships",
    tags=["Relationships"],
)


@router.get("/{schema_name}")
def get_relationships(
    schema_name: str,
    db: Session = Depends(get_db),
):
    """
    Discover, validate, and save relationships
    between tables inside the organization schema.
    """

    # Currently schema discovery is specifically
    # implemented for the organization schema.
    if schema_name != "organization":
        raise HTTPException(
            status_code=400,
            detail="Only the organization schema is supported currently.",
        )

    try:
        # --------------------------------------------------
        # 1. Discover physical database schema
        # --------------------------------------------------

        schema_info = discover_schema(db)

        # --------------------------------------------------
        # 2. Discover candidate relationships
        # --------------------------------------------------

        relationships = discover_relationships(
            schema_info
        )

        # --------------------------------------------------
        # 3. Validate + save relationships
        # --------------------------------------------------

        saved_count = save_relationships(
            db,
            relationships,
        )

        # --------------------------------------------------
        # 4. Return results
        # --------------------------------------------------

        return {
            "schema": schema_name,
            "relationships": relationships,
            "candidate_count": len(
                relationships
            ),
            "saved_count": saved_count,
        }

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Relationship discovery failed: {exc}",
        )