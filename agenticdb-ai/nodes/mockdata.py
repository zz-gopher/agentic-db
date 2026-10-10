from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from config.config import llm
from graph.sql_state import SQLState
from schemas.models import MockDataResult


def mockdata_node(state: SQLState) -> dict:
    """
    【mock节点】
    当沙箱探测到数据饥荒时触发，利用大模型逆向解算 WHERE 条件，生成专属测试数据。
    """
    bad_sql = state.get("executable_sql") or state.get("bad_sql", "")
    schema = state.get("table_schema", "未提供表结构")

    # 2. 组装极具针对性的 System Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个资深的数据库测试专家。当前沙箱因为缺乏数据，无法校验 SQL 优化的正确性。
    请根据 [原 SQL 语句] 和 [物理表结构]，逆向推导并生成测试数据（INSERT 语句）。

    【核心约束】
    1. 必须命中：生成的数据必须 100% 满足原 SQL 的 WHERE 条件，确保原 SQL 执行后有结果返回。
    2. 类型自适应：请直接根据提供的表结构类型，自动推导合法的数据格式（区分数值、字符串、日期时间等）。
    3. 数量控制：
       - 单条查询（如 LIMIT 1 或主键精确匹配）：严格只生成 1 条。
       - 范围/集合查询：生成 3 条。
       - 绝对不允许超过 5 条。
    4. 【主键与防冲突机制】（生死红线）：
       - 如果表结构显示主键（如 id）带有自增属性（AUTO_INCREMENT），你在写 INSERT 语句时【必须直接省略】该主键字段，把主键的生成权交还给数据库！
       - 如果主键不能省略，请务必使用极其巨大的随机安全数字（如 9999801, 9999802）作为 ID，绝对禁止使用 1, 2, 3 等常规数字，防止与数据库中已存在的真实数据发生主键冲突！
       - 同一批生成的 INSERT 语句之间，任何唯一列的值也必须使用不同的后缀加以区分。
    5. 极度严格的输出格式：
       - 绝不允许包含任何解释性文本、对话、前言或后缀。
       - 绝对禁止使用 Markdown 代码块符号（严禁出现 ```sql 等字样）。
       - 每一个列表元素必须是一条纯粹的、无任何多余标点干扰的单行 INSERT 语句。"""),

        ("user", "【分析这句SQL】: {bad_sql} \n【表结构】: {schema}")
    ])

    # 3. 绑定工具并调用
    chain = prompt | llm.with_structured_output(MockDataResult, method="function_calling")

    try:
        result = chain.invoke({
            "bad_sql": bad_sql,
            "schema": schema
        })
        mock_inserts = result.inserts

        # 打印日志方便控制台观察
        if mock_inserts:
            print(f"\n👻 [幽灵播种] 成功根据条件解算出 {len(mock_inserts)} 条 Mock 数据。")
            for i, sql in enumerate(mock_inserts, 1):
                print(f"  ├─ {i}. {sql}")

    except ValidationError as e:
        # 降级处理：LLM 吐出的格式不对时，不阻断流程，返回空列表，交由沙箱再次判定饥荒
        mock_inserts = []

    except Exception as e:
        # 服务异常处理，参考了 diagnostic_node 的标准阻断写法
        error_msg = f"【沙箱防御】生成 Mock 数据服务异常，无法继续验证。详细信息: {e}"
        return {
            "is_valid": False,
            "block_node": "MockData (幽灵播种)",
            "block_reason": error_msg,
            "messages": [AIMessage(content=error_msg)]
        }

    # 4. 返回状态更新，将 mock_inserts 注入到状态机中
    return {
        "mock_inserts": mock_inserts,
        "messages": [AIMessage(content=f"已尝试生成 {len(mock_inserts)} 条测试数据准备注入沙箱。")]
    }

