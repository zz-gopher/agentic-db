import sqlglot
from sqlglot import exp
from tools.db_tools import get_table_schema
from graph.state import AgenticState

def prepare_schema_node(state: AgenticState) -> dict:
    bad_sql = state["bad_sql"]
    clean_sql = bad_sql.strip(" \n\r\t;")
    if clean_sql.startswith('"') and clean_sql.endswith('"'):
        clean_sql = clean_sql[1:-1]
    elif clean_sql.startswith("'") and clean_sql.endswith("'"):
        clean_sql = clean_sql[1:-1]
    tables = set()
    try:
        # 静态解析 SQL 语法树，精准提取所有表名（兼容多表 JOIN 和子查询）
        # read="mysql" 指定按照 MySQL 方言解析
        for table in sqlglot.parse_one(clean_sql, read="mysql").find_all(exp.Table):
            if table.name:
                tables.add(table.name)
    except Exception as e:
        print(f"⚠️ SQL 静态解析失败: {e}")
    schemas = []
    for table_name in tables:
        try:
            schema_info = get_table_schema.invoke(table_name)
            schemas.append(f"-- 表 {table_name} 真实结构 --\n{schema_info}")
        except Exception as e:
            schemas.append(f"-- 表 {table_name} 结构获取失败: {e} --")

    table_schema_str = "\n".join(schemas) if schemas else "未提取到表结构。"
    return {
        "table_schema": table_schema_str,
    }