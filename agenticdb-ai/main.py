import os
import uvicorn
import shutil
import zipfile
import tempfile
import subprocess

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response
from pydantic import BaseModel, Field
from typing import List, Optional
from graph.workflow import agent_app as agentic_graph
from run_pipeline import run_devops_pipeline
from tools.report_generator import generate_markdown_report

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


@app.post("/api/v1/audit-project")
def audit_project_cloud(
        # 核心沙箱参数
        db_uri: str = Form(...,
                           description="沙箱数据库连接串 (例如: mysql+pymysql://root:root@127.0.0.1:3306/ai_note)"),

        # 源码获取方式 (Git 或 ZIP，二选一)
        git_url: Optional[str] = Form(None, description="Git 仓库地址 (如 https://github.com/xxx.git)"),
        git_branch: Optional[str] = Form("main", description="Git 分支名"),
        file: Optional[UploadFile] = File(None, description="Spring项目的 .zip 压缩包"),
        max_workers: int = Form(3, description="并发执行的线程数")
):
    """
    云端项目级扫描与审计闭环：
    获取源码 (Git/ZIP) -> 扫描提取 SQL -> 送入沙箱 Agent -> 直接返回结果与 Markdown 报告文本
    """
    if not git_url and not file:
        raise HTTPException(status_code=400, detail="必须提供 git_url 或上传 .zip 文件")

    # 使用临时目录，请求结束自动销毁物理文件，防止磁盘溢出
    with tempfile.TemporaryDirectory() as temp_dir:
        target_scan_dir = os.path.join(temp_dir, "source_code")

        try:
            # 1. 源码落地机制
            if git_url:
                print(f"📦 正在从 {git_url} (分支: {git_branch}) 拉取代码...")
                subprocess.run(
                    ["git", "clone", "-b", git_branch, "--single-branch", git_url, target_scan_dir],
                    check=True, capture_output=True, text=True
                )
            elif file:
                if not file.filename.endswith('.zip'):
                    raise HTTPException(status_code=400, detail="必须上传 .zip 压缩包")
                zip_path = os.path.join(temp_dir, file.filename)
                with open(zip_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(target_scan_dir)

            # 2. 触发核心并发流水线，传入目标目录与沙箱连接串
            print(f"🚀 启动沙箱打分流水线，目标库: {db_uri}")
            audit_results = run_devops_pipeline(target_scan_dir, db_uri, max_workers)

            if not audit_results:
                return {
                    "status": "success",
                    "total_scanned": 0,
                    "message": "未在项目中扫描到任何 MyBatis XML 语句"
                }

            report_path = generate_markdown_report(audit_results)

            report_content = ""
            if report_path and os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report_content = f.read()

            if not report_content:
                return {"message": "报告生成失败"}

            return Response(
                content=report_content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="Agentic_SQL_Audit_Report.md"'
                }
            )

        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"Git 拉取失败: {e.stderr}")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="压缩包损坏，无法解压")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"流水线执行异常: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)