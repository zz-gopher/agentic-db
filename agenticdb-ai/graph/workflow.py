from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.documents import Document
from core.config import llm
from retrievers.vector_repo import vector_store
from schemas.models import SqlOptimizationDraft, EvaluationResult, ExperienceTagging, DiagnosticResult, TableExtraction
from tools.db_tools import get_table_schema
from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgenticState

tools = [get_table_schema]
tool_node = ToolNode(tools)


def generator_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    table_schema = state.get("table_schema", "暂无表结构")
    db_engine = state.get("db_engine", "mysql")
    examples_list = state.get("examples", [])
    examples_str = "\n".join(examples_list) if examples_list else "未检索到相关经验。"

    tools_and_schemas = [SqlOptimizationDraft]
    llm_with_tools = llm.bind_tools(tools_and_schemas)

    prompt = ChatPromptTemplate.from_template("""你是一个顶级的数据库优化专家。
        【原始 SQL】: {bad_sql}
        【表结构】: {schema}

        【知识库调取的优化法则】:
        {examples}

        任务：
        1. 结合知识库法则和表结构，推导优化方案，并在 thinking 字段写下推理过程。
        2. 必须调用 SqlOptimizationDraft 工具输出最终的优化方案。
        """)

    response = (prompt | llm_with_tools).invoke({
        "bad_sql": bad_sql,
        "schema": table_schema,
        "examples": examples_str
    })

    return {"messages": [response]}

def evaluator_node(state: AgenticState) -> dict:
    """批评家节点：负责打分，如果不通过则生成反馈消息"""
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")

    # 审查官不需要查数据库工具，直接强制输出 EvaluationResult JSON
    evaluator_chain = llm.with_structured_output(EvaluationResult, method="function_calling")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是架构审查主席。审查维度：1.消除全表扫描 2.逻辑等价。满分100，>70分 passed=True。"),
        ("user", "审查以下优化草案：\n原SQL: {bad_sql}\n草案: {draft}")
    ])

    # 调用大模型进行打分
    result: EvaluationResult = (prompt | evaluator_chain).invoke({
        "bad_sql": bad_sql,
        "draft": draft.model_dump_json() if draft else ""
    })

    # 核心逻辑：如果不通过，把反馈意见变成一条新的要求，塞进聊天记录里！
    if not result.passed:
        feedback_msg = HumanMessage(
            content=f"【审查未通过】打分:{result.score}。审查意见：{result.feedback}。请结合这些反馈重新修改 SQL！"
        )
        # 返回新消息，框架会自动触发 add_messages 追加，并更新分数
        return {"messages": [feedback_msg], "review_score": result.score}

    # 如果通过了，什么新消息都不用加，只记录高分
    return {"review_score": result.score}


def parse_json_node(state: AgenticState) -> dict:
    """当大模型提交最终方案时，这个节点负责把参数提取成 Pydantic 对象"""
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        # 理论上永远不会走到这里，除非路由写错了
        raise ValueError("解析节点收到了非预期的消息类型，缺少 tool_calls")
    # 获取大模型传入的 SqlOptimizationDraft 的参数
    draft_args = last_message.tool_calls[0]["args"]
    # 转换回强类型的 Pydantic 模型
    draft_obj = SqlOptimizationDraft(**draft_args)

    # 明确赋值给档案袋的 final_draft 字段
    return {"final_draft": draft_obj}


def route_after_generation(state: AgenticState) -> str:
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END

    tool_name = last_message.tool_calls[0]["name"]

    if tool_name == "get_table_schema":
        return "tools"
    elif tool_name == "SqlOptimizationDraft":
        return "parse_json"

    return END

# 查询历史经验
def retriever_node(state: AgenticState) -> dict:
    diagnoses = state.get("suspected_diagnoses", [])

    if not diagnoses:
        return {"examples": []}

    # 利用 ChromaDB 的 metadata 过滤功能
    # 只要命中了疑似的标签，就把库里对应的“精华法则”抽调出来
    results = vector_store.similarity_search(
        query="",  # 不再需要做向量比对
        k=5,
        filter={"anti_pattern": {"$in": diagnoses}}  # 直接匹配反模式标签
    )

    # 提取纯粹的优化法则片段
    rules = [doc.page_content for doc in results]
    return {"examples": rules}

