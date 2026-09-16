from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.embeddings import FakeEmbeddings

class FewShotRepository:
    def __init__(self):
        self.embeddings = FakeEmbeddings(size=384)
        self.vector_store = InMemoryVectorStore(self.embeddings)
        self._init_data()

    def _init_data(self):
        texts = [
            "SELECT * FROM orders WHERE DATE(create_time) = '2023-01-01'",
            "SELECT * FROM user WHERE id NOT IN (SELECT user_id FROM blacklist)"
        ]
        metadatas = [
            {
                "optimized": "SELECT id FROM orders WHERE create_time >= '2023-01-01' AND create_time < '2023-01-02'",
                "reason": "避免在索引列使用函数，改为范围查询"
            },
            {
                "optimized": "SELECT u.id FROM user u LEFT JOIN blacklist b ON u.id = b.user_id WHERE b.user_id IS NULL",
                "reason": "NOT IN 导致全表扫描，改用 LEFT JOIN + IS NULL"
            }
        ]
        self.vector_store.add_texts(texts=texts, metadatas=metadatas)

    def find_relevant_examples(self, bad_sql: str) -> str:
        docs = self.vector_store.similarity_search(bad_sql, k=1)
        if not docs:
            return "无历史参考案例。"
        doc = docs[0]
        return f"【参考案例】\n原SQL: {doc.page_content}\n优化后: {doc.metadata['optimized']}\n理由: {doc.metadata['reason']}\n"