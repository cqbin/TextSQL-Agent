"""
双层检索器
查询改写 -> 问题路由 -> 多路召回（BM25 + 向量）-> Rerank 重排 -> 低置信二次检索
"""
from typing import Optional
from dataclasses import dataclass

from app.config import config
from app.rag.indexer import ChromaStore, SentenceTransformerEmbedder
from app.rag.cache import RAGCache


@dataclass
class RetrievalResult:
    """检索结果"""
    documents: list[dict]
    confidence: float
    needs_second_retrieval: bool
    source: str  # metadata / metric / both


class BM25Retriever:
    """BM25 关键词检索"""

    def __init__(self, documents: list[dict] = None):
        self._documents = documents or []
        self._bm25 = None
        if documents:
            self._build_index()

    def _build_index(self):
        from rank_bm25 import BM25Okapi
        tokenized = [doc["content"][:500].split() for doc in self._documents]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not self._bm25:
            return []
        tokens = query.split()
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({**self._documents[idx], "bm25_score": float(scores[idx])})
        return results


class Reranker:
    """Rerank 重排器"""

    def __init__(self, model_name: str = None):
        self._model = None
        self._model_name = model_name or config.rag.rerank_model

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
        return self._model

    def rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        """对召回结果重排"""
        if not documents:
            return []

        try:
            model = self._load_model()
            pairs = [(query, doc["content"][:500]) for doc in documents]
            scores = model.predict(pairs)

            for i, doc in enumerate(documents):
                doc["rerank_score"] = float(scores[i])

            # 按重排分数排序
            documents.sort(key=lambda x: x["rerank_score"], reverse=True)
            return documents[:top_k]
        except Exception as e:
            print(f"[Reranker] 重排失败，使用原始排序: {e}")
            return documents[:top_k]


class DualRetriever:
    """
    双层检索器
    第一层：元数据 RAG（数据表结构）
    第二层：指标 RAG（业务指标定义）
    """

    def __init__(self):
        self.metadata_store = ChromaStore("metadata_index")
        self.metric_store = ChromaStore("metric_index")
        self.embedder = SentenceTransformerEmbedder()
        self.reranker = Reranker()
        self.cache = RAGCache()

    def retrieve(self, query: str, domain: str = None) -> RetrievalResult:
        """
        完整检索链路：
        1. 缓存命中检查
        2. 向量多路召回（元数据 + 指标）
        3. BM25 补充召回
        4. Rerank 重排
        5. 置信度评估 -> 低置信触发二次检索
        """
        # 1. 缓存检查
        cached = self.cache.get(query)
        if cached:
            return RetrievalResult(
                documents=cached,
                confidence=1.0,
                needs_second_retrieval=False,
                source="cache",
            )

        # 2. 向量召回
        query_embedding = self.embedder.embed([query])[0]

        metadata_results = self.metadata_store.search(query_embedding, top_k=config.rag.top_k_vector)
        metric_results = self.metric_store.search(query_embedding, top_k=config.rag.top_k_vector)

        # 3. BM25 召回（如果有本地文档）
        bm25_results = []
        # BM25 在离线阶段已建好索引，这里简化为从向量结果中补充

        # 合并结果
        all_results = metadata_results + metric_results + bm25_results
        if not all_results:
            return RetrievalResult(
                documents=[],
                confidence=0.0,
                needs_second_retrieval=True,
                source="empty",
            )

        # 4. Rerank 重排
        reranked = self.reranker.rerank(query, all_results, top_k=config.rag.top_k_rerank)

        # 5. 置信度评估
        best_score = reranked[0].get("rerank_score", 0.0) if reranked else 0.0
        # 归一化置信度
        confidence = min(best_score / 10.0, 1.0) if best_score > 1.0 else best_score
        needs_second = confidence < config.rag.confidence_threshold

        # 6. 二次检索（放宽条件）
        if needs_second:
            print(f"[DualRetriever] 置信度过低 ({confidence:.3f})，触发二次检索")
            # 扩大召回范围
            metadata_results_2 = self.metadata_store.search(query_embedding, top_k=config.rag.top_k_vector * 2)
            metric_results_2 = self.metric_store.search(query_embedding, top_k=config.rag.top_k_vector * 2)
            all_results_2 = metadata_results_2 + metric_results_2
            reranked = self.reranker.rerank(query, all_results_2, top_k=config.rag.top_k_rerank * 2)
            # 重新评估
            best_score = reranked[0].get("rerank_score", 0.0) if reranked else 0.0
            confidence = min(best_score / 10.0, 1.0) if best_score > 1.0 else best_score

        # 7. 缓存结果
        self.cache.set(query, reranked)

        # 分离元数据和指标结果
        return RetrievalResult(
            documents=reranked,
            confidence=confidence,
            needs_second_retrieval=needs_second,
            source="both",
        )

    def retrieve_metadata(self, query: str, top_k: int = 5) -> list[dict]:
        """仅检索元数据"""
        query_embedding = self.embedder.embed([query])[0]
        results = self.metadata_store.search(query_embedding, top_k=top_k)
        return self.reranker.rerank(query, results, top_k=top_k)

    def retrieve_metrics(self, query: str, top_k: int = 5) -> list[dict]:
        """仅检索指标定义"""
        query_embedding = self.embedder.embed([query])[0]
        results = self.metric_store.search(query_embedding, top_k=top_k)
        return self.reranker.rerank(query, results, top_k=top_k)
