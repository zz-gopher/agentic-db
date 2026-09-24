import hashlib
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

    # 获取前面 diagnostic_node 已经确诊的标签，省去重新判断的麻烦
    diagnoses = state.get("suspected_diagnoses", [])
    primary_anti_pattern = diagnoses[0] if diagnoses else "other"

    if not draft:
        return {}

    # 1. 生成唯一指纹：用原 SQL 的 MD5 作为向量文档的 ID
    sql_hash = hashlib.md5(bad_sql.encode('utf-8')).hexdigest()

    # 2. 生成“泛化诊断说明”(diagnosis)，直接告诉它病因,减少token
    tagging_chain = llm.with_structured_output(ExperienceTagging, method="function_calling")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个数据库经验总结专家。
            已知该 SQL 的错误分类是：{anti_pattern}。
            请对比原SQL和优化后SQL，提炼出一段具有高度泛化性的【优化法则】（限制在50字内）。
            注意：不要包含具体的业务表名和字段名。"""),
        ("user", "原SQL: {bad_sql}\n优化后SQL: {good_sql}")
    ])

    tags: ExperienceTagging = (prompt | tagging_chain).invoke({
        "anti_pattern": primary_anti_pattern,
        "bad_sql": bad_sql,
        "good_sql": draft.optimized_sql
    })

    # 3. 组装 Document 并强制传入 id 防重
    doc = Document(
        page_content=tags.diagnosis,
        metadata={
            "db_type": db_engine,
            "anti_pattern": primary_anti_pattern,  # 直接使用复用的标签
            "example_bad": bad_sql,
            "example_good": draft.optimized_sql
        },
        id=sql_hash  # 关键去重机制
    )

    # 4. 写入向量库 (带有相同 ID 时会自动 Upsert 覆盖)
    vector_store.add_documents([doc], ids=[sql_hash])
    print(f"\n 新经验已成功 Upsert 入库！指纹: {sql_hash[:8]}")
    print(f" 提炼法则: {tags.diagnosis}\n")

    return {}