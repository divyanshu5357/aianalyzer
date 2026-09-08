"""
Centralized Scalable Tool & Intent Registry
Maps analytical intents to tool definitions, parameter schemas, and tool executors.
"""
from typing import Any, Callable, Type
from sqlalchemy.orm import Session

from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.metric_tool import MetricTool
from app.agent.tools.breakdown_tool import BreakdownTool
from app.agent.tools.ranking_tool import RankingTool
from app.agent.tools.comparison_tool import ComparisonTool
from app.agent.tools.yoy_tool import YoYTool
from app.agent.tools.funnel_tool import FunnelTool
from app.agent.tools.filter_tool import FilterTool
from app.agent.tools.driver_analysis_tool import DriverAnalysisTool
from app.agent.tools.counsellor_tool import CounsellorTool
from app.agent.tools.report_generator_tool import ReportGeneratorTool
from app.agent.tools.target_performance_tool import TargetPerformanceTool
from app.agent.tools.source_category_tool import SourceCategoryTool
from app.agent.tools.prediction_tool import PredictionTool


class IntentType:
    METRIC = "metric"
    RANKING = "ranking"
    COMPARISON = "comparison"
    YOY = "yoy"
    FUNNEL = "funnel"
    BREAKDOWN = "breakdown"
    FILTER = "filter"
    NO_CALL_COUNSELLORS = "no_call_leads"
    OVERDUE_INTERESTED_COUNSELLORS = "overdue_interested"
    LOW_CALL_ATTEMPT_LEADS = "call_attempts"
    TIME_TO_FIRST_CALL_BY_COUNSELLOR = "time_to_first_call"
    COUNSELLOR_PERFORMANCE = "counsellor_performance"
    ADMISSIONS_DECLINE_ANALYSIS = "driver_analysis"
    PROGRAM_DECLINE_ANALYSIS = "program_decline"
    BELOW_TARGET_ANALYSIS = "below_target"
    SOURCE_BREAKDOWN_FOR_PROGRAM = "source_breakdown_program"
    STATE_BREAKDOWN_FOR_PROGRAM = "state_breakdown_program"
    REPORT_GENERATION = "generate_report"
    INHOUSE_VS_OUTSOURCE = "inhouse_vs_outsource"
    TOP_OWNERS_INHOUSE = "top_owners_inhouse"
    TOP_COURSE_MOHALI = "top_course_mohali"
    LOWEST_AVG_CALLS = "lowest_avg_calls"
    HIGHEST_CONVERSION_RATE = "highest_conversion_rate"
    PREDICTION_ANALYSIS = "prediction_analysis"


# Set of global analytical intents that do NOT require single-entity resolution
GLOBAL_ANALYTICAL_INTENTS = {
    IntentType.METRIC,
    IntentType.FUNNEL,
    IntentType.NO_CALL_COUNSELLORS,
    IntentType.OVERDUE_INTERESTED_COUNSELLORS,
    IntentType.LOW_CALL_ATTEMPT_LEADS,
    IntentType.TIME_TO_FIRST_CALL_BY_COUNSELLOR,
    IntentType.COUNSELLOR_PERFORMANCE,
    IntentType.ADMISSIONS_DECLINE_ANALYSIS,
    IntentType.PROGRAM_DECLINE_ANALYSIS,
    IntentType.BELOW_TARGET_ANALYSIS,
    IntentType.REPORT_GENERATION,
    IntentType.INHOUSE_VS_OUTSOURCE,
    IntentType.TOP_OWNERS_INHOUSE,
    IntentType.TOP_COURSE_MOHALI,
    IntentType.LOWEST_AVG_CALLS,
    IntentType.HIGHEST_CONVERSION_RATE,
    IntentType.PREDICTION_ANALYSIS,
}


class ToolDefinition:
    def __init__(
        self,
        intent_type: str,
        name: str,
        description: str,
        tool_class: Type[BaseAnalyticsTool],
        is_global: bool = False,
    ):
        self.intent_type = intent_type
        self.name = name
        self.description = description
        self.tool_class = tool_class
        self.is_global = is_global


