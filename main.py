"""
TextSQL-Agent 主入口
企业级自助数据分析 Agent

用法:
    # 命令行模式
    python main.py "上月销售额最高的门店"

    # 交互模式
    python main.py --interactive

    # 启动 API 服务
    python main.py --server

    # 构建索引
    python main.py --build-index
"""
import sys
import os
import argparse

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import config
from app.utils.logger import setup_logger

logger = setup_logger()


def cmd_query(query: str, user_permission: str = "low"):
    """命令行查询"""
    from app.agent.workflow import run_agent
    from app.agent.state import UserPermission

    permission = UserPermission(user_permission)
    logger.info(f"用户查询: {query} (权限: {permission.value})")

    result = run_agent(query=query, user_permission=permission)

    print("\n" + "=" * 60)
    print("📊 分析报告")
    print("=" * 60)
    print(result.get("final_report", "无报告"))

    if result.get("error_message"):
        print(f"\n⚠️ 错误: {result['error_message']}")

    return result


def cmd_interactive():
    """交互模式"""
    print("\n" + "=" * 60)
    print("🔍 TextSQL-Agent 交互模式")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            query = input("❓ 请输入问题> ").strip()
            if query.lower() in ("quit", "exit", "q"):
                print("再见！👋")
                break
            if not query:
                continue

            cmd_query(query, "low")
            print()
        except KeyboardInterrupt:
            print("\n再见！👋")
            break
        except Exception as e:
            logger.error(f"查询失败: {e}")
            print(f"❌ 查询失败: {e}\n")


def cmd_server(port: int = 8000):
    """启动 API 服务"""
    logger.info(f"启动 API 服务，端口: {port}")
    print(f"\n🚀 TextSQL-Agent API 服务启动中...")
    print(f"   地址: http://localhost:{port}")
    print(f"   文档: http://localhost:{port}/docs")
    print(f"   前端: http://localhost:{port}/ 前端页面需配合 nginx 或直接打开 app/frontend/index.html\n")

    import uvicorn
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=port, reload=True)


def cmd_build_index():
    """构建 RAG 索引"""
    logger.info("开始构建 RAG 索引")
    print("\n📦 构建 RAG 索引...\n")

    # 元数据索引
    from app.rag.indexer import MetadataIndexer, MetricIndexer

    # 读取建表语句
    ddl_path = os.path.join(config.base_dir, "data", "sql", "init_database.sql")
    if os.path.exists(ddl_path):
        with open(ddl_path, "r", encoding="utf-8") as f:
            ddl_source = f.read()

        print("  构建元数据索引...")
        indexer = MetadataIndexer()
        count = indexer.build(ddl_source, force=True)
        print(f"  ✅ 元数据索引: {count} 个 chunk")
    else:
        print(f"  ⚠️ 未找到建表语句: {ddl_path}")

    # 指标索引
    metric_path = os.path.join(config.base_dir, "data", "docs", "metrics.md")
    if os.path.exists(metric_path):
        with open(metric_path, "r", encoding="utf-8") as f:
            doc_source = f.read()

        print("  构建指标索引...")
        indexer = MetricIndexer()
        count = indexer.build(doc_source, force=True)
        print(f"  ✅ 指标索引: {count} 个 chunk")
    else:
        print(f"  ⚠️ 未找到指标文档: {metric_path}")

    print("\n✅ 索引构建完成\n")


def cmd_run_tests():
    """运行测试"""
    import pytest
    sys.exit(pytest.main([os.path.join(config.base_dir, "tests"), "-v"]))


def main():
    parser = argparse.ArgumentParser(
        description="TextSQL-Agent | 企业级自助数据分析 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("query", nargs="?", help="直接查询")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互模式")
    parser.add_argument("-s", "--server", action="store_true", help="启动 API 服务")
    parser.add_argument("-p", "--port", type=int, default=8000, help="API 服务端口")
    parser.add_argument("-b", "--build-index", action="store_true", help="构建 RAG 索引")
    parser.add_argument("-t", "--test", action="store_true", help="运行测试")
    parser.add_argument("--permission", default="low", choices=["low", "medium", "high"], help="用户权限等级")

    args = parser.parse_args()

    if args.test:
        cmd_run_tests()
    elif args.build_index:
        cmd_build_index()
    elif args.server:
        cmd_server(args.port)
    elif args.interactive:
        cmd_interactive()
    elif args.query:
        cmd_query(args.query, args.permission)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
