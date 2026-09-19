from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from core.config import llm
from retrievers.vector_repo import vector_store
from schemas.models import SqlOptimizationDraft, EvaluationResult
from tools.db_tools import get_table_schema
from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgenticState

tools = [get_table_schema]
tool_node = ToolNode(tools)


def generator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    table_schema = state.get("table_schema", "暂无表结构，请调用 get_table_schema")
    db_engine = state.get("db_engine", "mysql")
    examples = state.get("examples", "未检索到相关经验。")
    # 把真实的工具，和 Pydantic 模型（结构化输出）一起绑给大模型！
    tools_and_schemas = [get_table_schema, SqlOptimizationDraft]
    llm_with_tools = llm.bind_tools(tools_and_schemas)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是资深数据库架构师。当前操作的数据库方言为：{db_engine}
                {examples}
                当前表结构：{schema}
                【最高指令约束】：
                1. 如果不懂表结构，立刻调用 get_table_schema 工具。
                2. 如果已经拿到表结构，绝对不要输出任何普通的聊天文本！
                3. 所有的分析和思考，必须且只能写在 SqlOptimizationDraft 工具的 thinking 字段里！
                4. 请直接调用 SqlOptimizationDraft 工具提交最终方案！"""),
                    ("user", "{bad_sql}"),
        ("placeholder", "{messages}")
    ])

    response = (prompt | llm_with_tools).invoke({
        "bad_sql": bad_sql,
        "schema": table_schema,
        "db_engine": db_engine,
        "examples": examples,
        "messages": state.get("messages", [])
    })

    return {"messages": [response]}


def evaluator_node(state: AgenticState) -> dict:
    """批评家节点：负责打分，如果不通过则生成反馈消息"""
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")

    # 审查官不需要查数据库工具，直接强制输出 EvaluationResult JSON
    evaluator_chain = llm.with_structured_output(EvaluationResult, method="function_calling")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是架构审查主席。审查维度：1.消除全表扫描 2.逻辑等价。满分100，>70分 passed=True。"),
        ("user", "审查以下优化草案：\n原SQL: {bad_sql}\n草案: {draft}")
    ])

    # 调用大模型进行打分
    result: EvaluationResult = (prompt | evaluator_chain).invoke({
        "bad_sql": bad_sql,
        "draft": draft.model_dump_json() if draft else ""
    })

    # 核心逻辑：如果不通过，把反馈意见变成一条新的要求，塞进聊天记录里！
    if not result.passed:
        feedback_msg = HumanMessage(
            content=f"【审查未通过】打分:{result.score}。审查意见：{result.feedback}。请结合这些反馈重新修改 SQL！"
        )
        # 返回新消息，框架会自动触发 add_messages 追加，并更新分数
        return {"messages": [feedback_msg], "review_score": result.score}

    # 如果通过了，什么新消息都不用加，只记录高分
    return {"review_score": result.score}


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


def route_after_generation(state: AgenticState) -> str:
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END

    tool_name = last_message.tool_calls[0]["name"]

    if tool_name == "get_table_schema":
        return "tools"
    elif tool_name == "SqlOptimizationDraft":
        return "parse_json"

    return END


def retriever_node(state: AgenticState):
    bad_sql = state["bad_sql"]
    # 如果没传，默认当做 mysql 处理
    db_engine = state.get("db_engine", "mysql")

    # 1. 带标签精准查询
    results = vector_store.similarity_search(
        query=bad_sql,
        k=2,
        filter={"db_type": db_engine}
    )

    # 2. 格式化组装
    if results:
        examples_str = "【参考历史经验】\n"
        for idx, doc in enumerate(results):
            examples_str += f"案例 {idx + 1}:\n诊断法则: {doc.page_content}\n"
            examples_str += f"反面SQL: {doc.metadata.get('example_bad', '')}\n"
            examples_str += f"标准解法: {doc.metadata.get('example_good', '')}\n\n"
    else:
        examples_str = "未检索到相关经验，请完全依赖自身工具与逻辑进行优化。"

    # 3. 返回更新的增量状态
    return {"examples": examples_str}

# 初始化一张图，状态挂载上去
workflow = StateGraph(AgenticState)
workflow.add_node("retriever", retriever_node)
workflow.add_node("generator", generator_node)
workflow.add_node("tools", tool_node)
workflow.add_node("evaluator", evaluator_node)
workflow.add_node("parse_json", parse_json_node)

workflow.add_edge(START, "retriever")
workflow.add_edge("retriever", "generator")

# 条件路由: 思考后的分支 (保持你原来的完美逻辑不变)
workflow.add_conditional_edges(
    "generator",
    route_after_generation,
    {
        "tools": "tools",            # 如果返回 "tools"，就走向 tools 节点
        "parse_json": "parse_json",  # 如果返回 "parse_json"，就走向 parse_json 节点
        END: END
    }
)

# 执行完毕，拿到 DDL 后，必须回到 generator，让大模型看着新 DDL 重新作答
workflow.add_edge("tools", "generator")
workflow.add_edge("parse_json", "evaluator")

def route_after_evaluation(state: AgenticState) -> str:
    """根据审查分数决定是结束还是重做"""
    if state.get("review_score", 0) > 80:
        return END
    else:
        return "generator"

workflow.add_conditional_edges(
    "evaluator",
    route_after_evaluation
)

# 编译成可执行的 Agent 引擎
agent_app = workflow.compile()