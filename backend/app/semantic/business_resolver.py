import re


def resolve_business_metric(
    column_name: str,
) -> dict | None:

    name = column_name.lower().strip()

    # --------------------------------------------------
    # CY Lead - Admission%
    # --------------------------------------------------

    if (
        re.search(r"\bcy\b", name)
        and "lead" in name
        and "admission" in name
        and "%" in name
    ):
        return {
            "concept_key": "lead_admission_rate",
            "time_context": "current_year",
            "data_role": "metric",
        }

    # --------------------------------------------------
    # CY Lead - CUCET%
    # --------------------------------------------------

    if (
        re.search(r"\bcy\b", name)
        and "lead" in name
        and "cucet" in name
        and "%" in name
    ):
        return {
            "concept_key": "lead_cucet_rate",
            "time_context": "current_year",
            "data_role": "metric",
        }

    # --------------------------------------------------
    # CY CUCET-Admission%
    # --------------------------------------------------

    if (
        re.search(r"\bcy\b", name)
        and "cucet" in name
        and "admission" in name
        and "%" in name
    ):
        return {
            "concept_key": "cucet_admission_rate",
            "time_context": "current_year",
            "data_role": "metric",
        }

    # --------------------------------------------------
    # PY/CY + Leads
    # --------------------------------------------------

    if "lead" in name:

        if re.search(r"\bpy\b", name):
            return {
                "concept_key": "leads",
                "time_context": "previous_year",
                "data_role": "metric",
            }

        if re.search(r"\bcy\b", name):
            return {
                "concept_key": "leads",
                "time_context": "current_year",
                "data_role": "metric",
            }

    # --------------------------------------------------
    # PY/CY + CUCET
    # --------------------------------------------------

    if "cucet" in name:

        if re.search(r"\bpy\b", name):
            return {
                "concept_key": "cucet",
                "time_context": "previous_year",
                "data_role": "metric",
            }

        if re.search(r"\bcy\b", name):
            return {
                "concept_key": "cucet",
                "time_context": "current_year",
                "data_role": "metric",
            }

    # --------------------------------------------------
    # PY/CY + Admission
    # --------------------------------------------------

    if (
        "admission" in name
        or re.search(r"\badm\b", name)
    ):

        if re.search(r"\bpy\b", name):
            return {
                "concept_key": "admission",
                "time_context": "previous_year",
                "data_role": "metric",
            }

        if re.search(r"\bcy\b", name):
            return {
                "concept_key": "admission",
                "time_context": "current_year",
                "data_role": "metric",
            }

    return None