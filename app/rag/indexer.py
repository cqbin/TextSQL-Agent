"""
离线索引构建模块
- 元数据索引：解析建表语句，构建 BM25 + 稠密向量混合索引
- 指标索引：解析指标文档，构建混合索引
- 工厂模式：解析、分块、向量化、存储各环节解耦
- 增量索引：基于文档 hash 只更新变化部分
"""
import hashlib
import json
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field

from app.config import config


# ==================== 工厂模式：各处理环节抽象接口 ====================

class DocumentParser(ABC):
    """文档解析器接口"""
    @abstractmethod
    def parse(self, source: str) -> list[dict]:
        """解析源文件，返回文档块列表"""
        pass


class Chunker(ABC):
    """分块器接口"""
    @abstractmethod
    def chunk(self, document: dict, chunk_size: int, overlap: int) -> list[dict]:
        pass


class Embedder(ABC):
    """向量化接口"""
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        pass


class IndexStore(ABC):
    """索引存储接口"""
    @abstractmethod
    def add(self, documents: list[dict], embeddings: list[list[float]], metadatas: list[dict]):
        pass

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[dict]:
        pass


# ==================== 具体实现 ====================

class TableDDLParser(DocumentParser):
    """建表语句解析器"""

    def parse(self, source: str) -> list[dict]:
        """
        解析 CREATE TABLE 语句
        source: SQL DDL 字符串
        """
        import re
        tables = []
        # 匹配 CREATE TABLE 块
        pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);'
        matches = re.findall(pattern, source, re.DOTALL | re.IGNORECASE)

        for table_name, body in matches:
            columns = []
            for line in body.strip().split('\n'):
                line = line.strip().rstrip(',')
                if not line or line.upper().startswith(('PRIMARY', 'FOREIGN', 'CONSTRAINT', 'UNIQUE', 'INDEX')):
                    continue
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    col_name = parts[0]
                    col_type = parts[1]
                    col_desc = parts[2] if len(parts) > 2 else ""
                    columns.append({"name": col_name, "type": col_type, "desc": col_desc})

            tables.append({
                "table_name": table_name,
                "columns": columns,
                "raw_ddl": f"CREATE TABLE {table_name} ({body});",
            })
        return tables


class MetricDocParser(DocumentParser):
    """指标文档解析器"""

    def parse(self, source: str) -> list[dict]:
        """解析 Markdown 格式的指标文档"""
        docs = []
        lines = source.split('\n')
        current_metric = None
        current_content = []

        for line in lines:
            if line.startswith('## '):
                if current_metric:
                    docs.append({
                        "metric_name": current_metric,
                        "content": '\n'.join(current_content),
                    })
                current_metric = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)

        if current_metric:
            docs.append({
                "metric_name": current_metric,
                "content": '\n'.join(current_content),
            })
        return docs


class FixedSizeChunker(Chunker):
    """固定大小分块器"""

    def chunk(self, document: dict, chunk_size: int = 512, overlap: int = 64) -> list[dict]:
        text = document.get("content", document.get("raw_ddl", ""))
        if not text:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            chunks.append({
                **document,
                "content": chunk_text,
                "chunk_index": len(chunks),
                "chunk_start": start,
                "chunk_end": end,
            })
            start = end - overlap
        return chunks


class SentenceTransformerEmbedder(Embedder):
    """Sentence-Transformer 向量化"""

    def __init__(self, model_name: str = None):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name or config.rag.embedding_model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()


class ChromaStore(IndexStore):
    """Chroma 向量库存储"""

    def __init__(self, collection_name: str):
        import chromadb
        client = chromadb.PersistentClient(path=config.rag.chroma_persist_dir)
        self.collection = client.get_or_create_collection(name=collection_name)

    def add(self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]):
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, query_embedding: list[float], top_k: int = 10) -> list[dict]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        entries = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                entries.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 1.0,
                })
        return entries


# ==================== 索引构建器（工厂模式组装） ====================

@dataclass
class IndexBuilder:
    """
    索引构建器：组装解析 -> 分块 -> 向量化 -> 存储
    支持增量索引：基于文档 hash 只更新变化部分
    """
    parser: DocumentParser
    chunker: Chunker
    embedder: Embedder
    store: ChromaStore
    collection_name: str
    _hash_cache: dict[str, str] = field(default_factory=dict)

    def _compute_hash(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()

    def build(self, source: str, force: bool = False) -> int:
        """
        构建索引
        返回新增的 chunk 数量
        """
        # 解析
        documents = self.parser.parse(source)
        if not documents:
            return 0

        total_added = 0
        for doc in documents:
            doc_text = doc.get("content", doc.get("raw_ddl", ""))
            doc_hash = self._compute_hash(doc_text)

            # 增量索引：跳过未变化的文档
            doc_key = doc.get("table_name", doc.get("metric_name", ""))
            if not force and self._hash_cache.get(doc_key) == doc_hash:
                continue
            self._hash_cache[doc_key] = doc_hash

            # 分块
            chunks = self.chunker.chunk(doc)
            if not chunks:
                continue

            # 向量化
            texts = [c["content"] for c in chunks]
            embeddings = self.embedder.embed(texts)

            # 生成 ID
            ids = [f"{self.collection_name}_{doc_key}_{i}" for i in range(len(chunks))]
            metadatas = [{"doc_key": doc_key, "doc_hash": doc_hash, **{k: v for k, v in c.items() if k != "content"}} for c in chunks]

            # 存储
            self.store.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
            total_added += len(chunks)

        return total_added


class MetadataIndexer:
    """元数据索引器"""

    def __init__(self):
        self.builder = IndexBuilder(
            parser=TableDDLParser(),
            chunker=FixedSizeChunker(),
            embedder=None,  # 延迟初始化
            store=ChromaStore("metadata_index"),
            collection_name="metadata",
        )

    def build(self, ddl_source: str, force: bool = False) -> int:
        if self.builder.embedder is None:
            self.builder.embedder = SentenceTransformerEmbedder()
        return self.builder.build(ddl_source, force=force)


class MetricIndexer:
    """指标索引器"""

    def __init__(self):
        self.builder = IndexBuilder(
            parser=MetricDocParser(),
            chunker=FixedSizeChunker(),
            embedder=None,
            store=ChromaStore("metric_index"),
            collection_name="metric",
        )

    def build(self, doc_source: str, force: bool = False) -> int:
        if self.builder.embedder is None:
            self.builder.embedder = SentenceTransformerEmbedder()
        return self.builder.build(doc_source, force=force)
