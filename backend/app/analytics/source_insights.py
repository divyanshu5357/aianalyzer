from typing import Any


def build_source_insights(
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Convert source-performance rows into
    business-friendly insights.
    """

    insights = []

    strong_sources = []
    weak_sources = []
    new_sources = []
    dropped_sources = []

    for row in source_rows:

        main_source = row["main_source"]
        source = row["source"]

        current = row["current"]
        flag = row["performance_flag"]
        growth_status = row["growth_status"]

        lead_admission = (
            current["lead_admission_percent"]
        )

        leads = current["leads"]
        admission = current["admission"]

        source_name = (
            f"{main_source} / {source}"
        )

        # ------------------------------------------
        # High leads but poor conversion
        # ------------------------------------------

        if flag == "high_leads_low_conversion":

            weak_sources.append(
                source_name
            )

            insights.append(
                {
                    "type": "high_leads_low_conversion",
                    "main_source": main_source,
                    "source": source,
                    "severity": "high",
                    "message": (
                        f"{source_name} generated "
                        f"{leads} leads but only "
                        f"{admission} admissions."
                    ),
                    "lead_admission_percent": (
                        lead_admission
                    ),
                }
            )

        # ------------------------------------------
        # Strong source
        # ------------------------------------------

        elif flag == "strong":

            strong_sources.append(
                source_name
            )

        # ------------------------------------------
        # New source
        # ------------------------------------------

        if growth_status == "new_source":

            new_sources.append(
                source_name
            )

            insights.append(
                {
                    "type": "new_source",
                    "main_source": main_source,
                    "source": source,
                    "severity": "info",
                    "message": (
                        f"{source_name} is a new "
                        f"source compared with the "
                        f"previous year."
                    ),
                }
            )

        # ------------------------------------------
        # Dropped source
        # ------------------------------------------

        if growth_status == "dropped":

            dropped_sources.append(
                source_name
            )

            insights.append(
                {
                    "type": "dropped_source",
                    "main_source": main_source,
                    "source": source,
                    "severity": "high",
                    "message": (
                        f"{source_name} generated "
                        f"leads in the previous year "
                        f"but none in the current year."
                    ),
                }
            )

    return {
        "summary": {
            "total_sources": len(
                source_rows
            ),
            "strong_sources": len(
                strong_sources
            ),
            "weak_sources": len(
                weak_sources
            ),
            "new_sources": len(
                new_sources
            ),
            "dropped_sources": len(
                dropped_sources
            ),
        },
        "strong_sources": strong_sources,
        "weak_sources": weak_sources,
        "new_sources": new_sources,
        "dropped_sources": dropped_sources,
        "insights": insights,
    }
