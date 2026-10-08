import os
import json
import subprocess
import shutil


def _get_java_command():
    """
    环境探针：智能寻找系统中的 Java 命令
    """
    # 1. 优先读取系统环境变量中的 JAVA_HOME
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        java_cmd = os.path.join(java_home, "bin", "java")
        if os.path.exists(java_cmd) or os.path.exists(java_cmd + ".exe"):
            return java_cmd

    # 2. 回退到全局 path 中寻找
    if shutil.which("java"):
        return "java"

    raise EnvironmentError(
        "❌ 致命错误：系统中未找到 Java 环境。\n"
        "解决方案：请安装 JDK (推荐 11 及以上) 并配置环境变量，或者在运行前设置 JAVA_HOME。"
    )


def _ensure_parser_jar(project_root: str, jar_path: str):
    """
    自愈机制：如果找不到 jar 包，尝试自动调用 Maven 构建
    """
    if os.path.exists(jar_path):
        return

    print("⚠️ 未检测到已编译的 Java 解析器 (jar包)。")

    if not shutil.which("mvn"):
        raise EnvironmentError(
            "❌ 致命错误：缺失 jar 包且系统中未找到 Maven (mvn)，无法自动构建。\n"
            "解决方案：请进入 agenticdb-parser 目录手动执行编译，或安装 Maven。"
        )

    print("⏳ 正在自动调用 Maven 构建底座，请稍候...")
    parser_dir = os.path.join(project_root, "agenticdb-parser")
    try:
        subprocess.run(
            ["mvn", "clean", "package", "-DskipTests"],
            cwd=parser_dir,
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ Java 解析器自动构建成功！\n")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"❌ 自动构建失败，请检查 Java 代码或 Maven 配置。错误信息:\n{e.stderr}")


def scan_project_mappers(target_dir: str):
    """
    遍历目录下的所有 XML 文件，并调用底层 Java 解析器提取纯净 SQL。
    任何人拉取代码后，均可无痛运行。
    """
    extracted_sqls = []

    # 1. 绝对路径推导 (兼容所有操作系统的路径分隔符)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ai_dir = os.path.dirname(current_dir)
    project_root = os.path.dirname(ai_dir)

    jar_path = os.path.join(project_root, "agenticdb-parser", "target", "agenticdb-parser-1.0-SNAPSHOT.jar")

    # 2. 检查并准备运行环境
    java_cmd = _get_java_command()
    _ensure_parser_jar(project_root, jar_path)

    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(".xml"):
                file_path = os.path.join(root, file)

                try:
                    # 3. 使用推导出的跨平台命令和绝对路径执行
                    result = subprocess.run(
                        [java_cmd, "-jar", jar_path, file_path],
                        capture_output=True,
                        text=True,
                        check=True
                    )

                    parsed_data = json.loads(result.stdout)

                    for item in parsed_data:
                        sql_type = "select" if item['sql'].strip().upper().startswith("SELECT") else "update"
                        clean_sql = item['sql'].replace('\u003d', '=').replace('\u003e', '>').replace('\u003c', '<')

                        extracted_sqls.append({
                            "file_path": file_path,
                            "id": item["id"],
                            "original_sql": clean_sql,
                            "type": sql_type
                        })

                except subprocess.CalledProcessError as e:
                    print(f"❌ 解析失败 [{file}]: 底层抛出异常或语法不规范。")
                except json.JSONDecodeError:
                    print(f"❌ 解析失败 [{file}]: Java 引擎返回了非法的 JSON 格式。")
                except KeyError as e:
                    print(f"❌ 解析失败 [{file}]: Java 引擎返回的 JSON 缺少必要字段 {e}。")

    return extracted_sqls