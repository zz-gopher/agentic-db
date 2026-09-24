from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from core.config import llm
from schemas.models import EvaluationResult
from graph.state import AgenticState

def evaluator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")
    # 初始化/增加重试次数
    retry_count = state.get("retry_count", 0)

    evaluator_chain = llm.with_structured_output(EvaluationResult, method="function_calling")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是架构审查主席。审查维度：1.消除全表扫描 2.逻辑等价。满分100，>70分 passed=True。"),
        ("user", "审查以下优化草案：\n原SQL: {bad_sql}\n草案: {draft}")
    ])

    result: EvaluationResult = (prompt | evaluator_chain).invoke({
        "bad_sql": bad_sql,
        "draft": draft.model_dump_json() if draft else ""
    })

    if not result.passed:
        feedback_msg = HumanMessage(
            content=f"【审查未通过】打分:{result.score}。审查意见：{result.feedback}。请结合这些反馈重新修改 SQL！"
        )
        return {"messages": [feedback_msg], "review_score": result.score, "retry_count": retry_count + 1}

    return {"review_score": result.score, "retry_count": retry_count}