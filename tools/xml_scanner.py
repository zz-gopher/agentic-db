import os
import re
from lxml import etree


def _clean_and_mock_sql(sql_str: str) -> str:
    clean_sql = re.sub(r'[#$]\{[^}]+\}', '?', sql_str)
    clean_sql = re.sub(r'\s+', ' ', clean_sql).strip()

    clean_sql = re.sub(r'(?i)WHERE\s+AND\s+', 'WHERE ', clean_sql)
    clean_sql = re.sub(r'(?i)WHERE\s+OR\s+', 'WHERE ', clean_sql)
    clean_sql = re.sub(r'(?i),\s+WHERE\s+', ' WHERE ', clean_sql)
    clean_sql = re.sub(r'(?i)SELECT\s+FROM', 'SELECT * FROM', clean_sql)
    return clean_sql


def _flatten_mybatis_node(node, sql_fragments: dict) -> str:
    """
    通用 MyBatis AST 展平引擎：完整覆盖 MyBatis 全量 10 大官方动态标签
    """
    text_parts = []
    if node.text:
        text_parts.append(node.text)

    for child in node:
        # 跳过 XML 注释节点 (<!-- ... -->)
        if not isinstance(child.tag, str):
            if child.tail:
                text_parts.append(child.tail)
            continue

        tag_name = child.tag.lower()

        # 1. <bind>: 纯变量声明标签，不产生任何 SQL 文本，直接跳过内部，仅保留 tail
        if tag_name == "bind":
            pass

        # 2. <include>: 递归展开代码片段
        elif tag_name == "include":
            refid = child.get("refid")
            clean_refid = refid.split('.')[-1] if refid else ""
            if clean_refid and clean_refid in sql_fragments:
                text_parts.append(_flatten_mybatis_node(sql_fragments[clean_refid], sql_fragments))
            else:
                text_parts.append(" * ")

        # 3. <where> 与 <set>: 自动补齐关键字
        elif tag_name == "where":
            text_parts.append(" WHERE " + _flatten_mybatis_node(child, sql_fragments))
        elif tag_name == "set":
            text_parts.append(" SET " + _flatten_mybatis_node(child, sql_fragments))

        # 4. <trim>: 通用前后缀注入 (无论是 prefix="WHERE" 还是 prefix="(" 全部自动兼容！)
        elif tag_name == "trim":
            prefix = child.get("prefix", "")
            suffix = child.get("suffix", "")
            inner_sql = _flatten_mybatis_node(child, sql_fragments).strip()
            # 模拟 MyBatis 的 prefixOverrides (如抹除开头的 AND/OR)
            prefix_overrides = child.get("prefixOverrides", "")
            if prefix_overrides:
                for ov in prefix_overrides.split("|"):
                    ov = ov.strip()
                    if ov:
                        inner_sql = re.sub(rf'^(?i){re.escape(ov)}\s+', '', inner_sql).strip()
            text_parts.append(f" {prefix} {inner_sql} {suffix} ")

        # 5. <foreach>: 自动读取 open 和 close 属性（如括号），生成单个占位符供 EXPLAIN 压测
        elif tag_name == "foreach":
            open_str = child.get("open", "")
            close_str = child.get("close", "")
            inner_sql = _flatten_mybatis_node(child, sql_fragments).strip()
            # 如果 SQL 里本身在 foreach 外面没写括号，且 open 属性也是空的，在 IN 场景下自动兜底保持原样
            text_parts.append(f" {open_str} {inner_sql} {close_str} ")

        # 6. <choose>: 互斥分支标签！如果把所有 <when> 和 <otherwise> 全拼进去会导致逻辑冲突（如 status=? AND status='1'）
        # 架构级处理：压测时提取所有 <when> 条件（模拟多条件组合压测），但跳过兜底的 <otherwise> 避免同字段互斥冲突！
        elif tag_name == "choose":
            when_nodes = child.findall("when")
            if when_nodes:
                for w in when_nodes:
                    text_parts.append(_flatten_mybatis_node(w, sql_fragments))
            else:
                otherwise_node = child.find("otherwise")
                if otherwise_node is not None:
                    text_parts.append(_flatten_mybatis_node(otherwise_node, sql_fragments))

        # 7. <if> 及其他常规标签：直接递归展开
        else:
            text_parts.append(_flatten_mybatis_node(child, sql_fragments))

        if child.tail:
            text_parts.append(child.tail)

    return " ".join(text_parts)


def scan_project_mappers(target_dir: str) -> list:
    extracted_sqls = []
    parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
    # 核心修改：将提取目标严格收缩为仅处理 select 标签
    target_tags = ['select']

    for root_dir, _, files in os.walk(target_dir):
        for file in files:
            if not file.endswith(".xml"):
                continue

            file_path = os.path.join(root_dir, file)
            try:
                tree = etree.parse(file_path, parser)
                root = tree.getroot()

                sql_fragments = {}
                for sql_node in root.findall('sql'):
                    node_id = sql_node.get('id')
                    if node_id:
                        sql_fragments[node_id] = sql_node

                for tag in target_tags:
                    for node in root.findall(tag):
                        node_id = node.get('id')
                        if not node_id:
                            continue

                        raw_xml_parts = [node.text or ""]
                        for child in node:
                            raw_xml_parts.append(etree.tostring(child, encoding='unicode'))
                        raw_xml_with_tags = "".join(raw_xml_parts).strip()

                        flat_sql = _flatten_mybatis_node(node, sql_fragments)
                        original_sql = _clean_and_mock_sql(flat_sql)
                        original_sql = original_sql.replace('\u003d', '=').replace('\u003e', '>').replace('\u003c',
                                                                                                              '<')

                        extracted_sqls.append({
                            "file_path": file_path,
                            "id": node_id,
                            "type": tag,
                            "raw_xml_fragment": raw_xml_with_tags,
                            "original_sql": original_sql
                        })

            except etree.XMLSyntaxError:
                print(f"⚠️ 解析跳过 [{file}]: 不是规范的 XML 文件。")
            except Exception as e:
                print(f"❌ 解析失败 [{file}]: {str(e)}")

    return extracted_sqls

if __name__ == "__main__":
    # 快速测试你的本地解析效果
    res = scan_project_mappers("../examples")
    for item in res:
        print(f"[{item['id']}] 纯净压测 SQL -> {item['original_sql']}")
        print(f"[{item['id']}] 原始带标签 XML -> {item['raw_xml_fragment']}\n")