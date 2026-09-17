from graph.workflow import agent_app
from langchain_core.messages import HumanMessage

if __name__ == "__main__":
    # 准备一句烂 SQL
    bad_query = "SELECT * FROM user_logs WHERE DATE(created_at) = '2026-03-01'"

    # 模拟第一次放入档案袋的数据
    # 注意：为了触发你的断点，我们要保证大模型一开始不知道 user_logs 的表结构！
    initial_state = {
        "bad_sql": bad_query,
        "messages": [HumanMessage(content=f"请优化: {bad_query}")]
    }

    print("🚀 启动 Agent 工作流...")

    # 运行图！
    final_state = agent_app.invoke(initial_state)
    print("\n🎉 工作流执行完毕！")

    # 获取最终提取出的 Pydantic 对象
    final_draft = final_state.get("final_draft")

    if final_draft:
        print("\n✅ 最终优化草案 (JSON):")
        print(final_draft.model_dump_json(indent=2))
    else:
        print("\n⚠️ 未能生成结构化草案。最后的消息是：")
        print(final_state["messages"][-1].content)

    print("\n⚖️ 批评家最终打分:", final_state.get("review_score"))