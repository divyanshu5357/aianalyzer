from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def calculate_source_hierarchy(
    db: Session,
    year: int,
) -> list[dict[str, Any]]:
    """
    Return source hierarchy with funnel performance.

    Current hierarchy:
        main_source -> source

    Example:
        Digital -> Google
        Digital -> Facebook
        Organic -> Website
        Offline -> Education Fair
    """

    query = text(
        """
        WITH lead_base AS (
            SELECT
                enquiry_id,
                main_source,
                source
            FROM organization.enquiries
            WHERE enquiry_date >= :start_date
              AND enquiry_date < :end_date
        ),

        cucet_by_enquiry AS (
            SELECT
                enquiry_id
            FROM organization.cucet_registrations
            WHERE registration_date >= :start_date
              AND registration_date < :end_date
            GROUP BY enquiry_id
        ),

        admission_by_enquiry AS (
            SELECT
                enquiry_id
            FROM organization.admissions
            WHERE admission_date >= :start_date
              AND admission_date < :end_date
            GROUP BY enquiry_id
        )

        SELECT
            lb.main_source,
            lb.source,

            COUNT(DISTINCT lb.enquiry_id) AS leads,

            COUNT(
                DISTINCT CASE
                    WHEN cb.enquiry_id IS NOT NULL
                    THEN lb.enquiry_id
                END
            ) AS cucet,

            COUNT(
                DISTINCT CASE
                    WHEN ab.enquiry_id IS NOT NULL
                    THEN lb.enquiry_id
                END
            ) AS admission

        FROM lead_base lb

        LEFT JOIN cucet_by_enquiry cb
            ON cb.enquiry_id = lb.enquiry_id

        LEFT JOIN admission_by_enquiry ab
            ON ab.enquiry_id = lb.enquiry_id

        GROUP BY
            lb.main_source,
            lb.source

        ORDER BY
            lb.main_source,
            leads DESC,
            lb.source;
        """
    )

    rows = db.execute(
        query,
        {
            "start_date": f"{year}-01-01",
            "end_date": f"{year + 1}-01-01",
        },
    ).mappings().all()

    result = []

    for row in rows:

        leads = int(row["leads"])
        cucet = int(row["cucet"])
        admission = int(row["admission"])

        lead_cucet = (
            round(cucet / leads * 100, 2)
            if leads
            else None
        )

        lead_admission = (
            round(admission / leads * 100, 2)
            if leads
            else None
        )

        cucet_admission = (
            round(admission / cucet * 100, 2)
            if cucet
            else None
        )

        if leads > 0 and lead_admission is not None:
            if lead_admission < 20:
                performance = "high_leads_low_conversion"
            elif lead_admission >= 50:
                performance = "strong"
            else:
                performance = "normal"
        else:
            performance = "normal"

        result.append(
            {
                "main_source": row["main_source"],
                "source": row["source"],
                "year": year,
                "leads": leads,
                "cucet": cucet,
                "admission": admission,
                "conversion": {
                    "lead_cucet_percent": lead_cucet,
                    "lead_admission_percent": lead_admission,
                    "cucet_admission_percent": cucet_admission,
                },
                "performance": performance,
            }
        )

    return result
