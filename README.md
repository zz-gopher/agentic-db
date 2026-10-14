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

**一个带“物理沙箱”和“记忆库”的多智能体 SQL 优化系统**

</div>

## 架构图

Agentic-DB 采用 **Neuro-Symbolic Agentic Engine**（神经符号智能体引擎）架构，将大模型（LLM）的非确定性推理与 LangGraph 的确定性状态机、AST 解析以及 MySQL 物理沙盒深度结合，旨在保障企业级代码迁移与 SQL 重构的 100% 准确性。

```mermaid
flowchart TB
    %% 定义样式
    classDef external fill:#f9f9f9,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
    classDef core fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef model fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef sandbox fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,stroke-dasharray: 5 5;
    classDef agent fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    classDef state fill:#ffe0b2,stroke:#ef6c00,stroke-width:2px,stroke-dasharray: 3 3;

    %% 外部输入输出
    Input["输入源：Java项目 (Git/ZIP) 或 纯SQL文本"]:::external
    Output["输出制品：自动化迁移审计报告 (含优化代码、诊断建议与沙箱打分)"]:::external

    %% 接入层
    subgraph API_Layer ["接入层 (FastAPI)"]
        Gateway["任务接收与分发网关"]
    end

    %% ================= 核心图编排 =================
    subgraph Agentic_Engine ["多智能体嵌套图编排 (LangGraph Nested Workflows)"]
        
        %% 【外层：Mapper Workflow】
        subgraph Mapper_Workflow ["【外层中枢】Mapper Workflow (处理 XML)"]
            Mapper_State(("MapperAuditState")):::state
            Call_SQL_Node["call_sql_optimizer (调用底层沙箱)"]
            Stitcher_Node["mapper_stitcher (XML 格式化与缝合 Agent)"]:::agent
            
            Mapper_State --> Call_SQL_Node
            Call_SQL_Node -->|"底层审核通过 (Score >= 70)"| Stitcher_Node
            Call_SQL_Node -->|"底层熔断/拒绝"| END_Mapper((END))
        end

        %% 【内层：SQL Workflow】
        subgraph SQL_Workflow ["【内层沙箱】SQL Workflow (纯净 SQL 压测部门)"]
            SQL_State(("SQLState")):::state
            Schema_Node["prepare_schema (准备表结构)"]
            Diag_Node["diagnostic_node (病理诊断)"]
            Gen_Node["generator (SQL 优化推理 Agent)"]:::agent
            Eval_Node["evaluator (双轨验证与评估)"]
            Mock_Node["mockdata_node (Phantom Seeder 幽灵播种)"]:::agent
            Memory_Node["memory_node (记忆固化)"]
            
            %% 内层主干连线
            SQL_State --> Schema_Node
            Schema_Node -->|"OK"| Diag_Node
            Diag_Node -->|"生成初步诊断建议"| Gen_Node
            Gen_Node -->|"OK"| Eval_Node
            
            %% 评估后的路由逻辑
            Eval_Node -->|"数据饥荒 (needs_mock)"| Mock_Node
            Mock_Node -->|"逆向推导条件 -> 注入数据"| Eval_Node
            
            Eval_Node -->|"分数 < 70 (打回重写)"| Gen_Node
            Eval_Node -->|"分数 >= 70"| Memory_Node
            Eval_Node -->|"熔断/失效"| END_SQL((END))
            Memory_Node --> END_SQL
        end
        
        %% 建立内外层嵌套关系
        Call_SQL_Node -->|"剥离脏 SQL 注入内层"| SQL_Workflow
        SQL_Workflow -->|"返回 final_draft (含诊断建议与打分)"| Call_SQL_Node
        
    end

    %% 工具与模型层
    subgraph Infrastructure ["基础设施与模型层"]
        LLM_API(("LLM (OpenAI/DeepSeek)")):::model
        ChromaDB[("ChromaDB (向量记忆与前置知识)")]:::model
    end

    %% 沙盒层
    subgraph Sandbox_Layer ["插件化执行沙盒层 (Pluggable Sandbox)"]
        MySQL[("MySQL 物理沙盒")]:::sandbox
        OtherDB[("扩展 DB 接口 (PostgreSQL/Oracle...)")]:::sandbox
        MySQL -.->|"实现标准化接口"| OtherDB
    end

    %% 全局连接线与业务流向
    Input -->|"提交任务"| Gateway
    Gateway -->|"触发外层 Workflow"| Mapper_Workflow
    
    %% 工具调用连接
    Diag_Node <-->|"病理诊断/建议提取"| LLM_API
    Gen_Node <-->|"Prompt 交互"| LLM_API
    Stitcher_Node <-->|"对齐标签"| LLM_API
    Mock_Node <-->|"逆向解算 WHERE 条件"| LLM_API
    Memory_Node <-->|"固化/检索"| ChromaDB
    
    %% 沙盒连接
    Eval_Node <-->|"双轨执行 (Shadow Execution)"| Sandbox_Layer
    Mock_Node <-->|"DML 注入与回滚 (事务隔离)"| Sandbox_Layer
    
    Stitcher_Node -->|"汇聚数据，生成 XML 与审计报告"| Output

    %% 应用样式
    class API_Layer,Agentic_Engine core;
```
