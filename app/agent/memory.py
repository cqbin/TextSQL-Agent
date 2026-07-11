"""
记忆系统模块
短时记忆：分层上下文压缩 + Redis 缓存
长期记忆：向量库存储高频查询经验，按需复用
"""
import json
import hashlib
from typing import Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from app.config import config


@dataclass
class ShortTermMemory:
    """
    短时记忆：管理当前会话的上下文
    - 完整结果缓存到内存/Redis，Prompt 只放摘要
    - 超过 Token 上限时自动压缩历史
    """
    max_messages: int = 20
    max_tokens: int = 6000
    messages: list[dict[str, Any]] = field(default_factory=list)
    # 缓存完整的 SQL 执行结果，Prompt 中只放占位符
    result_cache: dict[str, list[dict]] = field(default_factory=dict)

    def add_message(self, role: str, content: str, metadata: Optional[dict] = None):
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        })
        # 超过上限时压缩
        if len(self.messages) > self.max_messages:
            self._compress()

    def add_result(self, key: str, result: list[dict]):
        """缓存完整执行结果"""
        self.result_cache[key] = result

    def get_result(self, key: str) -> Optional[list[dict]]:
        """获取缓存的执行结果"""
        return self.result_cache.get(key)

    def _compress(self):
        """
        分层上下文压缩：
        - 保留最近 5 条完整消息
        - 较早的消息压缩为摘要
        """
        if len(self.messages) <= 5:
            return

        # 保留最近 5 条
        recent = self.messages[-5:]
        older = self.messages[:-5]

        # 将较早的消息压缩为摘要
        summary_parts = []
        for msg in older:
            if msg["role"] == "user":
                summary_parts.append(f"用户曾问: {msg['content'][:80]}")
            elif msg["role"] == "assistant":
                summary_parts.append(f"助手回答: {msg['content'][:80]}")

        summary = "【历史对话摘要】\n" + "\n".join(summary_parts)

        self.messages = [
            {"role": "system", "content": summary, "timestamp": datetime.now().isoformat()}
        ] + recent

    def to_prompt_messages(self) -> list[dict[str, str]]:
        """转换为 LLM Prompt 格式"""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]

    def estimate_tokens(self) -> int:
        """粗略估算 Token 数"""
        total = 0
        for msg in self.messages:
            total += len(msg["content"]) // 3  # 中文约 3 字符/token
        return total

    def needs_compression(self) -> bool:
        """是否需要压缩"""
        return self.estimate_tokens() > self.max_tokens


@dataclass
class MemoryEntry:
    """长期记忆条目"""
    query: str                    # 用户原始问题
    rewritten_query: str          # 改写后的标准问题
    domain: str                   # 业务域
    sql: str                      # 正确的 SQL
    intent: str                   # 意图
    success: bool                 # 是否执行成功
    timestamp: str = ""
    query_hash: str = ""
    access_count: int = 1         # 被命中次数

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.query_hash:
            self.query_hash = hashlib.md5(self.rewritten_query.encode()).hexdigest()


class LongTermMemory:
    """
    长期记忆：向量库存储
    - 每次查询成功后，判断是否为高频查询，存入向量库
    - 下次相似问题直接召回历史 SQL，无需重新生成
    """

    def __init__(self):
        self._collection = None
        self._init_collection()

    def _init_collection(self):
        """初始化 Chroma 集合"""
        try:
            import chromadb
            client = chromadb.PersistentClient(path=config.rag.chroma_persist_dir)
            self._collection = client.get_or_create_collection(
                name="long_term_memory",
                metadata={"description": "用户查询历史记忆"}
            )
        except Exception as e:
            print(f"[LongTermMemory] 初始化失败: {e}")
            self._collection = None

    def store(self, entry: MemoryEntry):
        """存储一条记忆"""
        if not self._collection:
            return

        # 检查是否已有相似记忆
        existing = self._search_internal(entry.rewritten_query, top_k=1)
        if existing and existing[0]["similarity"] > 0.85:
            # 已有相似记忆，增加访问计数
            self._collection.update(
                ids=[existing[0]["id"]],
                metadatas=[{
                    **existing[0]["metadata"],
                    "access_count": existing[0]["metadata"].get("access_count", 1) + 1,
                }]
            )
            return

        # 存储新记忆
        self._collection.add(
            ids=[entry.query_hash],
            documents=[entry.rewritten_query],
            metadatas={
                "query": entry.query,
                "domain": entry.domain,
                "sql": entry.sql,
                "intent": entry.intent,
                "success": entry.success,
                "timestamp": entry.timestamp,
                "access_count": entry.access_count,
            }
        )

    def search(self, query: str, top_k: int = 3) -> Optional[dict[str, Any]]:
        """搜索长期记忆，返回最相似的历史查询"""
        if not self._collection:
            return None

        results = self._search_internal(query, top_k=top_k)
        if not results:
            return None

        best = results[0]
        if best["similarity"] > 0.75:
            return {
                "query": best["metadata"].get("query", ""),
                "sql": best["metadata"].get("sql", ""),
                "domain": best["metadata"].get("domain", ""),
                "similarity": best["similarity"],
                "access_count": best["metadata"].get("access_count", 1),
            }
        return None

    def _search_internal(self, query: str, top_k: int = 3) -> list[dict]:
        """内部搜索"""
        if not self._collection:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
            )
            entries = []
            if results["ids"] and results["ids"][0]:
                for i, idx in enumerate(results["ids"][0]):
                    dist = results["distances"][0][i] if results["distances"] else 1.0
                    sim = 1.0 - dist  # 距离转相似度
                    entries.append({
                        "id": idx,
                        "similarity": sim,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    })
            return entries
        except Exception as e:
            print(f"[LongTermMemory] 搜索失败: {e}")
            return []


class MemoryManager:
    """
    记忆管理器：统一管理短时和长期记忆
    执行 -> 反思 -> 提炼 -> 分类存储 -> 按需复用
    """

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()

    def should_store(self, state: AgentState) -> bool:
        """
        判断是否需要存入长期记忆
        - 执行成功的查询
        - SQL 有效
        - 非错误结果
        """
        return (
            state.get("sql_valid", False)
            and state.get("execution_result") is not None
            and not state.get("error_message")
            and state.get("fix_attempts", 0) <= 1  # 一次成功才存（多次纠错的不存）
        )

    def build_memory_entry(self, state: AgentState) -> MemoryEntry:
        """从当前状态构建记忆条目"""
        return MemoryEntry(
            query=state.get("user_query", ""),
            rewritten_query=state.get("rewritten_query", state.get("user_query", "")),
            domain=state.get("intent", "general"),
            sql=state.get("generated_sql", ""),
            intent=state.get("intent", "general"),
            success=True,
        )

    def retrieve(self, query: str) -> Optional[dict]:
        """从长期记忆中检索相似查询"""
        return self.long_term.search(query)
