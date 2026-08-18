from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def calculate_source_detail(
    db: Session,
    year: int,
    main_source: str,
    source: str,
) -> dict[str, Any] | None:

    query = text(
        """
        WITH lead_base AS (
            SELECT
                enquiry_id
            FROM organization.enquiries
            WHERE enquiry_date >= :start_date
              AND enquiry_date < :end_date
              AND LOWER(main_source) = LOWER(:main_source)
              AND LOWER(source) = LOWER(:source)
        ),

        cucet_base AS (
            SELECT DISTINCT
                enquiry_id
            FROM organization.cucet_registrations
            WHERE registration_date >= :start_date
              AND registration_date < :end_date
        ),

        admission_base AS (
            SELECT DISTINCT
                enquiry_id
            FROM organization.admissions
            WHERE admission_date >= :start_date
              AND admission_date < :end_date
        )

        SELECT
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

        LEFT JOIN cucet_base cb
            ON cb.enquiry_id = lb.enquiry_id

        LEFT JOIN admission_base ab
            ON ab.enquiry_id = lb.enquiry_id
        """
    )

    row = db.execute(
        query,
        {
            "start_date": f"{year}-01-01",
            "end_date": f"{year + 1}-01-01",
            "main_source": main_source,
            "source": source,
        },
    ).mappings().first()

    if row is None:
        return None

    leads = int(row["leads"] or 0)
    cucet = int(row["cucet"] or 0)
    admission = int(row["admission"] or 0)

    def percentage(
        numerator: int,
        denominator: int,
    ) -> float | None:

        if denominator == 0:
            return None

        return round(
            (numerator / denominator) * 100,
            2,
        )

    lead_cucet = percentage(
        cucet,
        leads,
    )

    lead_admission = percentage(
        admission,
        leads,
    )

    cucet_admission = percentage(
        admission,
        cucet,
    )

    if leads > 0 and admission == 0:
        performance = (
            "high_leads_low_conversion"
        )

    elif (
        lead_admission is not None
        and lead_admission >= 50
    ):
        performance = "strong"

    else:
        performance = "normal"

    return {
        "year": year,
        "main_source": main_source,
        "source": source,

        "funnel": {
            "leads": leads,
            "cucet": cucet,
            "admission": admission,
        },

        "conversion": {
            "lead_cucet_percent": lead_cucet,
            "lead_admission_percent": lead_admission,
            "cucet_admission_percent": (
                cucet_admission
            ),
        },

        "performance": performance,
    }