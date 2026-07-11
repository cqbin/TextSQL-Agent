"""
LangGraph 工作流编排
完整执行链路：
意图识别 → 权限校验 → RAG双层召回 → SQL生成 → SQL安全检测 → 执行SQL
→ Python数据分析 → 记忆沉淀 → 输出报告
"""
import json
from typing import Annotated
from datetime import datetime
from langgraph.graph import StateGraph, END

from app.agent.state import AgentState, QueryIntent, UserPermission, ApprovalStatus
from app.agent.skill_router import SkillRouter
from app.agent.sql_validator import SQLValidator
from app.agent.memory import MemoryManager
from app.rag.retriever import DualRetriever
from app.rag.rewriter import QueryRewriter
from app.tools.sql_executor import SQLExecutor
from app.tools.analysis_tool import AnalysisTool
from app.config import config


# ==================== 节点函数 ====================

def node_intent_recognition(state: AgentState) -> AgentState:
    """节点1: 意图识别 - 判断用户问题属于哪个业务域"""
    query = state.get("user_query", "")

    # 长期记忆检索：先查是否有相似历史查询
    memory_manager: MemoryManager = state.get("_memory_manager", MemoryManager())
    memory_hit = memory_manager.retrieve(query)

    if memory_hit:
        # 命中长期记忆，直接复用
        state["long_term_memory_hit"] = memory_hit
        state["intent"] = QueryIntent(memory_hit.get("domain", "general"))
        state["rewritten_query"] = memory_hit.get("query", query)
        state["generated_sql"] = memory_hit.get("sql", "")  # 复用历史 SQL
        state["_skip_sql_generation"] = True  # 跳过 SQL 生成节点
    else:
        # 查询改写
        rewriter = QueryRewriter()
        rewritten = rewriter.rewrite(query)
        state["rewritten_query"] = rewritten

        # 意图识别（基于关键词路由）
        intent = _classify_intent(rewritten)
        state["intent"] = intent

    # 根据意图获取可用数据表
    router = SkillRouter()
    domain_key = state["intent"].value if isinstance(state["intent"], QueryIntent) else "general"
    tables = router.get_tables_by_domain(domain_key)
    state["domain_tables"] = [t.table_name for t in tables]

    state["timestamp"] = datetime.now().isoformat()
    print(f"[节点1] 意图识别: {state['intent']}, 域内表: {state['domain_tables']}")
    return state


def _classify_intent(query: str) -> QueryIntent:
    """基于关键词分类意图"""
    query_lower = query.lower()
    sales_keywords = ["销售", "卖出", "订单", "营业额", "销量", "成交", "销售额", "卖"]
    inventory_keywords = ["库存", "存货", "补货", "缺货", "备货", "仓"]
    finance_keywords = ["毛利", "成本", "利润", "财务", "营收", "毛利率", "净利"]
    customer_keywords = ["客户", "会员", "顾客", "用户"]

    scores = {
        QueryIntent.SALES: sum(1 for k in sales_keywords if k in query_lower),
        QueryIntent.INVENTORY: sum(1 for k in inventory_keywords if k in query_lower),
        QueryIntent.FINANCE: sum(1 for k in finance_keywords if k in query_lower),
        QueryIntent.CUSTOMER: sum(1 for k in customer_keywords if k in query_lower),
    }

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return QueryIntent.GENERAL
    return best


def node_permission_check(state: AgentState) -> AgentState:
    """节点2: 权限校验"""
    user_id = state.get("user_id", "default")
    permission = state.get("user_permission", UserPermission.LOW)

    # 根据意图和权限判断是否需要审批
    intent = state.get("intent", QueryIntent.GENERAL)
    if intent == QueryIntent.FINANCE and permission != UserPermission.HIGH:
        state["approval_status"] = ApprovalStatus.PENDING
    else:
        state["approval_status"] = ApprovalStatus.NOT_REQUIRED

    print(f"[节点2] 权限校验: 用户={user_id}, 权限={permission}, 审批={state['approval_status']}")
    return state


