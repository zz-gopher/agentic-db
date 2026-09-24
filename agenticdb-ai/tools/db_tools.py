from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import os

REAL_DB_URI = os.getenv("DB_URI", "mysql+pymysql://readonly_user:your_password@localhost:3306/your_database")

# 初始化带连接池的引擎，pool_pre_ping=True 会在每次借出连接时测试是否断线
schema_engine = create_engine(REAL_DB_URI, pool_pre_ping=True)

@tool
def get_table_schema(table_name: str) -> str:
    """当需要了解某张数据库表的真实结构、字段类型或索引情况时，调用此工具获取 DDL 语句。"""
    print(f"⚙️ [物理探针] 正在前往真实数据库抓取表结构: {table_name}")

    # 基础清洗，防止 LLM 提取表名时带了多余的引号或反引号
    clean_table = table_name.strip(" `'\"")

    if not clean_table:
        return "传入的表名为空。"

    try:
        with schema_engine.connect() as conn:
            # 针对 MySQL 的语法：获取建表语句 (DDL)
            sql = f"SHOW CREATE TABLE `{clean_table}`"
            result = conn.execute(text(sql))
            row = result.fetchone()

            if row:
                # SHOW CREATE TABLE 默认返回两列：[0]是表名，[1]是完整的 DDL 字符串
                ddl = row[1]
                return ddl
            else:
                return f"【警告】真实数据库中未找到表 `{clean_table}`，请检查 SQL 是否拼写错误！"

    except SQLAlchemyError as e:
        return f"【提取失败】数据库查询报错: {str(e._message())}"