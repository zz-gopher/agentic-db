import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["LANGCHAIN_OPENAI_TCP_KEEPALIVE"] = "0"
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["NO_PROXY"] = "*"
from dotenv import load_dotenv
load_dotenv()
from langchain_openai import ChatOpenAI
import httpx

direct_client = httpx.Client(trust_env=False)
# 获取环境变量中的 Key
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise ValueError("请在项目根目录的 .env 文件中配置 DEEPSEEK_API_KEY")

llm = ChatOpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
    http_client=direct_client,
    temperature=0
)