def node_rag_retrieval(state: AgentState) -> AgentState:
    """节点3: RAG 双层知识召回"""
    if state.get("_skip_sql_generation"):
        # 命中长期记忆，跳过 RAG
        state["retrieved_tables"] = []
        state["retrieved_metrics"] = []
        state["rag_confidence"] = 1.0
        return state

    query = state.get("rewritten_query", state.get("user_query", ""))
    domain = state.get("intent", QueryIntent.GENERAL)
    domain_str = domain.value if isinstance(domain, QueryIntent) else str(domain)

    try:
        retriever = DualRetriever()
        result = retriever.retrieve(query, domain=domain_str)

        state["retrieved_tables"] = [d for d in result.documents if d.get("metadata", {}).get("doc_key", "").startswith(("sales", "order", "stores", "inventory", "products", "finance", "customer"))]
        state["retrieved_metrics"] = [d for d in result.documents if d.get("metadata", {}).get("doc_key", "").startswith("metric")]
        state["rag_confidence"] = result.confidence
        state["needs_second_retrieval"] = result.needs_second_retrieval
    except Exception as e:
        print(f"[节点3] RAG 检索失败，使用降级方案: {e}")
        # 降级：使用 Skill Router 提供的表信息
        router = SkillRouter()
        domain_key = domain_str if domain_str in router.get_all_domains() else "sales"
        tables = router.get_tables_by_domain(domain_key)
        state["retrieved_tables"] = [{"content": t.description, "metadata": {"table_name": t.table_name, "columns": t.columns}} for t in tables]
        state["retrieved_metrics"] = []
        state["rag_confidence"] = 0.5
        state["needs_second_retrieval"] = False

    print(f"[节点3] RAG 召回: {len(state.get('retrieved_tables', []))} 表, 置信度={state.get('rag_confidence', 0):.3f}")
    return state


def node_sql_generation(state: AgentState) -> AgentState:
    """节点4: SQL 生成"""
    if state.get("_skip_sql_generation") and state.get("generated_sql"):
        print(f"[节点4] 跳过 SQL 生成（复用长期记忆）")
        return state

    query = state.get("rewritten_query", state.get("user_query", ""))
    retrieved_tables = state.get("retrieved_tables", [])
    retrieved_metrics = state.get("retrieved_metrics", [])

    # 构建 Prompt
    table_info = _build_table_context(retrieved_tables)
    metric_info = _build_metric_context(retrieved_metrics)

    prompt = f"""你是一个专业的 SQL 生成助手。根据用户问题和数据表信息生成 PostgreSQL 查询语句。

数据表信息：
{table_info}

指标定义：
{metric_info}

用户问题：{query}

规则：
1. 只生成 SELECT 语句
2. 使用正确的表名和字段名
3. 如果涉及指标计算，严格按照指标定义的公式
4. 如果需要聚合，使用 GROUP BY
5. 如果需要排序，使用 ORDER BY
6. 不要添加 LIMIT（系统会自动添加）

直接输出 SQL 语句，不要解释："""

    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            temperature=0.0,
            max_tokens=1024,
        )
        response = llm.invoke(prompt)
        sql = response.content.strip()
        # 清理可能的 markdown 代码块
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        state["generated_sql"] = sql
    except Exception as e:
        # 降级：基于意图生成简单 SQL
        state["generated_sql"] = _fallback_sql(state)
        print(f"[节点4] LLM 不可用，使用降级 SQL: {e}")

    print(f"[节点4] SQL 生成: {state.get('generated_sql', '')[:80]}...")
    return state


def _build_table_context(tables: list[dict]) -> str:
    """构建表结构上下文"""
    if not tables:
        return "（无可用表信息）"
    parts = []
    for t in tables:
        meta = t.get("metadata", {})
        table_name = meta.get("table_name", meta.get("doc_key", "unknown"))
        parts.append(f"表名: {table_name}")
        if meta.get("columns"):
            for col in meta["columns"]:
                sensitive = " (敏感)" if col.get("sensitive") else ""
                parts.append(f"  - {col['name']}: {col.get('type', '')} - {col.get('desc', '')}{sensitive}")
        parts.append(f"  描述: {t.get('content', t.get('document', ''))[:200]}")
        parts.append("")
    return "\n".join(parts)


