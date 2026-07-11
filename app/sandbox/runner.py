"""
沙盒安全工具
"""
import os
import sys
import subprocess
import tempfile
from typing import Any


class SandboxRunner:
    """
    代码沙盒执行器
    - 资源限制：CPU、内存、时间
    - 网络隔离
    - 文件系统隔离
    """

    def __init__(self, use_docker: bool = True):
        self.use_docker = use_docker

    def run_code(self, code: str, timeout: int = 30) -> dict[str, Any]:
        """执行 Python 代码"""
        if self.use_docker:
            return self._run_docker(code, timeout)
        return self._run_local(code, timeout)

    def _run_docker(self, code: str, timeout: int) -> dict[str, Any]:
        """Docker 隔离执行"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            script_path = f.name

        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--cpus", "1.0",
                    "--memory", "512m",
                    "--memory-swap", "512m",
                    "--read-only",
                    "--tmpfs", "/tmp:rw,size=64m",
                    "-v", f"{script_path}:/app/script.py:ro",
                    "python-sandbox:latest",
                    "python", "/app/script.py",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": f"执行超时（{timeout}秒）"}
        except FileNotFoundError:
            return self._run_local(code, timeout)
        finally:
            os.unlink(script_path)

    def _run_local(self, code: str, timeout: int) -> dict[str, Any]:
        """本地受限执行（降级方案）"""
        # 禁用危险模块
        restricted_globals = {
            "__builtins__": {
                **{k: v for k, v in __builtins__.__dict__.items()
                   if k not in ("__import__", "open", "exec", "eval", "compile")},
                "__import__": _restricted_import,
            }
        }

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured = tempfile.StringIO()
        sys.stderr = captured_err = tempfile.StringIO()

        try:
            exec(code, restricted_globals)
            return {
                "success": True,
                "stdout": captured.getvalue(),
                "stderr": captured_err.getvalue(),
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": captured.getvalue(),
                "stderr": str(e),
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


# 安全模块白名单
_ALLOWED_MODULES = {
    "math", "statistics", "json", "datetime", "collections",
    "itertools", "functools", "pandas", "numpy", "matplotlib",
    "re", "csv", "io",
}

_BLOCKED_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "http",
    "urllib", "requests", "ftplib", "smtplib", "telnetlib",
    "pickle", "shelve", "marshal", "ctypes",
}


def _restricted_import(name: str, *args, **kwargs):
    """受限的 import 函数"""
    top = name.split('.')[0]
    if top in _BLOCKED_MODULES:
        raise ImportError(f"模块 '{name}' 在沙盒中被禁止")
    if top not in _ALLOWED_MODULES:
        raise ImportError(f"模块 '{name}' 不在白名单中")
    return __builtins__.__import__(name, *args, **kwargs)
