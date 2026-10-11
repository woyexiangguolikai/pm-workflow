#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03b 组件库 质量检查器 · 对 `components.json` 执行 A1–A5
========================================================
实现 03b-components rubric 的 A 类判据 —— 可脚本化、必须自动判、不许推给人。

用法:
    python check-components.py <components.json> [--tokens <tokens.css|tokens.json>]
                               [--html <design-system.html>] [--json <输出路径>]
    python check-components.py --selftest        # 变异测试：证明检查有判别力

判据:
    A1  id 唯一且 kebab-case
    A2  契约字段齐全（id/name/category/states/tokens/usedIn/a11y），且 tokens 项是变量名
    A3  states 覆盖该类别的最低要求
    A4  tokens 引用的变量在 03 的 token 集里存在（跨阶段闭环）
    A5  组件不出现字面量色值（预览 HTML + JSON 一起扫）

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么本阶段的核心是「契约」而不是「好看」
--------------------------------------------
组件库是**唯一被多处复用的层**。它的一处错会被放大到每个用到它的页面，
而页面上的人永远不知道错在组件 —— 他们只会觉得「这里显示不对」。
所以能机械核对的（id 规范、字段齐全、状态覆盖、token 闭环）必须机械核对。

为什么 A4 一定要拿真实的 token 集去取差集
-------------------------------------------
若把「允许的 token」写成常量清单，token 改名后判据**照样全绿** ——
这正是铁律 2 说的「写死数字的检查在数据源变更后照样全绿，等于没有检查」。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
VAR_RE = re.compile(r"^--[a-z0-9-]+$")

CONTRACT_FIELDS = ("id", "name", "category", "states", "tokens", "usedIn", "a11y")

REQUIRED_STATES = {
    "action": ["default", "hover", "active", "disabled", "loading"],
    "input": ["default", "focus", "error", "disabled", "readonly"],
    "display": ["default", "empty", "loading", "error"],
    "feedback": ["success", "warning", "error", "info"],
    "nav": ["default", "hover", "active", "disabled"],
}

# 字面量色值：仅在 JSON / HTML 文本里扫
COLOR_LITERAL_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\("
)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
VAR_DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:")


def read_code(p: Path) -> str:
    """剥离注释（等长空白替换，保持行号稳定）。

    注释里的色值不参与渲染，不构成事实源 —— 扫它只会产出假阳性。（见 AP-07 陷阱四）
    """
    s = p.read_text(encoding="utf-8")
    for rx in (CSS_COMMENT_RE, HTML_COMMENT_RE):
        s = rx.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), s)
    return s


def collect_token_vars(text: str) -> set[str]:
    """token 变量名集合：CSS 自定义属性声明 + JSON 里的 --var 字符串。"""
    return {m.group(1) for m in VAR_DECL_RE.finditer(text)} | set(
        re.findall(r"(--[a-z0-9-]+)", text)
    )


def analyze(data: dict,
            token_vars: set[str] | None = None,
            html_text: str | None = None) -> dict:
    comps = data.get("components")
    if not isinstance(comps, list) or not comps:
        return {"error": "components.json 里没有 components 数组"}

    checks: list[dict] = []

    # ---------- A1 id 唯一且 kebab-case ----------
    ids = [str(c.get("id", "")) for c in comps]
    bad_ids = [c.get("id") for c in comps if not KEBAB_RE.match(str(c.get("id", "")))]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    checks.append({
        "id": "A1", "title": "id 唯一且 kebab-case",
        "status": "fail" if (bad_ids or dup) else "pass",
        "evidence": {"badFormat": bad_ids, "duplicates": dup, "count": len(comps)},
    })

    # ---------- A2 契约字段齐全 ----------
    lack_field, bad_token_name = [], []
    for c in comps:
        miss = [f for f in CONTRACT_FIELDS if f not in c or c[f] in (None, "", [], {})]
        if miss:
            lack_field.append({"id": c.get("id"), "missing": miss})
        for t in c.get("tokens", []) or []:
            if not VAR_RE.match(str(t)):
                bad_token_name.append({"id": c.get("id"), "token": t})
    bad_a2 = bool(lack_field or bad_token_name)
    checks.append({
        "id": "A2", "title": "契约字段齐全，且 tokens 项是变量名",
        "status": "fail" if bad_a2 else "pass",
        "evidence": {"fields": list(CONTRACT_FIELDS),
                     "missingFields": lack_field,
                     "notVariableName": bad_token_name},
    })

    # ---------- A3 states 覆盖类别最低要求 ----------
    lack_state = []
    for c in comps:
        cat = str(c.get("category", ""))
        need = REQUIRED_STATES.get(cat)
        if need is None:
            lack_state.append({"id": c.get("id"), "category": cat,
                               "missing": ["（未知类别，无法判定必需状态）"],
                               "unknownCategory": True})
            continue
        have = set(c.get("states") or [])
        miss = [s for s in need if s not in have]
        if miss:
            lack_state.append({"id": c.get("id"), "category": cat, "missing": miss})
    checks.append({
        "id": "A3", "title": "states 覆盖该类别最低要求",
        "status": "fail" if lack_state else "pass",
        "evidence": {"required": REQUIRED_STATES, "violations": lack_state},
    })

    # ---------- A4 tokens 跨阶段闭环 ----------
    if token_vars is None:
        checks.append({
            "id": "A4", "title": "tokens 在 03 的 token 集里存在",
            "status": "skip",
            "evidence": {"reason": "未提供 --tokens，无法取差集"},
        })
    else:
        dangling = []
        for c in comps:
            for t in c.get("tokens", []) or []:
                if str(t) not in token_vars:
                    dangling.append({"id": c.get("id"), "token": t})
        checks.append({
            "id": "A4", "title": "tokens 在 03 的 token 集里存在",
            "status": "fail" if dangling else "pass",
            "evidence": {"tokenCount": len(token_vars), "dangling": dangling},
        })

    # ---------- A5 无字面量色值 ----------
    literals = []
    json_text = json.dumps(comps, ensure_ascii=False)
    for src, txt in (("components.json", json_text),
                     ("design-system.html", html_text or "")):
        if not txt:
            continue
        for m in COLOR_LITERAL_RE.finditer(txt):
            literals.append({"source": src, "value": m.group(0)})
    checks.append({
        "id": "A5", "title": "组件不出现字面量色值",
        "status": "fail" if literals else "pass",
        "evidence": {"literals": literals[:40], "total": len(literals)},
    })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {
        "checks": checks,
        "failed": failed,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "totalChecks": len(checks),
        "componentCount": len(comps),
    }


