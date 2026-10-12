import os
import concurrent.futures
from lxml import etree
from langchain_core.messages import HumanMessage

from tools.xml_scanner import scan_project_mappers
from graph.workflow import master_agent_app
from tools.report_generator import generate_markdown_report


def _process_single_sql(item: dict, db_uri: str) -> dict:
    """内部工作函数：将 XML 与单条 SQL 送入 Agent 物理沙箱流转并缝合"""
    # 1. 从扫描器字典里取值（扫描器用的 key 是 'id'，我们赋值给变量 sql_id 避免覆盖 Python 内置的 id 函数）
    sql_id = item['id']
    raw_sql = item['original_sql']
    raw_xml = item.get('raw_xml_fragment', '')

    initial_state = {
        "raw_xml_fragment": raw_xml,
        "extracted_raw_sql": raw_sql,
        "is_valid": True,
        "db_uri": db_uri,
        "messages": [HumanMessage(content=f"请分析并缝合 Mapper 节点: {sql_id}")]
    }

    # 触发核心工作流 (先去底层 SQL 沙箱压测，再回顶层 Mapper 缝合)
    final_state = master_agent_app.invoke(initial_state)

    # 提取最终缝合结果与校验状态
    is_valid = final_state.get("is_valid", True)
    score = final_state.get("review_score", 0)
    reconstructed_xml = final_state.get("reconstructed_xml")
    optimized_sql = final_state.get("optimized_plain_sql")
    error_msg = final_state.get("error_msg")

    # 2. 组装审计结果字典（统一使用 'sql_id'，完美匹配 report_generator.py）
    return {
        "file_path": item["file_path"],
        "sql_id": sql_id,  # <--- 统一叫 sql_id！彻底解决报告 N/A 问题
        "type": item["type"],
        "original_sql": raw_sql,
        "optimized_sql": optimized_sql,
        "final_xml_fragment": reconstructed_xml,
        "score": score,
        "is_valid": is_valid,
        "error_msg": error_msg,
        "block_node": "mapper_stitcher" if not is_valid else None,
        "block_reason": error_msg,
        "feedback": final_state.get("feedback") if is_valid else error_msg
    }


def save_fixed_mappers(audit_results: list, output_dir: str):
    """
    纯粹的文件落盘器：将内存里已经完全合法的 XML 片段，精准热替换回原 Mapper 文件并输出到 fixed_mappers 目录
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. 收集所有成功缝合的节点 (按文件路径分组)
    file_updates = {}
    for res in audit_results:
        if res.get("is_valid") and res.get("score", 0) >= 70 and res.get("final_xml_fragment"):
            fpath = res["file_path"]
            file_updates.setdefault(fpath, {})[res["sql_id"]] = res["final_xml_fragment"]

    if not file_updates:
        return

    parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)

    # 2. 遍历原文件，执行 DOM 节点级替换并落盘
    for fpath, id_map in file_updates.items():
        try:
            tree = etree.parse(fpath, parser)
            root = tree.getroot()

            for select_node in root.findall("select"):
                node_id = select_node.get("id")
                if node_id in id_map:
                    # 方案一已经保证了这段 XML 语法 100% 合法，这里直接解析，无需任何正则清洗！
                    new_inner_xml = id_map[node_id]
                    temp_root = etree.fromstring(f"<temp_wrapper>\n    {new_inner_xml}\n  </temp_wrapper>", parser)

                    # 清空原节点内部旧内容，塞入新内容
                    for child in list(select_node):
                        select_node.remove(child)
                    select_node.text = temp_root.text
                    for child in temp_root:
                        select_node.append(child)

            out_path = os.path.join(output_dir, os.path.basename(fpath))
            tree.write(out_path, encoding="utf-8", xml_declaration=True)
            print(f"📦 [构建产物] 已生成修复版 Mapper 文件 -> {out_path} (成功重构 {len(id_map)} 处节点)")

        except Exception as e:
            print(f"❌ 生成修复文件失败 [{fpath}]: {str(e)}")


def run_devops_pipeline(target_dir: str, db_uri: str, max_workers: int = 3):
    """
    正式的并发流水线入口
    """
    print(f"🚀 [DevOps 流水线] 启动代码库扫描: {target_dir}")

    extracted_sqls = scan_project_mappers(target_dir)
    if not extracted_sqls:
        print("✅ 未发现待迁移的 XML SQL。")
        return []

    print(f"\n⚙️ 启动并发引擎 (线程数: {max_workers})，将 {len(extracted_sqls)} 条 SQL 与 XML 送入 Agentic-DB...")

    audit_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sql = {executor.submit(_process_single_sql, item, db_uri): item for item in extracted_sqls}

        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_sql):
            completed_count += 1
            item = future_to_sql[future]
            file_name = os.path.basename(item['file_path'])

            try:
                result = future.result()
                audit_results.append(result)

                # 终端实时反馈进度（这里用 result['sql_id'] 取值，清晰明了）
                if result['is_valid'] and result['score'] >= 70:
                    print(
                        f"[{completed_count}/{len(extracted_sqls)}] ✅ {file_name} -> {result['sql_id']} (完美缝合 | 沙箱打分: {result['score']})")
                else:
                    print(
                        f"[{completed_count}/{len(extracted_sqls)}] ❌ {file_name} -> {result['sql_id']} (校验熔断: {result.get('error_msg')})")
            except Exception as exc:
                print(f"[{completed_count}/{len(extracted_sqls)}] 💥 {file_name} -> {item['id']} 发生程序异常: {exc}")
                audit_results.append({
                    "file_path": item["file_path"],
                    "sql_id": item["id"],
                    "type": item["type"],
                    "original_sql": item["original_sql"],
                    "optimized_sql": None,
                    "final_xml_fragment": None,
                    "score": 0,
                    "is_valid": False,
                    "block_node": "System Exception (系统异常)",
                    "block_reason": str(exc)
                })
    print("\n🎉 全部流转完成！")
    return audit_results


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_mapper_dir = os.path.join(current_dir, "examples")
    fixed_mapper_dir = os.path.join(current_dir, "fixed_mappers")

    final_reports = run_devops_pipeline(test_mapper_dir, "mysql+pymysql://root:root@127.0.0.1:3306/ai_note",
                                        max_workers=3)

    if final_reports:
        # 1. 生成 Markdown 审计报告
        generate_markdown_report(final_reports)
        # 2. 生成修复后的 XML 文件到 fixed_mappers 目录
        save_fixed_mappers(final_reports, fixed_mapper_dir)