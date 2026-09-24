import json
import decimal
import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# ==========================================
# 1. 动态引擎缓存池 (避免频繁建连)
# ==========================================
_engine_cache = {}


def get_engine(db_uri: str):
    """根据传入的 URI 获取或创建连接池"""
    if db_uri not in _engine_cache:
        # 示例 URI:
        # PG: postgresql+psycopg2://user:pass@host:5432/dbname
        # MySQL: mysql+pymysql://user:pass@host:3306/dbname
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
def get_explain_plan(sql: str, db_uri: str) -> str:
    clean_sql = sql.strip()
    if not clean_sql.upper().startswith("SELECT"):
        return "【安全拦截】沙箱环境目前仅支持 SELECT 语句的分析。"

    engine = get_engine(db_uri)
    dialect = engine.dialect.name  # 自动识别当前连接的数据库类型

    try:
        with engine.connect() as conn:
            # 方案 A: MySQL, PostgreSQL, SQLite 均原生支持 EXPLAIN
            if dialect in ["mysql", "postgresql", "sqlite"]:
                result = conn.execute(text(f"EXPLAIN {clean_sql}"))
                columns = result.keys()
                explain_data = [dict(zip(columns, row)) for row in result.fetchall()]
                return json.dumps(explain_data, indent=2, ensure_ascii=False)

            # 方案 B: SQL Server 使用 SHOWPLAN
            elif dialect == "mssql":
                conn.execute(text("SET SHOWPLAN_TEXT ON"))
                result = conn.execute(text(clean_sql))
                explain_data = "\n".join([str(row[0]) for row in result.fetchall()])
                conn.execute(text("SET SHOWPLAN_TEXT OFF"))
                return explain_data

            # 方案 C: Oracle 使用 EXPLAIN PLAN FOR + DBMS_XPLAN
            elif dialect == "oracle":
                conn.execute(text(f"EXPLAIN PLAN FOR {clean_sql}"))
                result = conn.execute(text("SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY())"))
                explain_data = "\n".join([str(row[0]) for row in result.fetchall()])
                return explain_data

            else:
                return f"【方言未适配】暂不支持 {dialect} 引擎的执行计划查询。"

    except SQLAlchemyError as e:
        return f"【SQL执行报错】{str(e._message())}"


# ==========================================
# 3. 工具二：多库通用的逻辑校验器
# ==========================================
def verify_logic_equivalence(original_sql: str, optimized_sql: str, db_uri: str) -> str:
    """
    不管底层是 Oracle 还是 PG，游标层的 fetchmany(100) 行为是完全一致的！
    """
    if not original_sql.upper().startswith("SELECT") or not optimized_sql.upper().startswith("SELECT"):
        return "【安全拦截】只支持 SELECT 语句的逻辑校验。"

    engine = get_engine(db_uri)

    try:
        with engine.connect() as conn:
            # 执行原 SQL
            res_orig = conn.execute(text(original_sql))
            cols_orig = list(res_orig.keys())
            data_orig = res_orig.fetchmany(100)

            # 执行优化后的 SQL
            res_opt = conn.execute(text(optimized_sql))
            cols_opt = list(res_opt.keys())
            data_opt = res_opt.fetchmany(100)

            if cols_orig != cols_opt:
                return (f"【致命错误：输出列被篡改】\n原 SQL 输出列: {cols_orig}\n优化后输出列: {cols_opt}")

            str_orig = json.dumps([tuple(row) for row in data_orig], default=custom_serializer)
            str_opt = json.dumps([tuple(row) for row in data_opt], default=custom_serializer)

            if str_orig != str_opt:
                return "【致命错误：业务逻辑被破坏】优化后的 SQL 查出的前 100 条数据内容或排序与原 SQL 不一致！"

            return "【逻辑校验通过】输出字段与数据与原逻辑完美一致。"

    except SQLAlchemyError as e:
        return f"【运行报错】执行优化后的 SQL 时报错：{str(e._message())}"