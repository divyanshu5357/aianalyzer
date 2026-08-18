from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _year_range(year: int) -> tuple[str, str]:
    """
    Return inclusive start and exclusive end dates
    for a calendar year.
    """

    return (
        f"{year}-01-01",
        f"{year + 1}-01-01",
    )


def _count_metric(
    db: Session,
    table: str,
    identifier_column: str,
    date_column: str,
    year: int,
) -> int:
    """
    Count records for a metric in a given year.
    """

    start_date, end_date = _year_range(year)

    query = text(
        f"""
        SELECT COUNT("{identifier_column}") AS metric_value
        FROM "organization"."{table}"
        WHERE "{date_column}" >= :start_date
          AND "{date_column}" < :end_date
        """
    )

    result = db.execute(
        query,
        {
            "start_date": start_date,
            "end_date": end_date,
        },
    ).mappings().one()

    return int(
        result["metric_value"] or 0
    )


def calculate_funnel(
    db: Session,
    current_year: int,
) -> dict[str, Any]:
    """
    Calculate PY/CY funnel metrics.

    Funnel:

        Leads
          ↓
        CUCET
          ↓
        Admission
    """

    previous_year = current_year - 1

    # --------------------------------------------------
    # Current Year
    # --------------------------------------------------

    cy_leads = _count_metric(
        db=db,
        table="enquiries",
        identifier_column="enquiry_id",
        date_column="enquiry_date",
        year=current_year,
    )

    cy_cucet = _count_metric(
        db=db,
        table="cucet_registrations",
        identifier_column="registration_id",
        date_column="registration_date",
        year=current_year,
    )

    cy_admission = _count_metric(
        db=db,
        table="admissions",
        identifier_column="admission_id",
        date_column="admission_date",
        year=current_year,
    )

    # --------------------------------------------------
    # Previous Year
    # --------------------------------------------------

    py_leads = _count_metric(
        db=db,
        table="enquiries",
        identifier_column="enquiry_id",
        date_column="enquiry_date",
        year=previous_year,
    )

    py_cucet = _count_metric(
        db=db,
        table="cucet_registrations",
        identifier_column="registration_id",
        date_column="registration_date",
        year=previous_year,
    )

    py_admission = _count_metric(
        db=db,
        table="admissions",
        identifier_column="admission_id",
        date_column="admission_date",
        year=previous_year,
    )

    # --------------------------------------------------
    # Conversion rates
    # --------------------------------------------------

    lead_cucet_rate = (
        cy_cucet / cy_leads * 100
        if cy_leads
        else 0
    )

    lead_admission_rate = (
        cy_admission / cy_leads * 100
        if cy_leads
        else 0
    )

    cucet_admission_rate = (
        cy_admission / cy_cucet * 100
        if cy_cucet
        else 0
    )

    # --------------------------------------------------
    # Year-over-year changes
    # --------------------------------------------------

    def percentage_change(
        current: int,
        previous: int,
    ) -> float | None:

        if previous == 0:
            return None

        return (
            (current - previous)
            / previous
        ) * 100

    return {
        "current_year": current_year,
        "previous_year": previous_year,

        "current_year_funnel": {
            "leads": cy_leads,
            "cucet": cy_cucet,
            "admission": cy_admission,
        },

        "previous_year_funnel": {
            "leads": py_leads,
            "cucet": py_cucet,
            "admission": py_admission,
        },

        "conversion_rates": {
            "lead_cucet_percent": round(
                lead_cucet_rate,
                2,
            ),
            "lead_admission_percent": round(
                lead_admission_rate,
                2,
            ),
            "cucet_admission_percent": round(
                cucet_admission_rate,
                2,
            ),
        },

        "year_over_year_change": {
            "leads_percent": percentage_change(
                cy_leads,
                py_leads,
            ),
            "cucet_percent": percentage_change(
                cy_cucet,
                py_cucet,
            ),
            "admission_percent": percentage_change(
                cy_admission,
                py_admission,
            ),
        },
    }
