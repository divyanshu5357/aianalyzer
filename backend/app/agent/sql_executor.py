from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def execute_query(
    db: Session,
    sql: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Execute a generated read-only SQL query.

    Supports:
        SELECT ...
        WITH ... SELECT ...
    """

    parameters = parameters or {}

    # --------------------------------------------------
    # Basic read-only protection
    # --------------------------------------------------

    normalized = sql.strip().lower()

    forbidden = [
        "insert ",
        "update ",
        "delete ",
        "drop ",
        "alter ",
        "truncate ",
        "create ",
        "grant ",
        "revoke ",
    ]

    for keyword in forbidden:

        if keyword in normalized:

            raise ValueError(
                "Only read-only SQL queries "
                "are allowed."
            )

    # --------------------------------------------------
    # Allow SELECT and CTE queries
    # --------------------------------------------------

    if not (
        normalized.startswith("select")
        or normalized.startswith("with")
    ):

        raise ValueError(
            "Only SELECT queries are allowed."
        )

    # --------------------------------------------------
    # Execute query
    # --------------------------------------------------

    result = db.execute(
        text(sql),
        parameters,
    )

    rows = result.mappings().all()

    return [
        dict(row)
        for row in rows
    ]