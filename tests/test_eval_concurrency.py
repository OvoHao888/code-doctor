"""评测并发执行的回归测试。

原实现是 `for ... await run_one(...)`：`await` 写在循环体里，等价于串行执行，
`--concurrency` 参数完全不起作用。这组测试用假的 run_one（纯 sleep，不调用任何模型、
不花 token）把并发行为钉住：
  - 6 条各 0.2 秒的样本，3 路并发应约 0.4 秒，而串行需要 1.2 秒
  - 同时运行的任务数不得超过 concurrency
"""

import asyncio
import time

import eval.run_eval as run_eval


def test_并发跑数据集_总耗时接近单条而不是累加(monkeypatch):
    async def fake_run_one(sample, workflow, sem):
        async with sem:
            await asyncio.sleep(0.2)
        return {"id": sample["id"], "has_bug_predicted": False, "duration": 0.2}

    monkeypatch.setattr(run_eval, "run_one", fake_run_one)

    samples = [{"id": f"s{i}"} for i in range(6)]
    started = time.time()
    rows = asyncio.run(
        run_eval.run_dataset(samples, workflow=None, concurrency=3, progress=False)
    )
    elapsed = time.time() - started

    assert len(rows) == 6, "结果条数应与样本数一致"
    assert [r["id"] for r in rows] == [s["id"] for s in samples], "结果顺序必须与数据集一致"
    # 串行需要 6 × 0.2 = 1.2 秒；并发 3 路约 0.4 秒。留足容差，只要证明不是串行即可。
    assert elapsed < 0.8, f"仍然是串行执行：耗时 {elapsed:.2f}s"


def test_并发度不超过指定值(monkeypatch):
    """同时运行的任务数必须受 Semaphore 约束，且确实发生了并发。"""
    running = 0
    peak = 0

    async def fake_run_one(sample, workflow, sem):
        nonlocal running, peak
        async with sem:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.1)
            running -= 1
        return {"id": sample["id"], "has_bug_predicted": False, "duration": 0.1}

    monkeypatch.setattr(run_eval, "run_one", fake_run_one)

    samples = [{"id": f"s{i}"} for i in range(8)]
    asyncio.run(
        run_eval.run_dataset(samples, workflow=None, concurrency=2, progress=False)
    )

    assert peak <= 2, f"并发度超过上限：峰值 {peak}"
    assert peak == 2, f"没有真正并发：峰值仅 {peak}"
