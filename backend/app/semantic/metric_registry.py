"""
Central Business Metric Registry
Defines canonical business semantics, source fields, aggregation rules, and definitions
for all institutional KPIs across RAW, DIMENSION, and TARGET datasets.
Supports both object property access and dictionary subscripting for full backward compatibility.
"""
from typing import Any, Dict, List, Optional


class MetricDefinition(dict):
    """
    MetricDefinition extends dict for backward compatibility with dictionary subscript access metric_spec["is_ratio"],
    while providing clean attribute access defn.metric_key.
    """
    def __init__(
        self,
        metric_key: str,
        display_name: str,
        synonyms: List[str],
        source_workbook_type: str,
        source_fields: List[str],
        date_field: str,
        aggregation: str,
        description: str,
        column: str = "cy_admission",
        sql_expression: str = "SUM(a.cy_admission)",
        is_ratio: bool = False,
        numerator: Optional[str] = None,
        denominator: Optional[str] = None,
        status: str = "CONFIRMED",
        confidence_score: float = 1.0,
        filters: Optional[Dict[str, Any]] = None,
    ):
        dict_data = {
            "metric_key": metric_key,
            "name": display_name,
            "display_name": display_name,
            "synonyms": synonyms,
            "source_workbook_type": source_workbook_type,
            "source_fields": source_fields,
            "date_field": date_field,
            "aggregation": aggregation,
            "description": description,
            "column": column,
            "sql_expression": sql_expression,
            "is_ratio": is_ratio,
            "numerator": numerator,
            "denominator": denominator,
            "status": status,
            "confidence_score": confidence_score,
            "filters": filters or {},
        }
        super().__init__(dict_data)
        self.__dict__ = self


# Central Metric Registry
METRIC_REGISTRY: Dict[str, MetricDefinition] = {
    "admissions": MetricDefinition(
        metric_key="admissions",
        display_name="Admissions",
        synonyms=["admission", "admissions", "enrolled", "enrollment", "total enrolled", "admission count"],
        source_workbook_type="RAW",
        source_fields=["mx_AdmissionDate", "ProspectStage"],
        date_field="mx_AdmissionDate",
        aggregation="DISTINCT ProspectID",
        description="Confirmed admissions where mx_AdmissionDate is non-null/non-empty in raw CRM records.",
        column="cy_admission",
        sql_expression="SUM(cy_admission)",
        is_ratio=False,
    ),
    "admission": MetricDefinition(
        metric_key="admissions",
        display_name="Admissions",
        synonyms=["admission", "admissions", "enrolled"],
        source_workbook_type="RAW",
        source_fields=["mx_AdmissionDate"],
        date_field="mx_AdmissionDate",
        aggregation="DISTINCT ProspectID",
        description="Confirmed admissions alias.",
        column="cy_admission",
        sql_expression="SUM(cy_admission)",
        is_ratio=False,
    ),
    "leads": MetricDefinition(
        metric_key="leads",
        display_name="Total Leads",
        synonyms=["lead", "leads", "total leads", "enquiries", "inquiries", "prospects"],
        source_workbook_type="RAW",
        source_fields=["ProspectID", "CreatedOn"],
        date_field="CreatedOn",
        aggregation="DISTINCT ProspectID",
        description="Distinct lead count based on unique ProspectID in raw CRM records.",
        column="cy_leads",
        sql_expression="SUM(cy_leads)",
        is_ratio=False,
    ),
    "cucet": MetricDefinition(
        metric_key="cucet",
        display_name="CUCET Applicants",
        synonyms=["cucet", "cucet exam", "cucet score", "cucet attempt"],
        source_workbook_type="RAW",
        source_fields=["mx_CUCET_Score", "mx_CUCET_Exam_Status"],
        date_field="CreatedOn",
        aggregation="DISTINCT ProspectID",
        description="Leads with recorded CUCET exam score or eligible scholarship status.",
        column="cy_cucet",
        sql_expression="SUM(cy_cucet)",
        is_ratio=False,
    ),
    "conversion_rate": MetricDefinition(
        metric_key="conversion_rate",
        display_name="Conversion Rate",
        synonyms=["conversion", "conversion rate", "conversion %", "admissions rate"],
        source_workbook_type="RAW",
        source_fields=["mx_AdmissionDate", "ProspectID"],
        date_field="CreatedOn",
        aggregation="SUM(admissions) / SUM(leads) * 100",
        description="Percentage of distinct leads converted into confirmed admissions.",
        column="conversion_rate",
        sql_expression="SUM(cy_admission) / NULLIF(SUM(cy_leads), 0) * 100",
        is_ratio=True,
        numerator="admissions",
        denominator="leads",
    ),
    "time_to_first_call": MetricDefinition(
        metric_key="time_to_first_call",
        display_name="Average Time to First Call",
        synonyms=["time to first call", "first call duration", "response time", "avg time to call"],
        source_workbook_type="RAW",
        source_fields=["mx_First_Allocation_Date_and_Time", "mx_First_Call_Disposition_Date"],
        date_field="mx_First_Allocation_Date_and_Time",
        aggregation="AVG(mx_First_Call_Disposition_Date - mx_First_Allocation_Date_and_Time) IN HOURS",
        description="Average elapsed duration in hours from lead assignment to first call disposition.",
        column="time_to_first_call",
        sql_expression="AVG(time_to_first_call)",
        is_ratio=False,
    ),
    "no_call_leads": MetricDefinition(
        metric_key="no_call_leads",
        display_name="Leads Never Called",
        synonyms=["no call leads", "leads never called", "0 call leads", "uncalled leads"],
        source_workbook_type="RAW",
        source_fields=["OwnerIdName", "mx_First_Call_Disposition_Date"],
        date_field="CreatedOn",
        aggregation="COUNT(DISTINCT ProspectID) WHERE mx_First_Call_Disposition_Date IS NULL",
        description="Leads assigned to an owner where no call disposition has been recorded.",
        column="no_call_leads",
        sql_expression="COUNT(ProspectID)",
        is_ratio=False,
    ),
}


def resolve_metric(term: str) -> Optional[MetricDefinition]:
    """Resolve natural-language string to canonical MetricDefinition."""
    clean = term.strip().lower()
    for key, defn in METRIC_REGISTRY.items():
        if clean == key or clean in [s.lower() for s in defn["synonyms"]]:
            return defn
    return None


def get_metric(term: str) -> Optional[MetricDefinition]:
    """Alias for resolve_metric."""
    return resolve_metric(term)


def resolve_metric_name(term: str) -> str:
    """Resolve natural-language string to canonical metric string name e.g. 'admission' -> 'admissions'."""
    defn = resolve_metric(term)
    if defn:
        return defn["metric_key"]
    return term.strip().lower()


def calculate_ratio(num: float, den: float) -> float:
    """Safely calculate percentage ratio."""
    if not den:
        return 0.0
    return round((num / den) * 100.0, 2)
