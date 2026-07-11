"""
SQL 执行工具
"""
from typing import Any, Optional
from app.config import config
from app.agent.state import UserPermission
from app.agent.sql_validator import SQLValidator


class SQLExecutor:
    """
    SQL 执行器
    - 使用只读账户连接数据库
    - 自动脱敏敏感字段
    - 限制返回行数
    - 慢查询检测
    """

    def __init__(self):
        self.validator = SQLValidator()
        self._engine = None

    def _get_engine(self):
        """延迟初始化数据库连接"""
        if self._engine is None:
            from sqlalchemy import create_engine
            url = f"postgresql+psycopg2://{config.database.user}:{config.database.password}@{config.database.host}:{config.database.port}/{config.database.database}"
            self._engine = create_engine(url, pool_pre_ping=True, pool_size=5)
        return self._engine

    def execute(self, sql: str, user_permission: UserPermission = UserPermission.LOW) -> dict[str, Any]:
        """
        执行 SQL 查询
        返回: {"success": bool, "data": list[dict], "row_count": int, "error": str, "is_slow": bool}
        """
        # 安全校验
        valid, errors, sensitive_fields = self.validator.validate(sql, user_permission)
        if not valid:
            return {
                "success": False,
                "data": [],
                "row_count": 0,
                "error": "; ".join(errors),
                "is_slow": False,
            }

        # 自动追加 LIMIT
        sql = self.validator.auto_append_limit(sql)

        # 慢查询检测
        is_slow = self.validator.is_slow_query(sql)

        try:
            from sqlalchemy import text
            engine = self._get_engine()
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = result.fetchmany(config.security.max_return_rows)
                data = [dict(zip(columns, row)) for row in rows]

                # 敏感字段脱敏
                for row in data:
                    for field_name in sensitive_fields:
                        if field_name in row:
                            row[field_name] = self.validator.mask_sensitive_value(
                                row[field_name], field_name, user_permission
                            )

                return {
                    "success": True,
                    "data": data,
                    "row_count": len(data),
                    "error": "",
                    "is_slow": is_slow,
                    "columns": columns,
                }
        except Exception as e:
            return {
                "success": False,
                "data": [],
                "row_count": 0,
                "error": f"SQL 执行失败: {str(e)}",
                "is_slow": is_slow,
            }

    def dry_run(self, sql: str) -> dict[str, Any]:
        """
        EXPLAIN 分析 SQL，不实际执行
        """
        try:
            from sqlalchemy import text
            engine = self._get_engine()
            explain_sql = f"EXPLAIN {sql}"
            with engine.connect() as conn:
                result = conn.execute(text(explain_sql))
                plan = [row[0] for row in result.fetchall()]
                return {"success": True, "plan": plan, "error": ""}
        except Exception as e:
            return {"success": False, "plan": [], "error": str(e)}
