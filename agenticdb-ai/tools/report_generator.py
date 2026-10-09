import datetime
import os


def generate_markdown_report(audit_results: list, output_path: str = None):
    """
    根据 Agentic-DB 的批量跑批结果生成专业的 Markdown 审计报告
    """
    total_count = len(audit_results)
    if total_count == 0:
        print("没有可生成的报告数据。")
        return

    now = datetime.datetime.now()
    # 报告头部依然保留人类可读的时间格式
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 修改点：生成纯连续数字的 Unix 时间戳作为文件后缀
    if output_path is None:
        # 获取纯数字时间戳，例如: 1788153041
        time_suffix = str(int(now.timestamp()))
        output_path = f"reports/migration_audit_report_{time_suffix}.md"

    # 分类统计
    success_results = [r for r in audit_results if r.get('is_valid') and r.get('score', 0) >= 70]
    failed_results = [r for r in audit_results if not r.get('is_valid') or r.get('score', 0) < 70]

    success_count = len(success_results)
    failed_count = len(failed_results)

    # 1. 组装报告头部
    md_lines = [
        f"# 🚨 Agentic-DB 自动化迁移审计报告",
        f"**扫描时间**: {now_str}",
        f"**总览**: 共扫描 `{total_count}` 条 SQL | ✅ 成功转换: `{success_count}` | ❌ 拦截高危: `{failed_count}`",
        "---",
        "## ❌ 阻断拦截详情 (需人工介入)\n"
    ]

    # 2. 组装失败拦截表格
    if failed_results:
        md_lines.append("| 文件路径 | SQL ID | 拦截节点 | 阻断原因 | 打分 |")
        md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for f in failed_results:
            file_name = os.path.basename(f.get('file_path', 'Unknown'))
            sql_id = f.get('sql_id', 'N/A')
            # 优先取节点明确报出的原因，如果没有则取兜底
            node = f.get('block_node', 'Evaluator (审查打回)')
            reason = f.get('block_reason', f.get('error_reason', '审查不达标'))
            score = f.get('score', 0)

            # 清洗换行符，防止破坏 Markdown 表格结构
            clean_reason = str(reason).replace('\n', ' ').replace('\r', '')[:100]
            md_lines.append(f"| `{file_name}` | `{sql_id}` | {node} | {clean_reason} | {score} |")
    else:
        md_lines.append("> 🎉 完美运行，未发现任何高危拦截。")

    md_lines.extend(["\n---", "## ✅ 核心优化成果展示\n"])

    # 3. 展示所有成功的 SQL
    if success_results:
        for s in success_results:
            file_name = os.path.basename(s.get('file_path', 'Unknown'))
            md_lines.append(f"### 🎯 [{file_name} -> {s.get('sql_id')}]")
            md_lines.append(f"**沙箱验证得分**: `{s.get('score')}`")
            md_lines.append("**[原版 SQL]**:")
            md_lines.append("```sql\n" + str(s.get('original_sql')).strip() + "\n```")
            md_lines.append("**[Agentic-DB 优化版]**:")
            md_lines.append("```sql\n" + str(s.get('optimized_sql')).strip() + "\n```")
            feedback = s.get('feedback', '经过沙箱与大模型联合评估，原 SQL 逻辑已达标或优化方案已验证通过。')
            # 替换换行符以确保在 Markdown 引用块中渲染正常
            clean_feedback = str(feedback).replace('\n', '\n> ')
            md_lines.append(f"> **💡 优化/诊断建议**:\n> {clean_feedback}\n")

            md_lines.append("---")
    else:
        md_lines.append("> 暂无成功优化的案例。")

    # 在写入前自动创建目标文件夹
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 写入文件
    final_md = "\n".join(md_lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_md)

    print(f"\n📊 审计报告已生成: {os.path.abspath(output_path)}")
    return os.path.abspath(output_path)