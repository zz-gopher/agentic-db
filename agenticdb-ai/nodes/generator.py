from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from core.config import llm
from schemas.models import SqlOptimizationDraft
from graph.state import AgenticState

def generator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    table_schema = state.get("table_schema", "暂无表结构")
    # 如果核心参数缺失，或者表结构未能成功提取（比如上游传过来的是默认错误提示），直接熔断
    if not bad_sql or not table_schema or table_schema == "未提取到表结构。":
        print("⚠️ 缺少核心上下文，Generator 拒绝执行。")
        return {
            "is_valid": False,
            "messages": [AIMessage(content="【阻断】由于缺乏原始 SQL 或真实的表结构上下文，无法生成优化方案。")]
        }
    examples_list = state.get("examples", [])
    examples_str = "\n".join(examples_list) if examples_list else "未检索到相关经验。"
    messages = state.get("messages", [])
    feedback_history = ""
    for msg in reversed(messages):
        if "沙箱审查未通过" in msg.content or "物理沙箱执行失败" in msg.content:
            feedback_history = msg.content
            break  # 只取最新的一次打回意见，防止上下文过长

    feedback_context = f"\n【前次沙箱测试报错，请务必修复！】:\n{feedback_history}\n" if feedback_history else ""
    generator_chain = llm.with_structured_output(SqlOptimizationDraft, method="function_calling")

    prompt = ChatPromptTemplate.from_template("""你是一个顶级的数据库优化专家。
            【原始 SQL】: {bad_sql}
            【表结构】: {schema}

            【知识库调取的优化法则】:
            {examples}
            {feedback_context}
            
            任务：结合知识库法则和表结构推导优化方案。如果存在报错反馈，请首先在 thinking 字段反思错误原因并在本次草案中修复。
            
            【⚠️ 极其严格的格式红线 ⚠️】：
            1. 你的 optimized_sql 字段中【必须且只能】包含纯粹的 SELECT 语句，不能有 Markdown 代码块 (如 ```sql)，不能有 SQL 注释 (如 -- )，句尾不要加分号！
            2. 绝对不允许在 optimized_sql 中混入 ALTER TABLE、CREATE INDEX 等 DDL 语句，否则会导致下游物理沙箱直接崩溃！
            3. 如果你判断必须通过建索引才能解决全表扫描问题，请将建索引的 DDL 语句单独写入 `index_recommendations` 列表字段中。
            """)

    # 调用大模型，拿到的一定是直接解析好的 SqlOptimizationDraft 对象
    try:
        # 调用大模型，拿到的一定是直接解析好的 SqlOptimizationDraft 对象
        draft_obj: SqlOptimizationDraft = (prompt | generator_chain).invoke({
            "bad_sql": bad_sql,
            "schema": table_schema,
            "examples": examples_str,
            "feedback_context": feedback_context
        })
    except ValidationError as e:
        # Pydantic 校验失败（大模型输出的 JSON 漏了字段）
        print(f"⚠️ Generator 输出格式崩坏: {e}")
        return {
            "is_valid": False,
            "messages": [AIMessage(content=f"【阻断】优化方案生成格式异常，流程终止。详细信息: {e}")]
        }
    except Exception as e:
        # API 超时、限流等未知错误
        print(f"⚠️ Generator 节点发生未知错误: {e}")
        return {
            "is_valid": False,
            "messages": [AIMessage(content=f"【阻断】优化专家服务异常，流程终止。详细信息: {e}")]
        }

    # 直接将对象写入 final_draft，彻底省去原先的 parse_json 节点
    return {
        "final_draft": draft_obj,
        "messages": [AIMessage(content=f"已生成优化草案:\n{draft_obj.optimized_sql}")]
    }