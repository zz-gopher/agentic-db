from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from core.config import llm
from graph.state import AgenticState
from retrievers.vector_repo import vector_store
from schemas.models import DiagnosticResult


def diagnostic_node(state: AgenticState) -> dict:
    bad_sql = state["bad_sql"]
    schema = state.get("table_schema", "")

    # 1.让大模型先用自己的原生智力“看个大概”
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个顶级的数据库性能诊断专家。请仔细分析 SQL 的性能瓶颈。
            你必须从以下反模式标签库中选择对应的病因（可多选）：
            - func_index: 在 WHERE 条件的等号左侧对字段使用了函数或计算。
            - implicit_conversion: 传入的参数类型与表字段类型不一致，导致隐式转换。
            - select_all: 在没有必要的情况下使用了 SELECT *。
            - deep_paging: 使用了 LIMIT M, N 且 M 的值非常大。
            - missing_join_index: JOIN 关联的多表字段没有建立有效索引。
            - other: 明确不属于以上任何一种情况。"""),

        ("user", "【分析这句SQL】: {bad_sql} \n【表结构】: {schema}")
    ])

    chain = prompt | llm.with_structured_output(DiagnosticResult, method="function_calling")
    result = chain.invoke({
        "bad_sql": bad_sql,
        "schema": schema
    })
    # 2. 利用诊断出的标签，利用 ChromaDB 的 metadata 进行精准过滤
    examples_list = []
    if result.suspected_patterns:
        try:
            # 核心精髓：不比对 SQL 字符串，直接按照病理标签过滤精华法则！
            search_results = vector_store.similarity_search(
                query="",
                k=3,
                filter={"anti_pattern": {"$in": result.suspected_patterns}}
            )
            examples_list = [doc.page_content for doc in search_results]
        except Exception as e:
            print(f"⚠️ 向量库标签检索失败: {e}")
    return {
        "suspected_diagnoses": result.suspected_patterns,
        "examples": examples_list,
        "messages": [HumanMessage(content=f"初步诊断: {result.diagnostic_reasoning}")]
    }