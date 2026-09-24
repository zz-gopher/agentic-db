from langchain_core.prompts import ChatPromptTemplate
from core.config import llm
from schemas.models import SqlOptimizationDraft
from graph.state import AgenticState

def generator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    table_schema = state.get("table_schema", "暂无表结构")
    examples_list = state.get("examples", [])
    examples_str = "\n".join(examples_list) if examples_list else "未检索到相关经验。"

    tools_and_schemas = [SqlOptimizationDraft]
    llm_with_tools = llm.bind_tools(tools_and_schemas)

    prompt = ChatPromptTemplate.from_template("""你是一个顶级的数据库优化专家。
        【原始 SQL】: {bad_sql}
        【表结构】: {schema}

        【知识库调取的优化法则】:
        {examples}

        任务：
        1. 结合知识库法则和表结构，推导优化方案，并在 thinking 字段写下推理过程。
        2. 必须调用 SqlOptimizationDraft 工具输出最终的优化方案。
        """)

    response = (prompt | llm_with_tools).invoke({
        "bad_sql": bad_sql,
        "schema": table_schema,
        "examples": examples_str
    })

    return {"messages": [response]}