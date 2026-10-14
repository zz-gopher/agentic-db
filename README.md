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

## 🛠 前置环境与运行时拦截机制

在任务启动前，Agentic-DB 具备严格的配置要求与防故障拦截机制：
1. **全局环境配置**：系统底层依赖 `.env` 文件加载 LLM 引擎的全局参数（如 `OPENAI_API_KEY`、`BASE_URL`、`LLM_MODEL` 等）以激活推理大脑。
2. **动态沙盒注入**：物理沙盒的连接凭证 (`DB_URI`) 并非全局写死，而是由用户在调用 FastAPI 提交任务时动态传入。这使得系统原生支持多数据源切换与并发审计任务。
3. **前置探活与表校验**：在任何 LLM 消耗 Token 开始优化前，系统的主动探针会第一时间测试用户传入的 `DB_URI` 的连通性，并从沙盒中核实待优化 SQL 关联的表结构是否真实存在。若物理表缺失或无法连接，系统将立即**熔断并出具高危拦截报告**，避免无效的“大模型幻觉”。

## 🚀 架构图

Agentic-DB 采用 **Neuro-Symbolic Agentic Engine**（神经符号智能体引擎）架构，将大模型（LLM）的非确定性推理与 LangGraph 的确定性嵌套状态机、AST 解析以及 MySQL 物理沙盒深度结合。系统不仅输出语法转换后的可用代码，还会生成详尽的**自动化迁移审计报告（包含沙箱打分、高危拦截原因与 SQL 诊断建议）**，旨在保障企业级代码迁移与 SQL 重构的 100% 准确性。

```mermaid
flowchart TB
    %% 定义样式
    classDef external fill:#f9f9f9,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
    classDef core fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef model fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef sandbox fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,stroke-dasharray: 5 5;
    classDef agent fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    classDef state fill:#ffe0b2,stroke:#ef6c00,stroke-width:2px,stroke-dasharray: 3 3;

    %% 1. 顶部接入层
    subgraph Top_Layer [" "]
        direction LR
        Config["全局配置 (.env)<br>API_KEY / BASE_URL"]:::external
        Input["用户请求 (API Payload)<br>待优化项目 (Git/ZIP/SQL) + 动态 DB_URI"]:::external
        Gateway["接入层 (FastAPI)<br>任务接收与并发分发网关"]:::core
        
        Config -.->|"加载引擎配置"| Gateway
        Input -->|"提交任务 (携带 DB_URI)"| Gateway
    end
    style Top_Layer fill:none,stroke:none

    %% ================= 核心图编排 =================
    subgraph Agentic_Engine ["多智能体嵌套图编排 (LangGraph Nested Workflows)"]
        direction TB
        
        %% 【外层：Mapper Workflow】
        subgraph Mapper_Workflow ["【外层中枢】Mapper Workflow (处理 XML / 代码)"]
            direction LR
            Mapper_State(("MapperAuditState")):::state
            Dispatcher_Node["并发调度节点<br>(Async Map)"]
            Gather_Node["结果汇聚节点<br>(Async Reduce)"]
            Stitcher_Node["mapper_stitcher<br>(XML 格式化与缝合 Agent)"]:::agent
            
            Mapper_State -->|"解析出 N 条脏 SQL"| Dispatcher_Node
            Gather_Node -->|"底层审核通过<br>(汇总 N 份草案)"| Stitcher_Node
            Gather_Node -->|"全部熔断/拒绝"| END_Mapper((END))
        end

        %% 【内层：SQL Workflow】
        subgraph SQL_Workflow ["【内层沙箱】SQL Workflow (并发执行的多实例压测部门)"]
            direction LR
            SQL_State(("SQLState")):::state
            Schema_Node["prepare_schema<br>(DB探活 & 表校验)"]
            Diag_Node["diagnostic_node<br>(病理诊断与记忆唤醒)"]
            Gen_Node["generator<br>(推导并生成 SQL 草案)"]:::agent
            Eval_Node["evaluator<br>(基于 EXPLAIN 打分与双轨验证)"]
            
            subgraph Fallback_Mechanisms ["自我进化与兜底机制"]
                direction TB
                Mock_Node["mockdata_node<br>(Phantom Seeder)"]:::agent
                Memory_Node["memory_node<br>(提炼法则与记忆固化)"]
            end
            
            SQL_State --> Schema_Node
            Schema_Node -->|"正常且表存在"| Diag_Node
            Schema_Node -->|"表缺失/断连"| END_SQL((END))
            Diag_Node -->|"携带诊断与历史经验"| Gen_Node
            Gen_Node -->|"输出 final_draft"| Eval_Node
            
            Eval_Node -->|"数据饥荒 (needs_mock)"| Mock_Node
            Mock_Node -->|"逆向推导 -> 注入数据"| Eval_Node
            
            Eval_Node -->|"分数 < 70 (携带 feedback 打回)"| Gen_Node
            Eval_Node -->|"分数 >= 70 (审核通过)"| Memory_Node
            Eval_Node -->|"评估熔断 (物理执行失败等)"| END_SQL
        end
        
        %% 并发嵌套关系
        Dispatcher_Node ==>|"并发批量注入内层 (Map)"| SQL_Workflow
        SQL_Workflow ==>|"异步返回 N 个打分草案"| Gather_Node
    end

    Gateway -->|"触发外层 Workflow"| Mapper_Workflow

    %% ================= 底部依赖层 =================
    subgraph Bottom_Layer ["外部基础设施与执行环境"]
        direction LR
        
        subgraph Infrastructure ["基础设施与模型层"]
            direction LR
            LLM_API(("LLM (OpenAI/DeepSeek)")):::model
            ChromaDB[("ChromaDB<br>(向量记忆与前置知识)")]:::model
        end
        
        subgraph Sandbox_Layer ["插件化执行沙盒层 (Pluggable Sandbox)"]
            direction LR
            MySQL[("MySQL 物理沙盒")]:::sandbox
            OtherDB[("扩展 DB 接口<br>(PostgreSQL/Oracle...)")]:::sandbox
            MySQL -.->|"实现标准化接口"| OtherDB
        end
    end

    Agentic_Engine -.->|"组件依赖调用"| Bottom_Layer

    Output["输出制品：自动化迁移审计报告<br>(含优化代码、诊断建议与沙箱打分)"]:::external
    Stitcher_Node -->|"汇聚数据，生成 XML 与审计报告"| Output

    %% 细节调用连线 (凸显记忆闭环)
    Schema_Node -.->|"获取表结构"| Sandbox_Layer
    Gen_Node -.->|"Prompt 交互生成草案"| LLM_API
    Stitcher_Node -.->|"对齐标签"| LLM_API
    Mock_Node -.->|"DML 注入与回滚"| Sandbox_Layer
    Eval_Node -.->|"提取 EXPLAIN 并验证逻辑"| Sandbox_Layer
    Eval_Node -.->|"基于 EXPLAIN 请求模型打分"| LLM_API
    
    %% 记忆飞轮核心连线
    Diag_Node -.->|"提取反模式标签<br>请求模型诊断"| LLM_API
    Diag_Node -.->|"基于标签唤醒<br>相似历史优化案例"| ChromaDB
    Memory_Node -.->|"提炼泛化法则<br>并 Upsert 注入库"| ChromaDB

    %% 应用样式
    class API_Layer,Agentic_Engine core;
```
