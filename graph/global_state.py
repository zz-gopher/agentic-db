from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class GlobalOrchestratorState(TypedDict):
    """
    全局中枢状态 (Supervisor State)
    充当 Agent 架构的“API 网关”，负责接收前端请求，进行意图识别，并调度底层的 SQL 优化子图与 Mapper 修复子图。
    """
    # --- LangGraph 标准消息流 (记录大模型在全局路由时的思考过程) ---
    messages: Annotated[List[AnyMessage], add_messages]

    # --- 1. 全局输入参数 (FastAPI 直接透传进来的基础物料) ---
    input_content: str  # 原始输入内容 (可能是单条 SQL，也可能是一段带标签的 Mapper XML)
    db_uri: str  # 物理沙箱连接串 (包工头自己不用，仅负责透传给 SQL 子图)
    db_engine: str  # 数据库方言 (默认 mysql)

    # --- 2. 路由与调度控制 (Supervisor Agent 决定的走向) ---
    task_type: Optional[str]  # 路由决策结果，例如：'sql_tuning' (纯SQL性能压测), 'mapper_fixing' (标签映射修复), 'both' (两者都需要)
    current_subgraph: Optional[str]  # 记录当前任务流转到了哪个部门 (方便 Trace 和日志打印)

    # --- 3. 聚合输出与汇总 (最终抛给 FastAPI 返回给前端的数据) ---
    final_output_code: Optional[str]  # 最终缝合/优化后的完美代码
    global_status: str  # 整体任务状态: 'pending', 'processing', 'success', 'failed'
    global_error_msg: Optional[str]  # 全局阻断的报错信息 (比如大模型拒绝回答，或系统级崩溃)