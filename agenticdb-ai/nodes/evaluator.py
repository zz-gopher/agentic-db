from dotenv import load_dotenv

load_dotenv()
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError
from core.config import llm, settings
from schemas.models import EvaluationResult
from graph.state import AgenticState
from tools.sandbox_tools import get_explain_plan, verify_logic_equivalence


def evaluator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")
    retry_count = state.get("retry_count", 0)

    def _handle_retry(error_title: str, detailed_msg: str, score: int = 0) -> dict:
        """统一处理打回逻辑，如果超过重试次数，直接触发死循环熔断"""
        if retry_count >= 2:  # 0, 1, 2 已经是第三次失败了
            block_msg = f"{error_title} (已达最大重试次数 3)。最后一次报错: {detailed_msg[:100]}"
            print(f"🛑 触发熔断：{block_msg}")
            return {
                "is_valid": False,
                "block_node": "evaluator_node (沙箱护栏)",
                "block_reason": block_msg,
                "messages": [AIMessage(content=f"【阻断】{block_msg}")]
            }

        # 还没超限，正常打回让 Generator 重写
        return {
            "is_valid": True,
            "messages": [HumanMessage(content=f"{error_title}\n{detailed_msg}\n请立即修复并重新生成 SQL！")],
            "review_score": score,
            "retry_count": retry_count + 1
        }

    # ==========================================

    # 兜底防御：上游要是传了个空的过来，直接熔断
    if not draft:
        error_msg = f"【阻断】评测沙箱未接收到优化草案，无法执行。"
        return {
            "is_valid": False,
            "block_node": "evaluator_node (评测)",
            "block_reason": error_msg,
            "messages": [AIMessage(content=error_msg)]
        }

    optimized_sql = draft.optimized_sql.replace("```sql", "").replace("```", "").strip(" \n\r\t;")
    print("⚙️ [物理沙箱] 正在运行 EXPLAIN 并校验数据一致性...")

    # 1. 物理执行校验
    explain_result = get_explain_plan(optimized_sql, settings.db_uri)
    if not explain_result.get("success", False):
        print(f"🚫 触发物理一票否决！引擎报错信息: {explain_result.get('msg')}")
        return _handle_retry(
            error_title="【致命错误】优化草案在物理沙箱中直接执行失败（语法错误或字段不明）！",
            detailed_msg=explain_result.get('msg')
        )

    # 2. 逻辑等价校验
    logic_result = verify_logic_equivalence(bad_sql, optimized_sql, settings.db_uri)
    if not logic_result.get("is_equivalent", False):
        print("🚫 触发物理一票否决！逻辑校验未通过，直接打回重审。")
        return _handle_retry(
            error_title="【物理沙箱执行失败】您的优化草案改变了原有的业务逻辑！",
            detailed_msg=logic_result.get('msg')
        )

    # 3. LLM 审查打分
    evaluator_chain = llm.with_structured_output(EvaluationResult, method="function_calling")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个冷酷的数据库架构审查主席。
                        目前该 SQL 已完美通过物理沙箱的【可执行性测试】和【逻辑一致性测试】。

                        你的唯一任务是基于 EXPLAIN 执行计划，评估其【性能提升】：
                        1. 扫描红线：阅读执行计划的 JSON，如果 type 是 ALL（全表扫描），或者没有走任何索引，必须判定 passed=False！
                        2. 【新增：索引缺失豁免权】：如果你仔细审查草案后，发现 SQL 已经采用了最优的改写方案（例如完美消除了函数包裹、实现了 SARGable），但 EXPLAIN 依然是 ALL，这说明完全是【物理表缺失索引】导致的。此时，你允许判定 passed=True，给 80 分，但必须在 feedback 中提供具体的 ALTER TABLE 建索引建议！
                        3. 如果走了高效索引（如 ref, range, eq_ref），则基于优化程度打分。

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
        return _handle_retry(
            error_title="【系统打回】审查官服务返回格式异常，本次评估作废。",
            detailed_msg=str(e)
        )
    except Exception as e:
        error_msg = f"【阻断】审查官服务宕机，流程终止。详细信息: {e}"
        return {
            "is_valid": False,
            "block_node": "evaluator_node (评测)",
            "block_reason": error_msg,
            "messages": [AIMessage(content=error_msg)]
        }

    # 4. 判断最终打分并打回重审
    if not result.passed:
        return _handle_retry(
            error_title=f"【沙箱审查未通过】打分:{result.score}。",
            detailed_msg=f"审查意见：{result.feedback}",
            score=result.score
        )

    # 完全通过，正常放行
    return {
        "is_valid": True,
        "review_score": result.score,
        "retry_count": retry_count
    }