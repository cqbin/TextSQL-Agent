"""
查询改写模块
将用户口语化问题改写为标准检索查询
"""
from typing import Optional
from app.config import config


class QueryRewriter:
    """
    查询改写器
    - 口语化问题 -> 标准检索语句
    - 补充上下文信息
    - 支持多轮对话中的指代消解
    """

    REWRITE_PROMPT = """你是一个查询改写助手。请将用户的口语化问题改写为标准的检索查询。

规则：
1. 保留用户的核心意图
2. 将口语化表达转为书面标准表达
3. 补充隐含的业务术语（如"卖了多少" -> "销售额"）
4. 消除代词指代（如"它"、"这个"替换为具体实体）
5. 输出简洁的标准查询语句，不要解释

示例：
- "上个月哪个门店卖得最好" -> "上月销售额最高的门店排名"
- "库存够不够" -> "当前库存量与安全库存对比分析"
- "毛利率多少" -> "各门店毛利率统计"

用户问题：{query}
改写结果："""

    def __init__(self, llm=None):
        self._llm = llm

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                api_key=config.llm.api_key,
                base_url=config.llm.base_url,
                model=config.llm.model,
                temperature=0.0,
                max_tokens=256,
            )
        return self._llm

    def rewrite(self, query: str, context: Optional[str] = None) -> str:
        """
        改写查询
        context: 前几轮对话的上下文，用于指代消解
        """
        # 简单规则改写（无需 LLM）
        simple_rewrites = {
            "卖了多少": "销售额统计",
            "赚了多少": "毛利润统计",
            "库存够不够": "库存量与安全库存对比",
            "哪个卖得好": "销量排名",
            "还剩多少": "当前库存量",
        }

        for old, new in simple_rewrites.items():
            if old in query and len(query) < 15:
                return query.replace(old, new)

        # 如果有上下文，做指代消解
        if context:
            query = f"{context}\n当前问题：{query}"

        # LLM 改写
        try:
            llm = self._get_llm()
            prompt = self.REWRITE_PROMPT.format(query=query)
            response = llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"[QueryRewriter] LLM 改写失败，使用原始查询: {e}")
            return query
