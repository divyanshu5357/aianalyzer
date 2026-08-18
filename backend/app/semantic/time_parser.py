import re


def detect_time_context(column_name: str) -> str | None:
    """
    Detect temporal meaning from a column name.

    Examples:

        PY Leads
        -> previous_year

        CY Leads
        -> current_year

        Admission 2024
        -> 2024

        Penetration 2026
        -> 2026
    """

    name = column_name.lower().strip()

    # Previous Year
    if re.search(r"\bpy\b", name):
        return "previous_year"

    # Current Year
    if re.search(r"\bcy\b", name):
        return "current_year"

    # Explicit year
    year_match = re.search(
        r"\b(20\d{2})\b",
        name,
    )

    if year_match:
        return year_match.group(1)

    return None