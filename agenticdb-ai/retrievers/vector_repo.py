import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 全局初始化一次，保证极速读取
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
vector_store = Chroma(
    collection_name="sql_experience",
    embedding_function=embeddings,
    persist_directory="./agenticdb-ai/bge_db"
)