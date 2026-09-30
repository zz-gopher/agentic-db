import os
import concurrent.futures
from langchain_core.messages import HumanMessage

# 引入你的解析器和 Agent 图
from cli.xml_scanner import scan_project_mappers
from graph.workflow import agent_app

from tools.report_generator import generate_markdown_report

def _process_single_sql(item: dict) -> dict:
    """内部工作函数：将单条 SQL 送入 Agent 物理沙箱流转"""
    sql_id = item['id']
    raw_sql = item['original_sql']

    # 组装 LangGraph 需要的初始状态
    initial_state = {
        "bad_sql": raw_sql,
        "messages": [HumanMessage(content=f"请优化:  {raw_sql}")]
    }

    # 触发核心工作流
    final_state = agent_app.invoke(initial_state)

    # 提取沙箱打分和最终生成的 SQL
    score = final_state.get("review_score", 0)
    is_valid = final_state.get("is_valid", True)
    draft = final_state.get("final_draft")


    return {
        "file_path": item["file_path"],
        "sql_id": sql_id,
        "type": item["type"],
        "original_sql": raw_sql,
        "optimized_sql": draft.optimized_sql if draft else None,
        "score": score,
        "is_valid": is_valid,
        "block_node": final_state.get("block_node"),
        "block_reason": final_state.get("block_reason")
    }


def run_devops_pipeline(target_dir: str, max_workers: int = 5):
    """
    正式的并发流水线入口
    """
    print(f"🚀 [DevOps 流水线] 启动代码库扫描: {target_dir}")

    # 1. 调用提取器 (目前只扫描 SELECT)
    extracted_sqls = scan_project_mappers(target_dir)

    if not extracted_sqls:
        print("✅ 未发现待迁移的 XML SQL。")
        return []

    print(f"\n⚙️ 启动并发引擎 (线程数: {max_workers})，将 {len(extracted_sqls)} 条 SQL 送入 Agentic-DB...")

    audit_results = []

    # 2. 线程池并发调用 Agent
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sql = {executor.submit(_process_single_sql, item): item for item in extracted_sqls}

        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_sql):
            completed_count += 1
            item = future_to_sql[future]
            file_name = os.path.basename(item['file_path'])

            try:
                result = future.result()
                audit_results.append(result)

                # 终端实时反馈进度
                if result['is_valid'] and result['score'] >= 70:
                    print(
                        f"[{completed_count}/{len(extracted_sqls)}] ✅ {file_name} -> {item['id']} (打分: {result['score']})")
                else:
                    print(f"[{completed_count}/{len(extracted_sqls)}] ❌ {file_name} -> {item['id']} (熔断)")
            except Exception as exc:
                print(f"[{completed_count}/{len(extracted_sqls)}] 💥 {file_name} -> {item['id']} 发生程序异常: {exc}")

    print("\n🎉 全部流转完成！")
    return audit_results


if __name__ == "__main__":
    # 测试环境：指向 cli 目录去扫描你刚刚建好的 TestMapper.xml
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_mapper_dir = os.path.join(current_dir, "cli")

    # 触发整条流水线
    final_reports = run_devops_pipeline(test_mapper_dir, max_workers=3)
    if final_reports:
        generate_markdown_report(final_reports, output_path="Migration_Audit_Report.md")