def memory_node(state: AgenticState) -> dict:
    bad_sql = state.get("bad_sql", "")
    draft = state.get("final_draft")
    db_engine = state.get("db_engine", "mysql")

    # 如果没有最终草案，说明出了异常，直接跳过
    if not draft:
        return {}

    # 1. 召唤“标签提取员”，强制输出 JSON 标签
    tagging_chain = llm.with_structured_output(ExperienceTagging, method="function_calling")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个数据库经验总结专家。
            请对比用户输入的烂SQL和最终的优化草案，提取出最通用的【病理特征】和【错误标签】。
            注意：诊断说明必须具有泛化性，不要包含具体的业务表名。"""),
            ("user", "原SQL: {bad_sql}\n优化后SQL: {good_sql}")
    ])

    # 动态生成标签
    tags: ExperienceTagging = (prompt | tagging_chain).invoke({
        "bad_sql": bad_sql,
        "good_sql": draft.optimized_sql
    })

    # 2. 组装为 Chroma 需要的向量文档格式
    doc = Document(
        page_content=tags.diagnosis,  # 核心向量特征：用病理描述去计算相似度
        metadata={
            "db_type": db_engine,
            "anti_pattern": tags.anti_pattern,
            "example_bad": bad_sql,
            "example_good": draft.optimized_sql
        }
    )

    # 3. 永久写入本地向量库
    vector_store.add_documents([doc])
    print(f"\n 新经验已自动入库！标签分类: {tags.anti_pattern}")
    print(f" 提炼法则: {tags.diagnosis}\n")

    # 状态无需改变，只做副作用操作 (Side Effect)
    return {}


def diagnostic_node(state: AgenticState) -> dict:
    bad_sql = state["bad_sql"]
    schema = state.get("table_schema", "")

    # 让大模型先用自己的原生智力“看个大概”
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个顶级的数据库性能诊断专家。请仔细分析 SQL 的性能瓶颈。

            你必须从以下反模式标签库中选择对应的病因（可多选）：
            - func_index: 在 WHERE 条件的等号左侧对字段使用了函数或计算。
            - implicit_conversion: 传入的参数类型与表字段类型不一致，导致隐式转换。
            - select_all: 在没有必要的情况下使用了 SELECT *。
            - deep_paging: 使用了 LIMIT M, N 且 M 的值非常大。
            - missing_join_index: JOIN 关联的多表字段没有建立有效索引。
            - other: 明确不属于以上任何一种情况。"""),

        ("user", "【分析这句SQL】: {bad_sql} \n【表结构】: {schema}")
    ])

    chain = prompt | llm.with_structured_output(DiagnosticResult, method="function_calling")
    result = chain.invoke({
        "bad_sql": bad_sql,
        "schema": schema
    })

    return {
        "suspected_diagnoses": result.suspected_patterns,
        # 可以把大模型的初步推理记录进消息流，供后续节点参考
        "messages": [HumanMessage(content=f"初步诊断: {result.diagnostic_reasoning}")]
    }


def prepare_schema_node(state: AgenticState) -> dict:
    """前置节点：专门负责提取表名并获取表结构，然后再进入诊断"""
    bad_sql = state["bad_sql"]

    # 1. 快速提取表名
    extractor = llm.with_structured_output(TableExtraction, method="function_calling")
    result = extractor.invoke(f"请提取以下SQL中涉及的所有数据库表名，只需返回表名即可：\n{bad_sql}")

    # 2. 循环调用现有的查表工具
    schemas = []
    for table_name in result.tables:
        try:
            schema_info = get_table_schema.invoke({"table_name": table_name})
            schemas.append(f"-- 表 {table_name} 结构 --\n{schema_info}")
        except Exception as e:
            schemas.append(f"-- 表 {table_name} 结构获取失败: {e} --")

    return {"table_schema": "\n".join(schemas)}

# 初始化一张图，状态挂载上去
workflow = StateGraph(AgenticState)
workflow.add_node("prepare_schema", prepare_schema_node)
workflow.add_node("diagnostic_node", diagnostic_node)
workflow.add_node("retriever", retriever_node)
workflow.add_node("generator", generator_node)
workflow.add_node("evaluator", evaluator_node)
workflow.add_node("parse_json", parse_json_node)
workflow.add_node("memory_node", memory_node)

workflow.add_edge(START, "prepare_schema")             # 1. 查表结构
workflow.add_edge("prepare_schema", "diagnostic_node") # 2. 根据表结构和SQL看病
workflow.add_edge("diagnostic_node", "retriever")      # 3. 找药方
workflow.add_edge("retriever", "generator")            # 4. 生成草案
workflow.add_edge("generator", "parse_json")           # 5. 解析 JSON
workflow.add_edge("parse_json", "evaluator")           # 6. 审查打分

def route_after_evaluation(state: AgenticState) -> str:
    if state.get("review_score", 0) > 80:
        return "memory_node"
    else:
        return "generator"

workflow.add_conditional_edges("evaluator", route_after_evaluation)
workflow.add_edge("memory_node", END)

# 编译成可执行的 Agent 引擎
agent_app = workflow.compile()