from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional
import uvicorn

# 导入你写好的 LangGraph 引擎和状态定义
from graph.workflow import agent_app as agentic_graph
from graph.state import AgenticState

app = FastAPI(title="Agentic-DB SQL Optimizer API", version="1.0.0")


# 1. 定义请求与响应数据模型
class SQLAuditRequest(BaseModel):
    sql: str = Field(..., description="需要审计的原始 SQL")
    db_uri: str = Field(..., description="沙箱数据库连接串")
    db_engine: str = Field(default="mysql", description="数据库方言")


class SQLAuditResponse(BaseModel):
    is_valid: bool
    optimized_sql: Optional[str] = None
    score: int = 0
    feedback: Optional[str] = None
    block_reason: Optional[str] = None


@app.post("/api/v1/audit", response_model=SQLAuditResponse)
async def audit_single_sql(request: SQLAuditRequest):
    """同步等待审查结果的端点"""
    try:
        initial_state = {
            "bad_sql": request.sql,
            "db_engine": request.db_engine,
            "db_uri": request.db_uri,
            "retry_count": 0,
            "messages": []
        }

        # 异步调用状态机
        final_state = await agentic_graph.ainvoke(initial_state)

        draft_obj = final_state.get("final_draft")
        # 如果对象存在，用点号(.)获取 optimized_sql，否则返回 None
        extracted_sql = draft_obj.optimized_sql if draft_obj else None

        return SQLAuditResponse(
            is_valid=final_state.get("is_valid", False),
            optimized_sql=extracted_sql,
            score=final_state.get("review_score", 0),
            feedback=final_state.get("feedback"),
            block_reason=final_state.get("block_reason")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"审计流水线异常: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)