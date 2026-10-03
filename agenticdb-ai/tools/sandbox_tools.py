import json
import decimal
import datetime
import re
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

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


def _mock_placeholders(sql: str) -> str:
    """
    智能占位符预处理：根据 SQL 上下文推断 ? 的数据类型，防止数据库报类型转换错误。
    """
    if "?" not in sql:
        return sql

    # 1. 匹配常规操作符：字段名 =/>/</>=/<=/LIKE ?
    # 捕获组1: 字段名
    pattern = re.compile(r'([a-zA-Z0-9_]+)\s*(?:=|>=|<=|>|<|!=|<>|LIKE)\s*\?')

    def replacer(match):
        col_name = match.group(1).lower()
        # 提取中间的操作符并保留前后空格
        operator_str = match.group(0)[len(match.group(1)):-1]

        # 探测字段名特征，分配匹配数据库严格校验的 Mock 数据
        if any(keyword in col_name for keyword in ['time', 'date', 'created', 'updated']):
            mock_value = "'2023-10-01 10:00:00'"  # 满足 datetime/date 格式
        elif col_name.endswith('id') or col_name == 'id':
            mock_value = "1"  # 满足 int/bigint 格式
        else:
            mock_value = "'1'"  # varchar 等字符串兜底

        return f"{match.group(1)}{operator_str}{mock_value}"

    # 先做精准替换
    smart_sql = pattern.sub(replacer, sql)

    # 2. 兜底处理：把剩下的 ? (比如 IN (?, ?) 里的集合元素) 替换为安全的 '1'
    smart_sql = smart_sql.replace("?", "'1'")

    return smart_sql


# ==========================================
# 2. 工具一：多库自适应的 EXPLAIN 提取器
# ==========================================
def get_explain_plan(sql: str, db_uri: str) -> dict:
    clean_sql = sql.strip()
    if not clean_sql.upper().startswith("SELECT"):
        return {"success": False, "msg": "【安全拦截】沙箱环境目前仅支持 SELECT 语句的分析。"}

    # 预处理占位符
    executable_sql = _mock_placeholders(clean_sql)
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
    exec_orig = _mock_placeholders(original_sql)
    exec_opt = _mock_placeholders(optimized_sql)
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