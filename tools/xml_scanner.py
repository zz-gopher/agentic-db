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
    text_parts = []
    if node.text:
        text_parts.append(node.text)

    for child in node:
        tag_name = child.tag.lower() if child.tag else ""

        if tag_name == "include":
            refid = child.get("refid")
            clean_refid = refid.split('.')[-1] if refid else ""
            if clean_refid and clean_refid in sql_fragments:
                text_parts.append(_flatten_mybatis_node(sql_fragments[clean_refid], sql_fragments))
            else:
                text_parts.append(" /* MISSING_INCLUDE */ ")

        elif tag_name == "where":
            text_parts.append(" WHERE ")
            text_parts.append(_flatten_mybatis_node(child, sql_fragments))
        # 补全了 trim 标签的处理逻辑
        elif tag_name == "trim":
            prefix = child.get("prefix", "").upper() if child.get("prefix") else ""
            if "WHERE" in prefix:
                text_parts.append(" WHERE ")
            text_parts.append(_flatten_mybatis_node(child, sql_fragments))
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