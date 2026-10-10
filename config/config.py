from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()
from langchain_openai import ChatOpenAI
import httpx

#  定义统一配置中心
class Settings(BaseSettings):
    deepseek_api_key: str = Field(...)
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    llm_model: str = Field(default="deepseek-chat")
    llm_temperature: float = Field(default=0.0)

    db_uri: str = Field(...)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# 3. 初始化全局共享实例
direct_client = httpx.Client(trust_env=False)

llm = ChatOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
    model=settings.llm_model,
    http_client=direct_client,
    temperature=settings.llm_temperature
)