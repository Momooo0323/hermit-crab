"""
工具：执行 shell 命令（exec）
"""

import subprocess
import shlex
from app.tools import register


# 危险命令片段黑名单
_DANGEROUS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf .",
    "format ", "mkfs", "dd if=", ">:",
    "del /f /s", "rd /s /q",
    "shutdown", "reboot", "init 0",
    "chmod -R 777 /", "chmod 777 /",
    ":(){ :|:& };:",  # fork bomb
]


def _is_dangerous(cmd: str) -> bool:
    cmd_lower = cmd.lower()
    for pattern in _DANGEROUS:
        if pattern.lower() in cmd_lower:
            return True
    return False


@register(name="shell_exec", icon="⚡",
          keywords=["执行", "运行", "终端", "命令", "cmd", "shell"],
          description="在系统终端执行 shell 命令并返回输出结果。参数 command 为要执行的命令，workdir 可选工作目录，timeout 可选超时秒数（默认 30）。注意：高危命令会被拦截。")
def shell_exec(app, command: str, workdir: str = "", timeout: int = 30) -> str:
    """执行 shell 命令，返回 stdout + stderr。"""
    if not command or not command.strip():
        return "[错误] 命令不能为空"

    if _is_dangerous(command):
        return "[拦截] 命令被判定为高危操作，已阻止执行。"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir if workdir else None,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        rc = result.returncode

        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        parts.append(f"\n➜ 退出码: {rc}")

        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"[超时] 命令执行超过 {timeout} 秒，已终止。"
    except Exception as e:
        return f"[执行错误] {e}"
