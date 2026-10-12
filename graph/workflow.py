from langgraph.graph import StateGraph, START, END

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
    sql_feedback = final_sql_state.get("feedback") or "底层物理沙箱 EXPLAIN 压测与数据一致性校验通过。"
    return {
        "optimized_plain_sql": draft.optimized_sql,
        "review_score": final_sql_state.get("review_score", 0),
        "feedback": sql_feedback,
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