class ToolRegistry:
    _registry: dict[str, ToolDefinition] = {}

    @classmethod
    def register(cls, intent_type: str, name: str, description: str, tool_class: Type[BaseAnalyticsTool], is_global: bool = False):
        cls._registry[intent_type] = ToolDefinition(intent_type, name, description, tool_class, is_global)

    @classmethod
    def get_definition(cls, intent_type: str) -> ToolDefinition | None:
        return cls._registry.get(intent_type)

    @classmethod
    def get_executor(cls, intent_type: str) -> BaseAnalyticsTool:
        defn = cls.get_definition(intent_type)
        if defn:
            return defn.tool_class()
        # Fallbacks
        if intent_type == IntentType.RANKING:
            return RankingTool()
        elif intent_type == IntentType.COMPARISON:
            return ComparisonTool()
        elif intent_type in (IntentType.YOY, "yoy_change"):
            return YoYTool()
        elif intent_type == IntentType.FUNNEL:
            return FunnelTool()
        elif intent_type == IntentType.FILTER:
            return FilterTool()
        elif intent_type == IntentType.PREDICTION_ANALYSIS:
            return PredictionTool()
        else:
            return BreakdownTool()

    @classmethod
    def is_global_intent(cls, intent_type: str) -> bool:
        if intent_type in GLOBAL_ANALYTICAL_INTENTS:
            return True
        defn = cls.get_definition(intent_type)
        return defn.is_global if defn else False


# Register default tools
ToolRegistry.register(IntentType.METRIC, "metric_tool", "Computes total single or aggregated metric values", MetricTool, is_global=True)
ToolRegistry.register(IntentType.NO_CALL_COUNSELLORS, "counsellor_no_call", "Counsellors with uncalled leads", CounsellorTool, is_global=True)
ToolRegistry.register(IntentType.OVERDUE_INTERESTED_COUNSELLORS, "counsellor_overdue", "Overdue interested follow-ups", CounsellorTool, is_global=True)
ToolRegistry.register(IntentType.LOW_CALL_ATTEMPT_LEADS, "counsellor_call_attempts", "Leads by call attempt bucket", CounsellorTool, is_global=True)
ToolRegistry.register(IntentType.TIME_TO_FIRST_CALL_BY_COUNSELLOR, "counsellor_ttfc", "Average time to first call", CounsellorTool, is_global=True)
ToolRegistry.register(IntentType.COUNSELLOR_PERFORMANCE, "counsellor_summary", "Overall counsellor performance", CounsellorTool, is_global=True)
ToolRegistry.register(IntentType.ADMISSIONS_DECLINE_ANALYSIS, "driver_analysis", "Admissions variance & driver analysis", DriverAnalysisTool, is_global=True)
ToolRegistry.register(IntentType.PROGRAM_DECLINE_ANALYSIS, "program_decline", "Declining programs analysis", DriverAnalysisTool, is_global=True)
ToolRegistry.register(IntentType.BELOW_TARGET_ANALYSIS, "target_performance", "Entities below target performance", TargetPerformanceTool, is_global=True)
ToolRegistry.register(IntentType.REPORT_GENERATION, "report_generator", "Generates CSV/XLSX reports", ReportGeneratorTool, is_global=True)
ToolRegistry.register(IntentType.INHOUSE_VS_OUTSOURCE, "source_category", "Inhouse vs Outsource lead comparison", SourceCategoryTool, is_global=True)
ToolRegistry.register(IntentType.TOP_OWNERS_INHOUSE, "source_category", "Top owners for Inhouse sources", SourceCategoryTool, is_global=True)
ToolRegistry.register(IntentType.HIGHEST_CONVERSION_RATE, "source_category", "Owners with highest conversion rate", SourceCategoryTool, is_global=True)
ToolRegistry.register(IntentType.LOWEST_AVG_CALLS, "counsellor_lowest_calls", "Owners with lowest average calls", CounsellorTool, is_global=True)
ToolRegistry.register(IntentType.PREDICTION_ANALYSIS, "prediction_analysis", "Predicts lead admission probabilities", PredictionTool, is_global=True)

