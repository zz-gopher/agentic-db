from typing import List

from pydantic import BaseModel, Field

from schemas.enums import AntiPatternTag


class SqlOptimizationDraft(BaseModel):
    thinking: str = Field(description="思考过程，分析原 SQL 瓶颈以及应对报错的反思")
    optimized_sql: str = Field(
        description="纯粹的 SELECT 查询语句。绝对不允许包含任何注释、分号或 ALTER/CREATE 等 DDL 语句！")
    # 【新增】：为未来的 Index Agent 准备的专用字段
    index_recommendations: List[str] = Field(
        default_factory=list,
        description="【极其严格】只能包含合法的 ALTER TABLE 或 CREATE INDEX 语句，绝不允许包含任何注释文本或说明性文字。若无则为空。"
    )
class EvaluationResult(BaseModel):
    score: int = Field(description="打分结果，满分100")
    passed: bool = Field(description="是否通过审查")
    feedback: str = Field(description="具体的改进建议")

class ExperienceTagging(BaseModel):
    diagnosis: str = Field(description="一句话总结这个烂SQL的核心病理特征，必须脱敏（不包含具体的表名和字段名）。例如：'对索引字段使用了日期函数导致全表扫描'")
    anti_pattern: AntiPatternTag = Field(description="错误模式的英文简写标签")

class DiagnosticResult(BaseModel):
    suspected_patterns: list[AntiPatternTag] = Field(description="疑似的反模式标签列表。必须且只能从预设的枚举选项中选择。")
    diagnostic_reasoning: str = Field(description="对这句 SQL 可能存在的性能瓶颈的自然语言描述")

class TableExtraction(BaseModel):
    # 它会自动输出一个包含多个元素的列表，例如：["users", "orders", "products"]
    tables: list[str] = Field(description="SQL中涉及的所有表名列表")
