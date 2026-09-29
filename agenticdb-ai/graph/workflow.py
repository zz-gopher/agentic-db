from langgraph.graph import StateGraph, START, END
from graph.state import AgenticState

# 1. 导入所有拆分出去的节点
from nodes.schema_prepare import prepare_schema_node
from nodes.diagnostic import diagnostic_node
from nodes.generator import generator_node
from nodes.evaluator import evaluator_node
from nodes.memory import memory_node

# 2. 初始化图状态
workflow = StateGraph(AgenticState)

# 3. 注册所有节点
workflow.add_node("prepare_schema", prepare_schema_node)
workflow.add_node("diagnostic_node", diagnostic_node)
workflow.add_node("generator", generator_node)
workflow.add_node("evaluator", evaluator_node)
workflow.add_node("memory_node", memory_node)
def check_valid_and_route(next_node: str):
    def router(state: AgenticState) -> str:
        if state.get("is_valid", True) == False:
            return END
        return next_node
    return router

def route_after_evaluation(state: AgenticState) -> str:
    if state.get("is_valid", True) == False:
        return END
    if state.get("retry_count", 0) >= 3:
        print("🛑 触发熔断：多次优化依然无法通过物理沙箱审查，放弃流转。")
        return END
    if state.get("review_score", 0) >= 70 and state.get("is_valid", True):
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
workflow.add_edge("memory_node", END)

# 6. 编译输出
agent_app = workflow.compile()