from langchain_core.tools import tool


@tool
def get_table_schema(table_name: str) -> str:
    """当需要了解某张数据库表的真实结构、字段类型或索引情况时，调用此工具获取 DDL 语句。"""
    print(f"⚙️ [Tool被触发] 查询表结构: {table_name}")

    if table_name.lower() == "user_logs":
        return """
        CREATE TABLE `user_logs` (
          `id` bigint(20) NOT NULL AUTO_INCREMENT,
          `user_id` varchar(64) NOT NULL,
          `status` tinyint(4) NOT NULL DEFAULT '0',
          `created_at` datetime NOT NULL,
          KEY `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB;
        """
    return f"表 {table_name} 不存在！"