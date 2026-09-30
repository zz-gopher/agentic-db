import os
from dotenv import load_dotenv

# 1. 第一时间读取 .env 文件，激活 LangSmith
load_dotenv()

from graph.workflow import agent_app
from langchain_core.messages import HumanMessage

if __name__ == "__main__":
    print("⏳ 正在唤醒 Agent 并加载本地模型，请稍候...")
    # ... 在这里，顶部的 import 已经把模型和图加载进内存了 ...
    print("✅ 系统就绪！")
    bad_query = "SELECT * FROM notes WHERE DATE(created_at) = '2026-03-01'"
    while True:
        # 1. 持续监听输入
        bad_query = input("\n👇 请输入烂 SQL (输入 'q' 退出): ")
        if bad_query.lower() == 'q':
            print("再见！")
            break

        # 2. 组装初始状态
        initial_state = {
            "bad_sql": bad_query,
            "messages": [HumanMessage(content=f"请优化: {bad_query}")]
        }

        print("🚀 正在流转节点...")
        # 3. 执行工作流 (这里是秒级的，因为模型全在内存里)
        final_state = agent_app.invoke(initial_state)
        score = final_state.get("review_score", 0)
        is_valid = final_state.get("is_valid", True)
        retry_count = final_state.get("retry_count", 0)
        if is_valid and score >= 70:
            draft = final_state.get("final_draft")
            print(f"\n✅ 优化成功 (最终打分: {score}):")

            # 打印拆分后的结构化数据
            if draft:
                if draft.index_recommendations:
                    print("-- 建议添加的索引 --")
                    for idx_sql in draft.index_recommendations:
                        print(idx_sql)
                    print("----------------------")

                print(f"{draft.optimized_sql}")

        else:
            print(f"\n❌ 优化失败或被熔断 (最终打分: {score})")

            # 精准提示失败原因
            if retry_count >= 3:
                print("【失败原因】: 多次尝试均无法通过物理沙箱验证，触发系统熔断。")
            elif not is_valid:
                # 打印最后一条错误阻断信息
                messages = final_state.get("messages", [])
                if messages:
                    print(f"【系统阻断】: {messages[-1].content}")
            else:
                print("【失败原因】: 审查官打分未达标。")