def _build_metric_context(metrics: list[dict]) -> str:
    """构建指标上下文"""
    if not metrics:
        return "（无指标定义）"
    parts = []
    for m in metrics:
        content = m.get("content", m.get("document", ""))
        parts.append(content[:300])
        parts.append("")
    return "\n".join(parts)


def _fallback_sql(state: AgentState) -> str:
    """降级 SQL 生成"""
    intent = state.get("intent", QueryIntent.GENERAL)
    domain_tables = state.get("domain_tables", [])

    if not domain_tables:
        return "SELECT 1;"

    main_table = domain_tables[0]
    if intent == QueryIntent.SALES:
        return f"SELECT * FROM {main_table} ORDER BY order_date DESC LIMIT 20;"
    elif intent == QueryIntent.INVENTORY:
        return f"SELECT * FROM {main_table} ORDER BY stock_quantity ASC LIMIT 20;"
    elif intent == QueryIntent.FINANCE:
        return f"SELECT * FROM {main_table} ORDER BY month DESC LIMIT 12;"
    else:
        return f"SELECT * FROM {main_table} LIMIT 20;"


def node_sql_validation(state: AgentState) -> AgentState:
    """节点5: SQL 安全校验"""
    sql = state.get("generated_sql", "")
    permission = state.get("user_permission", UserPermission.LOW)

    validator = SQLValidator()
    valid, errors, sensitive = validator.validate(sql, permission)

    # 自动追加 LIMIT
    if valid:
        sql = validator.auto_append_limit(sql)
        state["generated_sql"] = sql

    state["sql_valid"] = valid
    state["sql_errors"] = errors
    state["sensitive_fields_detected"] = sensitive

    # 慢查询检测
    state["is_slow_query"] = validator.is_slow_query(sql)

    if not valid:
        print(f"[节点5] SQL 校验失败: {errors}")
    else:
        print(f"[节点5] SQL 校验通过, 敏感字段: {sensitive}")

    return state


def node_sql_execution(state: AgentState) -> AgentState:
    """节点6: 执行 SQL"""
    if not state.get("sql_valid", False):
        state["error_message"] = "SQL 校验未通过，无法执行"
        return state

    # 审批检查
    if state.get("approval_status") == ApprovalStatus.PENDING:
        state["error_message"] = "查询需要人工审批，已提交审批请求"
        return state

    sql = state.get("generated_sql", "")
    permission = state.get("user_permission", UserPermission.LOW)

    executor = SQLExecutor()
    result = executor.execute(sql, permission)

    state["execution_result"] = result.get("data", [])
    state["result_row_count"] = result.get("row_count", 0)
    state["is_slow_query"] = state.get("is_slow_query", False) or result.get("is_slow", False)

    if not result["success"]:
        state["error_message"] = result["error"]
        state["sql_errors"] = [result["error"]]

    print(f"[节点6] SQL 执行: {'成功' if result['success'] else '失败'}, 行数={result.get('row_count', 0)}")
    return state


def node_sql_fix(state: AgentState) -> AgentState:
    """节点6.5: SQL 纠错（执行失败后自动修复）"""
    if not state.get("error_message") and not state.get("sql_errors"):
        return state

    fix_attempts = state.get("fix_attempts", 0)
    if fix_attempts >= 2:  # 最多纠错 2 次
        print(f"[节点6.5] 达到最大纠错次数")
        return state

    state["fix_attempts"] = fix_attempts + 1
    error = state.get("error_message", "; ".join(state.get("sql_errors", [])))
    original_sql = state.get("generated_sql", "")

    prompt = f"""SQL 执行出错，请修复。

原始 SQL：
{original_sql}

错误信息：
{error}

数据表信息：
{json.dumps(state.get('domain_tables', []), ensure_ascii=False)}

请输出修复后的 SQL，不要解释："""

    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            temperature=0.0,
        )
        response = llm.invoke(prompt)
        fixed_sql = response.content.strip()
        if fixed_sql.startswith("```"):
            fixed_sql = fixed_sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        state["generated_sql"] = fixed_sql
        state["error_message"] = ""
        state["sql_errors"] = []

        # 重新校验
        validator = SQLValidator()
        permission = state.get("user_permission", UserPermission.LOW)
        valid, errors, _ = validator.validate(fixed_sql, permission)
        state["sql_valid"] = valid
        state["sql_errors"] = errors

        if valid:
            # 重新执行
            executor = SQLExecutor()
            result = executor.execute(fixed_sql, permission)
            state["execution_result"] = result.get("data", [])
            state["result_row_count"] = result.get("row_count", 0)
            if not result["success"]:
                state["error_message"] = result["error"]

        print(f"[节点6.5] SQL 纠错第 {state['fix_attempts']} 次: {'成功' if not state.get('error_message') else '仍失败'}")
    except Exception as e:
        print(f"[节点6.5] 纠错失败: {e}")

    return state


