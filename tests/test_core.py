"""
TextSQL-Agent 测试套件
"""
import sys
import os
import pytest

# 添加项目根目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_skill_router():
    """测试 Skill 分层路由"""
    from app.agent.skill_router import SkillRouter
    router = SkillRouter()

    # 测试按域获取表
    sales_tables = router.get_tables_by_domain("sales")
    assert len(sales_tables) > 0
    assert any(t.table_name == "sales_orders" for t in sales_tables)

    # 测试跨域查找
    table = router.get_table_by_name("inventory")
    assert table is not None
    assert table.domain == "inventory"

    # 测试获取敏感字段
    finance_sensitive = router.get_sensitive_fields("finance")
    assert "cost_price" in finance_sensitive or "profit_margin" in finance_sensitive


def test_sql_validator():
    """测试 SQL 安全校验"""
    from app.agent.sql_validator import SQLValidator
    from app.agent.state import UserPermission

    validator = SQLValidator()

    # 测试合法 SELECT
    valid, errors, sensitive = validator.validate(
        "SELECT * FROM stores",
        UserPermission.LOW
    )
    assert valid

    # 测试黑名单拦截
    valid, errors, sensitive = validator.validate(
        "DROP TABLE stores",
        UserPermission.HIGH
    )
    assert not valid
    assert any("DROP" in e for e in errors)

    # 测试 DELETE 拦截
    valid, errors, _ = validator.validate(
        "DELETE FROM stores WHERE store_id = 1",
        UserPermission.HIGH
    )
    assert not valid

    # 测试自动追加 LIMIT
    sql = validator.auto_append_limit("SELECT * FROM stores")
    assert "LIMIT" in sql.upper()

    # 测试低权限敏感字段拦截
    valid, errors, sensitive = validator.validate(
        "SELECT cost_price FROM products",
        UserPermission.LOW
    )
    assert not valid
    assert "cost_price" in sensitive


def test_sql_validator_slow_query():
    """测试慢查询检测"""
    from app.agent.sql_validator import SQLValidator
    validator = SQLValidator()

    # 无 WHERE 的全表扫描
    assert validator.is_slow_query("SELECT * FROM stores")

    # 正常查询不是慢查询
    assert not validator.is_slow_query("SELECT * FROM stores WHERE store_id = 1")


def test_memory_system():
    """测试记忆系统"""
    from app.agent.memory import ShortTermMemory, MemoryEntry

    # 短时记忆压缩
    stm = ShortTermMemory(max_messages=5)
    for i in range(10):
        stm.add_message("user", f"测试消息 {i}")
    # 应该被压缩
    assert len(stm.messages) <= 6

    # 长期记忆条目
    entry = MemoryEntry(
        query="上月销售额",
        rewritten_query="上月各门店销售额统计",
        domain="sales",
        sql="SELECT store_id, SUM(total_amount) FROM sales_orders GROUP BY store_id",
        intent="sales",
        success=True,
    )
    assert entry.query_hash != ""
    assert entry.timestamp != ""


def test_query_rewriter():
    """测试查询改写"""
    from app.rag.rewriter import QueryRewriter
    rewriter = QueryRewriter()

    # 测试简单规则改写
    result = rewriter.rewrite("卖了多少")
    assert "销售额" in result


def test_rag_cache():
    """测试 RAG 缓存"""
    from app.rag.cache import RAGCache
    cache = RAGCache()

    # 设置缓存
    cache.set("测试查询", [{"table": "stores"}])

    # 获取缓存
    result = cache.get("测试查询")
    assert result is not None
    assert len(result) == 1

    # 缓存未命中
    miss = cache.get("不存在的查询")
    assert miss is None


def test_agent_state():
    """测试 Agent 状态定义"""
    from app.agent.state import AgentState, QueryIntent, UserPermission

    state: AgentState = {
        "user_query": "上月销售额",
        "user_id": "test_user",
        "user_permission": UserPermission.LOW,
        "intent": QueryIntent.SALES,
        "fix_attempts": 0,
    }
    assert state["intent"] == QueryIntent.SALES
    assert state["user_permission"] == UserPermission.LOW


def test_analysis_tool():
    """测试数据分析工具"""
    from app.tools.analysis_tool import AnalysisTool
    tool = AnalysisTool(use_docker=False)

    # 生成分析代码
    code = tool.generate_analysis_code("销售额统计", [], "sales")
    assert "销售" in code

    # 本地执行
    result = tool.execute("result_text = 'test'", [{"a": 1}])
    assert result["success"]


def test_rag_evaluator():
    """测试 RAG 评测器"""
    from app.rag.evaluator import RAGEvaluator

    evaluator = RAGEvaluator()

    # 测试召回评估
    retrieval_results = [
        {
            "retrieved_docs": [
                {"metadata": {"table_name": "sales_orders"}},
                {"metadata": {"table_name": "stores"}},
            ],
            "expected": {"expected_tables": ["sales_orders"]},
        }
    ]
    metrics = evaluator.evaluate_retrieval(retrieval_results)
    assert metrics["precision"] > 0
    assert metrics["hit_rate"] > 0


def test_config():
    """测试配置"""
    from app.config import config
    assert config.security.sql_blacklist is not None
    assert "DROP" in config.security.sql_blacklist
    assert config.security.max_return_rows > 0
    assert config.rag.chunk_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
