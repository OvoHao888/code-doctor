"""评测 harness —— 批量跑数据集，输出可量化的指标。

用法：
    python eval/run_eval.py --rag on            # 完整评测
    python eval/run_eval.py --rag off           # 消融：关闭 RAG
    python eval/run_eval.py --limit 5           # 只跑前 5 条（快速冒烟）
    python eval/run_eval.py --validate-dataset  # 只校验数据集本身

指标说明：
    只报召回率会被一句"那我全报 bug 不就 100% 了"问倒。所以同时报：
      - 召回率 recall     ：标注的问题中被检出的比例
      - 精确率 precision  ：报出的问题中真实存在的比例
      - F1                ：两者的调和平均，作为主指标
      - 误报率 fpr        ：**干净样本**上被误报的比例（防"永远报 bug"）
      - 修复成功率        ：修复后代码拼上隐藏断言能执行通过的比例
    判定"修复成功"用的是隐藏断言而非"退出码 0"—— 否则 return / pass 空实现也能拿满分。
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from graph import build_workflow  # noqa: E402
from graph.verify import execute_code  # noqa: E402

# 问题类型的别名映射：LLM 输出的类型描述往往比标注更啰嗦
TYPE_ALIASES = {
    "除零": ["除零", "zero", "division", "取模", "modulo"],
    "索引越界": ["索引", "越界", "index"],
    "空值解引用": ["空值", "none", "attribute", "typeerror", "解引用", "null", "未定义"],
    "可变默认参数": ["可变", "默认参数", "mutable", "default"],
    "资源泄漏": ["资源", "泄漏", "leak", "未关闭", "with"],
    "裸except": ["裸", "except", "吞", "静默"],
    "死循环": ["死循环", "无限循环", "infinite", "while"],
}

LINE_TOLERANCE = 3


def run_static_check(kind: str, code: str) -> bool:
    """非崩溃类缺陷的静态判据 —— 光执行代码无法区分修没修。"""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    if kind == "no_bare_except":
        return not any(
            isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree)
        )

    if kind == "uses_with_open":
        inside_with = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.With):
                for c in ast.walk(n):
                    inside_with.add(id(c))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
                if id(n) not in inside_with:
                    return False
        return True

    return True


def judge(sample, code: str) -> bool:
    """判定一份代码是否算"修复正确"：执行断言通过 + 可选的静态判据通过。"""
    if not execute_code(code + "\n" + sample["assertions"]).passed:
        return False
    static_kind = sample.get("static_check")
    if static_kind and not run_static_check(static_kind, code):
        return False
    return True


def type_matches(expected: str, predicted: str) -> bool:
    pred = (predicted or "").lower()
    aliases = TYPE_ALIASES.get(expected, [expected.lower()])
    return any(a in pred for a in aliases)


def match_bugs(expected_pairs, predicted_bugs):
    """返回 (tp, fp, fn)。匹配规则：类型一致 且 行号在容差内。

    行号容差是必要的：同一个 bug，LLM 可能标在 def 行、return 行或调用行。
    """
    used = set()
    tp = 0
    for e_line, e_type in expected_pairs:
        for i, bug in enumerate(predicted_bugs):
            if i in used:
                continue
            b_line = bug["line"] if isinstance(bug, dict) else bug.line
            b_type = bug["type"] if isinstance(bug, dict) else bug.type
            if abs(b_line - e_line) <= LINE_TOLERANCE and type_matches(e_type, b_type):
                used.add(i)
                tp += 1
                break
    fp = len(predicted_bugs) - len(used)
    fn = len(expected_pairs) - tp
    return tp, fp, fn


def validate_dataset(dataset) -> bool:
    """数据集自检：正样本的隐藏断言必须在**原始有 bug 代码**上失败。

    否则断言没有区分度（无论修没修都通过），修复成功率这个指标就是假的。
    """
    print("校验数据集...")
    ok = True
    for sample in dataset:
        if not sample["has_bug"]:
            continue
        if judge(sample, sample["code"]):
            print(f"  [警告] {sample['id']}: 判据在原始有 bug 代码上就通过了，无区分度")
            ok = False
    print("数据集校验通过\n" if ok else "数据集存在问题\n")
    return ok


async def run_one(sample, workflow, sem):
    async with sem:
        started = time.time()
        try:
            result = await workflow.ainvoke(
                {
                    "code": sample["code"],
                    "error": sample.get("error", ""),
                    "messages": [{"role": "user", "content": sample["code"]}],
                },
                config={"recursion_limit": 25},
            )
        except Exception as e:
            return {"id": sample["id"], "error": f"{type(e).__name__}: {e}"}

        return {
            "id": sample["id"],
            "category": sample["category"],
            "has_bug_expected": sample["has_bug"],
            "has_bug_predicted": bool(result["bug_report"].has_bug) if result.get("bug_report") else False,
            "predicted_bugs": [b.model_dump() for b in (result["bug_report"].bugs if result.get("bug_report") else [])],
            "expected_pairs": list(zip(sample["lines"], sample["types"]))
            if sample["has_bug"]
            else [],
            "fixed_code": result.get("fixed_code", ""),
            "verify_passed": bool(result["verification"].passed) if result.get("verification") else False,
            "fix_attempts": result.get("fix_attempts", 0),
            "duration": round(time.time() - started, 2),
            "tokens": result.get("total_tokens", 0),
            "llm_calls": result.get("llm_calls", 0),
        }


def evaluate_outcome(sample, row) -> bool:
    """修复成功 = 修复后代码通过隐藏断言（+ 静态判据）。

    干净样本不进入修复流程，用原始代码判断。
    """
    code = row.get("fixed_code") or sample["code"]
    return judge(sample, code)


async def run_dataset(dataset, workflow, concurrency: int = 3, progress: bool = True):
    """并发跑完整个数据集，返回与 dataset 顺序一致的明细列表。

    注意这里不用 `for ... await run_one(...)`：`await` 出现在循环体里意味着每个样本
    都要等上一个结束才开始，Semaphore 形同虚设，`--concurrency N` 与 1 没有区别。
    改成 asyncio.gather 之后，真实并发度才等于 concurrency；用下标回填保证 rows 的
    顺序仍然与 dataset 一一对应，下游按 zip(dataset, rows) 取数不受影响。
    """
    sem = asyncio.Semaphore(concurrency)
    rows: List[Optional[dict]] = [None] * len(dataset)

    async def run_slot(i: int, sample) -> dict:
        row = await run_one(sample, workflow, sem)
        rows[i] = row
        if progress:
            status = "ERR" if "error" in row else ("BUG" if row["has_bug_predicted"] else "clean")
            print(f"  [{i + 1}/{len(dataset)}] {sample['id']:<28} {status:<5} {row.get('duration', 0)}s")
        return row

    await asyncio.gather(*(run_slot(i, s) for i, s in enumerate(dataset)))
    return rows


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rag", choices=["on", "off"], default="on")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--out", default="")
    parser.add_argument("--validate-dataset", action="store_true")
    args = parser.parse_args()

    from eval.dataset import DATASET

    dataset = DATASET[: args.limit] if args.limit else DATASET

    if args.validate_dataset:
        validate_dataset(dataset)
        return

    os.environ["RAG_ENABLED"] = "1" if args.rag == "on" else "0"

    from langchain_openai import ChatOpenAI
    from rag.bugrag import make_rag_search

    model = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek-v4.1-flash"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        temperature=0,
    )
    rag_search = make_rag_search() if args.rag == "on" else None
    if args.rag == "on" and rag_search is None:
        print("警告: RAG 开启但向量库不可用，将退化为无检索\n")

    workflow = build_workflow(model, rag_search=rag_search)

    print(f"运行评测: RAG={args.rag} | 样本数={len(dataset)} | 并发={args.concurrency}\n")

    rows = await run_dataset(dataset, workflow, args.concurrency)

    # —— 汇总指标 ——
    positives = [(s, r) for s, r in zip(dataset, rows) if s["has_bug"]]
    negatives = [(s, r) for s, r in zip(dataset, rows) if not s["has_bug"]]

    tp = fp = fn = 0
    fix_ok = 0
    for s, r in positives:
        if "error" in r:
            fn += len(s["lines"])
            continue
        t, f, n = match_bugs(r["expected_pairs"], r["predicted_bugs"])
        tp += t
        fp += f
        fn += n
        if evaluate_outcome(s, r):
            fix_ok += 1

    tn = sum(1 for _, r in negatives if not r.get("has_bug_predicted"))
    neg_fp = len(negatives) - tn

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = neg_fp / len(negatives) if negatives else 0.0
    fix_rate = fix_ok / len(positives) if positives else 0.0

    durations = [r["duration"] for r in rows if "error" not in r]
    tokens = [r["tokens"] for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]

    print("\n" + "=" * 56)
    print(f"评测结果  (RAG={args.rag})")
    print("=" * 56)
    print(f"样本总数            {len(dataset)}  (正样本 {len(positives)} / 负样本 {len(negatives)})")
    print(f"检测召回率 recall   {recall:.1%}   ({tp}/{tp + fn})")
    print(f"检测精确率 precis   {precision:.1%}   (TP {tp} / FP {fp})")
    print(f"检测 F1             {f1:.1%}   <- 主指标")
    print(f"干净样本误报率 fpr  {fpr:.1%}   ({neg_fp}/{len(negatives)})")
    print(f"修复成功率          {fix_rate:.1%}   ({fix_ok}/{len(positives)})")
    if durations:
        print(f"平均耗时            {statistics.mean(durations):.1f}s  (中位 {statistics.median(durations):.1f}s)")
        print(f"平均 token          {statistics.mean(tokens):.0f}")
    if errors:
        print(f"执行异常样本        {len(errors)}: {[e['id'] for e in errors]}")

    out = args.out or f"eval/results/{args.rag}_{int(time.time())}.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "rag": args.rag,
                "metrics": {
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "false_positive_rate": fpr,
                    "fix_success_rate": fix_rate,
                    "n_samples": len(dataset),
                },
                "rows": rows,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n明细已保存: {out}")


if __name__ == "__main__":
    asyncio.run(main())