def node_data_analysis(state: AgentState) -> AgentState:
    """节点7: Python 数据分析"""
    data = state.get("execution_result", [])
    if not data:
        state["analysis_result"] = {"summary": "无数据可分析"}
        return state

    intent = state.get("intent", QueryIntent.GENERAL)
    intent_str = intent.value if isinstance(intent, QueryIntent) else "general"

    tool = AnalysisTool(use_docker=False)  # 本地执行（兼容无 Docker 环境）
    analysis_code = tool.generate_analysis_code(
        state.get("rewritten_query", ""),
        data,
        intent_str,
    )
    result = tool.execute(analysis_code, data)

    state["analysis_code"] = analysis_code
    state["analysis_result"] = {
        "output": result.get("output", ""),
        "charts": result.get("charts", []),
        "success": result["success"],
        "error": result.get("error", ""),
    }

    print(f"[节点7] 数据分析: {'成功' if result['success'] else '失败'}")
    return state


def node_memory_update(state: AgentState) -> AgentState:
    """节点8: 记忆沉淀 - 执行->反思->提炼->存储"""
    memory_manager: MemoryManager = state.get("_memory_manager", MemoryManager())

    # 判断是否需要存入长期记忆
    if memory_manager.should_store(state):
        entry = memory_manager.build_memory_entry(state)
        memory_manager.long_term.store(entry)
        state["should_store_memory"] = True
        print(f"[节点8] 记忆已沉淀: {entry.query_hash}")
    else:
        state["should_store_memory"] = False
        print(f"[节点8] 不满足存储条件，跳过记忆沉淀")

    return state


def node_report_generation(state: AgentState) -> AgentState:
    """节点9: 生成可视化报告"""
    data = state.get("execution_result", [])
    analysis = state.get("analysis_result", {})
    intent = state.get("intent", QueryIntent.GENERAL)

    report_parts = []

    # 标题
    query = state.get("user_query", "")
    report_parts.append(f"# 数据分析报告\n")
    report_parts.append(f"**查询问题：** {query}\n")
    report_parts.append(f"**业务域：** {intent.value if isinstance(intent, QueryIntent) else 'general'}\n")
    report_parts.append(f"**生成时间：** {state.get('timestamp', datetime.now().isoformat())}\n")

    # SQL 信息
    sql = state.get("generated_sql", "")
    if sql:
        report_parts.append(f"\n## 执行的 SQL\n```sql\n{sql}\n```\n")

    # 执行结果
    if data:
        report_parts.append(f"\n## 查询结果（共 {state.get('result_row_count', len(data))} 行）\n")
        # 表格展示（最多 10 行）
        headers = list(data[0].keys()) if data else []
        report_parts.append("| " + " | ".join(headers) + " |")
        report_parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in data[:10]:
            values = [str(row.get(h, "")) for h in headers]
            report_parts.append("| " + " | ".join(values) + " |")
        if len(data) > 10:
            report_parts.append(f"\n*... 还有 {len(data) - 10} 行数据*\n")
    else:
        report_parts.append("\n## 查询结果\n无数据返回\n")

    # 分析结论
    if analysis.get("output"):
        report_parts.append(f"\n## 数据分析\n```\n{analysis['output']}\n```\n")

    # 图表
    charts = analysis.get("charts", [])
    if charts:
        report_parts.append("\n## 图表\n")
        for chart in charts:
            report_parts.append(f"![图表]({chart})\n")

    # 安全信息
    sensitive = state.get("sensitive_fields_detected", [])
    if sensitive:
        report_parts.append(f"\n## 安全提示\n")
        report_parts.append(f"本次查询涉及敏感字段: {', '.join(sensitive)}\n")
        permission = state.get("user_permission", UserPermission.LOW)
        if permission == UserPermission.LOW:
            report_parts.append("敏感数据已脱敏处理\n")

    # 记忆信息
    if state.get("long_term_memory_hit"):
        report_parts.append("\n## 备注\n本次查询命中历史记忆，复用了历史 SQL\n")
    elif state.get("should_store_memory"):
        report_parts.append("\n## 备注\n本次查询已存入记忆库，下次相似问题可快速复用\n")

    # 错误信息
    if state.get("error_message"):
        report_parts.append(f"\n## ⚠️ 错误信息\n{state['error_message']}\n")

    state["final_report"] = "\n".join(report_parts)
    print(f"[节点9] 报告生成完成")
    return state


