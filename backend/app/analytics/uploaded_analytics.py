from typing import Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.dashboard import _percentage
from app.database.repository import get_active_dataset


def get_year_columns(year: int, native_cy: int, native_py: int) -> tuple[str, str, str, str, str, str]:
    if year == native_cy:
        return "cy_leads", "cy_cucet", "cy_admission", "py_leads", "py_cucet", "py_admission"
    elif year == native_py:
        return "py_leads", "py_cucet", "py_admission", "0", "0", "0"
    elif year == native_cy + 1:
        return "0", "0", "0", "cy_leads", "cy_cucet", "cy_admission"
    else:
        return "0", "0", "0", "0", "0", "0"



def get_latest_dataset_id(db: Session) -> UUID | str | None:
    """
    Get the active dataset ID from system.datasets.
    """
    return get_active_dataset(db)




def calculate_funnel_uploaded(
    db: Session, dataset_id: Any, current_year: int
) -> dict[str, Any]:
    previous_year = current_year - 1
    query = text(
        """
        SELECT
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(cy_cucet), 0) AS cy_cucet,
            COALESCE(SUM(cy_admission), 0) AS cy_admission,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(py_cucet), 0) AS py_cucet,
            COALESCE(SUM(py_admission), 0) AS py_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :dataset_id
        """
    )
    row = db.execute(query, {"dataset_id": dataset_id}).mappings().one()

    cy_leads = int(row["cy_leads"])
    cy_cucet = int(row["cy_cucet"])
    cy_admission = int(row["cy_admission"])

    py_leads = int(row["py_leads"])
    py_cucet = int(row["py_cucet"])
    py_admission = int(row["py_admission"])

    lead_cucet_rate = (cy_cucet / cy_leads * 100) if cy_leads else 0.0
    lead_admission_rate = (cy_admission / cy_leads * 100) if cy_leads else 0.0
    cucet_admission_rate = (cy_admission / cy_cucet * 100) if cy_cucet else 0.0

    def percentage_change(current: int, previous: int) -> float | None:
        if previous == 0:
            return None
        return ((current - previous) / previous) * 100

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
            "lead_cucet_percent": round(lead_cucet_rate, 2),
            "lead_admission_percent": round(lead_admission_rate, 2),
            "cucet_admission_percent": round(cucet_admission_rate, 2),
        },
        "year_over_year_change": {
            "leads_percent": percentage_change(cy_leads, py_leads),
            "cucet_percent": percentage_change(cy_cucet, py_cucet),
            "admission_percent": percentage_change(cy_admission, py_admission),
        },
    }


def calculate_source_performance_uploaded(
    db: Session, dataset_id: Any, year: int
) -> list[dict[str, Any]]:
    from app.agent.agent_service import get_active_dataset_years
    native_cy, native_py = get_active_dataset_years(db, dataset_id)
    cy_l_col, cy_c_col, cy_a_col, py_l_col, py_c_col, py_a_col = get_year_columns(year, native_cy, native_py)

    query = text(
        f"""
        SELECT
            COALESCE(main_source, 'Unknown') AS main_source,
            COALESCE(source, 'Unknown') AS source,
            COALESCE(SUM({cy_l_col}), 0) AS leads,
            COALESCE(SUM({cy_c_col}), 0) AS cucet,
            COALESCE(SUM({cy_a_col}), 0) AS admission,
            COALESCE(SUM({py_l_col}), 0) AS previous_leads,
            COALESCE(SUM({py_c_col}), 0) AS previous_cucet,
            COALESCE(SUM({py_a_col}), 0) AS previous_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :dataset_id
        GROUP BY COALESCE(main_source, 'Unknown'), COALESCE(source, 'Unknown')
        ORDER BY leads DESC, admission DESC, main_source, source
        """
    )
    rows = db.execute(query, {"dataset_id": dataset_id}).mappings().all()

    results = []
    for row in rows:
        leads = int(row["leads"])
        cucet = int(row["cucet"])
        admission = int(row["admission"])

        previous_leads = int(row["previous_leads"])
        previous_cucet = int(row["previous_cucet"])
        previous_admission = int(row["previous_admission"])

        lead_admission_percent = _percentage(admission, leads)
        previous_lead_admission_percent = _percentage(previous_admission, previous_leads)

        if leads >= 1 and (lead_admission_percent is not None and lead_admission_percent < 20):
            performance_flag = "high_leads_low_conversion"
        elif lead_admission_percent is not None and lead_admission_percent >= 50:
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
                "main_source": row["main_source"],
                "source": row["source"],
                "current_year": year,
                "previous_year": year - 1,
                "current": {
                    "leads": leads,
                    "cucet": cucet,
                    "admission": admission,
                    "lead_cucet_percent": _percentage(cucet, leads),
                    "lead_admission_percent": lead_admission_percent,
                    "cucet_admission_percent": _percentage(admission, cucet),
                },
                "previous": {
                    "leads": previous_leads,
                    "cucet": previous_cucet,
                    "admission": previous_admission,
                    "lead_cucet_percent": _percentage(previous_cucet, previous_leads),
                    "lead_admission_percent": previous_lead_admission_percent,
                    "cucet_admission_percent": _percentage(previous_admission, previous_cucet),
                },
                "lead_growth_percent": (
                    _percentage(leads - previous_leads, previous_leads)
                    if previous_leads
                    else None
                ),
                "admission_growth_percent": (
                    _percentage(admission - previous_admission, previous_admission)
                    if previous_admission
                    else None
                ),
                "performance_flag": performance_flag,
                "growth_status": growth_status,
            }
        )

    return results


