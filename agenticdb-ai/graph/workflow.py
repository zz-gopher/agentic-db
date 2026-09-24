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

# 4. 连线：主干流水线
workflow.add_edge(START, "prepare_schema")
workflow.add_edge("prepare_schema", "diagnostic_node")
workflow.add_edge("diagnostic_node", "generator")
workflow.add_edge("generator", "evaluator")

# 5. 连线：评测与重试路由（引入了防死循环机制）
def route_after_evaluation(state: AgenticState) -> str:
    if state.get("retry_count", 0) >= 3:
        return END  # 超过3次打回，强行终止
    if state.get("review_score", 0) > 80:
        return "memory_node" # 审核通过，去入库
    else:
        return "generator"   # 没通过，滚回去重写

workflow.add_conditional_edges("evaluator", route_after_evaluation)
workflow.add_edge("memory_node", END)

# 6. 编译输出
agent_app = workflow.compile()