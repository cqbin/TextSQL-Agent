# TextSQL-Agent | 企业级自助数据分析 Agent

> 业务人员用自然语言提问，Agent 自动完成意图识别 → 知识库召回 → SQL 生成 → 安全校验 → 执行 → 数据分析 → 生成报告

## 🏗️ 架构概览

```
用户提问
  → 意图识别（判断业务域：销售/库存/财务/客户）
  → 权限校验（用户等级 + 敏感数据审批）
  → RAG 双层召回（元数据 + 指标定义）
  → SQL 生成（LLM + 上下文 + 记忆复用）
  → SQL 安全校验（SQLGlot 语法树 + 黑名单 + 脱敏 + 慢查询检测）
  → SQL 执行（只读账户 + 行数限制）
  → [失败] → SQL 纠错 Agent（自动分析修复）
  → Python 数据分析（Docker 沙盒隔离）
  → 记忆沉淀（执行→反思→提炼→向量库存储）
  → 生成 Markdown 报告
```

## 📦 核心模块

### 模块一：Data-SQL Agent（LangGraph 工作流编排）

| 功能 | 实现方式 |
|------|----------|
| Tool-Calling | SQL 执行工具 + Python 数据分析工具 |
| Skill 分层路由 | 按业务域（销售/库存/财务）组织数据表，先路由域再召回表 |
| 分层记忆系统 | 短时记忆（上下文压缩 + Redis 缓存）+ 长期记忆（向量库存储 + 复用） |
| 多 Agent 协作 | Main-Agent（规划+审批）、SQL-Agent（生成）、Fix-Agent（纠错）、Analysis-Agent（分析） |
| Prompt-Cache | 摘要预览、占位替换、超限兜底 |
| 安全审查 | SQLGlot 语法树 + 黑名单 + 字段脱敏 + 慢查询检测 + 人工审批 |

### 模块二：双层 RAG 知识库

| 层级 | 内容 | 技术实现 |
|------|------|----------|
| 元数据 RAG | 数据表结构、字段含义、关联关系 | TableDDL 解析 → 分块 → BM25 + 稠密向量混合索引 |
| 指标 RAG | 坪效、毛利率、库存周转率等定义 | Markdown 解析 → 分块 → 混合索引 |

**检索链路**：查询改写 → 问题路由 → 多路召回 → Rerank 重排 → 低置信二次检索

**工程优化**：增量索引（文档 hash）+ 工厂模式解耦 + 分层缓存 + RAGAS 评测

## 🛠️ 技术栈

- **Agent**：LangGraph、LangChain、Tool-Calling
- **RAG**：Chroma、BM25、Sentence-Transformer、Reranker、RAGAS
- **SQL**：SQLGlot（语法树解析）、SQLAlchemy、PostgreSQL
- **安全**：Docker Python 沙盒（网络隔离 + 资源限制）
- **API**：FastAPI + SSE 流式输出
- **前端**：Vue 风格单页应用

## 🚀 快速开始

### 1. 安装依赖

```bash
cd TextSQL-Agent
pip install -r requirements.txt
cp .env.example .env  # 编辑配置
```

### 2. 构建索引

```bash
python main.py --build-index
```

### 3. 运行测试

```bash
python main.py --test
```

### 4. 命令行查询

```bash
python main.py "上月各门店销售额排名"
```

### 5. 交互模式

```bash
python main.py --interactive
```

### 6. 启动 API 服务

```bash
python main.py --server
# 打开 http://localhost:8000
```

### 7. Docker 一键部署

```bash
cd docker
docker-compose up -d
```

## 📁 项目结构

```
TextSQL-Agent/
├── app/
│   ├── agent/              # Agent 核心模块
│   │   ├── state.py        # AgentState 状态定义
│   │   ├── workflow.py     # LangGraph 工作流编排
│   │   ├── skill_router.py # Skill 分层路由
│   │   ├── sql_validator.py# SQL 安全校验（SQLGlot）
│   │   └── memory.py       # 分层记忆系统
│   ├── rag/                # RAG 知识库模块
│   │   ├── indexer.py      # 离线索引构建（工厂模式）
│   │   ├── retriever.py    # 双层检索器（BM25+向量+Rerank）
│   │   ├── rewriter.py     # 查询改写
│   │   ├── cache.py        # 分层缓存（L1内存+L2 Redis）
│   │   └── evaluator.py    # RAGAS 评测
│   ├── tools/              # Agent 工具
│   │   ├── sql_executor.py # SQL 执行器
│   │   └── analysis_tool.py# Python 数据分析工具
│   ├── sandbox/            # 代码沙盒
│   │   └── runner.py       # Docker 隔离执行
│   ├── api/                # FastAPI 后端
│   │   └── server.py       # RESTful API + SSE
│   ├── frontend/           # 前端页面
│   │   └── index.html      # 对话式 UI
│   ├── utils/              # 工具
│   │   └── logger.py       # 日志
│   └── config.py           # 全局配置
├── data/
│   ├── sql/                # 建表语句 + 测试数据
│   │   └── init_database.sql
│   └── docs/               # 指标定义文档
│       └── metrics.md
├── docker/                 # Docker 配置
│   ├── docker-compose.yml
│   ├── Dockerfile.api
│   └── Dockerfile.sandbox
├── tests/
│   └── test_core.py        # 核心测试
├── main.py                 # 主入口
├── requirements.txt
├── .env.example
└── .gitignore
```

## 🔒 安全设计

| 层级 | 措施 |
|------|------|
| SQL 注入 | SQLGlot 语法树解析，只允许 SELECT |
| 写操作 | 黑名单拦截 DROP/DELETE/ALTER/TRUNCATE |
| 数据泄露 | 敏感字段自动脱敏，按权限等级分级 |
| 资源耗尽 | 限制返回行数 + 慢查询检测 + 执行超时 |
| 代码执行 | Docker 沙盒隔离，禁用网络，CPU/内存限制 |
| 敏感数据 | 高敏感操作需人工审批 |

## 📊 评测指标

| 指标 | 说明 |
|------|------|
| Precision | 召回的表中有多少是正确的 |
| Recall | 相关表中有多少被召回了 |
| MRR | 平均倒数排名 |
| Hit Rate | 第一正确结果的命中率 |
| SQL Accuracy | SQL 执行结果正确率 |
| SQL Syntax Valid | SQL 语法合法率 |

## 📝 License

MIT
