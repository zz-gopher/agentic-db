from langchain_core.prompts import ChatPromptTemplate
from core.config import llm
from schemas.models import SqlOptimizationDraft, EvaluationResult
from tools.db_tools import get_table_schema

class SqlAgents:
    def __init__(self):
        # 生成器绑定工具
        generator_model = llm.bind_tools([get_table_schema])
        self.generator_chain = generator_model.with_structured_output(
            SqlOptimizationDraft, method="function_calling"
        )
        # 批评家
        self.evaluator_chain = llm.with_structured_output(
            EvaluationResult, method="function_calling"
        )

    def generate_draft(self, examples: str, feedback: str, bad_sql: str) -> SqlOptimizationDraft:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是数据库调优专家。如果不知道表结构，请务必先使用工具查询。\n【约束】：必须在 thinking 字段推演原因。"),
            ("user", "{examples}\n【历史反馈】：{feedback}\n请优化：\n{bad_sql}")
        ])
        chain = prompt | self.generator_chain
        return chain.invoke({"examples": examples, "feedback": feedback, "bad_sql": bad_sql})

    def evaluate_draft(self, bad_sql: str, draft: SqlOptimizationDraft) -> EvaluationResult:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是架构审查主席。审查维度：1.消除全表扫描 2.逻辑等价。满分100，>85分 passed=True。"),
            ("user", "审查以下优化草案：\n原SQL: {bad_sql}\n草案: {draft}")
        ])
        chain = prompt | self.evaluator_chain
        return chain.invoke({"bad_sql": bad_sql, "draft": draft.model_dump_json()})