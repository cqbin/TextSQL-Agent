"""
TextSQL-Agent 全局配置
"""
import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class LLMConfig(BaseModel):
    """大模型配置"""
    api_key: str = os.getenv("LLM_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model: str = os.getenv("LLM_MODEL", "qwen-plus")
    temperature: float = 0.1
    max_tokens: int = 4096


class DatabaseConfig(BaseModel):
    """业务数据库配置"""
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "retail_db")
    user: str = os.getenv("DB_USER", "readonly_user")
    password: str = os.getenv("DB_PASSWORD", "readonly_pass")
    # 只读账户，禁止写操作
    readonly: bool = True


class RAGConfig(BaseModel):
    """RAG 配置"""
    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma_db")
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k_bm25: int = 10
    top_k_vector: int = 10
    top_k_rerank: int = 5
    rerank_threshold: float = 0.5
    rerank_model: str = "BAAI/bge-reranker-base"
    confidence_threshold: float = 0.3  # 低于此值触发二次检索


class RedisConfig(BaseModel):
    """Redis 缓存配置"""
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    db: int = 0
    password: str = os.getenv("REDIS_PASSWORD", "")


class SandboxConfig(BaseModel):
    """Python 沙盒配置"""
    docker_image: str = "python-sandbox:latest"
    cpu_limit: str = "1.0"
    memory_limit: str = "512m"
    timeout: int = 30  # 秒
    network_disabled: bool = True


class SecurityConfig(BaseModel):
    """安全配置"""
    # SQL 黑名单关键词
    sql_blacklist: list[str] = ["DROP", "DELETE", "ALTER", "TRUNCATE", "INSERT", "UPDATE", "GRANT", "REVOKE"]
    max_return_rows: int = 1000
    slow_query_timeout: int = 30  # 秒
    # 敏感字段映射（字段名 -> 脱敏方式）
    sensitive_fields: dict[str, str] = {
        "cost_price": "mask",       # 成本价 -> 脱敏
        "profit_margin": "mask",    # 毛利率 -> 脱敏
        "customer_phone": "hash",   # 手机号 -> 哈希
        "customer_idcard": "hash",  # 身份证 -> 哈希
    }
    # 需要人工审批的敏感等级
    approval_required_level: str = "high"


class Config:
    """全局配置单例"""
    llm = LLMConfig()
    database = DatabaseConfig()
    rag = RAGConfig()
    redis = RedisConfig()
    sandbox = SandboxConfig()
    security = SecurityConfig()
    base_dir = BASE_DIR


config = Config()
