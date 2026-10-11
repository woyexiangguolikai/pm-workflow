#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02 PRD · 口径副本检测（02 A7，由 02 B3 升级而来）
=================================================
实现 02-prd rubric 的 A7 判据：**一个口径只能有一处权威定义**。

用法:
    python check-duplicate-norms.py <文档目录> --norms <口径声明文件> [--json <输出>]
    python check-duplicate-norms.py --selftest

判据:
    A7  每个已声明的口径，其「定义正文指纹」在全部文档里：
          · 权威处 恰好 1 次
          · 其他出现处必须含**指向权威处的标识**（即「引用」）
          · 既不在权威处、又不含指向标识的 → **定义副本**，判失败

为什么这条判据必须机械化
------------------------
「口径应当只有一处」这种话写一百遍也没有约束力。
它必须变成：**声明一个指纹 → 数它出现了几次 → 多出来的那些必须是引用**。

副本的危害不是「重复」本身，而是：**改一处、漏一处，两处都自称权威**。
本项目 AP-01 已证实同一舍入口径曾出现在 5 处。

🔴 指纹要取「**定义正文**」，不要取「**口径名**」（首版踩过）
------------------------------------------------------------
首版拿口径名当指纹，实测 12 处命中里**只有 1 处是真副本**，
其余 11 处全是正当引用（「四舍六入五成双」被各文档反复提及，这很正常）。
判据立刻变成噪音，而**被无视一次的判据会永久失效**。

真正区分「定义」与「提及」的是**定义正文里那句独特的话**：

    口径名  「四舍六入五成双」            ← 出现 12 次，其中 11 次正常
    定义正文「尾数 <5 舍；>5 入；=5 且其后全为 0…」  ← 出现 2 次，第 2 次就是副本

所以声明文件里写的是后者。

怎么区分「定义」与「引用」（这条判据的核心）
--------------------------------------------
不能只看关键词出现次数 —— 那会把正常的引用也报成副本，判据立刻被无视。
判据用一个**引用标识**（通常是权威章节号，如 `2.2`）来分流：

    · 该处文本含引用标识          → 引用 ✅（它指向权威处，不宣称自己权威）
    · 权威文件内、且含引用标识    → 权威定义 ✅
    · 其余                        → 定义副本 ❌

⚠️ 声明文件是**项目内容**，不随工作流走。它写在项目目录里，不写进 skill。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

# 递归时跳过的目录：都不是「被下游消费的逐条文档」
# 🔴 必须跳过工作流的**运行产物目录**（评审报告、锚定记录、状态页）——
#    它们会引用这些口径（那正是它们的工作），不跳过的话
#    「评审发现了一处副本」会被判成「又多了一处副本」。判据不能把自己算进去。
SKIP_DIRS = {"node_modules", ".git", "_manual", "__pycache__", ".workbuddy",
             "pm-workflow-runs", "feedback-review"}
SKIP_NAME_HINTS = ("review-log", "CHANGELOG")


def parse_norms(path: Path) -> list[dict]:
    """口径声明文件格式（`#` 开头为注释）：
        口径名 | 指纹正则 | 权威文件片段 | 引用标识
    引用标识留空表示「该口径在别处不得出现」。
    """
    rows = []
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        parts = [p.strip() for p in s.split("|")]
        if len(parts) < 3:
            raise ValueError(f"{path.name}:{ln} 需要至少 3 段（口径名 | 指纹 | 权威文件片段 | 引用标识）")
        name, pat, canon = parts[0], parts[1], parts[2]
        ref = parts[3] if len(parts) > 3 else ""
        rows.append({"line": ln, "name": name, "pattern": pat,
                     "canonical": canon, "refToken": ref,
                     "re": re.compile(pat)})
    return rows


