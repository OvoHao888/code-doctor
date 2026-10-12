"""确定性静态分析 —— 用代码出事实，不用 LLM。

设计说明：
    这一层刻意只做**低误报**的检查。原项目 tools/code_tools.py 里的
    find_logic_error 对每一个下标访问、属性访问、函数参数都报"可能越界/可能为 None"，
    几乎任何真实代码都会吐出一大串 —— 精确率低到无法用于评测（会拖垮 precision）。
    与其让 LLM 在一堆噪声里挑，不如只喂高置信度的事实。
"""

import ast
import os
from typing import List

from pyflakes.api import check as pyflakes_check
from pyflakes.reporter import Reporter
from langchain_core.messages import AIMessage


class _CollectingReporter(Reporter):
    """把 pyflakes 的输出收集到列表里。

    不能用 sys.stdout 重定向 —— 那是进程级全局状态，FastAPI 并发请求下会串台
    （A 请求的诊断结果跑到 B 请求的响应里）。
    """

    def __init__(self):
        self.messages: List[str] = []

    def flake(self, message):
        self.messages.append(str(message))

    def unexpectedError(self, filename, msg):
        self.messages.append(str(msg))

    def syntaxError(self, filename, msg, lineno, offset, text):
        self.messages.append(f"语法错误 行{lineno}: {msg}")


def run_pyflakes(code: str) -> List[str]:
    """语法 / 未定义名 / 未使用导入等。"""
    reporter = _CollectingReporter()
    pyflakes_check(code, "<submitted>", reporter=reporter)
    return reporter.messages


def _line(node) -> int:
    return getattr(node, "lineno", 0)


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def run_logic_checks(tree: ast.AST) -> List[str]:
    """聚焦的高置信度逻辑检查。每条都要求明确证据，避免大面积误报。"""
    findings: List[str] = []

    # 已被显式零值守卫保护过的变量名（如 if b == 0: raise ...），不再重复报警
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
            isinstance(c, ast.Constant) and c.value == 0 for c in node.comparators
        ):
            if isinstance(node.left, ast.Name):
                guarded.add(node.left.id)

    # 1) 除零风险：除数是可以静态断定的 0 或 len()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            right = node.right
            if isinstance(right, ast.Constant) and right.value == 0:
                findings.append(f"行{_line(node)}: 除数为字面量 0，必然抛出除零错误")
            elif isinstance(right, ast.Call) and isinstance(right.func, ast.Name) and right.func.id == "len":
                findings.append(f"行{_line(node)}: 以 len() 结果为除数，当序列为空时除零")
            elif isinstance(right, ast.Name) and right.id not in guarded:
                findings.append(
                    f"行{_line(node)}: 以变量 '{right.id}' 为除数，调用方可能传入 0，缺少入参校验"
                )

    # 2) 可变对象作默认参数（Python 经典陷阱）
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        f"行{_line(node)}: 函数 '{node.name}' 使用可变对象作默认参数，"
                        f"多次调用会共享同一份状态"
                    )

    # 3) 裸 except / 静默吞异常
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(f"行{node.lineno}: 裸 except 会吞掉所有异常（含 KeyboardInterrupt）")
            elif node.body and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(f"行{node.lineno}: except 块为空 pass，异常被静默忽略")

    # 4) 资源泄漏：open() 未使用 with
    inside_with = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for child in ast.walk(node):
                inside_with.add(id(child))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            if id(node) not in inside_with:
                findings.append(f"行{_line(node)}: open() 未使用 with 上下文管理器，异常时文件句柄泄漏")

    # 5) while True 无退出路径
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            test = node.test
            is_true = isinstance(test, ast.Constant) and test.value is True
            has_exit = any(isinstance(n, (ast.Break, ast.Return)) for n in ast.walk(node))
            if is_true and not has_exit:
                findings.append(f"行{node.lineno}: while True 内没有 break/return，存在死循环风险")

    return findings


def collect_evidence(code: str) -> str:
    """汇总所有确定性分析结果，供 LLM 判断时参考。"""
    parts: List[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"[语法分析]\n无法解析：行{e.lineno}: {e.msg}\n（代码存在语法错误，后续检查已跳过）"

    # 代码规模
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    parts.append(f"[代码规模]\n行数: {len(code.splitlines())} | 函数: {', '.join(funcs) if funcs else '无'}")

    # pyflakes
    flakes = run_pyflakes(code)
    if flakes:
        parts.append("[静态检查 pyflakes]\n" + "\n".join(f"- {m}" for m in flakes))

    # 逻辑检查
    logic = run_logic_checks(tree)
    if logic:
        parts.append("[逻辑风险检查]\n" + "\n".join(f"- {m}" for m in logic))

    if len(parts) == 1:
        parts.append("[静态检查]\n未发现明显问题")

    return "\n\n".join(parts)


def make_analyze_node(rag_search=None):
    """构造分析节点。

    rag_search: 可选的可调用对象 (query: str) -> str，用于注入 RAG 检索结果。
                消融实验通过传 None 来关闭 RAG。
    """

    def analyze(state) -> dict:
        code = state.code
        evidence = collect_evidence(code)

        if rag_search is not None:
            # 检索 query 的构造方式（RAG_QUERY_MODE）：
            #   enriched（默认）：错误信息 + 静态分析发现的问题 + 代码。
            #     直接把代码丢去检索时，代码与知识库里的中文叙述语义距离很远，
            #     实测相关性差（相关块的距离排在无关块之后）。
            #   code：仅用原始代码 —— 保留此模式是为了消融实验能隔离"query 构造"
            #     这一个变量，避免一次改两处导致结果无法归因。
            if os.getenv("RAG_QUERY_MODE", "enriched") == "code":
                query = code
            else:
                query_parts = []
                if state.error:
                    query_parts.append(state.error.strip())
                if _parses(code):
                    query_parts.extend(run_logic_checks(ast.parse(code)))
                query_parts.append(code)
                query = "\n".join(query_parts)

            try:
                retrieved = rag_search(query)
                if retrieved:
                    evidence += f"\n\n[知识库检索]\n{retrieved}"
            except Exception as e:
                evidence += f"\n\n[知识库检索]\n检索失败（不影响分析）：{e}"

        return {
            "evidence": evidence,
            "messages": [AIMessage(content="【静态分析完成】\n" + evidence)],
        }

    return analyze
