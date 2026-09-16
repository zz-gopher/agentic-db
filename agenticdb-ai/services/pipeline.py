from agents.sql_agents import SqlAgents
from retrievers.few_shot_repo import FewShotRepository
from schemas.models import SqlOptimizationDraft

class SqlPipelineService:
    def __init__(self):
        self.agents = SqlAgents()
        self.few_shot_repo = FewShotRepository()

    def optimize_with_reflection(self, bad_sql: str) -> SqlOptimizationDraft:
        examples = self.few_shot_repo.find_relevant_examples(bad_sql)
        print(f"注入参考案例:\n{examples}")

        attempt, max_retries = 0, 3
        feedback = "无（初次生成）"

        while attempt < max_retries:
            attempt += 1
            print(f"\n▶️ 第 {attempt} 次迭代...")

            draft = self.agents.generate_draft(examples, feedback, bad_sql)
            print(f"📝 CoT思考: {draft.thinking}\n📝 SQL: {draft.optimizedSql}")

            eval_result = self.agents.evaluate_draft(bad_sql, draft)
            print(f"⚖️ 审查结果: 评分={eval_result.score}, Pass={eval_result.passed}, 意见={eval_result.feedback}")

            if eval_result.passed:
                return draft
            feedback = eval_result.feedback

        raise RuntimeError("达到最大重试次数！")