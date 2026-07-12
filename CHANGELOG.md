# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-12

### Added
- 初始化 TextSQL-Agent 企业级自助数据分析 Agent 项目
- Agent 核心模块：LangGraph 工作流编排、状态定义、Skill 分层路由、SQL 安全校验、分层记忆系统
- 双层 RAG 知识库：元数据 + 指标定义双库，支持混合检索、查询改写、分层缓存、RAGAS 评测
- 工具层：SQL 执行器、Python 数据分析工具
- Docker 沙盒隔离执行环境
- FastAPI + SSE 流式 API 服务
- 对话式前端 UI，支持实时进度展示与 Markdown 报告渲染
- 零售场景测试数据集与指标定义文档
- 11 个核心单元测试
- Docker Compose 一键部署方案
