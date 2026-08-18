from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _calculate_year(
    db: Session,
    year: int,
) -> list[dict[str, Any]]:
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
                enquiry_id,
                COUNT(DISTINCT registration_id) AS cucet_count
            FROM organization.cucet_registrations
            WHERE registration_date >= :start_date
              AND registration_date < :end_date
            GROUP BY enquiry_id
        ),

        admission_by_enquiry AS (
            SELECT
                enquiry_id,
                COUNT(DISTINCT admission_id) AS admission_count
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
                    WHEN cb.cucet_count > 0
                    THEN lb.enquiry_id
                END
            ) AS cucet,

            COUNT(
                DISTINCT CASE
                    WHEN ab.admission_count > 0
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
            leads DESC,
            admission DESC,
            lb.main_source,
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

    return [
        dict(row)
        for row in rows
    ]


def _percentage(
    numerator: int,
    denominator: int,
) -> float | None:

    if denominator == 0:
        return None

    return round(
        (numerator / denominator) * 100,
        2,
    )


def calculate_source_performance(
    db: Session,
    year: int,
) -> list[dict[str, Any]]:
    """
    Compare current year with previous year
    for every source.

    Also identifies high-lead / low-conversion
    sources.
    """

    current = _calculate_year(
        db,
        year,
    )

    previous = _calculate_year(
        db,
        year - 1,
    )

    previous_map = {
        (
            row["main_source"],
            row["source"],
        ): row
        for row in previous
    }

    results = []

    current_map = {
        (
            row["main_source"],
            row["source"],
        ): row
        for row in current
    }

    all_keys = set(
        current_map.keys()
    ) | set(
        previous_map.keys()
    )

    for key in all_keys:

        row = current_map.get(
            key,
            {
                "main_source": key[0],
                "source": key[1],
                "leads": 0,
                "cucet": 0,
                "admission": 0,
            },
        )

        previous_row = previous_map.get(
            key,
            {
                "leads": 0,
                "cucet": 0,
                "admission": 0,
            },
        )

        leads = int(
            row["leads"]
        )

        cucet = int(
            row["cucet"]
        )

        admission = int(
            row["admission"]
        )

        previous_leads = int(
            previous_row["leads"]
        )

        previous_cucet = int(
            previous_row["cucet"]
        )

        previous_admission = int(
            previous_row["admission"]
        )

        lead_admission_percent = (
            _percentage(
                admission,
                leads,
            )
        )

        previous_lead_admission_percent = (
            _percentage(
                previous_admission,
                previous_leads,
            )
        )

        if leads >= 1 and (
            lead_admission_percent is not None
            and lead_admission_percent < 20
        ):
            performance_flag = (
                "high_leads_low_conversion"
            )

        elif (
            lead_admission_percent is not None
            and lead_admission_percent >= 50
        ):
            performance_flag = "strong"

        else:
            performance_flag = "normal"

        if previous_leads == 0 and leads > 0:
            growth_status = "new_source"

        elif previous_leads > 0 and leads == 0:
            growth_status = "dropped"

        elif leads > previous_leads:
            growth_status = "increased"

        elif leads < previous_leads:
            growth_status = "decreased"

        else:
            growth_status = "unchanged"

        results.append(
            {
                "main_source": row[
                    "main_source"
                ],
                "source": row[
                    "source"
                ],

                "current_year": year,
                "previous_year": year - 1,

                "current": {
                    "leads": leads,
                    "cucet": cucet,
                    "admission": admission,
                    "lead_cucet_percent": (
                        _percentage(
                            cucet,
                            leads,
                        )
                    ),
                    "lead_admission_percent": (
                        lead_admission_percent
                    ),
                    "cucet_admission_percent": (
                        _percentage(
                            admission,
                            cucet,
                        )
                    ),
                },

                "previous": {
                    "leads": previous_leads,
                    "cucet": previous_cucet,
                    "admission": previous_admission,
                    "lead_cucet_percent": (
                        _percentage(
                            previous_cucet,
                            previous_leads,
                        )
                    ),
                    "lead_admission_percent": (
                        previous_lead_admission_percent
                    ),
                    "cucet_admission_percent": (
                        _percentage(
                            previous_admission,
                            previous_cucet,
                        )
                    ),
                },

                "lead_growth_percent": (
                    _percentage(
                        leads - previous_leads,
                        previous_leads,
                    )
                    if previous_leads
                    else None
                ),

                "admission_growth_percent": (
                    _percentage(
                        admission - previous_admission,
                        previous_admission,
                    )
                    if previous_admission
                    else None
                ),

                "performance_flag": performance_flag,
                "growth_status": growth_status,
            }
        )

    return results