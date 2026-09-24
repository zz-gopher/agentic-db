from core.config import llm
from schemas.models import TableExtraction
from tools.db_tools import get_table_schema
from graph.state import AgenticState

def prepare_schema_node(state: AgenticState) -> dict:
    bad_sql = state["bad_sql"]

    extractor = llm.with_structured_output(TableExtraction, method="function_calling")
    result = extractor.invoke(f"请提取以下SQL中涉及的所有数据库表名，只需返回表名即可：\n{bad_sql}")

    schemas = []
    for table_name in result.tables:
        try:
            schema_info = get_table_schema.invoke({"table_name": table_name})
            schemas.append(f"-- 表 {table_name} 结构 --\n{schema_info}")
        except Exception as e:
            schemas.append(f"-- 表 {table_name} 结构获取失败: {e} --")

    return {"table_schema": "\n".join(schemas)}