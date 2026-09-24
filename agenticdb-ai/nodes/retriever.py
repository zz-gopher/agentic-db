from graph.state import AgenticState
from retrievers.vector_repo import vector_store


def retriever_node(state: AgenticState) -> dict:
    diagnoses = state.get("suspected_diagnoses", [])

    if not diagnoses:
        return {"examples": []}

    # 利用 ChromaDB 的 metadata 过滤功能
    # 只要命中了疑似的标签，就把库里对应的“精华法则”抽调出来
    results = vector_store.similarity_search(
        query="",  # 不再需要做向量比对
        k=5,
        filter={"anti_pattern": {"$in": diagnoses}}  # 直接匹配反模式标签
    )

    # 提取纯粹的优化法则片段
    rules = [doc.page_content for doc in results]
    return {"examples": rules}
