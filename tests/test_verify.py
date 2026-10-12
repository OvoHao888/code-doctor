"""执行式验证单测 —— 真实起子进程，覆盖通过/失败/超时/空代码。"""

from graph.verify import execute_code


def test_正常代码_通过():
    r = execute_code("print(1 + 1)")
    assert r.passed is True
    assert r.exit_code == 0
    assert "2" in r.stdout


def test_运行时异常_失败且能拿到stderr():
    r = execute_code("print(1 / 0)")
    assert r.passed is False
    assert r.exit_code == 1
    assert "ZeroDivisionError" in r.stderr


def test_语法错误_失败():
    r = execute_code("def f(: pass")
    assert r.passed is False
    assert r.exit_code != 0


def test_超时被截断():
    """死循环必须被硬超时掐掉，不能挂住整个服务。"""
    r = execute_code("while True: pass", timeout=1.5)
    assert r.passed is False
    assert r.timed_out is True
    assert r.duration < 5


def test_空代码不通过():
    assert execute_code("").passed is False
    assert execute_code("   \n  ").passed is False


def test_中文与emoji输出不因编码失败():
    """子进程必须显式用 UTF-8，否则 Windows GBK 下会误判成执行失败。"""
    r = execute_code('print("中文输出 ✅")')
    assert r.passed is True
    assert "中文输出" in r.stdout


def test_在隔离目录执行_无法导入本项目模块():
    """cwd 是独立临时目录，用户代码不应能 import 到项目源码。"""
    r = execute_code("import graph")
    assert r.passed is False
    assert "ModuleNotFoundError" in r.stderr
