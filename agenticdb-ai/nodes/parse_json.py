from langchain_core.messages import AIMessage

from graph.state import AgenticState
from schemas.models import SqlOptimizationDraft


def parse_json_node(state: AgenticState) -> dict:
    """当大模型提交最终方案时，这个节点负责把参数提取成 Pydantic 对象"""
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        # 理论上永远不会走到这里，除非路由写错了
        raise ValueError("解析节点收到了非预期的消息类型，缺少 tool_calls")
    # 获取大模型传入的 SqlOptimizationDraft 的参数
    draft_args = last_message.tool_calls[0]["args"]
    # 转换回强类型的 Pydantic 模型
    draft_obj = SqlOptimizationDraft(**draft_args)

    # 明确赋值给档案袋的 final_draft 字段
    return {"final_draft": draft_obj}