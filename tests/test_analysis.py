"""静态分析单测 —— 重点覆盖「真阳性」与「不误报」两侧。

不误报和检出同样重要：检测器若对干净代码也乱报，评测里的精确率会崩，
消融实验的结论也就不可信了。
"""

import ast

from graph.analysis import collect_evidence, run_logic_checks


def _findings(code: str):
    return run_logic_checks(ast.parse(code))


def _has(code: str, keyword: str) -> bool:
    return any(keyword in f for f in _findings(code))


# —— 真阳性 ——

def test_检出字面量除零():
    assert _has("x = 10 / 0", "必然抛出除零错误")


def test_检出len作除数():
    assert _has("def avg(xs):\n    return sum(xs) / len(xs)", "除零")


def test_检出未校验的变量除数():
    assert _has("def d(a, b):\n    return a / b", "缺少入参校验")


def test_检出可变默认参数():
    assert _has("def f(items=[]):\n    items.append(1)", "可变对象作默认参数")


def test_检出裸except():
    assert _has("try:\n    pass\nexcept:\n    pass", "裸 except")


def test_检出while_true死循环():
    assert _has("while True:\n    print(1)", "死循环")


def test_检出open未使用with():
    assert _has("f = open('a.txt')\nx = f.read()", "句柄泄漏")


# —— 不误报（精确率保障）——

def test_已有零值守卫的不报警():
    """已经 if b == 0: raise 保护过的除零，不应重复报警。"""
    code = "def d(a, b):\n    if b == 0:\n        raise ValueError('zero')\n    return a / b"
    assert not _has(code, "缺少入参校验")


def test_使用with的不报资源泄漏():
    code = "with open('a.txt') as f:\n    x = f.read()"
    assert not _has(code, "句柄泄漏")


def test_正常变量运算不报警():
    assert _findings("def d(a, b):\n    if b == 0:\n        raise ValueError\n    return a / b") == []


def test_干净代码无任何发现():
    code = "def add(a, b):\n    return a + b\n\nprint(add(1, 2))"
    assert _findings(code) == []


# —— 证据汇总 ——

def test_语法错误时给出明确提示():
    ev = collect_evidence("def f(: pass")
    assert "无法解析" in ev


def test_证据包含代码规模():
    ev = collect_evidence("def foo():\n    pass")
    assert "[代码规模]" in ev and "foo" in ev
