from langgraph.graph import StateGraph, START, END

from graph.global_state import GlobalOrchestratorState
from graph.mapper_state import MapperAuditState
from graph.sql_state import SQLState
from nodes.mapper_stitcher import mapper_stitcher_node

# 1. 导入所有拆分出去的节点
from nodes.schema_prepare import prepare_schema_node
from nodes.diagnostic import diagnostic_node
from nodes.generator import generator_node
from nodes.evaluator import evaluator_node
from nodes.memory import memory_node
from nodes.mockdata import mockdata_node

# 2. 初始化图状态
workflow = StateGraph(SQLState)

# 3. 注册所有节点
workflow.add_node("prepare_schema", prepare_schema_node)
workflow.add_node("diagnostic_node", diagnostic_node)
workflow.add_node("generator", generator_node)
workflow.add_node("evaluator", evaluator_node)
workflow.add_node("memory_node", memory_node)
workflow.add_node("mockdata_node", mockdata_node)
def check_valid_and_route(next_node: str):
    def router(state: SQLState) -> str:
        if state.get("is_valid", True) == False:
            return END
        return next_node
    return router

def route_after_evaluation(state: SQLState) -> str:
    if state.get("is_valid", True) == False:
        return END
    if state.get("needs_mock", False) and not state.get("mock_inserts"):
        print("👻 触发幽灵防线：启动 PhantomSeeder 尝试逆向注入数据...")
        return "mockdata_node"

    if state.get("review_score", 0) >= 70:
        return "memory_node"
    else:
        print(f"🔄 沙箱审查未通过(当前分数: {state.get('review_score')})，已打回 Generator 重写...")
        return "generator"
# 4. 连线：主干流水线
workflow.add_edge(START, "prepare_schema")
workflow.add_conditional_edges("prepare_schema", check_valid_and_route("diagnostic_node"))
workflow.add_conditional_edges("diagnostic_node", check_valid_and_route("generator"))
workflow.add_conditional_edges("generator", check_valid_and_route("evaluator"))
workflow.add_conditional_edges("evaluator", route_after_evaluation)
workflow.add_edge("mockdata_node", "evaluator")
workflow.add_edge("memory_node", END)

# 6. 编译输出
agent_app = workflow.compile()


def call_sql_optimizer_subgraph(state: MapperAuditState) -> dict:
    """委派给底层 SQL 沙箱压测部门"""
    print("🚀 [调度中枢] 提取纯净 SQL，正在下发给底层的 SQL 沙箱压测部门...")

    initial_sql_state = {
        "bad_sql": state["extracted_raw_sql"],
        "db_uri": state["db_uri"],
        "messages": [("user", f"请优化: {state['extracted_raw_sql']}")]
    }

    final_sql_state = agent_app.invoke(initial_sql_state)
    draft = final_sql_state.get("final_draft")

    if not draft or final_sql_state.get("is_valid") == False:
        block_node = final_sql_state.get("block_node", "未知节点")
        block_reason = final_sql_state.get("block_reason") or final_sql_state.get("feedback") or "重试耗尽或未生成有效草案"
        real_error = f"底层沙箱在 [{block_node}] 节点熔断 -> {block_reason}"

        return {
            "is_valid": False,
            "error_msg": real_error,
            "review_score": final_sql_state.get("review_score", 0)
        }

    return {
        "optimized_plain_sql": draft.optimized_sql,
        "review_score": final_sql_state.get("review_score", 0),
        "is_valid": True
    }

def check_mapper_valid(state: MapperAuditState) -> str:
    if not state.get("is_valid", True):
         return END
    if state.get("review_score",0) < 70:
        return END
    return "mapper_stitcher"

# 1. 初始化外层图
mapper_workflow = StateGraph(MapperAuditState)

# 2. 注册节点
mapper_workflow.add_node("call_sql_optimizer", call_sql_optimizer_subgraph)
mapper_workflow.add_node("mapper_stitcher", mapper_stitcher_node)

# 3. 连线
mapper_workflow.add_edge(START, "call_sql_optimizer")
# 如果底层 SQL 优化成功，再走缝合节点；如果底层崩了，直接结束
mapper_workflow.add_conditional_edges("call_sql_optimizer", check_mapper_valid)
mapper_workflow.add_edge("mapper_stitcher", END)

# 4. 编译暴露出唯一的“大网关”给 run_pipeline.py
master_agent_app = mapper_workflow.compile()


def supervisor_router_node(state: GlobalOrchestratorState) -> dict:
    """网关节点：识别输入内容，决定路由走向"""
    content = state["input_content"]

    # 简单的路由逻辑（实际可用 LLM 或正则增强识别）
    if "<select" in content or "<update" in content or "mybatis" in content.lower():
        task_type = "mapper_fixing"
    else:
        task_type = "sql_tuning"

    print(f"🚥 [全局网关] 意图识别完成，任务分发至: {task_type}")
    return {"task_type": task_type, "global_status": "processing"}


def call_mapper_subgraph(state: GlobalOrchestratorState) -> dict:
    """委派给 Mapper 部门"""
    print("🏢 [全局网关] 正在调用 Mapper 解析部门...")
    initial_mapper_state = {
        "raw_xml_fragment": state["input_content"],
    }
    result = master_agent_app.invoke(initial_mapper_state)
    return {
        "final_output_code": result.get("reconstructed_xml"),
        "global_status": "success" if result.get("is_valid") else "failed"
    }


def call_sql_subgraph(state: GlobalOrchestratorState) -> dict:
    """委派给纯 SQL 压测部门"""
    print("🏢 [全局网关] 正在调用 SQL 沙箱压测部门...")
    initial_sql_state = {
        "bad_sql": state["input_content"],
        "db_uri": state["db_uri"],
    }
    result = agent_app.invoke(initial_sql_state)
    draft = result.get("final_draft")
    return {
        "final_output_code": draft.optimized_sql if draft else None,
        "global_status": "success" if result.get("is_valid") else "failed"
    }


def route_by_task_type(state: GlobalOrchestratorState) -> str:
    """条件路由函数"""
    return state["task_type"]


# 构建全局状态机
global_workflow = StateGraph(GlobalOrchestratorState)

global_workflow.add_node("supervisor_router", supervisor_router_node)
global_workflow.add_node("mapper_fixing", call_mapper_subgraph)
global_workflow.add_node("sql_tuning", call_sql_subgraph)

global_workflow.add_edge(START, "supervisor_router")
# 根据任务类型，动态分发到不同的子图
global_workflow.add_conditional_edges(
    "supervisor_router",
    route_by_task_type,
    {"mapper_fixing": "mapper_fixing", "sql_tuning": "sql_tuning"}
)
global_workflow.add_edge("mapper_fixing", END)
global_workflow.add_edge("sql_tuning", END)

# 这是你暴露给 FastAPI 接口的唯一入口！
super_agent_api = global_workflow.compile()