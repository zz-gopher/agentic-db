import re
from lxml import etree
from langchain_core.prompts import ChatPromptTemplate
from graph.mapper_state import MapperAuditState
from config.config import llm  # 确保导入你的 llm
from schemas.models import XmlStitchingResult


def _extract_dynamic_signatures(xml_string: str) -> set:
    """终极静态护栏：提取所有标签、属性与 #{} / ${} 占位符指纹"""
    signatures = []
    # 提取占位符
    for ph in re.findall(r'([#$]\{[^}]+\})', xml_string):
        signatures.append(f"VAR:{ph}")

    # 提取 XML 标签与属性
    try:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(f"<root>{xml_string}</root>", parser)
        for elem in root.iter():
            if elem.tag in ('root', etree.Comment, etree.Entity):
                continue
            sig = f"TAG:{elem.tag}"
            if elem.attrib:
                attrs = ",".join([f"{k}={v}" for k, v in sorted(elem.attrib.items())])
                sig = f"{elem.tag}:{attrs}"
            signatures.append(sig)
    except Exception:
        pass
    return set(signatures)


def mapper_stitcher_node(state: MapperAuditState) -> dict:
    raw_xml = state["raw_xml_fragment"]
    raw_sql = state["extracted_raw_sql"]  # 新增参照物：原版纯 SQL
    optimized_sql = state["optimized_plain_sql"]  # 优化版纯 SQL

    if not optimized_sql:
        return {"is_valid": False, "error_msg": "缝合失败：未获取到优化后的 SQL"}

    # 如果优化前后纯 SQL 一模一样，根本不需要大模型缝合，直接原样返回原始 XML！（省 Token 且 100% 零风险）
    if raw_sql.strip() == optimized_sql.strip():
        return {"is_valid": True, "reconstructed_xml": raw_xml, "error_msg": None}

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个顶尖的 MyBatis AST 语法树重构专家。
        你的任务是执行【三路合并（3-Way Merge）】：
        通过对比【1. 剥离标签后的原版纯 SQL】与【2. 沙箱优化后的纯 SQL】，找出所有的性能优化点，然后将这些优化点精准无损地移植回【3. 原始带标签的 MyBatis XML】中。

        【重构铁律】：
        1. 思维链先行：必须先在 diff_analysis 中明确指出【优化后的纯 SQL】相比【原版纯 SQL】改了哪里（包括表结构重写、JOIN 改写、甚至常量字面量如 '1024' 变成 1024 的隐式类型转换修复），并100%采纳这些性能修改！
        2. 契约不可变：必须 100% 保留原始 XML 中的所有动态标签（<if>, <where>, <choose>, <when>, <foreach>, <bind>, <include> 等）、OGNL 表达式（test="..."）以及 #{{}} / ${{}} 变量名。如果 SQL 结构大改（如子查询拍平为 JOIN），请将对应的 <if> 等标签整体搬迁到新结构的对应逻辑位置上。
        3. XML 语法绝对合法（极其重要）：在生成的 XML 中，如果 SQL 语句里出现了小于号 `<` 或 `<=`（例如时间区间 `created_at < '2023-10-02'`），必须将其转义为 `&lt;` 或使用 `<![CDATA[ < ]]>` 包裹！绝对禁止在 XML 文本中裸露 `<` 号，否则会导致 XML 解析器崩溃！"""),
        ("user", """
        【1. 剥离标签后的原版纯 SQL (参照基准)】:
        {raw_sql}

        【2. 沙箱优化后的纯 SQL (目标性能形态)】:
        {optimized_sql}

        【3. 原始带标签的 MyBatis XML (待重构源码)】:
        {raw_xml}
        """)
    ])

    # 使用 structured_output 强迫大模型先思考 diff_analysis，再生成 reconstructed_xml
    structured_llm = llm.with_structured_output(XmlStitchingResult, method="function_calling")
    chain = prompt | structured_llm

    try:
        result: XmlStitchingResult = chain.invoke({
            "raw_sql": raw_sql,
            "optimized_sql": optimized_sql,
            "raw_xml": raw_xml
        })
        stitched_xml = result.reconstructed_xml.strip()
        print(f"🧩 [AST 缝合思考] {result.diff_analysis}")
    except Exception as e:
        return {"is_valid": False, "error_msg": f"大模型缝合调用异常: {e}", "reconstructed_xml": None}

    # 清理可能残留的 markdown 标记
    stitched_xml = re.sub(r'^```(xml)?\s*', '', stitched_xml, flags=re.IGNORECASE)
    stitched_xml = re.sub(r'\s*```$', '', stitched_xml, flags=re.IGNORECASE)

    # 物理底线 1：用 lxml 真实解析一次，看大模型有没有忘了转义 `<` 号导致 XML 语法损坏！
    try:
        strict_parser = etree.XMLParser(recover=False)  # 严格模式，有裸 `<` 直接报错
        etree.fromstring(f"<root>{stitched_xml}</root>", strict_parser)
    except etree.XMLSyntaxError as e:
        # 兜底自愈：如果大模型还是忘了转义 `<`，我们在代码层帮它自动转义非标签的 `<`
        stitched_xml = re.sub(r'<(?![a-zA-Z/!?])', '&lt;', stitched_xml)

    # 物理底线 2：签名比对，防丢标签、防改变量名
    original_sigs = _extract_dynamic_signatures(raw_xml)
    new_sigs = _extract_dynamic_signatures(stitched_xml)

    missing_tags = original_sigs - new_sigs
    if missing_tags:
        error_info = f"❌ 物理校验拦截：LLM 缝合丢失或篡改了核心业务契约 -> {missing_tags}"
        print(error_info)
        return {"is_valid": False, "error_msg": error_info, "reconstructed_xml": None}

    return {
        "is_valid": True,
        "reconstructed_xml": stitched_xml,
        "error_msg": None
    }