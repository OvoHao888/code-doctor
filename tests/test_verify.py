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

# —— 临时目录异常不得影响验证结论 ——
#
# 背景：TemporaryDirectory 的清理在 __exit__ 里执行（shutil.rmtree → _resetperms → chmod）。
# 在杀毒软件占用文件、受限令牌或权限异常的临时目录下，这一步会抛 PermissionError。
# 如果让它向外抛，异常会一路穿到 FastAPI，调用方看到的是"检查代码失败"，
# 而真实语义只是"代码没跑通"——两者完全不同。


def test_临时目录清理失败不改变验证结论(monkeypatch):
    """清理失败只能记日志：代码本身跑通了，结论就必须是通过。"""
    import tempfile

    import graph.verify as verify

    holder = {}

    class CleanupFails:
        def __init__(self, *args, **kwargs):
            if "dir" not in holder:
                holder["dir"] = tempfile.mkdtemp(prefix="verify-cleanup-fail-")
            self.name = holder["dir"]

        def __enter__(self):
            return self.name

        def __exit__(self, *exc):
            raise PermissionError("模拟临时目录清理失败（chmod 被拒绝）")

    monkeypatch.setattr(verify.tempfile, "TemporaryDirectory", CleanupFails)

    r = verify.execute_code("print(1 + 1)")

    assert r is not None, "清理失败不应让 execute_code 抛异常"
    assert r.passed is True, "代码本身执行成功，结论必须保持通过"
    assert r.exit_code == 0
    assert "2" in r.stdout, "输出也应完整保留"


def test_临时目录创建失败时如实报告无法执行(monkeypatch):
    """连临时目录都建不出来时，应返回"无法执行"，而不是抛异常。"""
    import graph.verify as verify

    class EnterFails:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise PermissionError("模拟无法创建临时目录")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(verify.tempfile, "TemporaryDirectory", EnterFails)

    r = verify.execute_code("print(1)")

    assert r.passed is False
    assert "无法执行代码" in r.stderr
