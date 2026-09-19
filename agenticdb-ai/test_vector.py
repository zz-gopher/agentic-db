from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
# 初始化本地中文向量模型
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5")

# 1. 初始化持久化向量库（数据会保存在当前目录的 chroma_db 文件夹中）
vector_store = Chroma(
    collection_name="sql_experience",
    embedding_function=embeddings,
    persist_directory="./agenticdb-ai/bge_db"
)

# 2. 存入一条带有“方言标签”和“优化套路”的经验
sample_experience = Document(
    # page_content 是大模型用来计算相似度的核心“病理特征”
    page_content="对索引字段使用了 DATE() 函数导致全表扫描，需改为常量范围比较。",
    metadata={
        "db_type": "mysql",
        "anti_pattern": "func_index",
        "example_bad": "SELECT * FROM orders WHERE DATE(create_time) = '2023-01-01'",
        "example_good": "SELECT * FROM orders WHERE create_time >= '2023-01-01' AND create_time < '2023-01-02'"
    }
)
# 首次运行会写入本地文件，后续运行可以注释掉这行
vector_store.add_documents([sample_experience])

print("✅ 经验录入成功！")

# 3. 模拟 Retriever Node 的检索过程
test_bad_sql = "SELECT * FROM user_logs WHERE DATE(login_time) = '2024-05-01'"

# 带着条件去搜：只找 MySQL 的案例
results = vector_store.similarity_search(
    query=test_bad_sql,
    k=1,
    filter={"db_type": "mysql"}  # 核心机制：元数据硬过滤
)

if results:
    print("\n🔍 检索到匹配的优化套路：")
    print(f"诊断说明: {results[0].page_content}")
    print(f"标准解法: {results[0].metadata['example_good']}")
else:
    print("\n⚠️ 未找到相关经验，准备让 Agent 硬解...")