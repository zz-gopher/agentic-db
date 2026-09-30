<div align="center">

<!-- 如果你有 Logo，可以取消下面这行的注释并替换路径 -->
<!-- <img src="assets/logo.svg" alt="Agentic-DB Logo" width="128" /> -->

# Agentic-DB

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Ready-DD0031.svg)](https://langchain-ai.github.io/langgraph/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Memory-FF9900.svg)](https://www.trychroma.com/)
[![MySQL](https://img.shields.io/badge/MySQL-Sandbox-4479A1.svg?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/zz-gopher/agentic-db/pulls)

**一个带“物理沙箱”和“记忆库”的生产级多智能体 SQL 优化系统**

[English](README_EN.md) | 简体中文

</div>


## 🎯 核心理念
市面上的 AI 写 SQL 工具往往是在“盲写”——大模型看一眼表结构，靠猜给出一个优化方案。但在真实的生产环境中，这种做法非常危险。AI 很容易擅自改变原有的业务逻辑（比如把 `LEFT JOIN` 改成 `INNER JOIN`），或者捏造出不存在的字段。

Agentic-DB 提供了一种更安全的落地思路。它不仅让 AI 重写 SQL，还给 AI 穿上了一层约束衣：**物理沙箱测试**、**严格的客观审查**和**历史经验库**。任何一段优化后的代码，都必须在真实数据库里跑通，证明“查询结果没变”且“执行计划确实更优”，才会最终交付。

围绕这一核心思路，我们将 AI 的创造力与传统 DBA 的严苛工程规范结合起来：

- **绝对不破坏业务逻辑**：性能可以优化，规范可以提升，但查询结果绝对不能变。系统会通过比对优化前后的真实输出，一票否决任何企图篡改业务逻辑的草案。
- **用事实打分，拒绝幻觉**：AI 不能凭空吹嘘自己的 SQL 有多快。系统会直连数据库抓取真实的 `EXPLAIN` 执行计划，基于客观指标（是否全表扫描、是否走索引）来评估。
- **越用越聪明的“错题本”**：引入向量数据库（ChromaDB）。每次成功优化一条 SQL，系统就会把它存起来。下次遇到类似的“烂 SQL”，AI 会直接参考历史成功案例去写代码。

---
## ✨ 主要功能

- **智能诊断**：识别烂 SQL 的核心病灶（如隐式转换、函数包裹索引列、深分页、无条件笛卡尔积等），并打上病理标签。
- **代码与物理结构分离**：要求 AI 将“SQL 代码改写”与“建索引建议（DDL）”分开输出，保证查询语句的纯粹，并提供清晰的建索引工单。
- **物理沙箱拦截**：
  - 自动前往真实数据库获取最新的表结构。
  - 强制比对优化前后的数据逻辑，防止乱改条件。
  - 抓取底层的 EXPLAIN 执行计划用于最终评分。
- **RAG 经验检索**：在优化前，去经验库里搜索长得最像的历史烂 SQL 和标准解法，直接喂给 AI 当参考，大幅提高一次性写对的概率。
- **自动重试与熔断**：当 AI 写出的代码没通过沙箱测试时，系统会带着真实的报错信息把它打回重写。超过 3 次则触发熔断，防止死循环。
- **极简配置**：基于 `pydantic-settings`，统一通过 `.env` 管理 API Key 和数据库连接，带类型强校验，开箱即用。

<img width="1307" height="831" alt="QQ_1790755649857" src="https://github.com/user-attachments/assets/2c09d760-09c5-4f64-af39-22fd3750d3ba" />

---


## 🏗️ 工作流说明

项目底层基于 LangGraph，将整个 SQL 调优过程拆解为一个多智能体协作的工作流：

1. **🔍 诊断节点 (Diagnostic)**：拿到用户的烂 SQL，结合真实的表结构，指出病因，并从“错题本”里翻出两道最相似的历史案例。
2. **💻 生成节点 (Generator)**：拿着诊断报告和参考案例，开始改写 SQL，并评估是否需要给出 `ALTER TABLE` 建议。
3. **🧪 沙箱测试 (Sandbox)**：完全客观的物理探针。把新写的 SQL 扔进数据库跑逻辑比对和 `EXPLAIN`。报错或逻辑不符直接打回。
4. **👨‍⚖️ 审查节点 (Evaluator)**：拿着沙箱反馈的 EXPLAIN 报告进行把关。如果发现严重语法不规范（如老式的逗号连接），或依然是全表扫描且没给索引建议，直接给 0 分打回。及格（>70分）才允许放行。
5. **🧠 记忆节点 (Memory)**：代码通过所有测试并及格后，为原 SQL 生成 MD5 指纹，将优化过程存入 ChromaDB，成为后续优化的参考范例。

---

## 🚀 快速开始

**1. 克隆项目并安装依赖**
```bash
git clone https://github.com/zz-gopher/agentic-db.git
cd agentic-db/agenticdb-ai
pip install -r requirements.txt
```

**2. 配置环境变量**

在 agenticdb-ai 目录下创建 .env 文件，填入你的配置：
```bash
DEEPSEEK_API_KEY=your_api_key_here
DB_URI=mysql+pymysql://user:password@localhost:3306/your_db
HF_ENDPOINT=https://hf-mirror.com
```

**2. 运行程序**

```bash
python main.py
```
---
## 🗺️ 后续规划 (V2.0 展望)
1.**自治索引助手 (Index Agent)**：独立处理建索引建议，在沙箱中推演索引成本，并自动合并表内冗余的索引。

2.**造数防御 (Mock Data Seeding)**：解决表数据为空时导致逻辑比对失效的问题。通过智能生成少量测试数据骗过数据库优化器，获取更真实的执行成本。

3.**可视化工作台 (Tuning Workspace)**：告别纯命令行，提供带有执行图谱、代码 Diff 对比与沙箱监控面板的前端交互界面。
