import os
from dotenv import load_dotenv

load_dotenv()
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from core.config import llm
from schemas.models import EvaluationResult
from graph.state import AgenticState
from tools.sandbox_tools import get_explain_plan, verify_logic_equivalence

REAL_DB_URI = os.getenv("DB_URI", "mysql+pymysql://readonly_user:your_password@localhost:3306/your_database")

def evaluator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")
    retry_count = state.get("retry_count", 0)



    # 兜底防御：上游要是传了个空的过来，直接熔断
    if not draft:
        return {
            "is_valid": False,
            "messages": [AIMessage(content="【阻断】评测沙箱未接收到优化草案，无法执行。")]
        }

    optimized_sql = draft.optimized_sql
    print("⚙️ [物理沙箱] 正在运行 EXPLAIN 并校验数据一致性...")
    explain_result = get_explain_plan(optimized_sql, REAL_DB_URI)
    if not explain_result.get("success", False):
        print("🚫 触发物理一票否决！大模型生成的 SQL 存在语法/方言错误。")
        feedback_msg = HumanMessage(
            content=f"【致命错误】您的优化草案在物理沙箱中直接执行失败（语法错误或字段不明）！\n引擎报错信息: {explain_result.get('msg')}\n请仔细阅读报错，重新生成能够运行的 SQL 草案！"
        )
        return {
            "is_valid": True,
            "messages": [feedback_msg],
            "review_score": 0,
            "retry_count": retry_count + 1
        }
    logic_result = verify_logic_equivalence(bad_sql, optimized_sql, REAL_DB_URI)
    if not logic_result.get("is_equivalent", False):
        print("🚫 触发物理一票否决！逻辑校验未通过，直接打回重审。")
        feedback_msg = HumanMessage(
            content=f"【物理沙箱执行失败】您的优化草案改变了原有的业务逻辑！\n沙箱反馈: {logic_result.get('msg')}\n请立即修复并重新生成 SQL！"
        )
        return {
            "is_valid": True,  # 流程继续流转（打回），没有彻底崩溃
            "messages": [feedback_msg],
            "review_score": 0,
            "retry_count": retry_count + 1
        }
    evaluator_chain = llm.with_structured_output(EvaluationResult, method="function_calling")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个冷酷的数据库架构审查主席。
                    目前该 SQL 已完美通过物理沙箱的【可执行性测试】和【逻辑一致性测试】。

                    你的唯一任务是基于 EXPLAIN 执行计划，评估其【性能提升】：
                    1. 扫描红线：阅读执行计划的 JSON，如果 type 是 ALL（全表扫描），或者没有走任何索引，必须判定 passed=False！
                    2. 如果走了高效索引（如 ref, range, eq_ref），则基于优化程度打分。

                    满分100分，>70分 passed=True。"""),

        ("user", """审查以下优化草案：
                    【原 SQL】: {bad_sql}
                    【草案 SQL】: {optimized_sql}

                    === EXPLAIN 物理计划 ===
                    {explain_data}
                    =======================

                    请基于上述执行计划给出你的打分，并在 feedback 中说明性能提升点或严厉指出剩余的性能瓶颈！""")
    ])
    try:
        result: EvaluationResult = (prompt | evaluator_chain).invoke({
            "bad_sql": bad_sql,
            "optimized_sql": optimized_sql,
            "explain_data": explain_result.get("data", "未获取到执行计划")
        })
    except ValidationError as e:
        print(f"⚠️ Evaluator 输出格式崩坏: {e}")
        # 如果是评委自己格式崩坏，算作打回一次，让上游重写
        return {
            "is_valid": True,
            "retry_count": retry_count + 1,
            "messages": [HumanMessage(content=f"【系统打回】审查官服务返回格式异常，本次评估作废，请重试。")]
        }
    except Exception as e:
        print(f"⚠️ Evaluator 节点服务发生未知异常: {e}")
        return {
            "is_valid": False,
            "messages": [AIMessage(content=f"【阻断】审查官服务宕机，流程终止。详细信息: {e}")]
        }
    # 判断并打回重审
    if not result.passed:
        feedback_msg = HumanMessage(
            content=f"【沙箱审查未通过】打分:{result.score}。审查意见：{result.feedback}。请结合这些物理沙箱的反馈，重新修改 SQL！"
        )
        return {
            "is_valid": True,
            "messages": [feedback_msg],
            "review_score": result.score,
            "retry_count": retry_count + 1
        }
    return {
        "is_valid": True,
        "review_score": result.score,
        "retry_count": retry_count
    }