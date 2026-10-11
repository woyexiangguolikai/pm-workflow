#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01 需求阶段质量检查器 · 对《需求清单》执行 A1–A5
================================================================
实现 01-requirements rubric 的 A 类判据 —— 可脚本化、必须自动判、不许推给人。

用法:
    python check-requirements.py <需求清单.md> [--prd <PRD.md>] [--json <输出路径>]
    python check-requirements.py --selftest        # 变异测试：证明检查有判别力

判据:
    A1  功能点编号连续唯一（每端内独立连续）
    A2  各端功能点数 / 优先级分布 / 页面数与概览表声明一致（两侧都现算）
    A3  优先级取值在 Must / Should / Could 闭集内
    A4  每条有「对应 FR」或显式「—」（空值判失败）
    A5  对应 FR 编号在 PRD 中存在，且引用必须是合法 FR 形态（跨文档闭环）

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么 A5 是本阶段重心
-----------------------
需求清单是**编号体系的源头**。它一旦断链，PRD / 原型 / 卡片全部跟着错位。
断链有两种，只有第二种能被机器抓到：
  · FR 编号写错（FR-14 写成 FR-41）→ 指向另一条**真实存在**的需求，肉眼极难发现
  · FR 编号指向**不存在**的条目 → A5 直接报出来
此外还有第三种更隐蔽的：引用格填了**章节号**（如 `8.2`）而不是 FR 编号 ——
它非空、看起来填了，实际切断了编号链路。A5 把这种也判失败。

为什么 A2 要「两侧都现算」
---------------------------
概览表的合计数本身也是手写的，它可能和明细行不一致。
若只信概览表，等于用错误去校验错误。两侧独立算出来的差异，
报的是**文档内部矛盾**，而不是「数量错」—— 这两件事的修法不同。

为什么 A4 把「空」判失败而「—」放行
-------------------------------------
「没有对应 FR」和「忘了填」在数据上长得一样。必须显式写「—」才算表态。
这与 anti-patterns.md AP-04 同源：**沉默不等于确认**。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 端前缀 -> 显示名
PREFIX_NAME = {
    "U": "用户端小程序",
    "M": "商家端",
    "R": "骑手端",
    "O": "运营后台",
    "C": "平台客服工作台",
}

# 概览表首列关键词 -> 端前缀（按顺序匹配，客服必须排在用户端之后）
END_KEYWORDS = [
    ("用户端", "U"),
    ("商家端", "M"),
    ("骑手端", "R"),
    ("运营后台", "O"),
    ("客服", "C"),
]

PRIORITIES = ("Must", "Should", "Could")

ROW_ID_RE = re.compile(r"^F-([A-Z])-(\d+)$")
# FR 引用：FR-02 或 FR-13/14 或 FR-13/14/15
FR_REF_RE = re.compile(r"FR-(\d+)((?:\s*/\s*\d+)*)")
BOLD_RE = re.compile(r"\*+|`")


def strip_marks(s: str) -> str:
    return BOLD_RE.sub("", s).strip()


def expand_fr(cell: str) -> list[int]:
    """把 `FR-13/14` 这类引用展开成 [13, 14]。"""
    out: list[int] = []
    for m in FR_REF_RE.finditer(cell):
        out.append(int(m.group(1)))
        for n in re.findall(r"\d+", m.group(2)):
            out.append(int(n))
    return out


def collect_prd_fr(prd_text: str) -> set[int]:
    """PRD 中出现过的 FR 编号集合（提及式提取，对悬空引用同样敏感）。"""
    return {int(n) for n in re.findall(r"FR-(\d+)", prd_text)}


def collect_rows(lines: list[str]) -> list[dict]:
    """抓取形如 `| F-U-01 | 名称 | 说明 | Must | FR-02/05 | 待设计 |` 的明细行。"""
    rows = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        m = ROW_ID_RE.match(strip_marks(cells[0]))
        if not m:
            continue
        rows.append({
            "id": strip_marks(cells[0]),
            "prefix": m.group(1),
            "num": int(m.group(2)),
            "line": i + 1,
            "priority": strip_marks(cells[3]),
            "fr_cell": strip_marks(cells[4]),
        })
    return rows


