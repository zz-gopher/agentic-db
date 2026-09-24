from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from core.config import llm
from schemas.models import SqlOptimizationDraft
from graph.state import AgenticState

def generator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    table_schema = state.get("table_schema", "暂无表结构")
    examples_list = state.get("examples", [])
    examples_str = "\n".join(examples_list) if examples_list else "未检索到相关经验。"

    generator_chain = llm.with_structured_output(SqlOptimizationDraft, method="function_calling")

    prompt = ChatPromptTemplate.from_template("""你是一个顶级的数据库优化专家。
        【原始 SQL】: {bad_sql}
        【表结构】: {schema}

        【知识库调取的优化法则】:
        {examples}

        任务：结合知识库法则和表结构，推导优化方案，并在 thinking 字段写下推理过程。
        """)

    # 调用大模型，拿到的一定是直接解析好的 SqlOptimizationDraft 对象
    draft_obj: SqlOptimizationDraft = (prompt | generator_chain).invoke({
        "bad_sql": bad_sql,
        "schema": table_schema,
        "examples": examples_str
    })

    # 【优化 2】直接将对象写入 final_draft，彻底省去原先的 parse_json 节点
    return {
        "final_draft": draft_obj,
        "messages": [AIMessage(content=f"已生成优化草案:\n{draft_obj.optimized_sql}")]
    }