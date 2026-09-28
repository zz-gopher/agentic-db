import sqlglot
from sqlglot import exp
from langchain_core.messages import AIMessage

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

    # 尝试一：静态解析
    try:
        # read="mysql" 指定按照 MySQL 方言解析
        for table in sqlglot.parse_one(clean_sql, read="mysql").find_all(exp.Table):
            if table.name:
                tables.add(table.name)
    except Exception as e:
        error_msg = f"【阻断】您的 SQL 存在严重的语法缺失或格式错误，解析器拒绝执行。\n详细错误: {e}"
        return {
            "is_valid": False,  # 状态机标记，告诉框架准备熔断
            "messages": [AIMessage(content=error_msg)]
        }

    # 查库逻辑
    schemas = []
    missing_tables = []
    for table_name in tables:
        try:
            schema_info = get_table_schema.invoke(table_name)

            # 判断物理探针是否返回了警告或失败
            if "【警告】" in schema_info or "【提取失败】" in schema_info:
                schemas.append(f"-- 表 {table_name} 物理探针异常: {schema_info} --")
                missing_tables.append(table_name)  # 记录这只“漏网之鱼”
            else:
                schemas.append(f"-- 表 {table_name} 真实结构 --\n{schema_info}")
        except Exception as e:
            schemas.append(f"-- 表 {table_name} 结构获取发生系统错误: {e} --")
            missing_tables.append(table_name)  # 系统报错也视为表不可用
    if missing_tables:
        missing_str = ", ".join(missing_tables)
        error_msg = f"【阻断】物理沙箱拒绝执行：SQL 中引用的以下表在数据库中不存在 [{missing_str}]，请检查表名拼写。"
        return {
            "is_valid": False,
            "messages": [AIMessage(content=error_msg)]
        }
    table_schema_str = "\n".join(schemas) if schemas else "未提取到表结构。"
    return {
        "is_valid": True,  # 标记为合法，放行
        "table_schema": table_schema_str,
    }