def normalize_level2(val: str) -> str:
    val = val.strip()
    if len(val) >= 3 and val[1] == ":" and val[2] == " ":
        val = val[3:]
    val_upper = val.upper()
    if val_upper == "OUT SOURCED":
        return "OUT-SOURCED"
    if val_upper == "IN HOUSE":
        return "IN-HOUSE"
    return val


def calculate_source_hierarchy_uploaded(
    db: Session, dataset_id: Any, year: int
) -> list[dict[str, Any]]:
    from app.agent.agent_service import get_active_dataset_years
    native_cy, native_py = get_active_dataset_years(db, dataset_id)
    cy_l_col, cy_c_col, cy_a_col, py_l_col, py_c_col, py_a_col = get_year_columns(year, native_cy, native_py)

    query = text(
        f"""
        SELECT
            COALESCE(lead_type, 'Unknown') AS lead_type,
            COALESCE(source, 'Unknown') AS source_col,
            COALESCE(main_source, 'Unknown') AS main_source_col,
            COALESCE(SUM({cy_l_col}), 0) AS leads,
            COALESCE(SUM({cy_c_col}), 0) AS cucet,
            COALESCE(SUM({cy_a_col}), 0) AS admission,
            COALESCE(SUM({py_l_col}), 0) AS py_leads,
            COALESCE(SUM({py_c_col}), 0) AS py_cucet,
            COALESCE(SUM({py_a_col}), 0) AS py_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :dataset_id
        GROUP BY COALESCE(lead_type, 'Unknown'), COALESCE(source, 'Unknown'), COALESCE(main_source, 'Unknown')
        ORDER BY lead_type, source_col, leads DESC, main_source_col
        """
    )
    rows = db.execute(query, {"dataset_id": dataset_id}).mappings().all()

    # Build the tree structure
    tree = {}
    for r in rows:
        raw_l1 = str(r["lead_type"]).strip()
        l1 = raw_l1
        if not l1 or l1.upper() == "NONE" or l1.upper() == "NULL" or l1.upper() == "UNKNOWN":
            l1 = "OTHERS"
        elif l1.upper() == "IN HOUSE":
            l1 = "IN-HOUSE"
        elif l1.upper() == "OUT SOURCED":
            l1 = "OUT-SOURCED"

        raw_l2 = str(r["source_col"]).strip()
        l2 = normalize_level2(raw_l2)
        if not l2 or l2.upper() == "NONE" or l2.upper() == "NULL":
            l2 = "OTHER"

        raw_l3 = str(r["main_source_col"]).strip()
        l3 = raw_l3
        if not l3 or l3.upper() == "NONE" or l3.upper() == "NULL":
            l3 = "UNKNOWN"

        leads = int(r["leads"])
        cucet = int(r["cucet"])
        admission = int(r["admission"])
        py_leads = int(r["py_leads"])
        py_cucet = int(r["py_cucet"])
        py_admission = int(r["py_admission"])

        # Level 1 node
        if l1 not in tree:
            tree[l1] = {
                "name": l1,
                "raw_name": raw_l1,
                "leads": 0, "cucet": 0, "admission": 0,
                "py_leads": 0, "py_cucet": 0, "py_admission": 0,
                "children": {}
            }
        
        # Level 2 node
        if l2 not in tree[l1]["children"]:
            tree[l1]["children"][l2] = {
                "name": l2,
                "raw_name": raw_l2,
                "leads": 0, "cucet": 0, "admission": 0,
                "py_leads": 0, "py_cucet": 0, "py_admission": 0,
                "children": {}
            }

        # Level 3 node
        if l3 not in tree[l1]["children"][l2]["children"]:
            lead_admission = round(admission / leads * 100, 2) if leads else 0.0
            if leads >= 1 and lead_admission < 20:
                performance = "high_leads_low_conversion"
            elif lead_admission >= 50:
                performance = "strong"
            else:
                performance = "normal"

            tree[l1]["children"][l2]["children"][l3] = {
                "name": l3,
                "raw_name": raw_l3,
                "leads": leads,
                "cucet": cucet,
                "admission": admission,
                "py_leads": py_leads,
                "py_cucet": py_cucet,
                "py_admission": py_admission,
                "performance": performance
            }

        # Accumulate sums up to parent nodes
        for node in [tree[l1], tree[l1]["children"][l2]]:
            node["leads"] += leads
            node["cucet"] += cucet
            node["admission"] += admission
            node["py_leads"] += py_leads
            node["py_cucet"] += py_cucet
            node["py_admission"] += py_admission

    # Format the nested dicts into lists
    formatted_tree = []
    for l1_key, l1_node in tree.items():
        l2_list = []
        for l2_key, l2_node in l1_node["children"].items():
            l3_list = []
            for l3_key, l3_node in l2_node["children"].items():
                l3_list.append(l3_node)

            # Sort Level 3 children by leads DESC
            l3_list.sort(key=lambda x: x["leads"], reverse=True)

            # Calculate L2 conversions
            leads2 = l2_node["leads"]
            admission2 = l2_node["admission"]
            lead_admission2 = round(admission2 / leads2 * 100, 2) if leads2 else 0.0
            if leads2 >= 1 and lead_admission2 < 20:
                perf2 = "high_leads_low_conversion"
            elif lead_admission2 >= 50:
                perf2 = "strong"
            else:
                perf2 = "normal"

            l2_list.append({
                "name": l2_node["name"],
                "raw_name": l2_node["raw_name"],
                "leads": l2_node["leads"],
                "cucet": l2_node["cucet"],
                "admission": l2_node["admission"],
                "py_leads": l2_node["py_leads"],
                "py_cucet": l2_node["py_cucet"],
                "py_admission": l2_node["py_admission"],
                "performance": perf2,
                "children": l3_list
            })

        # Sort Level 2 children by leads DESC
        l2_list.sort(key=lambda x: x["leads"], reverse=True)

        # Calculate L1 conversions
        leads1 = l1_node["leads"]
        admission1 = l1_node["admission"]
        lead_admission1 = round(admission1 / leads1 * 100, 2) if leads1 else 0.0
        if leads1 >= 1 and lead_admission1 < 20:
            perf1 = "high_leads_low_conversion"
        elif lead_admission1 >= 50:
            perf1 = "strong"
        else:
            perf1 = "normal"

        formatted_tree.append({
            "name": l1_node["name"],
            "raw_name": l1_node["raw_name"],
            "leads": l1_node["leads"],
            "cucet": l1_node["cucet"],
            "admission": l1_node["admission"],
            "py_leads": l1_node["py_leads"],
            "py_cucet": l1_node["py_cucet"],
            "py_admission": l1_node["py_admission"],
            "performance": perf1,
            "children": l2_list
        })

    # Sort Level 1 by leads DESC
    formatted_tree.sort(key=lambda x: x["leads"], reverse=True)
    return formatted_tree


