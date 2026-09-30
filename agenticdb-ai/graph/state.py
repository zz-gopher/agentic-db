from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from schemas.models import SqlOptimizationDraft

class AgenticState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    bad_sql: str # 待优化SQL
    db_engine: str # 数据库引擎
    suspected_diagnoses: list[str] # 用于存放 LLM 对这句 SQL 的初步病理诊断和疑似标签
    examples: str # LLM参考经验
    table_schema: Optional[str]        # 明确的表结构字段
    final_draft: Optional[SqlOptimizationDraft] # 明确的最终 JSON 结果字段
    review_score: Optional[int]  # 记录批评家给出的分数
    retry_count: int # 重试次数
    is_valid: bool # 是否是合法的sql
    # 用于 DevOps 报告的标准化熔断信息
    block_node: Optional[str]
    block_reason: Optional[str]