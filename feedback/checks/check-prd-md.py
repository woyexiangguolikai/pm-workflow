#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02 PRD 质量检查器（Markdown 单文档形态）
=========================================
实现 02-prd rubric 的 A 类判据 —— 可脚本化、必须自动判、不许推给人。

用法:
    python check-prd-md.py <PRD.md> [--json <输出路径>]
    python check-prd-md.py --selftest        # 变异测试：证明检查有判别力

判据:
    A1  功能需求编号连续且唯一，总数与文档自述一致
    A2  需求描述列使用 EARS 句式（含模态词）
    A3  每条功能需求三列非空（需求描述 / 业务规则 / 验收标准）
    A4  验收标准列含 Given / When / Then 三段
    A5  功能需求章节不出现字段名 / 表名（snake_case 泄漏）
    A6  每条需求可追溯（[Dxx]/[Rxx]/[Mx] 或显式标注「本文档新增」）

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么要有这个文件
------------------
pm-workflow 原有的 check 全是「结构自洽性」检查（json↔html 一致、锚点可对齐）。
它们保证「不崩」，不保证「好」—— 一份平庸但格式完整的 PRD 能全绿通过。
本脚本补的是「内容最低标准」这一层：能自动判的绝不推给人。
判不了的（如论证是否有说服力）才留给 B 类自评 + 人评。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MODALS = ("必须", "应该", "可以", "禁止")
FIELD_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
TRACE_RE = re.compile(r"\[[DRM]\d+\]|本文档新增")


def _collect_rows(lines: list[str], start: int, end: int) -> list[dict]:
    """抓取形如 `| FR-xx | ... |` 的功能需求行。"""
    rows = []
    for i in range(start, end):
        m = re.match(r"^\|\s*(FR-\d+)\s*\|", lines[i])
        if not m:
            continue
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append({"no": m.group(1), "line": i + 1, "cells": cells})
    return rows


def analyze(text: str) -> dict:
    lines = text.splitlines()

    def heading(prefix: str):
        return next((i for i, l in enumerate(lines) if l.startswith(prefix)), None)

    s7, s8 = heading("## 七、"), heading("## 八、")
    if s7 is None:
        return {"error": "未找到「## 七、」功能需求章节"}
    if s8 is None:
        s8 = len(lines)

    rows = _collect_rows(lines, s7, s8)
    checks: list[dict] = []
    nums = [int(r["no"].split("-")[1]) for r in rows]

    # ---------- A1 编号连续唯一 ----------
    dup = sorted({n for n in nums if nums.count(n) > 1})
    miss = [n for n in range(min(nums), max(nums) + 1) if n not in nums] if nums else []
    declared = re.search(r"功能需求\s*(\d+)\s*条", text)
    declared_n = int(declared.group(1)) if declared else None
    ok = bool(nums) and not dup and not miss and (declared_n is None or declared_n == len(rows))
    checks.append({
        "id": "A1", "title": "编号连续唯一，且总数与文档自述一致",
        "status": "pass" if ok else "fail",
        "evidence": {"actual": len(rows), "declared": declared_n,
                     "range": [min(nums), max(nums)] if nums else None,
                     "duplicates": dup, "missing": miss},
    })

    def violations(pred) -> list[dict]:
        out = []
        for r in rows:
            if not pred(r):
                desc = r["cells"][1][:60] if len(r["cells"]) > 1 else ""
                out.append({"line": r["line"], "no": r["no"], "detail": desc})
        return out

    # ---------- A2 EARS 句式 ----------
    bad = violations(lambda r: len(r["cells"]) > 1 and any(m in r["cells"][1] for m in MODALS))
    checks.append({"id": "A2", "title": "需求描述使用 EARS 句式（含模态词）",
                   "status": "pass" if not bad else "fail",
                   "evidence": {"scanned": len(rows), "violations": bad}})

    # ---------- A3 三列非空 ----------
    bad = violations(lambda r: len(r["cells"]) >= 4 and all(r["cells"][k] for k in (1, 2, 3)))
    checks.append({"id": "A3", "title": "需求描述 / 业务规则 / 验收标准三列均非空",
                   "status": "pass" if not bad else "fail",
                   "evidence": {"scanned": len(rows), "violations": bad}})

    # ---------- A4 Given-When-Then ----------
    bad = violations(lambda r: len(r["cells"]) >= 4
                     and all(k in r["cells"][3] for k in ("Given", "When", "Then")))
    checks.append({"id": "A4", "title": "验收标准含 Given / When / Then",
                   "status": "pass" if not bad else "fail",
                   "evidence": {"scanned": len(rows), "violations": bad}})

    # ---------- A5 业务章节无字段名泄漏 ----------
    leaks = []
    for i in range(s7, s8):
        for m in FIELD_RE.finditer(lines[i]):
            leaks.append({"line": i + 1, "token": m.group(0)})
    checks.append({"id": "A5", "title": "功能需求章节无字段名 / 表名泄漏",
                   "status": "pass" if not leaks else "fail",
                   "evidence": {"leaks": leaks}})

    # ---------- A6 可追溯标注（覆盖率制） ----------
    # 为什么用覆盖率而不是二元判定：来源可以标在模块引导语上（如 7.5 的
    # 「底线三件套：幂等(FR-29)…」），二元判定会把这类判成假阳性。
    # 判据一旦假阳性，人就会开始忽略它 —— 被无视一次的判据等于永久失效。
    TRACE_MIN = 0.90
    bad = violations(lambda r: bool(TRACE_RE.search(" | ".join(r["cells"]))))
    cov = (len(rows) - len(bad)) / len(rows) if rows else 0.0
    checks.append({
        "id": "A6", "title": f"可追溯标注覆盖率 ≥ {TRACE_MIN:.0%}",
        "status": "pass" if cov >= TRACE_MIN else "fail",
        "evidence": {"scanned": len(rows), "missing": len(bad),
                     "coverage": round(cov, 4), "threshold": TRACE_MIN,
                     "violations": bad},
    })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {"totalChecks": len(checks), "passed": len(checks) - len(failed),
            "failed": failed, "checks": checks}


