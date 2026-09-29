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

**A production-grade multi-agent SQL optimization system equipped with a "Physical Sandbox" and a "Memory Bank".**

English | [简体中文](README.md)

</div>

---

## 🎯 Core Concepts

Existing AI SQL tools often operate in "blind writing" mode—the LLM guesses an optimization strategy just by looking at the table schema. In a real production environment, this approach is extremely dangerous. AI can easily alter the original business logic (e.g., changing a `LEFT JOIN` to an `INNER JOIN`) or hallucinate non-existent fields.

Agentic-DB provides a safer implementation approach. It not only utilizes AI to rewrite SQL but also restrains it with a **Physical Sandbox Test**, **Strict Objective Review**, and a **Historical Experience Bank**. Any optimized code must run successfully in a real database to prove that "the query results remain unchanged" and "the execution plan is genuinely better" before final delivery.

Around this core concept, we combine the creative capabilities of AI with the rigorous engineering standards of traditional DBAs:
- **Absolute preservation of business logic**: Performance can be optimized and standards elevated, but query results must absolutely not change. The system uses real output comparisons before and after optimization to veto any drafts attempting to tamper with business logic.
- **Fact-based scoring, zero hallucinations**: AI cannot boast about the speed of its SQL out of thin air. The system connects directly to the database to fetch real `EXPLAIN` execution plans and evaluates based on objective metrics (e.g., full table scans, index usage).
- **Self-evolving "Error Log"**: Introduces a vector database (ChromaDB). Every time an SQL query is successfully optimized, the system saves it. When encountering similar "bad SQL" in the future, the AI will directly reference historical success cases to write the code.

---
## ✨ Key Features

- **Smart Diagnosis**: Identifies the core issues of bad SQL (e.g., implicit conversions, functions wrapping index columns, deep pagination, unconditional Cartesian products) and assigns pathology tags.
- **Separation of Code and Physical Structure**: Requires AI to output "SQL code rewriting" and "Index building suggestions (DDL)" separately, ensuring pure query statements and providing clear index creation tickets.
- **Physical Sandbox Interception**:
  - Automatically fetches the latest table schema from the real database.
  - Forcibly compares data logic before and after optimization to prevent condition tampering.
  - Retrieves the underlying EXPLAIN execution plan for final scoring.
- **RAG Experience Retrieval**: Before optimizing, it searches the memory bank for the most similar historical bad SQL and standard solutions, feeding them directly to the AI as references, drastically improving the first-pass success rate.
- **Auto-Retry & Circuit Breaker**: When AI-generated code fails the sandbox test, the system rejects it and sends it back with real error messages for rewriting. Exceeding 3 attempts triggers a circuit breaker to prevent infinite loops.
- **Minimalist Configuration**: Based on `pydantic-settings`, it uniformly manages API Keys and database connections via `.env` with strong type validation, ready out of the box.

---

## 🏗️ Workflow

The underlying project is based on LangGraph, breaking down the entire SQL tuning process into a multi-agent collaborative workflow:

1. **🔍 Diagnostic Node**: Receives the user's bad SQL, combines it with the real table schema, points out the root cause, and retrieves the two most similar historical cases from the "error log".
2. **💻 Generator Node**: Uses the diagnostic report and reference cases to rewrite the SQL and evaluates whether `ALTER TABLE` suggestions are needed.
3. **🧪 Sandbox Node**: A completely objective physical probe. It throws the newly written SQL into the database to run logic comparisons and `EXPLAIN`. Errors or logic mismatches are directly rejected.
4. **👨‍⚖️ Evaluator Node**: Acts as the gatekeeper using the EXPLAIN report from the sandbox. If severe syntax violations are found (like legacy comma joins), or if it remains a full table scan without index suggestions, it immediately rejects it with a score of 0. Only passing scores (>70) are permitted to proceed.
5. **🧠 Memory Node**: Once the code passes all tests and scores sufficiently, an MD5 fingerprint is generated for the original SQL, and the optimization process is saved into ChromaDB to serve as a reference paradigm for future optimizations.

---

## 🚀 Quick Start

**1. Clone the project and install dependencies**
```bash
git clone https://github.com/zz-gopher/agentic-db.git
cd agentic-db/agenticdb-ai
pip install -r requirements.txt
```

**2. Configure environment variables**

Create a .env file in the agenticdb-ai directory and fill in your configurations:
```bash
DEEPSEEK_API_KEY=your_api_key_here
DB_URI=mysql+pymysql://user:password@localhost:3306/your_db
HF_ENDPOINT=https://hf-mirror.com
```

**2. Run the application**

```bash
python main.py
```
---
## 🗺️ Roadmap (V2.0 Outlook)
1.**Index Agent**：Independently handles index creation suggestions, deduces index costs within the sandbox, and automatically merges redundant indexes within tables.

2.**Mock Data Seeding**：Resolves logic comparison failures caused by empty table data. It intelligently generates a small amount of test data to bypass the database optimizer, obtaining more realistic execution costs.

3.**Tuning Workspace**：Moves away from the pure CLI, providing a frontend interactive interface featuring execution graphs, code Diff comparisons, and sandbox monitoring panels.
