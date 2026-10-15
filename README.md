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

## ⚡ 快速启动（Docker 一键部署）

### 1. 环境准备

| 组件 | 版本要求 | 说明 |
| --- | --- | --- |
| Docker | 20.10+ | 需支持 BuildKit |
| Docker Compose | v2.0+ | `docker compose version` 可查看 |
| MySQL（物理沙盒） | 5.7 / 8.0 | 可部署在宿主机或远程，**不需要**放进容器 |

### 2. 配置 `.env` 文件

`docker-compose.yml` 通过 `env_file` 挂载根目录的 `.env`，缺失会导致启动失败。请复制模板并填入真实秘钥：

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

填写关键项（其余保持默认即可）：

```ini
OPENAI_API_KEY=你的真实秘钥
BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
HF_ENDPOINT=https://hf-mirror.com
```

### 3. 启动服务

```bash
# 前台启动（首次建议，便于观察日志）
docker compose up --build

# 后台常驻启动
docker compose up -d --build
```

- 首次构建会拉取 **CPU 版 PyTorch** 与业务依赖（走清华源），并预装 `git` 用于项目级审计，耗时较长，请耐心等待。
- 启动完成后访问 `http://localhost:8000/docs` 打开 Swagger 交互文档。

### 4. 关于物理沙盒（`DB_URI`）的连接

容器内不存在 MySQL，`docker-compose.yml` 默认通过 `host.docker.internal` 穿透访问宿主机数据库：

```yaml
DB_URI: mysql+pymysql://root:root@host.docker.internal:3306/ai_note
extra_hosts:
  - "host.docker.internal:host-gateway"
```

> **零感知重写**：`main.py` 中的 `normalize_db_uri()` 会检测容器环境（`/.dockerenv`），自动把调用方传入的 `127.0.0.1` / `localhost` 重写为 `host.docker.internal`。因此**调用接口时直接填本机地址即可**，无需手动改写。

Linux 宿主机请确保 Docker 版本 ≥ 20.10（支持 `host-gateway`）；如仍无法连通，请确认 MySQL 监听地址不是 `127.0.0.1` 且已放行 `3306` 端口。

### 5. 调用示例

**① 单条 SQL 审计**

```bash
curl -X POST "http://localhost:8000/api/v1/audit" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM users WHERE DATE(create_time) = CURDATE()",
    "db_uri": "mysql+pymysql://root:root@127.0.0.1:3306/ai_note"
  }'
```

**② 项目级审计（Git 仓库）**

```bash
curl -X POST "http://localhost:8000/api/v1/audit-project/git" \
  -H "Content-Type: application/json" \
  -d '{
    "git_url": "https://github.com/your-org/your-repo.git",
    "git_branch": "main",
    "db_uri": "mysql+pymysql://root:root@127.0.0.1:3306/ai_note",
    "max_workers": 3
  }'
```

**③ 项目级审计（ZIP 上传）**

```bash
curl -X POST "http://localhost:8000/api/v1/audit-project/zip" \
  -F "file=@./your-project.zip" \
  -F "db_uri=mysql+pymysql://root:root@127.0.0.1:3306/ai_note" \
  -F "max_workers=3" \
  --output Audit_Deliverables.zip
```

Git / ZIP 接口返回的是 ZIP 交付物，内含 `Agentic_SQL_Audit_Report.md`（审计报告）与 `fixed_mappers/`（修复后的 XML）。

### 6. 数据持久化说明

| 挂载项 | 容器内路径 | 用途 |
| --- | --- | --- |
| `./logs` | `/app/logs` | 运行日志 |
| `./Agentic_Audit_Artifacts` | `/app/Agentic_Audit_Artifacts` | 审计产物 |
| `./bge_db` | `/app/bge_db` | ChromaDB 向量经验库 |
| `hf_cache`（命名卷） | `/root/.cache/huggingface` | BGE 模型缓存，避免重复下载 |

### 7. 常用运维命令

```bash
docker compose logs -f agentic-db-engine   # 实时跟踪日志
docker compose ps                          # 查看运行状态
docker compose restart agentic-db-engine   # 重启服务（改了 .env 后）
docker compose down                        # 停止并移除容器
docker compose build --no-cache            # 强制重新构建镜像
```

### 8. 常见问题排查

| 现象 | 原因与解决 |
| --- | --- |
| 启动时报 `env file not found` | 未创建 `.env`，执行 `cp .env.example .env` 后重试 |
| 沙盒连接失败 / 表缺失 | 系统为**熔断保护**，非故障；检查 `DB_URI` 与物理表是否存在 |
| 容器访问不到宿主机 MySQL | 确认 `extra_hosts` 生效、MySQL 已放行 3306 且未仅监听 `127.0.0.1` |
| 首次调用卡在模型下载 | 容器内无预置 HF 权重，需联网经 `HF_ENDPOINT` 拉取 bge 模型，已缓存至 `hf_cache` 卷 |
| 构建时下载 torch 极慢或失败 | `Dockerfile` 已锁定 PyTorch 官方 CPU 源；国内环境下可重试或检查网络代理 |
