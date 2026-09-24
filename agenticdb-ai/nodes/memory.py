from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from core.config import llm
from graph.state import AgenticState
from retrievers.vector_repo import vector_store
from schemas.models import ExperienceTagging


def memory_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")
    db_engine = state.get("db_engine", "mysql")

    # 如果没有最终草案，说明出了异常，直接跳过
    if not draft:
        return {}

    # 1. 召唤“标签提取员”，强制输出 JSON 标签
    tagging_chain = llm.with_structured_output(ExperienceTagging, method="function_calling")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个数据库经验总结专家。
            请对比用户输入的烂SQL和最终的优化草案，提取出最通用的【病理特征】和【错误标签】。
            注意：诊断说明必须具有泛化性，不要包含具体的业务表名。"""),
            ("user", "原SQL: {bad_sql}\n优化后SQL: {good_sql}")
    ])

    # 动态生成标签
    tags: ExperienceTagging = (prompt | tagging_chain).invoke({
        "bad_sql": bad_sql,
        "good_sql": draft.optimized_sql
    })

    # 2. 组装为 Chroma 需要的向量文档格式
    doc = Document(
        page_content=tags.diagnosis,  # 核心向量特征：用病理描述去计算相似度
        metadata={
            "db_type": db_engine,
            "anti_pattern": tags.anti_pattern,
            "example_bad": bad_sql,
            "example_good": draft.optimized_sql
        }
    )

    # 3. 永久写入本地向量库
    vector_store.add_documents([doc])
    print(f"\n 新经验已自动入库！标签分类: {tags.anti_pattern}")
    print(f" 提炼法则: {tags.diagnosis}\n")

    # 状态无需改变，只做副作用操作 (Side Effect)
    return {}