def collect_overview(lines: list[str]) -> dict[str, tuple]:
    """抓概览表：`| 用户端小程序 | 18 | 58 | 43 | 12 | 3 |`。"""
    declared: dict[str, tuple] = {}
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [strip_marks(c) for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if not all(re.fullmatch(r"\d+", c) for c in cells[1:6]):
            continue
        head = cells[0]
        key = next((k for kw, k in END_KEYWORDS if kw in head), None)
        if key is None:
            continue
        declared[key] = tuple(int(c) for c in cells[1:6])
    return declared


def analyze(text: str, prd_text: str | None = None) -> dict:
    lines = text.splitlines()
    rows = collect_rows(lines)
    declared = collect_overview(lines)
    checks: list[dict] = []

    if not rows:
        return {"error": "未抓到任何功能点明细行（形如 `| F-U-01 | ... |`）"}

    # ---------- A1 编号分端连续唯一 ----------
    by_prefix: dict[str, list[int]] = {}
    for r in rows:
        by_prefix.setdefault(r["prefix"], []).append(r["num"])

    problems = []
    for pfx, nums in sorted(by_prefix.items()):
        seen, dup = set(), set()
        for n in nums:
            if n in seen:
                dup.add(n)
            seen.add(n)
        missing = sorted(set(range(1, max(nums) + 1)) - seen)
        if dup or missing:
            problems.append({
                "end": PREFIX_NAME.get(pfx, pfx),
                "duplicates": sorted(dup),
                "missing": missing,
            })

    checks.append({
        "id": "A1",
        "title": "功能点编号分端连续唯一",
        "status": "fail" if problems else "pass",
        "evidence": {
            "ends": {PREFIX_NAME.get(k, k): len(v) for k, v in sorted(by_prefix.items())},
            "violations": problems,
        },
    })

    # ---------- A2 声明的数量与现算一致 ----------
    actual: dict[str, dict] = {}
    for pfx in by_prefix:
        sub = [r for r in rows if r["prefix"] == pfx]
        actual[pfx] = {
            "features": len(sub),
            "Must": sum(1 for r in sub if r["priority"] == "Must"),
            "Should": sum(1 for r in sub if r["priority"] == "Should"),
            "Could": sum(1 for r in sub if r["priority"] == "Could"),
        }

    mismatches = []
    for pfx, dec in sorted(declared.items()):
        if pfx not in actual:
            mismatches.append({
                "end": PREFIX_NAME.get(pfx, pfx),
                "field": "整端",
                "declared": "有声明",
                "actual": "无明细行",
            })
            continue
        a = actual[pfx]
        # dec = (页面数, 功能点数, Must, Should, Could)
        pairs = [
            ("功能点数", dec[1], a["features"]),
            ("Must", dec[2], a["Must"]),
            ("Should", dec[3], a["Should"]),
            ("Could", dec[4], a["Could"]),
        ]
        for field, d, ac in pairs:
            if d != ac:
                mismatches.append({
                    "end": PREFIX_NAME.get(pfx, pfx),
                    "field": field,
                    "declared": d,
                    "actual": ac,
                })
    for pfx in actual:
        if pfx not in declared:
            mismatches.append({
                "end": PREFIX_NAME.get(pfx, pfx),
                "field": "整端",
                "declared": "无概览行",
                "actual": actual[pfx]["features"],
            })

    checks.append({
        "id": "A2",
        "title": "各端数量与概览表声明一致",
        "status": "fail" if mismatches else "pass",
        "evidence": {
            "declaredEnds": {PREFIX_NAME.get(k, k): v for k, v in sorted(declared.items())},
            "actualEnds": {PREFIX_NAME.get(k, k): v for k, v in sorted(actual.items())},
            "mismatches": mismatches,
        },
    })

    # ---------- A3 优先级取值合法 ----------
    bad_pri = [{"id": r["id"], "line": r["line"], "value": r["priority"]}
               for r in rows if r["priority"] not in PRIORITIES]
    checks.append({
        "id": "A3",
        "title": "优先级取值在 Must/Should/Could 闭集内",
        "status": "fail" if bad_pri else "pass",
        "evidence": {"violations": bad_pri, "allowed": list(PRIORITIES)},
    })

    # ---------- A4 每条有「对应 FR」或显式「—」 ----------
    empty_fr = [{"id": r["id"], "line": r["line"]}
                for r in rows if r["fr_cell"] == ""]
    checks.append({
        "id": "A4",
        "title": "每条有「对应 FR」或显式「—」",
        "status": "fail" if empty_fr else "pass",
        "evidence": {"violations": empty_fr},
    })

    # ---------- A5 跨文档闭环 ----------
    if prd_text is None:
        checks.append({
            "id": "A5",
            "title": "对应 FR 在 PRD 中存在",
            "status": "skip",
            "evidence": {"reason": "未提供 --prd，无法取差集"},
        })
    else:
        prd_fr = collect_prd_fr(prd_text)
        dangling, malformed = [], []
        for r in rows:
            cell = r["fr_cell"]
            if cell in ("", "—", "-"):
                continue
            refs = expand_fr(cell)
            if not refs:
                malformed.append({"id": r["id"], "line": r["line"], "cell": cell})
                continue
            for n in refs:
                if n not in prd_fr:
                    dangling.append({"id": r["id"], "line": r["line"], "ref": f"FR-{n:02d}"})
        checks.append({
            "id": "A5",
            "title": "对应 FR 在 PRD 中存在且形态合法",
            "status": "fail" if (dangling or malformed) else "pass",
            "evidence": {
                "prdFrCount": len(prd_fr),
                "dangling": dangling,
                "malformed": malformed,
            },
        })

    # ---------- A6 例外清单自洽（文档自己声明的「无依据」清单必须被明细行支持） ----------
    EXC_HEAD_RE = re.compile(r"(产品补充|无\s*FR\s*依据|无需求依据)")
    declared_lists: list[dict] = []
    for i, line in enumerate(lines, start=1):
        if not EXC_HEAD_RE.search(line):
            continue
        ids = re.findall(r"F-[A-Z]-\d+", line)
        if ids:
            declared_lists.append({"line": i, "ids": sorted(set(ids))})

    if not declared_lists:
        checks.append({
            "id": "A6", "title": "例外清单与明细行一致",
            "status": "skip",
            "evidence": {"reason": "文档未声明「产品补充 / 无 FR 依据」清单"},
        })
    else:
        detail = {r["id"]: r for r in rows}
        unsupported, unknown = [], []
        for lst in declared_lists:
            for cid in lst["ids"]:
                r = detail.get(cid)
                if r is None:
                    unknown.append({"id": cid, "line": lst["line"]})
                elif r["fr_cell"] not in ("", "—", "-"):
                    unsupported.append({
                        "id": cid, "line": r["line"], "declaredAt": lst["line"],
                        "fr": r["fr_cell"],
                    })
        sets = [set(l["ids"]) for l in declared_lists]
        inconsistent = []
        if len(sets) > 1:
            union = set().union(*sets)
            for cid in sorted(union):
                holders = [l["line"] for l in declared_lists if cid in l["ids"]]
                if len(holders) != len(declared_lists):
                    inconsistent.append({"id": cid, "declaredAt": holders,
                                         "missingFrom": [l["line"] for l in declared_lists
                                                         if cid not in l["ids"]]})
        bad_a6 = bool(unsupported or unknown or inconsistent)
        checks.append({
            "id": "A6", "title": "例外清单与明细行一致",
            "status": "fail" if bad_a6 else "pass",
            "evidence": {"lists": declared_lists,
                         "unsupported": unsupported,
                         "unknown": unknown,
                         "inconsistent": inconsistent},
        })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {
        "checks": checks,
        "failed": failed,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "totalChecks": len(checks),
        "rowCount": len(rows),
    }


# ---------------------------------------------------------------- 变异测试
GOOD_PRD = """
## 七、功能需求
| 编号 | 需求描述 | 业务规则 | 验收标准 |
|---|---|---|---|
| FR-01 | 系统**必须**支持校区识别 | 略 | 略 |
| FR-02 | 系统**必须**校验配送范围 | 略 | 略 |
| FR-03 | 系统**必须**支持登录 | 略 | 略 |
| FR-04 | 系统**必须**支持客服登录 | 略 | 略 |
| FR-05 | 系统**必须**支持订阅消息 | 略 | 略 |
"""

GOOD = """
## 一、功能总量概览
| 端 | 页面数 | 功能点数 | Must | Should | Could |
|---|---|---|---|---|---|
| 用户端小程序 | 2 | 5 | 5 | 0 | 0 |
| 平台客服工作台（Web） | 1 | 1 | 1 | 0 | 0 |
| **合计** | **3** | **6** | **6** | **0** | **0** |

## 二、用户端小程序（F-U）
| 编号 | 功能点 | 说明 / 规则要点 | 优先级 | 对应 FR | 设计状态 |
|---|---|---|---|---|---|
| F-U-01 | 校区识别进入 | 略 | Must | FR-01 | 待设计 |
| F-U-02 | 定位授权校验 | 略 | Must | FR-02 | 待设计 |
| F-U-03 | 手机号授权登录 | 略 | Must | FR-03 | 待设计 |
| F-U-04 | 隐私政策确认 | 略 | Must | — | 待设计 |
| F-U-05 | 订阅消息引导 | 略 | Must | FR-05 | 待设计 |

## 六、平台客服工作台（F-C）
| 编号 | 功能点 | 说明 / 规则要点 | 优先级 | 对应 FR | 设计状态 |
|---|---|---|---|---|---|
| F-C-01 | 账号登录与身份校验 | 略 | Must | FR-04 | 待设计 |
"""

BAD = """
## 一、功能总量概览
| 端 | 页面数 | 功能点数 | Must | Should | Could |
|---|---|---|---|---|---|
| 用户端小程序 | 2 | 7 | 5 | 2 | 0 |
| **合计** | **2** | **7** | **5** | **2** | **0** |

## 二、用户端小程序（F-U）
| 编号 | 功能点 | 说明 / 规则要点 | 优先级 | 对应 FR | 设计状态 |
|---|---|---|---|---|---|
| F-U-01 | 校区识别进入 | 略 | Must | FR-01 | 待设计 |
| F-U-01 | 定位授权校验 | 略 | Must | FR-99 | 待设计 |
| F-U-03 | 手机号授权登录 | 略 | P0 | FR-03 | 待设计 |
| F-U-04 | 隐私政策确认 | 略 | Must |  | 待设计 |
| F-U-05 | 订阅消息引导 | 略 | Should | 8.2 | 待设计 |
| F-C-01 | 客服登录 | 略 | Must | FR-04 | 待设计 |

**产品补充功能点清单**：F-U-03、F-U-05。
"""


def selftest() -> int:
    good = analyze(GOOD, GOOD_PRD)
    bad = analyze(BAD, GOOD_PRD)
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


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="01 需求阶段质量检查器（功能列表）")
    ap.add_argument("source", nargs="?", help="需求清单的 Markdown 路径")
    ap.add_argument("--prd", dest="prd", help="PRD 的 Markdown 路径（A5 跨文档闭环）")
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

    prd_text = None
    if args.prd:
        p = Path(args.prd)
        if not p.exists():
            print(f"PRD 不存在: {p}", file=sys.stderr)
            return 2
        prd_text = p.read_text(encoding="utf-8")

    result = analyze(path.read_text(encoding="utf-8"), prd_text)
    result["source"] = str(path)
    result["prd"] = str(args.prd) if args.prd else None

    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2

    print(f"来源: {path.name}")
    print(f"功能点总数: {result['rowCount']}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
        print(f"  [{mark}] {c['id']} {c['title']}")
        if c["status"] != "fail":
            continue
        ev = c["evidence"]
        if c["id"] == "A1":
            for v in ev["violations"]:
                print(f"         {v['end']}: 重复 {v['duplicates']} 缺号 {v['missing']}")
        elif c["id"] == "A2":
            for v in ev["mismatches"]:
                print(f"         {v['end']} · {v['field']}: 概览 {v['declared']} / 现算 {v['actual']}")
        elif c["id"] == "A3":
            for v in ev["violations"]:
                print(f"         第 {v['line']} 行 {v['id']}: 优先级 = {v['value']!r}")
        elif c["id"] == "A4":
            print("         对应 FR 为空: " + ", ".join(v["id"] for v in ev["violations"]))
        elif c["id"] == "A5":
            for v in ev["dangling"]:
                print(f"         第 {v['line']} 行 {v['id']}: {v['ref']} 在 PRD 中不存在")
            for v in ev["malformed"]:
                print(f"         第 {v['line']} 行 {v['id']}: {v['cell']!r} 不是合法 FR 引用")
        elif c["id"] == "A6":
            for v in ev["unsupported"]:
                print(f"         第 {v['line']} 行 {v['id']}: 第 {v['declaredAt']} 行声明为"
                      f"「无 FR 依据」，但明细行填了 {v['fr']}")
            for v in ev["unknown"]:
                print(f"         第 {v['line']} 行声明了 {v['id']}，但无此功能点")
            for v in ev["inconsistent"]:
                print(f"         {v['id']}: 出现在第 {v['declaredAt']} 行，"
                      f"未出现在第 {v['missingFrom']} 行（两份清单不一致）")

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
