from typing import Any


METRIC_SOURCES: dict[str, dict[str, Any]] = {

    "leads": {
        "table": "enquiries",
        "schema": "organization",
        "identifier_column": "enquiry_id",
        "date_column": "enquiry_date",
        "dimension_columns": [
            "program_name",
            "campus_name",
            "cluster",
            "state",
            "source",
            "main_source",
            "lead_type",
        ],
    },

    "cucet": {
        "table": "cucet_registrations",
        "schema": "organization",
        "identifier_column": "registration_id",
        "date_column": "registration_date",
        "dimension_columns": [
            "program_name",
            "campus_name",
        ],
    },

    "admission": {
        "table": "admissions",
        "schema": "organization",
        "identifier_column": "admission_id",
        "date_column": "admission_date",
        "dimension_columns": [
            "program_name",
            "campus_name",
            "cluster",
            "state",
            "admission_status",
        ],
    },
}