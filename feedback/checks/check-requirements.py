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
# 负向后顾 (?<![A-Z]) 是必需的：否则 `NFR-03` 里的 `FR-03` 会被误当成功能需求引用
FR_REF_RE = re.compile(r"(?<![A-Z])FR-(\d+)((?:\s*/\s*\d+)*)")
# 非功能需求引用：NFR-02
NFR_REF_RE = re.compile(r"NFR-(\d+)")
# 章节引用：§13.4 / §8.2（「§」前缀是硬要求，防止把裸章节号 8.3 放行）
SEC_REF_RE = re.compile(r"§\s*(\d+(?:\.\d+)*)")
# 标题里的章节号：`### 8.2 安全（NFR-02）` -> 8.2
HEADING_NUM_RE = re.compile(r"^#{1,6}\s*(\d+(?:\.\d+)*)")
BOLD_RE = re.compile(r"\*+|`")


def strip_marks(s: str) -> str:
    return BOLD_RE.sub("", s).strip()


def classify_cell(cell: str):
    """把「对应 FR」单元格解析为 [(kind, value)]；形态非法返回 None。

    合法形态**只有四种**（与需求清单「阅读与使用说明」第 5 条一致）：
      · `FR-xx`   —— 可并写 `FR-13/14`
      · `NFR-xx`  —— 非功能需求
      · `§x.y`    —— 非 FR、非 NFR 的正文依据
      · `—`       —— 无依据（由调用方提前跳过，不进入本函数）

    为什么要做「残留检查」：只判断「能不能解析出东西」会把
    `FR-01 见 8.2` 这种脏单元格放行 —— 它看着有编号，实际是两种语义糊在一起。
    因此解析掉全部合法引用后，**余下必须只剩分隔符**。
    """
    work = cell
    refs: list[tuple[str, object]] = []
    for m in SEC_REF_RE.finditer(work):
        refs.append(("SEC", m.group(1)))
    work = SEC_REF_RE.sub(" ", work)
    for m in NFR_REF_RE.finditer(work):
        refs.append(("NFR", int(m.group(1))))
    work = NFR_REF_RE.sub(" ", work)
    for m in FR_REF_RE.finditer(work):
        refs.append(("FR", int(m.group(1))))
        for n in re.findall(r"\d+", m.group(2)):
            refs.append(("FR", int(n)))
    work = FR_REF_RE.sub(" ", work)
    residue = re.sub(r"[\s,、，;；/·|]+", "", work)
    if residue or not refs:
        return None
    return refs


def expand_fr(cell: str) -> list[int]:
    """把 `FR-13/14` 这类引用展开成 [13, 14]（保留给旧调用方）。"""
    out: list[int] = []
    for m in FR_REF_RE.finditer(cell):
        out.append(int(m.group(1)))
        for n in re.findall(r"\d+", m.group(2)):
            out.append(int(n))
    return out


def collect_prd_fr(prd_text: str) -> set[int]:
    """PRD 中出现过的 FR 编号集合（提及式提取，对悬空引用同样敏感）。"""
    return {int(n) for n in re.findall(r"(?<![A-Z])FR-(\d+)", prd_text)}


def collect_prd_nfr(prd_text: str) -> set[int]:
    """PRD 中出现过的 NFR 编号集合。"""
    return {int(n) for n in re.findall(r"NFR-(\d+)", prd_text)}


def collect_prd_sections(prd_text: str) -> set[str]:
    """PRD 的章节号集合（从标题里取，如 `### 13.4 灰度与回滚` -> '13.4'）。

    只从标题取，不从正文取：正文里「见 5.4」这种提及不能证明章节存在，
    否则引用错到不存在的章节也会被判合法。
    """
    out: set[str] = set()
    for line in prd_text.split("\n"):
        m = HEADING_NUM_RE.match(line.strip())
        if m:
            out.add(m.group(1))
    return out


# 声明「产品补充清单」的标题（必须是真的 Markdown 标题，普通段落里的提及不算）
LIST_HEAD_RE = re.compile(r"^#{1,6}\s*[^\n]*产品补充[^\n]*清单")
# 块内「算作声明」的编号形态：必须**出现在行首**（可带 - / * / | 前缀）
LEAD_ID_RE = re.compile(r"^\s*(?:[-*+]\s*|\|\s*)?(F-[A-Z]-\d+)")