# --------------------------------------------------------------------------
# 变异测试样本：好样本必须全绿，坏样本必须六项全红
# --------------------------------------------------------------------------
GOOD = """# 样本 PRD

> 功能需求 2 条

## 七、功能需求

| 编号 | 需求描述（EARS） | 业务规则 | 验收标准（Given/When/Then） |
|---|---|---|---|
| FR-01 | 系统必须支持三级租户结构 `[D3]` | 校区不可跨运营商迁移 | Given 已有运营商 A，When 创建校区绑定 A，Then 数据归属 A |
| FR-02 | 当库存为 0 时，系统必须禁止下单（**本文档新增**） | 扣减必须原子 | Given 库存为 1，When 两人同时提交，Then 仅一单成功 |

## 八、非功能需求
"""

BAD = """# 坏样本

> 功能需求 4 条

## 七、功能需求

| 编号 | 需求描述（EARS） | 业务规则 | 验收标准（Given/When/Then） |
|---|---|---|---|
| FR-01 | 系统必须支持 A | 规则A | Given A，When B，Then C |
| FR-02 | 系统必须支持 B | 规则B | Given A，When B，Then C |
| FR-02 | 支持 C 但不含模态词 | 规则C | Given A，When B，Then C |
| FR-04 | 系统必须支持 D，写入 user_id |  | Given A，Then C |

## 八、非功能需求
"""


def selftest() -> int:
    good, bad = analyze(GOOD), analyze(BAD)
    expect_bad = ["A1", "A2", "A3", "A4", "A5", "A6"]
    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == expect_bad

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿       : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望六项全红   : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立：同一套探针在两种世界状态下产出不同结果。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="02 PRD 质量检查器（Markdown 形态）")
    ap.add_argument("source", nargs="?", help="PRD 的 Markdown 路径")
    ap.add_argument("--json", dest="json_out", help="结果写入的 JSON 路径")
    ap.add_argument("--selftest", action="store_true", help="运行变异测试")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.source:
        ap.print_help()
        return 2

    path = Path(args.source)
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 2

    result = analyze(path.read_text(encoding="utf-8"))
    result["source"] = str(path)

    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2

    print(f"来源: {path.name}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "pass" else "FAIL"
        print(f"  [{mark}] {c['id']} {c['title']}")
        if c["status"] != "fail":
            continue
        ev = c["evidence"]
        if c["id"] == "A1":
            print(f"         实际 {ev['actual']} 条 / 自述 {ev['declared']} 条；"
                  f"重复 {ev['duplicates']}；缺号 {ev['missing']}")
        elif c["id"] == "A5":
            for lk in ev["leaks"]:
                print(f"         第 {lk['line']} 行: {lk['token']}")
        elif c["id"] == "A6":
            print(f"         覆盖率 {ev['coverage']:.1%}（阈值 {ev['threshold']:.0%}）；"
                  f"缺失 {ev['missing']} 条")
            nos = [v["no"] for v in ev["violations"]]
            for i in range(0, len(nos), 10):
                print("         " + ", ".join(nos[i:i + 10]))
        else:
            for v in ev["violations"][:20]:
                print(f"         第 {v['line']} 行 {v['no']}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入: {out}")

    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
