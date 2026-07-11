"""
AgentState - 核心状态定义
整个 Agent 工作流的状态容器，所有节点共享和修改这个状态
"""
from typing import TypedDict, Literal, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class QueryIntent(str, Enum):
    """用户意图分类"""
    SALES = "sales"          # 销售查询
    INVENTORY = "inventory"  # 库存查询
    FINANCE = "finance"      # 财务毛利
    CUSTOMER = "customer"    # 客户分析
    GENERAL = "general"      # 通用查询


class UserPermission(str, Enum):
    """用户权限等级"""
    LOW = "low"        # 普通用户，只能看脱敏数据
    MEDIUM = "medium"  # 中级用户，可看部分敏感数据
    HIGH = "high"      # 高级用户，可看全部数据（需审批）


class ApprovalStatus(str, Enum):
    """审批状态"""
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentState(TypedDict, total=False):
    """
    LangGraph Agent 状态结构体
    所有节点共享此状态，通过状态传递数据
    """
    # 用户输入
    user_query: str                            # 用户原始问题
    rewritten_query: str                       # 查询改写后的标准问题
    user_id: str                               # 用户ID
    user_permission: UserPermission             # 用户权限等级

    # 意图识别
    intent: QueryIntent                         # 识别出的业务域
    domain_tables: list[str]                   # 该业务域可用的数据表

    # RAG 召回
    retrieved_tables: list[dict[str, Any]]     # 召回的表结构信息
    retrieved_metrics: list[dict[str, Any]]    # 召回的指标定义
    rag_confidence: float                      # RAG 召回置信度
    needs_second_retrieval: bool               # 是否需要二次检索

    # SQL 生成与执行
    generated_sql: str                         # 生成的SQL语句
    sql_valid: bool                            # SQL安全校验是否通过
    sql_errors: list[str]                      # SQL错误信息
    fix_attempts: int                          # SQL纠错次数
    execution_result: list[dict[str, Any]]     # SQL执行结果
    result_row_count: int                      # 返回行数

    # 安全与审批
    approval_status: ApprovalStatus            # 审批状态
    sensitive_fields_detected: list[str]       # 检测到的敏感字段
    is_slow_query: bool                        # 是否慢查询

    # 数据分析
    analysis_code: str                         # 生成的Python分析代码
    analysis_result: dict[str, Any]            # 分析结果（图表、统计等）
    charts: list[str]                          # 生成的图表路径

    # 记忆
    short_term_memory: list[dict[str, Any]]    # 短时记忆（当前会话）
    long_term_memory_hit: Optional[dict]       # 长期记忆命中（历史相似查询）
    should_store_memory: bool                  # 是否需要存入长期记忆

    # 输出
    final_report: str                          # 最终Markdown报告
    error_message: str                         # 错误信息

    # 元数据
    session_id: str                            # 会话ID
    timestamp: str                             # 时间戳
    total_tokens: int                          # Token消耗统计


class Message(BaseModel):
    """对话消息"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
