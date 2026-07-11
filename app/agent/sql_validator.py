"""
SQL 安全校验模块
使用 SQLGlot 解析 SQL 语法树，多层安全校验
"""
import re
import sqlglot
from sqlglot import exp
from typing import Optional
from app.config import config
from app.agent.state import AgentState, UserPermission


class SQLValidator:
    """SQL 安全校验器"""

    def __init__(self):
        self.blacklist = config.security.sql_blacklist
        self.max_rows = config.security.max_return_rows
        self.slow_query_timeout = config.security.slow_query_timeout
        self.sensitive_fields = config.security.sensitive_fields

    def validate(self, sql: str, user_permission: UserPermission) -> tuple[bool, list[str], list[str]]:
        """
        校验 SQL 安全性
        返回: (是否通过, 错误列表, 检测到的敏感字段)
        """
        errors: list[str] = []
        sensitive_detected: list[str] = []

        # 1. 基础非空检查
        if not sql or not sql.strip():
            errors.append("SQL 为空")
            return False, errors, sensitive_detected

        sql_upper = sql.upper().strip()

        # 2. 黑名单关键词检查
        for keyword in self.blacklist:
            if re.search(rf'\b{keyword}\b', sql_upper):
                errors.append(f"安全拦截：SQL 包含禁止操作 {keyword}")

        # 3. 使用 SQLGlot 解析语法树做深度校验
        try:
            parsed = sqlglot.parse_one(sql, dialect="postgres")
        except Exception as e:
            errors.append(f"SQL 语法解析失败: {str(e)}")
            return False, errors, sensitive_detected

        # 4. 只允许 SELECT 语句
        if not isinstance(parsed, exp.Select):
            errors.append("安全拦截：仅允许 SELECT 查询语句")
            return False, errors, sensitive_detected

        # 5. 禁止子查询中的写操作
        for subquery in parsed.find_all(exp.Subquery):
            if isinstance(subquery.this, (exp.Insert, exp.Update, exp.Delete, exp.Drop)):
                errors.append("安全拦截：子查询中包含禁止的写操作")

        # 6. 检测敏感字段
        all_columns = [col.name for col in parsed.find_all(exp.Column)]
        for col_name in all_columns:
            if col_name in self.sensitive_fields:
                sensitive_detected.append(col_name)
                # 低权限用户直接拦截敏感字段
                if user_permission == UserPermission.LOW:
                    errors.append(f"权限不足：字段 '{col_name}' 为敏感数据，当前权限等级不允许访问")

        # 7. 自动追加 LIMIT
        has_limit = parsed.args.get("limit") is not None
        if not has_limit:
            sql_with_limit = parsed.limit(self.max_rows).sql(dialect="postgres")
            # 调用方通过 state 拿到修改后的 SQL
            return (len(errors) == 0), errors, sensitive_detected

        # 8. LIMIT 行数检查
        if has_limit:
            limit_expr = parsed.args.get("limit")
            try:
                limit_val = int(limit_expr.this.this)  # type: ignore
                if limit_val > self.max_rows:
                    errors.append(f"返回行数超限：最大允许 {self.max_rows} 行，当前请求 {limit_val} 行")
            except (AttributeError, ValueError):
                pass  # 动态 LIMIT 不拦截

        return (len(errors) == 0), errors, sensitive_detected

    def auto_append_limit(self, sql: str) -> str:
        """自动给 SELECT 追加 LIMIT"""
        try:
            parsed = sqlglot.parse_one(sql, dialect="postgres")
            if isinstance(parsed, exp.Select) and parsed.args.get("limit") is None:
                return parsed.limit(self.max_rows).sql(dialect="postgres")
        except Exception:
            pass
        return sql

    def mask_sensitive_value(self, value, field_name: str, user_permission: UserPermission):
        """敏感字段脱敏"""
        if user_permission == UserPermission.HIGH:
            return value  # 高权限不脱敏

        if field_name not in self.sensitive_fields:
            return value

        mask_type = self.sensitive_fields[field_name]
        if mask_type == "mask":
            return "***"  # 完全遮盖
        elif mask_type == "hash":
            return f"hash_{abs(hash(str(value))) % 100000:05d}"  # 哈希脱敏
        return value

    def is_slow_query(self, sql: str) -> bool:
        """
        检测是否可能是慢查询
        简单规则：无 WHERE 的全表扫描、多表 JOIN、子查询嵌套
        """
        try:
            parsed = sqlglot.parse_one(sql, dialect="postgres")
            if not isinstance(parsed, exp.Select):
                return False

            # 无 WHERE 的全表扫描
            if parsed.args.get("where") is None:
                # 但 SELECT COUNT(*) 或聚合可以无 WHERE
                if not parsed.find(exp.Count) and not parsed.find(exp.Star):
                    joins = list(parsed.find_all(exp.Join))
                    if len(joins) == 0:
                        return True

            # 3表以上 JOIN
            joins = list(parsed.find_all(exp.Join))
            if len(joins) >= 3:
                return True

            # 子查询嵌套层数
            subqueries = list(parsed.find_all(exp.Subquery))
            if len(subqueries) >= 2:
                return True

        except Exception:
            pass
        return False
