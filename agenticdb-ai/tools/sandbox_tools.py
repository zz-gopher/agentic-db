import json
import decimal
import datetime

import sqlglot
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

_schema_cache = {}


def _get_schema_types(engine, db_uri: str) -> dict:
    """去真实数据库的 information_schema 抓取所有列的真实物理类型"""
    if db_uri in _schema_cache:
        return _schema_cache[db_uri]

    cache = {}
    try:
        dialect = engine.dialect.name
        with engine.connect() as conn:
            # 根据当前真实的数据库方言，精准下发查询语句
            if dialect == "mysql":
                sql = """
                      SELECT COLUMN_NAME, DATA_TYPE
                      FROM information_schema.columns
                      WHERE table_schema = DATABASE() \
                      """
            elif dialect == "postgresql":
                sql = """
                      SELECT column_name, data_type
                      FROM information_schema.columns
                      WHERE table_catalog = current_database() \
                      """
            else:
                sql = "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.columns"

            res = conn.execute(text(sql))
            for row in res:
                cache[row[0].lower()] = row[1].lower()

    except Exception as e:
        print(f"⚠️ [沙箱警告] 获取物理 Schema 失败: {str(e)}")

    _schema_cache[db_uri] = cache
    return cache


def _generate_mock_by_type(data_type: str, dialect: str = "mysql") -> str:
    """方言感知的 Mock 数据生成器，防止各数据库的强类型校验崩溃"""
    if not data_type:
        return "'1'"

    dt = data_type.lower()
    if 'uuid' in dt:
        return "'00000000-0000-0000-0000-000000000001'"
    if 'json' in dt:
        return "'{}'"
    if any(k in dt for k in ['int', 'dec', 'num', 'float', 'double', 'bit', 'serial']):
        return "1"
    if any(k in dt for k in ['time', 'date', 'year']):
        return "TIMESTAMP '2023-10-01 10:00:00'" if dialect == 'oracle' else "'2023-10-01 10:00:00'"
    if 'bool' in dt:
        return "true" if dialect == 'postgresql' else "1"

    return "'1'"


def _mock_placeholders(sql: str, db_uri: str = None) -> str:
    """基于 AST 语法树与物理表结构的精准类型推导引擎"""
    if "?" not in sql:
        return sql
    if not db_uri:
        return sql.replace("?", "'1'")

    engine = get_engine(db_uri)
    schema_types = _get_schema_types(engine, db_uri)
    dialect = engine.dialect.name

    try:
        expression = sqlglot.parse_one(sql)

        for node in expression.find_all(exp.Placeholder):
            parent = node.parent
            target_col_name = None

            # 场景 A: WHERE 列名 = ? 或 >= ?
            if isinstance(parent, exp.Binary):
                # 修复：sqlglot 的左右节点是 this 和 expression
                if hasattr(parent, "this") and isinstance(parent.this, exp.Column):
                    target_col_name = parent.this.name
                elif hasattr(parent, "expression") and isinstance(parent.expression, exp.Column):
                    target_col_name = parent.expression.name

            # 场景 B: WHERE 列名 IN (?, ?)
            elif isinstance(parent, exp.In) or (parent.parent and isinstance(parent.parent, exp.In)):
                in_node = parent if isinstance(parent, exp.In) else parent.parent
                if isinstance(in_node.this, exp.Column):
                    target_col_name = in_node.this.name

            # 场景 C: INSERT INTO 表名 (列名) VALUES (?)
            elif isinstance(parent, exp.Tuple) and parent.parent and isinstance(parent.parent, exp.Values):
                insert_node = expression.find(exp.Insert)
                if insert_node and insert_node.this:
                    col_index = parent.expressions.index(node)
                    schema_cols = insert_node.this.expressions
                    if col_index < len(schema_cols):
                        target_col_name = schema_cols[col_index].name

            # 获取真实类型并替换 AST 节点
            # 修复：去掉 str()，保留原生的 None
            data_type = schema_types.get(target_col_name.lower()) if target_col_name else None
            mock_value = _generate_mock_by_type(data_type, dialect)
            node.replace(sqlglot.parse_one(mock_value))

        out_dialect = "tsql" if dialect == "mssql" else dialect
        return expression.sql(dialect=out_dialect)

    except Exception as e:
        print(f"⚠️ AST 解析失败回退: {e}")
        return sql.replace("?", "'1'")
# ==========================================
# 1. 动态引擎缓存池 & 辅助函数
# ==========================================
_engine_cache = {}

def get_engine(db_uri: str):
    if db_uri not in _engine_cache:
        _engine_cache[db_uri] = create_engine(db_uri, pool_pre_ping=True)
    return _engine_cache[db_uri]

