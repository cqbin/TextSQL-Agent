"""
Python 数据分析工具
在 Docker 沙盒中隔离执行数据分析代码
"""
import json
import subprocess
import tempfile
import os
from typing import Any, Optional

from app.config import config


class AnalysisTool:
    """
    数据分析工具
    - 在隔离的 Docker 容器中执行 Python 代码
    - 禁用网络，限制 CPU/内存
    - 支持生成图表、计算环比同比、统计摘要
    """

    def __init__(self, use_docker: bool = True):
        self.use_docker = use_docker

    def execute(self, code: str, data: list[dict] = None) -> dict[str, Any]:
        """
        执行 Python 分析代码
        code: Python 代码字符串
        data: SQL 查询结果数据（通过 JSON 注入到代码中）
        """
        if self.use_docker:
            return self._execute_in_docker(code, data)
        else:
            return self._execute_local(code, data)

    def _execute_in_docker(self, code: str, data: Optional[list[dict]]) -> dict[str, Any]:
        """在 Docker 沙盒中执行"""
        # 将数据注入代码
        data_json = json.dumps(data or [], ensure_ascii=False)
        full_code = f"""
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 注入查询结果数据
query_data = json.loads('''{data_json}''')
df = pd.DataFrame(query_data)

# 用户代码开始
{code}
# 用户代码结束
"""

        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_code)
            script_path = f.name

        try:
            # Docker 执行
            cmd = [
                "docker", "run", "--rm",
                "--network", "none",  # 禁用网络
                "--cpus", config.sandbox.cpu_limit,
                "--memory", config.sandbox.memory_limit,
                "-v", f"{script_path}:/app/script.py:ro",
                "-v", f"{os.path.dirname(script_path)}:/app/output",
                config.sandbox.docker_image,
                "python", "/app/script.py",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=config.sandbox.timeout,
            )

            if result.returncode == 0:
                # 解析输出
                output = result.stdout
                charts = self._extract_charts(output, os.path.dirname(script_path))
                return {
                    "success": True,
                    "output": output,
                    "charts": charts,
                    "error": "",
                }
            else:
                return {
                    "success": False,
                    "output": result.stdout,
                    "charts": [],
                    "error": result.stderr,
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "charts": [],
                "error": f"执行超时（{config.sandbox.timeout}秒）",
            }
        except FileNotFoundError:
            # Docker 不可用，降级为本地执行
            print("[AnalysisTool] Docker 不可用，降级为本地执行")
            return self._execute_local(code, data)
        finally:
            # 清理临时文件
            if os.path.exists(script_path):
                os.unlink(script_path)

    def _execute_local(self, code: str, data: Optional[list[dict]]) -> dict[str, Any]:
        """本地执行（降级方案）"""
        data_json = json.dumps(data or [], ensure_ascii=False)
        full_code = f"""
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

query_data = json.loads('''{data_json}''')
df = pd.DataFrame(query_data)

{code}
"""

        # 本地命名空间
        local_ns: dict = {}
        try:
            exec(full_code, {"__builtins__": __builtins__}, local_ns)
            output = local_ns.get("result_text", "执行完成")
            charts = local_ns.get("chart_files", [])
            return {
                "success": True,
                "output": str(output),
                "charts": charts,
                "error": "",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "charts": [],
                "error": str(e),
            }

    def _extract_charts(self, output: str, output_dir: str) -> list[str]:
        """提取生成的图表文件路径"""
        charts = []
        for line in output.split('\n'):
            if line.strip().startswith('CHART:'):
                chart_path = line.strip()[6:].strip()
                charts.append(chart_path)
        return charts

    def generate_analysis_code(self, query: str, data: list[dict], intent: str) -> str:
        """
        根据查询意图自动生成分析代码
        """
        if intent == "sales":
            return self._sales_analysis_code(query)
        elif intent == "inventory":
            return self._inventory_analysis_code(query)
        elif intent == "finance":
            return self._finance_analysis_code(query)
        else:
            return self._general_analysis_code(query)

    def _sales_analysis_code(self, query: str) -> str:
        return f'''
# 销售数据分析
print("查询: {query}")
print(f"数据量: {{len(df)}} 行")

if not df.empty:
    # 基础统计
    numeric_cols = df.select_dtypes(include=['number']).columns
    if len(numeric_cols) > 0:
        print("\\n--- 数值统计 ---")
        print(df[numeric_cols].describe())

    # 如果有时间列，做趋势分析
    time_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()]
    if time_cols and len(numeric_cols) > 0:
        print(f"\\n--- 按时间趋势 ---")
        df[time_cols[0]] = pd.to_datetime(df[time_cols[0]])
        df.groupby(time_cols[0])[numeric_cols[0]].sum().plot(kind='line')
        plt.title('销售趋势')
        plt.savefig('/app/output/sales_trend.png')
        print('CHART:/app/output/sales_trend.png')

result_text = "销售数据分析完成"
'''

    def _inventory_analysis_code(self, query: str) -> str:
        return f'''
# 库存分析
print("查询: {query}")
print(f"数据量: {{len(df)}} 行")

if not df.empty:
    numeric_cols = df.select_dtypes(include=['number']).columns
    if len(numeric_cols) > 0:
        print("\\n--- 库存统计 ---")
        print(df[numeric_cols].describe())

    # 库存预警
    if 'stock_quantity' in df.columns and 'safety_stock' in df.columns:
        low_stock = df[df['stock_quantity'] < df['safety_stock']]
        if not low_stock.empty:
            print(f"\\n--- 库存预警: {{len(low_stock)}} 条低于安全库存 ---")
            print(low_stock)
        else:
            print("\\n所有库存充足")

result_text = "库存分析完成"
'''

    def _finance_analysis_code(self, query: str) -> str:
        return f'''
# 财务分析
print("查询: {query}")
print(f"数据量: {{len(df)}} 行")

if not df.empty:
    numeric_cols = df.select_dtypes(include=['number']).columns
    if len(numeric_cols) > 0:
        print("\\n--- 财务统计 ---")
        print(df[numeric_cols].describe())

    # 毛利率分析
    if 'profit_margin' in df.columns:
        print("\\n--- 毛利率分析 ---")
        print(f"平均毛利率: {{df['profit_margin'].mean():.2%}}")
        print(f"最高毛利率: {{df['profit_margin'].max():.2%}}")
        print(f"最低毛利率: {{df['profit_margin'].min():.2%}}")

result_text = "财务分析完成"
'''

    def _general_analysis_code(self, query: str) -> str:
        return f'''
# 通用数据分析
print("查询: {query}")
print(f"数据量: {{len(df)}} 行")

if not df.empty:
    print("\\n--- 数据概览 ---")
    print(df.head(10))
    print(f"\\n总行数: {{len(df)}}")
    print(f"列: {{list(df.columns)}}")

    numeric_cols = df.select_dtypes(include=['number']).columns
    if len(numeric_cols) > 0:
        print("\\n--- 数值统计 ---")
        print(df[numeric_cols].describe())

result_text = "数据分析完成"
'''