# ------------------------------------------------------------ 变异测试
GOOD_TOKENS = """
:root {
  --brand-500: #E4572E;
  --brand-600: #C9431E;
  --space-s3: 12px;
  --radius-r2: 6px;
}
"""

GOOD = {
    "meta": {"name": "demo", "version": "1.0", "basedOn": "tokens.css"},
    "components": [
        {
            "id": "btn-primary", "name": "主按钮", "category": "action",
            "states": ["default", "hover", "active", "disabled", "loading"],
            "sizes": ["sm", "md", "lg"],
            "tokens": ["--brand-500", "--brand-600", "--radius-r2"],
            "usedIn": ["UC", "MC", "OA"],
            "a11y": {"minTargetPx": 44, "contrastMin": 4.5},
        },
        {
            "id": "field-text", "name": "单行输入", "category": "input",
            "states": ["default", "focus", "error", "disabled", "readonly"],
            "tokens": ["--radius-r2", "--space-s3"],
            "usedIn": ["UC", "OA"],
            "a11y": {"minTargetPx": 44, "contrastMin": 4.5},
        },
    ],
}

BAD = {
    "meta": {"name": "demo", "version": "1.0"},
    "components": [
        {
            "id": "Btn_Primary", "name": "主按钮", "category": "action",
            "states": ["default"],
            "tokens": ["主色", "--brand-999"],
            "usedIn": ["UC"],
            "a11y": {"minTargetPx": 44},
            "style": {"color": "#E4572E"},
        },
        {
            "id": "Btn_Primary", "name": "次按钮", "category": "input",
            "states": ["default"], "tokens": [],
            "usedIn": ["UC"], "a11y": {"contrastMin": 4.5},
        },
    ],
}


def selftest() -> int:
    tv = collect_token_vars(GOOD_TOKENS)
    good = analyze(GOOD, tv, None)
    bad = analyze(BAD, tv, None)
    expect_bad = ["A1", "A2", "A3", "A4", "A5"]

    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == expect_bad

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿       : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望五项全红   : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立：同一套探针在两种世界状态下产出不同结果。")
    return 0


# ------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="03b 组件库 质量检查器")
    ap.add_argument("source", nargs="?", help="components.json 路径")
    ap.add_argument("--tokens", dest="tokens", help="tokens.css / tokens.json（A4）")
    ap.add_argument("--html", dest="html", help="design-system.html（A5 一起扫）")
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

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}", file=sys.stderr)
        return 2

    token_vars = None
    if args.tokens:
        p = Path(args.tokens)
        if not p.exists():
            print(f"token 文件不存在: {p}", file=sys.stderr)
            return 2
        token_vars = collect_token_vars(read_code(p))

    html_text = None
    if args.html:
        p = Path(args.html)
        if not p.exists():
            print(f"HTML 不存在: {p}", file=sys.stderr)
            return 2
        html_text = read_code(p)

    result = analyze(data, token_vars, html_text)
    result["source"] = str(path)

    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2

    print(f"来源: {path.name}")
    print(f"组件总数: {result['componentCount']}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
        print(f"  [{mark}] {c['id']} {c['title']}")
        if c["status"] != "fail":
            continue
        ev = c["evidence"]
        if c["id"] == "A1":
            if ev["badFormat"]:
                print(f"         非 kebab-case: {ev['badFormat']}")
            if ev["duplicates"]:
                print(f"         重复 id: {ev['duplicates']}")
        elif c["id"] == "A2":
            for v in ev["missingFields"]:
                print(f"         {v['id']}: 缺 {', '.join(v['missing'])}")
            for v in ev["notVariableName"]:
                print(f"         {v['id']}: tokens 项 {v['token']!r} 不是变量名")
        elif c["id"] == "A3":
            for v in ev["violations"]:
                print(f"         {v['id']}（{v['category']}）: 缺 {', '.join(v['missing'])}")
        elif c["id"] == "A4":
            for v in ev["dangling"]:
                print(f"         {v['id']}: {v['token']} 在 token 集中不存在")
        elif c["id"] == "A5":
            for v in ev["literals"][:20]:
                print(f"         {v['source']}: 字面量色值 {v['value']}")
            if ev["total"] > 20:
                print(f"         …共 {ev['total']} 处")

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
