import os
from dotenv import load_dotenv

# 1. 第一时间读取 .env 文件，激活 LangSmith
load_dotenv()
# 1. 禁用 Tokenizer 的底层多线程（解决 Debugger 死锁的绝对核心！）
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# 2. 强制断网离线（防止 Hugging Face 偷偷连网检测新版本导致超时）
os.environ["HF_HUB_OFFLINE"] = "1"

from graph.workflow import agent_app
from langchain_core.messages import HumanMessage

if __name__ == "__main__":
    print("⏳ 正在唤醒 Agent 并加载本地模型，请稍候...")
    # ... 在这里，顶部的 import 已经把模型和图加载进内存了 ...
    print("✅ 系统就绪！")
    bad_query = "SELECT * FROM user_logs WHERE DATE(created_at) = '2026-03-01'"
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

        # 4. 打印结果
        draft = final_state.get("final_draft")
        if draft:
            print(f"\n✅ 优化成功 (打分: {final_state.get('review_score')}):")
            print(draft.optimizedSql)