def collect_docs(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    out = []
    for p in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if any(h in p.name for h in SKIP_NAME_HINTS):
            continue
        out.append(p)
    return out


def analyze(root: Path, norms: list[dict]) -> dict:
    docs = collect_docs(root)
    if not docs:
        return {"error": f"没找到任何 .md 文档: {root}", "checks": [], "failed": []}

    checks = []
    for n in norms:
        occ = []
        for d in docs:
            try:
                text = d.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if n["re"].search(line):
                    occ.append({"file": str(d.relative_to(root) if root.is_dir() else d.name),
                                "line": i, "text": line.strip()[:140]})

        canon_file = [o for o in occ if n["canonical"] in o["file"]]
        # 引用标识为空 ⇒ 只允许权威处出现，别处一律算副本
        ref_ok = (lambda o: bool(n["refToken"]) and n["refToken"] in o["text"])
        authority = [o for o in canon_file if ref_ok(o)] or canon_file
        copies = [o for o in occ
                  if o not in authority and not ref_ok(o)]
        refs = [o for o in occ if o not in authority and ref_ok(o)]

        status = "pass"
        reason = ""
        if not occ:
            status, reason = "fail", "指纹在整个文档集里一次都没出现（样本为 0 判失败）"
        elif len(authority) != 1:
            status = "fail"
            reason = f"权威处应为 1 处，实得 {len(authority)} 处"
        elif copies:
            status = "fail"
            reason = f"{len(copies)} 处既不在权威处、又不含引用标识「{n['refToken']}」→ 定义副本"

        checks.append({
            "id": "A7", "title": f"口径单一定义：{n['name']}",
            "status": status, "reason": reason,
            "evidence": {"norm": n["name"], "pattern": n["pattern"],
                         "canonical": n["canonical"], "refToken": n["refToken"],
                         "occurrences": len(occ),
                         "authority": authority, "references": refs, "copies": copies},
        })

    failed = [c["title"] for c in checks if c["status"] == "fail"]
    return {"totalChecks": len(checks), "passed": len(checks) - len(failed),
            "failed": failed, "checks": checks, "docsScanned": len(docs)}


# --------------------------------------------------------------------------
# ⚠️ 注意两边的「口径名」都出现了多次（那是正常的），
#    差别只在**定义正文**有没有第二处。
GOOD = {
    "PRD.md": ("# PRD\n"
               "FR-17 金额舍入：采用四舍六入五成双，口径见《字段规格》2.2。\n"
               "FR-31 展示：口径见《字段规格》2.2。\n"),
    "字段规格.md": "# 字段规格\n## 2.2 舍入规则\n采用四舍六入五成双："
                   "尾数 <5 舍、>5 入、=5 且其后全为 0 时看保留位奇偶。\n",
}
BAD = {
    "PRD.md": ("# PRD\n"
               "FR-17 金额舍入：采用四舍六入五成双，尾数 <5 舍、>5 入、"
               "=5 且其后全为 0 时看保留位奇偶。\n"
               "FR-31 展示：口径见《字段规格》2.2。\n"),
    "字段规格.md": "# 字段规格\n## 2.2 舍入规则\n采用四舍六入五成双："
                   "尾数 <5 舍、>5 入、=5 且其后全为 0 时看保留位奇偶。\n",
}
# 指纹取「定义正文」里的独特说法，不取口径名
NORMS = ("# 口径名 | 定义正文指纹 | 权威文件片段 | 引用标识\n"
         "舍入口径 | 尾数\\s*<5\\s*舍 | 字段规格 | 2.2\n")


def _mk(base: Path, files: dict) -> tuple[Path, Path]:
    base.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (base / name).write_text(body, encoding="utf-8")
    nf = base / "norms.txt"
    nf.write_text(NORMS, encoding="utf-8")
    return base, nf


def selftest() -> int:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        gdir, gnf = _mk(p / "g", GOOD)
        good = analyze(gdir, parse_norms(gnf))
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        bdir, bnf = _mk(p / "b", BAD)
        bad = analyze(bdir, parse_norms(bnf))

    ok_good = good.get("failed") == []
    ok_bad = "A7" in bad.get("failed") or any(
        c["status"] == "fail" for c in bad.get("checks", []))
    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿      : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望 A7 变红  : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    if not ok_good:
        for c in good.get("checks", []):
            print(f"      好样本 {c['title']}: {c['status']} {c.get('reason','')}")
    if ok_bad:
        for c in bad.get("checks", []):
            if c["status"] == "fail":
                print(f"      坏样本命中: {c['title']} —— {c['reason']}")
                for o in c["evidence"]["copies"]:
                    print(f"        {o['file']}:{o['line']}  {o['text'][:70]}")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="02 PRD · 口径副本检测")
    ap.add_argument("root", nargs="?")
    ap.add_argument("--norms", help="口径声明文件")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.root or not args.norms:
        ap.print_help()
        return 2

    nf = Path(args.norms)
    if not nf.exists():
        print(f"口径声明文件不存在: {nf}", file=sys.stderr)
        return 2
    try:
        norms = parse_norms(nf)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not norms:
        print(f"⚠️ {nf} 里没有声明任何口径 —— A7 这一类**未扫描**", file=sys.stderr)
        return 2

    root = Path(args.root)
    result = analyze(root, norms)
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2
    result["root"] = str(root)
    result["normsFile"] = str(nf)

    print(f"扫描 {result['docsScanned']} 个 Markdown；声明口径 {len(norms)} 个")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "pass" else "FAIL"
        print(f"  [{mark}] A7 {c['title']}")
        ev = c["evidence"]
        print(f"         指纹 {ev['pattern']!r} 命中 {ev['occurrences']} 处"
              f"（权威 {len(ev['authority'])} / 引用 {len(ev['references'])}"
              f" / 副本 {len(ev['copies'])}）")
        if c["status"] == "fail":
            print(f"         🔴 {c['reason']}")
        for o in ev["copies"]:
            print(f"         🔴 副本 {o['file']}:{o['line']}")
            print(f"            {o['text']}")
        for o in ev["authority"]:
            print(f"         ✓ 权威 {o['file']}:{o['line']}")

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
