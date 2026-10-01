import xml.etree.ElementTree as ET
import os
import re


class MyBatisScanner:
    def __init__(self, xml_path):
        self.xml_path = xml_path
        self.target_tags = ['select']
        self.original_doctype = ""

    def _read_and_clean_xml(self):
        with open(self.xml_path, 'r', encoding='utf-8') as f:
            content = f.read()

        match = re.search(r'<!DOCTYPE[^>]+>', content)
        if match:
            self.original_doctype = match.group(0)
            content = content.replace(self.original_doctype, '')

        return content

    def extract_sqls(self):
        clean_xml_content = self._read_and_clean_xml()

        try:
            self.tree = ET.ElementTree(ET.fromstring(clean_xml_content))
            root = self.tree.getroot()
        except ET.ParseError as e:
            print(f"❌ [{os.path.basename(self.xml_path)}] XML 解析失败: {e}")
            return []

        extracted_sqls = []
        for tag in self.target_tags:
            for node in root.iter(tag):
                sql_id = node.get('id')
                sql_text = node.text.strip() if node.text else ""

                if sql_text:
                    extracted_sqls.append({
                        "file_path": self.xml_path,  # 记录来源文件，为回写和报告做准备
                        "id": sql_id,
                        "type": tag,
                        "original_sql": sql_text
                    })

        return extracted_sqls


def scan_project_mappers(directory_path):
    """递归扫描目录下的所有 XML 文件"""
    all_extracted_sqls = []
    xml_count = 0

    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.xml'):
                xml_count += 1
                full_path = os.path.join(root, file)
                scanner = MyBatisScanner(full_path)
                sqls = scanner.extract_sqls()
                all_extracted_sqls.extend(sqls)

    print(f"📂 共扫描 {xml_count} 个 XML 文件，提取到 {len(all_extracted_sqls)} 条待迁移 SQL。")
    return all_extracted_sqls


if __name__ == "__main__":
    # 测试：扫描当前 examples 目录（或者你可以传入你本地的真实的 Mapper 文件夹路径）
    current_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"🚀 开始全局扫描目录: {current_dir}\n" + "=" * 40)

    # 提取全局 SQL
    global_sqls = scan_project_mappers(current_dir)

    # 打印前 3 条作为验证，避免控制台刷屏
    for i, item in enumerate(global_sqls[:3]):
        filename = os.path.basename(item['file_path'])
        print(f"🎯 [{filename}] -> [{item['type'].upper()}] {item['id']}")
        print(f"📜 {item['original_sql']}")
        print("-" * 40)