from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# --- 1. Mapper 专属状态 (外层子图) ---
class MapperAuditState(TypedDict):
    """专门处理 MyBatis XML 标签拆解与缝合的状态机"""
    messages: Annotated[List[AnyMessage], add_messages]

    # 【输入输出】
    raw_xml_fragment: str  # 原始带有标签的 Mapper XML 块 (例如 <select id="...">...</select>)
    reconstructed_xml: Optional[str]  # 最终缝合好动态标签并替换了优化 SQL 的 XML

    # 【上下文保存】
    # 用于保存动态标签的 AST 或结构映射表，防止大模型缝合时丢失上下文
    tag_context_mapping: Optional[dict]

    # 【与 SQL 子图交互的桥梁】
    extracted_raw_sql: Optional[str]  # 从 XML 中剥离出来的“脏 SQL” (准备喂给 SQL 子图)
    optimized_plain_sql: Optional[str]  # SQL 子图优化完后返回的“纯净好 SQL” (准备缝合回 XML)

    # 【状态标记】
    is_valid: bool
    error_msg: Optional[str]


