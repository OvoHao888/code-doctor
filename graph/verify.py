"""执行式验证 —— 真的把修复后的代码跑一遍，用执行结果当裁判。

设计说明：
    原项目的 validate_fix_is_correct 只做 ast.parse —— **语法正确 ≠ 跑得起来**。
    更关键的是，让 LLM 自评"我修好了"存在确认偏误，它倾向于宣称成功。
    这里用真实的进程退出码和 stderr 作为判据，是**可证伪**的。

安全边界（诚实说明，见 README）：
    subprocess **不是安全边界**。这里做的是：
      - -I 隔离模式（忽略环境变量与用户 site-packages）
      - 独立临时工作目录（用户代码 import 不到本项目源码）
      - 硬超时
    它能防误伤，防不住蓄意逃逸。生产环境应放进一次性容器：
        docker run --rm --network none --read-only --memory 256m --pids-limit 64 ...
"""

import os
import subprocess
import sys
import tempfile
import time

from langchain_core.messages import AIMessage

from .state import VerifyResult

# 单次执行的最长耗时（秒）
EXEC_TIMEOUT = float(os.getenv("VERIFY_TIMEOUT", "5"))
# stdout/stderr 截断上限，避免恶意代码刷爆内存
MAX_OUTPUT = 2000


def execute_code(code: str, timeout: float = EXEC_TIMEOUT) -> VerifyResult:
    """在隔离的子进程里执行代码，返回可证伪的验证结果。"""
    started = time.time()

    if not code or not code.strip():
        return VerifyResult(passed=False, stderr="修复代码为空", duration=0.0)

    env = {
        # SYSTEMROOT 在 Windows 上必须保留，否则解释器可能无法启动
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }

    with tempfile.TemporaryDirectory() as workdir:
        try:
            proc = subprocess.run(
                # -I 隔离模式隐含 -E（忽略所有 PYTHON* 环境变量），所以编码必须用
                # 命令行开关 -X utf8 指定，而不能靠 PYTHONIOENCODING —— 否则用户代码
                # 一打印中文/emoji 就会因 GBK 编码失败，被误判成"修复失败"。
                [sys.executable, "-I", "-X", "utf8", "-c", code],
                cwd=workdir,
                capture_output=True,
                timeout=timeout,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return VerifyResult(
                passed=False,
                exit_code=None,
                stderr=f"执行超时（超过 {timeout}s），疑似死循环或阻塞调用",
                timed_out=True,
                duration=round(time.time() - started, 3),
            )
        except Exception as e:
            return VerifyResult(
                passed=False,
                stderr=f"无法执行代码：{e}",
                duration=round(time.time() - started, 3),
            )

    return VerifyResult(
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        stdout=proc.stdout.decode("utf-8", "replace")[:MAX_OUTPUT],
        stderr=proc.stderr.decode("utf-8", "replace")[:MAX_OUTPUT],
        timed_out=False,
        duration=round(time.time() - started, 3),
    )


def make_verify_node():
    """构造验证节点。纯代码，不调用 LLM。"""

    def verify(state) -> dict:
        result = execute_code(state.fixed_code)

        if result.passed:
            summary = f"【执行验证通过】退出码 0，耗时 {result.duration}s"
        else:
            summary = f"【执行验证失败】{result.feedback()}"

        updates = {
            "verification": result,
            "messages": [AIMessage(content=summary)],
        }

        # 失败时把执行反馈写回，供下一轮修复参考 —— 否则重试会产出完全相同的代码而空转
        if not result.passed:
            updates["verify_feedback"] = result.feedback()

        return updates

    return verify