# ==================== 条件路由函数 ====================

def should_fix_sql(state: AgentState) -> str:
    """判断是否需要 SQL 纠错"""
    if state.get("error_message") or state.get("sql_errors"):
        fix_attempts = state.get("fix_attempts", 0)
        if fix_attempts < 2:
            return "fix"
    return "skip"


def should_execute(state: AgentState) -> str:
    """判断是否可以执行 SQL"""
    if not state.get("sql_valid", False):
        return "skip"
    if state.get("approval_status") == ApprovalStatus.PENDING:
        return "skip"
    return "execute"


# ==================== 工作流构建 ====================

def build_workflow() -> StateGraph:
    """
    构建完整的 Agent 工作流
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("intent_recognition", node_intent_recognition)
    workflow.add_node("permission_check", node_permission_check)
    workflow.add_node("rag_retrieval", node_rag_retrieval)
    workflow.add_node("sql_generation", node_sql_generation)
    workflow.add_node("sql_validation", node_sql_validation)
    workflow.add_node("sql_execution", node_sql_execution)
    workflow.add_node("sql_fix", node_sql_fix)
    workflow.add_node("data_analysis", node_data_analysis)
    workflow.add_node("memory_update", node_memory_update)
    workflow.add_node("report_generation", node_report_generation)

    # 设置入口
    workflow.set_entry_point("intent_recognition")

    # 添加边（主流程）
    workflow.add_edge("intent_recognition", "permission_check")
    workflow.add_edge("permission_check", "rag_retrieval")
    workflow.add_edge("rag_retrieval", "sql_generation")
    workflow.add_edge("sql_generation", "sql_validation")

    # 条件边：校验后决定执行还是跳过
    workflow.add_conditional_edges(
        "sql_validation",
        should_execute,
        {
            "execute": "sql_execution",
            "skip": "report_generation",
        }
    )

    # 条件边：执行后决定纠错还是继续
    workflow.add_conditional_edges(
        "sql_execution",
        should_fix_sql,
        {
            "fix": "sql_fix",
            "skip": "data_analysis",
        }
    )

    # 纠错后继续分析
    workflow.add_edge("sql_fix", "data_analysis")

    # 后续流程
    workflow.add_edge("data_analysis", "memory_update")
    workflow.add_edge("memory_update", "report_generation")
    workflow.add_edge("report_generation", END)

    return workflow.compile()


# ==================== 运行入口 ====================

def run_agent(query: str, user_id: str = "default", user_permission: UserPermission = UserPermission.LOW) -> dict:
    """
    运行 Agent
    """
    graph = build_workflow()
    initial_state: AgentState = {
        "user_query": query,
        "user_id": user_id,
        "user_permission": user_permission,
        "fix_attempts": 0,
        "session_id": f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "total_tokens": 0,
        "_memory_manager": MemoryManager(),
    }

    result = graph.invoke(initial_state, config={"recursion_limit": 25})
    return result
