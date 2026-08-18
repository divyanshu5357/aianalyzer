from sqlalchemy import text
from sqlalchemy.orm import Session


def discover_tables(
    db: Session,
) -> list[dict]:
    """
    Discover tables available in the
    organization schema.
    """

    query = text(
        """
        SELECT
            table_schema,
            table_name
        FROM information_schema.tables
        WHERE table_schema = 'organization'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )

    rows = db.execute(query).mappings().all()

    return [
        {
            "schema": row["table_schema"],
            "table": row["table_name"],
        }
        for row in rows
    ]


def discover_columns(
    db: Session,
    table_name: str,
) -> list[dict]:
    """
    Discover columns for a specific
    organization table.
    """

    query = text(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'organization'
          AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )

    rows = db.execute(
        query,
        {
            "table_name": table_name,
        },
    ).mappings().all()

    return [
        {
            "column": row["column_name"],
            "data_type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
            "position": row["ordinal_position"],
        }
        for row in rows
    ]


def discover_schema(
    db: Session,
) -> dict:
    """
    Discover the complete organization
    database schema.
    """

    tables = discover_tables(db)

    result = []

    for table in tables:

        columns = discover_columns(
            db,
            table["table"],
        )

        result.append(
            {
                "schema": table["schema"],
                "table": table["table"],
                "columns": columns,
            }
        )

    return {
        "schema": "organization",
        "tables": result,
    }