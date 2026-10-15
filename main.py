import os
import re

import uvicorn
import shutil
import zipfile
import tempfile
import subprocess
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response
from pydantic import BaseModel, Field

# 引入底层纯 SQL 沙箱与外层 Mapper 缝合网关
from graph.workflow import agent_app as sql_agent_graph

# 引入流水线与文件落盘工具
from run_pipeline import run_devops_pipeline, save_fixed_mappers
from tools.report_generator import generate_markdown_report

app = FastAPI(title="Agentic-DB SQL & Mapper Optimizer API", version="2.0.0")


def normalize_db_uri(db_uri: str) -> str:
    """
    智能转换数据库连接串：
    如果后端运行在 Docker 容器中，自动将用户习惯输入的 127.0.0.1 / localhost
    静默重写为宿主机穿透地址 host.docker.internal，实现用户端零感知。
    """
    # 判断当前代码是否运行在 Docker 容器内（通过检测根目录下的 .dockerenv 文件）
    in_docker = os.path.exists('/.dockerenv') or os.environ.get('IN_DOCKER') == 'true'

    if in_docker:
        # 使用正则精准替换 @ 后面的 localhost 或 127.0.0.1
        new_uri = re.sub(r'@(localhost|127\.0\.0\.1)(:|/)', r'@host.docker.internal\2', db_uri)
        if new_uri != db_uri:
            print(f"🔄 [网络穿透] 检测到容器环境，已自动将本地回环地址映射为宿主机地址: {new_uri}")
            return new_uri
    return db_uri

# ==========================================
# 1. 数据模型定义 (Pydantic Models)
# ==========================================
class SQLAuditRequest(BaseModel):
    sql: str = Field(..., description="需要审计的原始纯 SQL")
    db_uri: str = Field(..., description="沙箱数据库连接串")


class SQLAuditResponse(BaseModel):
    is_valid: bool
    optimized_sql: Optional[str] = None
    score: int = 0
    feedback: Optional[str] = None
    block_reason: Optional[str] = None


class GitProjectAuditRequest(BaseModel):
    """Git 仓库审计专用请求体 (纯 JSON 交互，清爽规范)"""
    git_url: str = Field(..., description="Git 仓库地址 (如 https://github.com/xxx/xxx.git)")
    git_branch: str = Field(default="main", description="Git 分支名")
    db_uri: str = Field(..., description="沙箱数据库连接串 (如 mysql+pymysql://root:root@127.0.0.1:3306/ai_note)")
    max_workers: int = Field(default=3, description="并发执行的线程数")


# ==========================================
# 2. 内部公共执行引擎 (DRY 原则：复用于 Git 与 ZIP 接口)
# ==========================================
def _execute_project_pipeline_and_package(target_scan_dir: str, temp_dir: str, db_uri: str,
                                          max_workers: int) -> Response:
    """
    核心公共函数：执行扫描 -> 沙箱压测与 XML 缝合 -> 生成报告与修复版 XML -> 打包返回
    """
    db_uri = normalize_db_uri(db_uri)
    print(f"🚀 启动沙箱打分与 XML 缝合流水线，目标库: {db_uri}")
    audit_results = run_devops_pipeline(target_scan_dir, db_uri, max_workers)

    if not audit_results:
        raise HTTPException(status_code=404, detail="未在项目中扫描到任何可处理的 MyBatis XML <select> 节点")

    # 1. 创建交付物归档目录
    artifact_dir = os.path.join(temp_dir, "Agentic_Audit_Artifacts")
    os.makedirs(artifact_dir, exist_ok=True)

    # 2. 生成 Markdown 审计报告 (直接写入归档目录)
    report_path = os.path.join(artifact_dir, "Agentic_SQL_Audit_Report.md")
    generate_markdown_report(audit_results, output_path=report_path)

    # 3. 生成修复后的 Mapper XML 文件 (写入归档目录下的 fixed_mappers 文件夹)
    fixed_mappers_dir = os.path.join(artifact_dir, "fixed_mappers")
    save_fixed_mappers(audit_results, output_dir=fixed_mappers_dir)

    # 4. 将【审计报告 + 修复后的 XML 文件夹】一键打包成 ZIP 交付物返回给客户端
    output_zip_base = os.path.join(temp_dir, "Agentic_DB_Deliverables")
    final_zip_path = shutil.make_archive(output_zip_base, 'zip', artifact_dir)

    with open(final_zip_path, "rb") as f:
        zip_bytes = f.read()

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="Agentic_DB_Audit_Deliverables.zip"'
        }
    )


# ==========================================
# 3. API 路由端点
# ==========================================
@app.post("/api/v1/audit", response_model=SQLAuditResponse, summary="单条纯 SQL 沙箱审计")
async def audit_single_sql(request: SQLAuditRequest):
    """同步等待单条纯 SQL 审查结果的端点"""
    target_db_uri = normalize_db_uri(request.db_uri)
    try:
        initial_state = {
            "bad_sql": request.sql,
            "db_uri": target_db_uri,
            "retry_count": 0,
            "messages": []
        }

        final_state = await sql_agent_graph.ainvoke(initial_state)
        draft_obj = final_state.get("final_draft")
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


@app.post("/api/v1/audit-project/git", summary="项目级审计 (通过 Git 仓库拉取)")
def audit_project_by_git(request: GitProjectAuditRequest):
    """
    通过传入 Git 仓库地址拉取源码 -> 自动拆解并优化 Mapper XML -> 返回包含【审计报告 + 修复后 XML】的 ZIP 包
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        target_scan_dir = os.path.join(temp_dir, "source_code")

        try:
            print(f"📦 [Git 模式] 正在从 {request.git_url} (分支: {request.git_branch}) 拉取代码...")
            subprocess.run(
                ["git", "clone", "--depth", "1", "-b", request.git_branch, "--single-branch", request.git_url,
                 target_scan_dir],
                check=True, capture_output=True, text=True
            )
            return _execute_project_pipeline_and_package(
                target_scan_dir=target_scan_dir,
                temp_dir=temp_dir,
                db_uri=request.db_uri,
                max_workers=request.max_workers
            )

        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=400, detail=f"Git 仓库拉取失败，请检查地址或分支名: {e.stderr}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Git 审计流水线执行异常: {str(e)}")


@app.post("/api/v1/audit-project/zip", summary="项目级审计 (通过上传 ZIP 压缩包)")
def audit_project_by_zip(
        db_uri: str = Form(..., description="沙箱数据库连接串 (如 mysql+pymysql://root:root@127.0.0.1:3306/ai_note)"),
        file: UploadFile = File(..., description="包含 MyBatis Mapper 的项目 .zip 压缩包"),
        max_workers: int = Form(3, description="并发执行的线程数")
):
    """
    通过上传项目 .zip 压缩包 -> 自动拆解并优化 Mapper XML -> 返回包含【审计报告 + 修复后 XML】的 ZIP 包
    """
    if not file.filename or not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="文件格式错误：必须上传 .zip 格式的压缩包")

    with tempfile.TemporaryDirectory() as temp_dir:
        target_scan_dir = os.path.join(temp_dir, "source_code")
        zip_path = os.path.join(temp_dir, file.filename)

        try:
            print(f"📦 [ZIP 模式] 正在接收并解压上传文件: {file.filename}...")
            with open(zip_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(target_scan_dir)

            return _execute_project_pipeline_and_package(
                target_scan_dir=target_scan_dir,
                temp_dir=temp_dir,
                db_uri=db_uri,
                max_workers=max_workers
            )

        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="上传的 ZIP 压缩包已损坏，无法解压")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ZIP 审计流水线执行异常: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)