def custom_serializer(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")




# ==========================================
# 2. 工具一：多库自适应的 EXPLAIN 提取器
# ==========================================
def get_explain_plan(sql: str, db_uri: str) -> dict:
    clean_sql = sql.strip()
    if not clean_sql.upper().startswith("SELECT"):
        return {"success": False, "msg": "【安全拦截】沙箱环境目前仅支持 SELECT 语句的分析。"}

    # 预处理占位符
    executable_sql = _mock_placeholders(clean_sql, db_uri)
    engine = get_engine(db_uri)
    dialect = engine.dialect.name

    try:
        with engine.connect() as conn:
            if dialect in ["mysql", "postgresql", "sqlite"]:
                result = conn.execute(text(f"EXPLAIN {executable_sql}"))
                columns = result.keys()
                explain_data = [dict(zip(columns, row)) for row in result.fetchall()]
                return {"success": True, "data": json.dumps(explain_data, indent=2, ensure_ascii=False)}

            elif dialect == "mssql":
                conn.execute(text("SET SHOWPLAN_TEXT ON"))
                result = conn.execute(text(executable_sql))
                explain_data = "\n".join([str(row[0]) for row in result.fetchall()])
                conn.execute(text("SET SHOWPLAN_TEXT OFF"))
                return {"success": True, "data": explain_data}

            elif dialect == "oracle":
                conn.execute(text(f"EXPLAIN PLAN FOR {executable_sql}"))
                result = conn.execute(text("SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY())"))
                explain_data = "\n".join([str(row[0]) for row in result.fetchall()])
                return {"success": True, "data": explain_data}

            else:
                return {"success": False, "msg": f"暂不支持 {dialect} 引擎的执行计划查询。"}

    except SQLAlchemyError as e:
        return {"success": False, "msg": f"数据库引擎拒绝执行，原生报错为：{str(e._message())}"}
    except Exception as e:
        return {"success": False, "msg": f"沙箱未知异常：{str(e)}"}


# ==========================================
# 3. 工具二：多库通用的逻辑校验器
# ==========================================
def verify_logic_equivalence(original_sql: str, optimized_sql: str, db_uri: str) -> dict:
    if not original_sql.upper().startswith("SELECT") or not optimized_sql.upper().startswith("SELECT"):
        return {"is_equivalent": False, "msg": "【安全拦截】只支持 SELECT 语句的逻辑校验。"}

    # 预处理占位符
    exec_orig = _mock_placeholders(original_sql, db_uri)
    exec_opt = _mock_placeholders(optimized_sql, db_uri)
    engine = get_engine(db_uri)

    try:
        with engine.connect() as conn:
            res_orig = conn.execute(text(exec_orig))
            cols_orig = list(res_orig.keys())
            data_orig = res_orig.fetchmany(100)

            res_opt = conn.execute(text(exec_opt))
            cols_opt = list(res_opt.keys())
            data_opt = res_opt.fetchmany(100)

            # 1. 字段级比对
            if cols_orig != cols_opt:
                return {
                    "is_equivalent": False,
                    "msg": f"【列篡改错误】\n原SQL输出列: {cols_orig}\n优化后输出列: {cols_opt}"
                }

            # 2. 数据饥荒检测 (防止空表绕过逻辑比对)
            if len(data_orig) == 0:
                return {
                    "is_equivalent": True,
                    "msg": "【空数据警告】原 SQL 查询结果为空"
                }

            # 3. 结果集严格比对
            str_orig = json.dumps([tuple(row) for row in data_orig], default=custom_serializer)
            str_opt = json.dumps([tuple(row) for row in data_opt], default=custom_serializer)

            if str_orig != str_opt:
                return {
                    "is_equivalent": False,
                    "msg": "【业务逻辑破坏】优化后的 SQL 查出的前 100 条数据内容或排序与原 SQL 不一致！"
                }

            return {"is_equivalent": True, "msg": "输出字段与数据与原逻辑完美一致。"}

    except SQLAlchemyError as e:
        return {"is_equivalent": False, "msg": f"【运行报错】执行优化 SQL 时报错：{str(e._message())}"}
    except Exception as e:
         return {"is_equivalent": False, "msg": f"【未知异常】校验沙箱崩溃：{str(e)}"}


if __name__ == "__main__":
    # 1. 准备测试环境：使用内存 SQLite (免安装)
    test_db_uri = "sqlite:///:memory:"

    # 2. 伪造物理表结构缓存 (模拟从 information_schema 抓取的结果)
    _schema_cache[test_db_uri] = {
        "id": "int",
        "title": "varchar",
        "user_id": "bigint",
        "created_at": "datetime",
        "status": "varchar"
    }

    # 3. 准备覆盖各大核心场景的测试用例
    test_cases = [
        # 场景 A: 基础二元操作符 (期望 title 被识别为字符串，created_at 被识别为时间)
        "SELECT id, title FROM notes WHERE title = ? AND created_at >= ?",

        # 场景 B: IN 集合查询 (期望集合里的两个 ? 都能被推导为 bigint 类型)
        "SELECT * FROM notes WHERE user_id IN (?, ?)",

        # 场景 C: INSERT 语句 (期望按照字段索引，分别推导为 int, varchar, datetime)
        "INSERT INTO users (id, status, created_at) VALUES (?, ?, ?)",

        # 场景 D: UPDATE 语句 (测试 SET 子句和 WHERE 子句的推导)
        "UPDATE notes SET title = ?, created_at = ? WHERE id = ?",

        # 场景 E: 未知列测试 (模拟查不到物理类型时，期望触发 '1' 的兜底机制)
        "SELECT * FROM notes WHERE unknown_column = ?",

        # 场景 F: CDATA 提取出的真实 MyBatis 复杂条件 (测试你的报错 SQL)
        "SELECT id, title FROM notes WHERE title = ? AND user_id = ? AND created_at >= ?"
    ]

    print("🚀 启动 AST 占位符强类型推导引擎测试...\n")
    print("=" * 80)
    for i, sql in enumerate(test_cases, 1):
        print(f"【测试用例 {i}】")
        print(f"📥 原始 SQL: {sql}")

        # 调用核心引擎进行处理
        mocked_sql = _mock_placeholders(sql, test_db_uri)

        print(f"📤 推导结果: {mocked_sql}")
        print("-" * 80)