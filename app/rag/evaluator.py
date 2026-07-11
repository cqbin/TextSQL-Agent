"""
RAGAS 评测模块
评估 RAG 召回质量和 SQL 生成质量
"""
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class EvaluationResult:
    """评测结果"""
    # RAG 召回质量
    precision: float = 0.0       # 召回的文档中有多少是相关的
    recall: float = 0.0          # 相关文档中有多少被召回了
    mrr: float = 0.0            # 平均倒数排名 (Mean Reciprocal Rank)
    hit_rate: float = 0.0       # 命中率
    # SQL 生成质量
    sql_accuracy: float = 0.0   # SQL 执行结果正确率
    sql_syntax_valid: float = 0.0  # SQL 语法合法率
    # 详情
    details: list[dict] = field(default_factory=list)


class RAGEvaluator:
    """
    RAGAS + 自定义指标评测
    """

    def __init__(self):
        self.test_cases: list[dict] = []

    def load_test_cases(self, cases: list[dict]):
        """
        加载测试集
        每条格式：
        {
            "query": "上月销售额最高的门店",
            "expected_tables": ["sales_orders", "stores"],
            "expected_metrics": ["销售额"],
            "expected_sql_pattern": "SELECT.*store.*SUM.*total_amount.*ORDER BY.*DESC.*LIMIT",
            "domain": "sales"
        }
        """
        self.test_cases = cases

    def evaluate_retrieval(self, retrieval_results: list[dict]) -> dict:
        """
        评估召回质量
        retrieval_results: [{"query": ..., "retrieved_docs": [...], "expected": {...}}]
        """
        total = len(retrieval_results)
        if total == 0:
            return {"precision": 0, "recall": 0, "mrr": 0, "hit_rate": 0}

        precision_sum = 0
        recall_sum = 0
        mrr_sum = 0
        hit_count = 0

        for result in retrieval_results:
            retrieved = result.get("retrieved_docs", [])
            expected_tables = set(result.get("expected", {}).get("expected_tables", []))

            # 提取召回的表名
            retrieved_tables = set()
            for doc in retrieved:
                table_name = doc.get("metadata", {}).get("table_name", doc.get("metadata", {}).get("doc_key", ""))
                if table_name:
                    retrieved_tables.add(table_name)

            # Precision: 召回中有多少是正确的
            if retrieved_tables:
                relevant = retrieved_tables & expected_tables
                precision_sum += len(relevant) / len(retrieved_tables)

            # Recall: 期望中有多少被召回了
            if expected_tables:
                recalled = retrieved_tables & expected_tables
                recall_sum += len(recalled) / len(expected_tables)

            # MRR: 第一个正确结果的排名倒数
            for i, doc in enumerate(retrieved):
                table_name = doc.get("metadata", {}).get("table_name", doc.get("metadata", {}).get("doc_key", ""))
                if table_name in expected_tables:
                    mrr_sum += 1.0 / (i + 1)
                    hit_count += 1
                    break

        return {
            "precision": precision_sum / total,
            "recall": recall_sum / total,
            "mrr": mrr_sum / total,
            "hit_rate": hit_count / total,
        }

    def evaluate_sql(self, sql_results: list[dict]) -> dict:
        """
        评估 SQL 生成质量
        sql_results: [{"query": ..., "generated_sql": ..., "expected_pattern": ..., "executed": bool, "correct": bool}]
        """
        total = len(sql_results)
        if total == 0:
            return {"accuracy": 0, "syntax_valid": 0}

        import re
        correct = 0
        valid = 0

        for result in sql_results:
            sql = result.get("generated_sql", "")
            expected_pattern = result.get("expected_pattern", "")

            # 语法合法性（简单检查）
            if sql.strip().upper().startswith("SELECT"):
                valid += 1

            # 正则匹配期望模式
            if expected_pattern and re.search(expected_pattern, sql, re.IGNORECASE):
                correct += 1
            elif result.get("correct"):
                correct += 1

        return {
            "accuracy": correct / total,
            "syntax_valid": valid / total,
        }

    def run_full_evaluation(
        self,
        retrieval_results: list[dict],
        sql_results: list[dict],
    ) -> EvaluationResult:
        """运行完整评测"""
        rag_metrics = self.evaluate_retrieval(retrieval_results)
        sql_metrics = self.evaluate_sql(sql_results)

        return EvaluationResult(
            precision=rag_metrics["precision"],
            recall=rag_metrics["recall"],
            mrr=rag_metrics["mrr"],
            hit_rate=rag_metrics["hit_rate"],
            sql_accuracy=sql_metrics["accuracy"],
            sql_syntax_valid=sql_metrics["syntax_valid"],
            details=[{"rag": rag_metrics, "sql": sql_metrics}],
        )

    def format_report(self, result: EvaluationResult) -> str:
        """格式化评测报告"""
        return f"""
========== RAGAS 评测报告 ==========
RAG 召回质量:
  - Precision:  {result.precision:.4f}
  - Recall:     {result.recall:.4f}
  - MRR:        {result.mrr:.4f}
  - Hit Rate:   {result.hit_rate:.4f}

SQL 生成质量:
  - 准确率:     {result.sql_accuracy:.4f}
  - 语法合法率: {result.sql_syntax_valid:.4f}
====================================
"""
