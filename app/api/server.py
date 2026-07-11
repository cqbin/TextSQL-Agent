"""
FastAPI 后端接口
提供 RESTful API 和 SSE 流式输出
"""
import json
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.workflow import run_agent, build_workflow
from app.agent.state import AgentState, UserPermission, QueryIntent
from app.agent.memory import MemoryManager
from app.config import config

app = FastAPI(
    title="TextSQL-Agent",
    description="企业级自助数据分析 Agent API",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 请求/响应模型 ====================

class QueryRequest(BaseModel):
    """查询请求"""
    query: str
    user_id: str = "default"
    user_permission: str = "low"  # low / medium / high


class QueryResponse(BaseModel):
    """查询响应"""
    success: bool
    report: str
    sql: str = ""
    row_count: int = 0
    charts: list[str] = []
    intent: str = ""
    error: str = ""


class HealthResponse(BaseModel):
    """健康检查"""
    status: str
    version: str
    timestamp: str


# ==================== 接口 ====================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        timestamp=datetime.now().isoformat(),
    )


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    同步查询接口
    业务人员用自然语言提问，返回分析报告
    """
    try:
        permission = UserPermission(request.user_permission)
    except ValueError:
        permission = UserPermission.LOW

    try:
        result = run_agent(
            query=request.query,
            user_id=request.user_id,
            user_permission=permission,
        )

        return QueryResponse(
            success=not result.get("error_message"),
            report=result.get("final_report", "无报告"),
            sql=result.get("generated_sql", ""),
            row_count=result.get("result_row_count", 0),
            charts=result.get("analysis_result", {}).get("charts", []),
            intent=result.get("intent", QueryIntent.GENERAL).value if isinstance(result.get("intent"), QueryIntent) else "general",
            error=result.get("error_message", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/stream")
async def query_stream(request: QueryRequest):
    """
    SSE 流式查询接口
    实时推送 Agent 执行进度
    """
    async def event_stream():
        try:
            permission = UserPermission(request.user_permission)
        except ValueError:
            permission = UserPermission.LOW

        # 推送开始事件
        yield f"data: {json.dumps({'type': 'start', 'query': request.query})}\n\n"

        # 逐步执行并发送进度
        steps = [
            ("intent_recognition", "正在识别查询意图..."),
            ("permission_check", "正在校验用户权限..."),
            ("rag_retrieval", "正在检索知识库..."),
            ("sql_generation", "正在生成 SQL..."),
            ("sql_validation", "正在校验 SQL 安全性..."),
            ("sql_execution", "正在执行 SQL 查询..."),
            ("data_analysis", "正在进行数据分析..."),
            ("memory_update", "正在更新记忆库..."),
            ("report_generation", "正在生成分析报告..."),
        ]

        for step_name, step_desc in steps:
            yield f"data: {json.dumps({'type': 'progress', 'step': step_name, 'message': step_desc})}\n\n"
            await asyncio.sleep(0.3)

        # 执行完整工作流
        try:
            result = run_agent(
                query=request.query,
                user_id=request.user_id,
                user_permission=permission,
            )

            # 推送结果
            yield f"data: {json.dumps({
                'type': 'result',
                'success': not result.get('error_message'),
                'report': result.get('final_report', '无报告'),
                'sql': result.get('generated_sql', ''),
                'row_count': result.get('result_row_count', 0),
                'intent': result.get('intent', QueryIntent.GENERAL).value if isinstance(result.get('intent'), QueryIntent) else 'general',
            })}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history/{user_id}")
async def get_history(user_id: str, limit: int = 10):
    """获取用户查询历史"""
    memory = MemoryManager()
    # 从长期记忆中获取
    try:
        results = memory.long_term._collection.query(
            query_texts=[""],
            n_results=limit,
            where={"user_id": user_id} if user_id != "default" else None,
        )
        return {"history": results.get("metadatas", [[]])[0]}
    except Exception:
        return {"history": []}


@app.get("/api/domains")
async def get_domains():
    """获取所有业务域"""
    from app.agent.skill_router import SkillRouter
    router = SkillRouter()
    domains = {}
    for domain in router.get_all_domains():
        tables = router.get_tables_by_domain(domain)
        domains[domain] = {
            "tables": [t.table_name for t in tables],
            "table_count": len(tables),
        }
    return {"domains": domains}


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """启动服务器"""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
