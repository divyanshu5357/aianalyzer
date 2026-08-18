import re
from copy import deepcopy
from typing import Any


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


def is_missing(value: Any) -> bool:
    """
    Determine whether a value should be treated as missing.
    """

    if value is None:
        return True

    if isinstance(value, str):
        return value.strip() == ""

    return False


def normalize_string(value: Any) -> Any:
    """
    Remove unnecessary whitespace from strings.
    """

    if not isinstance(value, str):
        return value

    cleaned = value.strip()

    if cleaned == "":
        return None

    return cleaned


def validate_email(
    column_name: str,
    value: Any,
) -> str | None:

    if value is None:
        return None

    column_lower = column_name.lower()

    if "email" not in column_lower:
        return None

    if not isinstance(value, str):
        return "invalid_email"

    if not EMAIL_PATTERN.match(value.strip()):
        return "invalid_email"

    return None


def clean_record(
    record: dict,
) -> tuple[dict, list[dict]]:

    cleaned_record = deepcopy(record)

    issues = []

    for column, value in record.items():

        # -----------------------------
        # Missing values
        # -----------------------------

        if is_missing(value):

            cleaned_record[column] = None

            issues.append(
                {
                    "type": "missing_value",
                    "column": column,
                    "original_value": value,
                    "severity": "warning",
                }
            )

            continue

        # -----------------------------
        # Normalize strings
        # -----------------------------

        normalized_value = normalize_string(
            value
        )

        if normalized_value != value:

            cleaned_record[column] = (
                normalized_value
            )

            issues.append(
                {
                    "type": "whitespace_normalized",
                    "column": column,
                    "original_value": value,
                    "cleaned_value": normalized_value,
                    "severity": "info",
                }
            )

        # -----------------------------
        # Email validation
        # -----------------------------

        email_issue = validate_email(
            column,
            normalized_value,
        )

        if email_issue:

            issues.append(
                {
                    "type": email_issue,
                    "column": column,
                    "original_value": value,
                    "severity": "error",
                }
            )

    return cleaned_record, issues