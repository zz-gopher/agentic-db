from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from schemas.models import SqlOptimizationDraft

class AgenticState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    bad_sql: str
    table_schema: Optional[str]        # 明确的表结构字段
    final_draft: Optional[SqlOptimizationDraft] # 明确的最终 JSON 结果字段
    review_score: Optional[int]  # 记录批评家给出的分数