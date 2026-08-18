from sqlalchemy.orm import Session
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.breakdown_tool import BreakdownTool
from app.agent.tools.metric_tool import MetricTool


class FilterTool(BaseAnalyticsTool):
    name = "filter_tool"
    description = "Executes filtered subset analytical queries."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        if request.dimensions or request.dimension:
            return BreakdownTool().execute(db, request)
        else:
            return MetricTool().execute(db, request)
