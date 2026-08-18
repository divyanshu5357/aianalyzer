from typing import Any
from app.agent.tools.base import ToolResult

DERIVED_PERCENTAGE_METRICS = {
    "lead_cucet_rate": "lead-to-CUCET conversion rate",
    "lead_admission_rate": "lead-to-admission conversion rate",
    "cucet_admission_rate": "CUCET-to-admission conversion rate",
}


def format_tool_response(tool_res: ToolResult, question: str) -> dict[str, Any]:
    """
    Formulates natural language response text strictly grounded in structured ToolResult.
    Never alters numeric facts returned by the tool.
    """
    if not tool_res.success:
        # Map error_code to agent_status so tests and clients have a consistent field
        error_code = tool_res.error_code or "unknown"
        agent_status_map = {
            "entity_not_found": "entity_not_found",
            "insufficient_data": "insufficient_data",
            "ambiguous_entity": "ambiguous_entity",
            "unsupported": "unsupported",
            "no_data": "insufficient_data",
            "missing_dimension": "insufficient_data",
        }
        agent_status = agent_status_map.get(error_code, "insufficient_data")
        error_answer = tool_res.error or "I couldn't process that query."
        # Ensure the answer uses expected phrasing for unknown entities
        if error_code == "entity_not_found" and "couldn't find" not in error_answer.lower():
            pass  # keep tool error as-is
        return {
            "question": question,
            "answer": error_answer,
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": tool_res.year,
            "debug": {
                "error_code": error_code,
                "operation": tool_res.operation,
                "agent_status": agent_status,
            },
        }

    op = tool_res.operation
    data = tool_res.data
    meta = tool_res.metadata
    year = tool_res.year

    if not data:
        answer = "No matching records were found in the active dataset."
    elif op == "ranking":
        dim = meta.get("dimension", "entity")
        metric = meta.get("metric", "metric")
        limit = meta.get("limit", 1)
        sort_dir = meta.get("sort_direction", "DESC")

        top_item = data[0].get(dim, "Item")
        top_val = data[0].get(metric, 0)
        dim_title = dim.replace("_", " ").title()
        dim_label = dim.replace("_name", "").replace("_", " ")

        if sort_dir == "DESC" and top_val <= 0:
            if "admission" in metric.lower():
                answer = f"No admissions were recorded for any matching {dim_label} in the selected period."
            else:
                answer = f"No {metric}s were recorded for any matching {dim_label} in the selected period."
        elif limit == 1:
            if sort_dir == "DESC":
                answer = f"The {dim_title} with the highest {metric} in {year} is {top_item} with {top_val} {metric}."
            else:
                answer = f"The {dim_title} with the lowest {metric} in {year} is {top_item} with {top_val} {metric}."
        else:
            answer = f"Here are the top {len(data)} {dim.replace('_', ' ')}s by {metric} for {year}:"

    elif op == "comparison":
        metric = meta.get("metric", "metric")
        req_vals = meta.get("requested_values", [])
        val_str = " vs ".join(req_vals) if req_vals else "the requested items"
        chart_t = tool_res.chart_type or "pie"
        if tool_res.response_type == "chart":
            answer = f"Here is the {metric} comparison between {val_str} as a {chart_t} chart for {year}."
        else:
            answer = f"Here is the {metric} comparison between {val_str} for {year}."

    elif op == "yoy":
        dim = meta.get("dimension", "program_name")
        direction = meta.get("direction", "decrease")
        dim_title = dim.replace("_", " ").title()
        dir_label = "dropped" if direction == "decrease" else "improved"

        top = data[0]
        ent_title = top.get(dim, "")
        py_r = top.get("previous_year_admission_rate", 0.0)
        cy_r = top.get("current_year_admission_rate", 0.0)
        r_diff = top.get("rate_change", 0.0)

        if direction == "decrease":
            abs_diff = abs(r_diff)
            if len(data) == 1 or meta.get("limit") == 1:
                answer = (
                    f"{dim_title} {ent_title} had the largest admission-rate drop compared with previous year, "
                    f"decreasing from {py_r}% to {cy_r}% (-{abs_diff}% points)."
                )
            else:
                answer = (
                    f"Found {len(data)} {dim.replace('_', ' ')} records whose admission rate dropped in {year} compared with previous year. "
                    f"{ent_title} had the largest drop, moving from {py_r}% to {cy_r}% (-{abs_diff}% points)."
                )
        else:
            if len(data) == 1 or meta.get("limit") == 1:
                answer = (
                    f"{dim_title} {ent_title} had the largest admission-rate increase compared with previous year, "
                    f"improving from {py_r}% to {cy_r}% (+{r_diff}% points)."
                )
            else:
                answer = (
                    f"Found {len(data)} {dim.replace('_', ' ')} records whose admission rate improved in {year} compared with previous year. "
                    f"{ent_title} improved the most, moving from {py_r}% to {cy_r}% (+{r_diff}% points)."
                )

    elif op == "metric":
        metric = meta.get("metric", "metric")
        val = data[0].get(metric, 0)
        answer = f"There were {val} {metric} records in {year}."

    elif op == "breakdown":
        dims = meta.get("dimensions", ["dimension"])
        metric = meta.get("metric", "metric")
        if len(dims) == 1:
            top_item = data[0].get(dims[0], "Item")
            top_val = data[0].get(metric, 0)
            total = sum(r.get(metric, 0) for r in data if isinstance(r.get(metric), (int, float)))
            dim_label = dims[0].replace("_name", "").replace("_", " ")
            if top_val <= 0:
                if "admission" in metric.lower():
                    answer = f"No admissions were recorded for any matching {dim_label} in the selected period."
                else:
                    answer = f"No {metric}s were recorded for any matching {dim_label} in the selected period."
            else:
                answer = f"The {dims[0].replace('_', ' ')} with the highest {metric} in {year} is {top_item} with {top_val} {metric} (total: {total})."
        else:
            answer = f"Here is the multi-level breakdown across {', '.join(dims)} for {year}."

    elif op == "funnel":
        answer = f"Here is the admission conversion funnel for {year}."
    elif op == "driver_analysis":
        answer = meta.get("markdown_answer") or "Here is the driver analysis."
    else:
        answer = f"Here are the analysis results for {year}."

    sections = meta.get("sections")
    resp_type = "analysis" if sections else tool_res.response_type

    return {
        "question": question,
        "answer": answer,
        "response_type": resp_type,
        "chart_type": tool_res.chart_type,
        "columns": tool_res.columns,
        "data": data,
        "sections": sections,
        "year": year,
        "debug": {"operation": op, "metadata": meta},
    }


def format_answer(result: dict[str, Any]) -> dict[str, Any]:
    """Legacy compatibility response formatter."""
    question = result.get("question", "")
    results = result.get("results", [])
    intent = result.get("intent", {})
    metric = intent.get("metric", "metric")
    dimensions = intent.get("dimensions", [])

    if not results:
        return {"question": question, "answer": "No data was found for the requested question.", "data": []}

    if dimensions:
        dim = dimensions[0]
        rows = [{"dimension": r.get(dim), "value": r.get("metric_value", 0)} for r in results]
        total = sum(r["value"] for r in rows if isinstance(r["value"], (int, float)))
        return {
            "question": question,
            "answer": f"Here is the {metric} breakdown. The total is {total}.",
            "data": rows,
            "total": total,
        }

    val = results[0].get("metric_value", 0)
    return {"question": question, "answer": f"There were {val} {metric} records.", "value": val}