def calculate_source_detail_uploaded(
    db: Session,
    dataset_id: Any,
    year: int,
    main_source: str,
    source: str,
) -> dict[str, Any] | None:
    from app.agent.agent_service import get_active_dataset_years
    native_cy, native_py = get_active_dataset_years(db, dataset_id)
    cy_l_col, cy_c_col, cy_a_col, _, _, _ = get_year_columns(year, native_cy, native_py)

    query = text(
        f"""
        SELECT
            COALESCE(SUM({cy_l_col}), 0) AS leads,
            COALESCE(SUM({cy_c_col}), 0) AS cucet,
            COALESCE(SUM({cy_a_col}), 0) AS admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :dataset_id
          AND LOWER(main_source) = LOWER(:main_source)
          AND LOWER(source) = LOWER(:source)
        """
    )
    row = db.execute(
        query,
        {
            "dataset_id": dataset_id,
            "main_source": main_source,
            "source": source,
        },
    ).mappings().first()

    if row is None:
        return None

    leads = int(row["leads"] or 0)
    cucet = int(row["cucet"] or 0)
    admission = int(row["admission"] or 0)

    lead_cucet = _percentage(cucet, leads)
    lead_admission = _percentage(admission, leads)
    cucet_admission = _percentage(admission, cucet)

    if leads > 0 and admission == 0:
        performance = "high_leads_low_conversion"
    elif lead_admission is not None and lead_admission >= 50:
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
            "cucet_admission_percent": cucet_admission,
        },
        "performance": performance,
    }
