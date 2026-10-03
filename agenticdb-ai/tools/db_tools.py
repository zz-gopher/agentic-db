from core.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

schema_engine = create_engine(settings.db_uri, pool_pre_ping=True)

def get_table_schema(table_name: str) -> dict:
    """当需要了解某张数据库表的真实结构、字段类型或索引情况时，调用此工具获取 DDL 语句。"""
    print(f"⚙️ [物理探针] 正在前往真实数据库抓取表结构: {table_name}")

    clean_table = table_name.strip(" `'\"")

    if not clean_table:
        return {"success": False, "msg": "传入的表名为空。"}

    try:
        with schema_engine.connect() as conn:
            sql = f"SHOW CREATE TABLE `{clean_table}`"
            result = conn.execute(text(sql))
            row = result.fetchone()

            if row:
                # 成功找到表，返回 success=True 和 ddl 数据
                return {"success": True, "ddl": row[1]}
            else:
                # 表不存在，明确返回 success=False
                return {"success": False, "msg": f"真实数据库中未找到表 `{clean_table}`，请检查拼写。"}

    except SQLAlchemyError as e:
        return {"success": False, "msg": f"数据库查询报错: {str(e._message())}"}
    except Exception as e:
        return {"success": False, "msg": f"探针未知异常: {str(e)}"}