def collect_declared_lists(lines: list[str]) -> list[dict]:
    """收集「产品补充清单」声明块。

    一个声明块 = 一个匹配 LIST_HEAD_RE 的**标题**，加上其后直到下一个标题为止的行。
    块内**行首**出现的 `F-x-nn` 即为该声明主张的「无 FR 依据」集合。

    两道收窄都是为了挡住同一种失效 —— 「提及」被读成「声明」：

    1. **限定在标题块内**。文档讨论这件事一定会写下「产品补充」四个字，
       甚至写出「不属产品补充」这种**否定句**；全文关键词扫描会把否定读成肯定。
    2. **只认行首编号**。清单表格里，某一行完全可能在说明里顺带提到另一个功能点
       （实测：F-M-44 的说明写「同 F-M-07」，结果 F-M-07 被判为被声明无依据，
       而它其实有 FR-22）。行首限制让「引用」与「主张」在形态上就能分开。

    见反例库 AP-06：判据若无法区分这两种形态，假阳性只能靠人忽略，最终判据失效。
    """
    out: list[dict] = []
    i = 0
    while i < len(lines):
        if LIST_HEAD_RE.match(lines[i].strip()):
            block: list[str] = []
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("#"):
                block.append(lines[j].strip())
                j += 1
            ids = sorted({m.group(1) for l in block if (m := LEAD_ID_RE.match(l))})
            out.append({"line": i + 1, "ids": ids, "block": block})
            i = j
        else:
            i += 1
    return out


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
        prd_nfr = collect_prd_nfr(prd_text)
        prd_sec = collect_prd_sections(prd_text)
        dangling, malformed = [], []
        for r in rows:
            cell = r["fr_cell"]
            if cell in ("", "—", "-"):
                continue
            refs = classify_cell(cell)
            if refs is None:
                malformed.append({"id": r["id"], "line": r["line"], "cell": cell})
                continue
            for kind, val in refs:
                if kind == "FR" and val not in prd_fr:
                    dangling.append({"id": r["id"], "line": r["line"], "ref": f"FR-{val:02d}"})
                elif kind == "NFR" and val not in prd_nfr:
                    dangling.append({"id": r["id"], "line": r["line"], "ref": f"NFR-{val:02d}"})
                elif kind == "SEC" and val not in prd_sec:
                    dangling.append({"id": r["id"], "line": r["line"], "ref": f"§{val}"})
        checks.append({
            "id": "A5",
            "title": "对应 FR 在 PRD 中存在且形态合法",
            "status": "fail" if (dangling or malformed) else "pass",
            "evidence": {
                "prdFrCount": len(prd_fr),
                "prdNfrCount": len(prd_nfr),
                "prdSectionCount": len(prd_sec),
                "dangling": dangling,
                "malformed": malformed,
            },
        })

    # ---------- A6 例外清单自洽 ----------
    # 旧实现把「全文档任何提到『产品补充』且带编号的行」都当成声明 —— 结果
    # 任何讨论该主题的散文（甚至「不属产品补充」这种**否定句**）都会被读成声明，
    # 产生无法消除的假阳性。判据必须能自己区分「声明」和「提及」，
    # 因此声明处**限定为以标题形式开出的清单块**，块内直到下一个标题为止。
    declared = collect_declared_lists(lines)
    if not declared:
        checks.append({
            "id": "A6", "title": "例外清单与明细行一致",
            "status": "skip",
            "evidence": {"reason": "文档未以标题形式声明「产品补充功能点清单」；"
                                  "未声明不等于通过，也不等于失败，故跳过"},
        })
    else:
        detail = {r["id"]: r for r in rows}
        all_ids = set(detail)
        actual = {r["id"] for r in rows if r["fr_cell"] in ("", "—", "-")}
        declared_ids = set(declared[0]["ids"]) if len(declared) == 1 else set()

        # 声明处不唯一 —— 这本身就是缺陷（同一事实两处声明必然漂移）
        dup_decl = [{"line": l["line"]} for l in declared[1:]] if len(declared) > 1 else []

        unknown = sorted(declared_ids - all_ids)          # 声明了不存在的功能点编号
        has_fr = sorted(cid for cid in declared_ids
                        if cid in detail and detail[cid]["fr_cell"] not in ("", "—", "-"))
        missing = sorted(actual - declared_ids)           # 明细行为 — 却没被声明

        bad = bool(dup_decl or unknown or has_fr or missing)
        checks.append({
            "id": "A6", "title": "例外清单与明细行一致",
            "status": "fail" if bad else "pass",
            "evidence": {
                "declaredAt": declared[0]["line"],
                "declaredCount": len(declared_ids),
                "actualCount": len(actual),
                "duplicateDeclarations": dup_decl,
                "unknown": unknown,
                "declaredButHasFR": [
                    {"id": cid, "line": detail[cid]["line"], "fr": detail[cid]["fr_cell"]}
                    for cid in has_fr
                ],
                "dashButNotDeclared": [
                    {"id": cid, "line": detail[cid]["line"]} for cid in missing
                ],
            },
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

## 八、非功能需求
### 8.2 安全（`NFR-02`）

## 十三、上线计划
### 13.4 灰度与回滚
"""

GOOD = """
## 一、功能总量概览
| 端 | 页面数 | 功能点数 | Must | Should | Could |
|---|---|---|---|---|---|
| 用户端小程序 | 2 | 5 | 5 | 0 | 0 |
| 平台客服工作台（Web） | 1 | 3 | 3 | 0 | 0 |
| **合计** | **3** | **8** | **8** | **0** | **0** |

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
| F-C-02 | 用户信息脱敏查看 | 略 | Must | NFR-02 | 待设计 |
| F-C-03 | 看板按校区下钻 | 略 | Must | §13.4 | 待设计 |

### 产品补充功能点清单（=「对应 FR」列为 `—` 的全部行）

- F-U-04
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

### 产品补充功能点清单

- F-U-03
- F-U-05
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
                print(f"         第 {v['line']} 行 {v['id']}: {v['cell']!r} 不是合法引用"
                      f"（只接受 FR-xx / NFR-xx / §x.y / —）")
        elif c["id"] == "A6":
            for v in ev["duplicateDeclarations"]:
                print(f"         第 {v['line']} 行又开了一处「产品补充清单」标题 —— "
                      f"同一事实两处声明必然漂移，只允许一处（第 {ev['declaredAt']} 行）")
            for v in ev["unknown"]:
                print(f"         第 {ev['declaredAt']} 行声明了 {v}，但全文无此功能点")
            for v in ev["declaredButHasFR"]:
                print(f"         第 {v['line']} 行 {v['id']}: 被声明为「无 FR 依据」，"
                      f"但明细行填了 {v['fr']}")
            for v in ev["dashButNotDeclared"]:
                print(f"         第 {v['line']} 行 {v['id']}: 明细行为「—」却没进清单"
                      f"（清单共 {ev['declaredCount']} 个，明细行实有 {ev['actualCount']} 个）")

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
