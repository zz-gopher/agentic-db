from pydantic import BaseModel, Field

class SqlOptimizationDraft(BaseModel):
    thinking: str = Field(description="CoT推导：原SQL慢的原因分析")
    optimizedSql: str = Field(description="最终优化后的SQL")
    reason: str = Field(description="优化理由总结")

class EvaluationResult(BaseModel):
    score: int = Field(description="打分结果，满分100")
    passed: bool = Field(description="是否通过审查，>85分为True")
    feedback: str = Field(description="具体的改进建议")