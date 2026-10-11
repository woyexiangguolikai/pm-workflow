#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03 设计 · 设计令牌检查器
=========================
实现 03-design rubric 的 A 类判据 —— 可脚本化、必须自动判。

用法:
    python check-design-tokens.py <designs/<项目> > [--json <输出路径>]
    python check-design-tokens.py --selftest

判据:
    A1  主色单一事实源：品牌主色值全仓只允许出现一处（token 定义处）
    A2  Token 逃逸：除 tokens.css 外的文件不得复制 token 色值
    A3  深色主题完整性：--bg-* / --text-* / --border* 必须全部被深色主题覆盖
    A4  正文对比度：--text-1 / --text-2 在 --bg-page / --bg-surface 上 ≥ 4.5:1

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么 A1 是这里最重要的一条
----------------------------
tokens.css 的文件头写着「改主色只需改 --brand-500 一处」。
这是一个**可被证伪的承诺** —— 只要任何地方出现了该色值的另一种写法
（hex / rgb() / rgba()），承诺就是假的，而使用者不会知道。
把承诺变成检查，是 rubric 存在的意义。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

COLOR_RE = re.compile(
    r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b"
    r"|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)"
)
VAR_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
BLOCK_RE = r"\s*\{([^}]*)\}"
TEXT_WHITELIST = {"transparent", "currentcolor", "inherit", "none"}

SKIP_DIRS = {"vendor", "离线版", "node_modules", ".git"}


def parse_color(s: str):
    """把 #RGB / #RRGGBB / rgb() / rgba() / "R G B" 分量归一化成 (r, g, b)。"""
    s = s.strip()
    if s.lower() in TEXT_WHITELIST:
        return None
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return None
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", s)
    if m:
        return tuple(int(x) for x in m.groups())
    # 空格分隔的 RGB 分量（如 --brand-rgb: 228 87 46），供 rgb(var(--x) / a) 派生
    m = re.match(r"^(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})$", s)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def to_hex(rgb) -> str:
    return "#%02X%02X%02X" % rgb


def read_code(p: Path) -> str:
    """读文件并剥离块注释（用等长空白替换，行号保持不变）。

    注释里的色值提及是**文档**，不是样式定义 —— 例如
    `/* 主色分量：唯一色值事实源。原 hex = #E4572E */`。
    不剥离就会把说明文字判成「复制」，属假阳性，与 HTML 里的正文提及同性质。
    """
    txt = p.read_text(encoding="utf-8", errors="ignore")
    if p.suffix.lower() in (".css", ".jsx", ".js"):
        txt = re.sub(r"/\*.*?\*/",
                     lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                     txt, flags=re.S)
    return txt


def block_vars(css: str, selector: str) -> dict:
    """取某个选择器块内的自定义属性。"""
    m = re.search(re.escape(selector) + BLOCK_RE, css, re.S)
    if not m:
        return {}
    return {k: v.strip() for k, v in VAR_RE.findall(m.group(1))}


def resolve_rgb(name: str, vars_: dict, depth: int = 0):
    """沿 var() 引用链解析到具体色值。"""
    if depth > 12:
        return None
    raw = vars_.get(name)
    if raw is None:
        return None
    # rgb(var(--x)) / rgb(var(--x) / a) —— 由分量变量派生的色值
    m = re.match(r"rgba?\(\s*var\(\s*(--[\w-]+)", raw)
    if m:
        return resolve_rgb(m.group(1), vars_, depth + 1)
    m = re.match(r"var\(\s*(--[\w-]+)", raw)
    if m:
        return resolve_rgb(m.group(1), vars_, depth + 1)
    return parse_color(raw)


def rel_lum(rgb) -> float:
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def iter_scan_files(root: Path, token_file: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in (".css", ".jsx", ".js", ".html", ".htm"):
            continue
        if p == token_file:
            continue
        yield p


def analyze(root: Path) -> dict:
    token_file = root / "assets" / "tokens.css"
    if not token_file.exists():
        hits = list(root.rglob("tokens.css"))
        if not hits:
            return {"error": f"未在 {root} 下找到 tokens.css"}
        token_file = hits[0]

    css = read_code(token_file)
    light = block_vars(css, ":root")
    dark = block_vars(css, '[data-theme="dark"]')
    checks = []

    # 主色：优先 --brand-500，退回 --brand
    brand_hex = None
    n = 500
    while n >= 50:
        rgb = resolve_rgb(f"--brand-{n}", light)
        if rgb:
            brand_hex = to_hex(rgb)
            break
        n -= 50
    if brand_hex is None:
        rgb = resolve_rgb("--brand", light)
        brand_hex = to_hex(rgb) if rgb else None

    # ---------- A1 主色单一事实源 ----------
    # 只统计「样式与渲染代码」(.css/.jsx/.js) 里的复制 —— 那里的硬编码必然导致换色失效。
    # HTML 正文里的提及（如交付说明里写「当前用的是 #E4572E」）是文档，性质不同，
    # 单独归入 documentMentions，不参与判定。否则判据会因文档而假红。
    occurrences, mentions = [], []
    if brand_hex:
        target = parse_color(brand_hex)
        rel_token = token_file.relative_to(root).as_posix()
        for p in [token_file] + list(iter_scan_files(root, token_file)):
            txt = read_code(p)
            rel = p.relative_to(root).as_posix()
            is_code = p.suffix.lower() in (".css", ".jsx", ".js")
            for m in COLOR_RE.finditer(txt):
                if parse_color(m.group(0)) != target:
                    continue
                line = txt[: m.start()].count("\n") + 1
                snippet = txt.splitlines()[line - 1].strip()[:110]
                if rel == rel_token and re.search(r"--brand(?:-500|-rgb)?\s*:", snippet):
                    continue
                item = {"file": rel, "line": line,
                        "raw": m.group(0).strip(), "snippet": snippet}
                (occurrences if is_code else mentions).append(item)
    checks.append({
        "id": "A1", "title": f"主色 {brand_hex or '?'} 单一事实源（样式代码中 0 处复制）",
        "status": "pass" if brand_hex and not occurrences else "fail",
        "evidence": {"brand": brand_hex, "extraOccurrences": occurrences,
                     "documentMentions": mentions},
    })

    # ---------- A2 Token 逃逸（复制 token 色值） ----------
    # 豁免两类，否则判据会因通用写法而假红：
    #   ① 纯黑 / 纯白 —— 是通用底色，不是"色板成员"，几乎不会随设计变更而改
    #   ② rgba(...) —— 表达的是透明度叠加，语义与色板色值不同
    token_values = {}
    for k, v in light.items():
        rgb = parse_color(v)
        if rgb:
            token_values.setdefault(to_hex(rgb), []).append(k)
    escaped = []
    for p in iter_scan_files(root, token_file):
        if p.suffix.lower() not in (".css", ".jsx", ".js"):
            continue  # HTML 里的色值提及属文档，与 A1 口径保持一致
        txt = read_code(p)
        rel = p.relative_to(root).as_posix()
        for m in COLOR_RE.finditer(txt):
            raw = m.group(0).strip()
            if raw.lower().startswith("rgba("):
                continue
            c = parse_color(raw)
            if not c or c in ((0, 0, 0), (255, 255, 255)):
                continue
            h = to_hex(c)
            if h in token_values:
                line = txt[: m.start()].count("\n") + 1
                escaped.append({"file": rel, "line": line, "value": raw,
                                "equalsToken": token_values[h][:3],
                                "snippet": txt.splitlines()[line - 1].strip()[:110]})
    checks.append({
        "id": "A2", "title": "除 tokens.css 外无复制 token 色值（豁免纯黑白与 rgba 叠加）",
        "status": "pass" if not escaped else "fail",
        "evidence": {"count": len(escaped), "escaped": escaped[:60]},
    })

    # ---------- A3 深色主题完整性 ----------
    # 排除 --text-on-* ：它的语义是「某底色之上的文字色」，跟随那个底色（品牌色）而非主题。
    # 深色主题不覆盖它是对的，不应判红。
    required = [k for k in light if k.startswith(("--bg-", "--text-", "--border"))
                and not k.startswith("--text-on-")]
    missing = sorted(k for k in required if k not in dark)
    checks.append({
        "id": "A3", "title": "深色主题覆盖全部 --bg-* / --text-* / --border*（不含 --text-on-*）",
        "status": "pass" if not missing else "fail",
        "evidence": {"required": len(required), "missing": missing},
    })

    # ---------- A4 正文对比度 ----------
    pairs = [("--text-1", "--bg-page"), ("--text-1", "--bg-surface"),
             ("--text-2", "--bg-page"), ("--text-2", "--bg-surface")]
    results, below = [], []
    for fg, bg in pairs:
        a, b = resolve_rgb(fg, light), resolve_rgb(bg, light)
        if not a or not b:
            continue
        r = contrast_ratio(a, b)
        results.append({"fg": fg, "bg": bg, "ratio": round(r, 2)})
        if r < 4.5:
            below.append({"fg": fg, "bg": bg, "ratio": round(r, 2)})
    # 参考值（不参与判定）：辅助与占位文字
    advisory = []
    for fg in ("--text-3", "--text-4"):
        a, b = resolve_rgb(fg, light), resolve_rgb("--bg-page", light)
        if a and b:
            advisory.append({"fg": fg, "bg": "--bg-page",
                             "ratio": round(contrast_ratio(a, b), 2)})
    checks.append({
        "id": "A4", "title": "正文文字对比度 ≥ 4.5:1",
        "status": "pass" if not below else "fail",
        "evidence": {"measured": results, "belowThreshold": below,
                     "advisoryNotJudged": advisory},
    })

    # ---------- A5 游离色值 ----------
    # "游离色"= 代码里出现的不透明色值，既不等于任何 token 的值，也不在 tokens.css 里。
    # 它意味着设计系统之外还偷偷长了颜色 —— 换主题时无人知道要动它。
    all_token_hex = set(token_values.keys())
    for v in dark.values():
        rgb = parse_color(v)
        if rgb:
            all_token_hex.add(to_hex(rgb))
    strays = []
    for p in iter_scan_files(root, token_file):
        if p.suffix.lower() not in (".css", ".jsx", ".js"):
            continue
        txt = read_code(p)
        rel = p.relative_to(root).as_posix()
        for m in COLOR_RE.finditer(txt):
            raw = m.group(0).strip()
            if raw.lower().startswith("rgba("):
                continue
            c = parse_color(raw)
            if not c or c in ((0, 0, 0), (255, 255, 255)):
                continue
            if to_hex(c) not in all_token_hex:
                line = txt[: m.start()].count("\n") + 1
                strays.append({"file": rel, "line": line, "value": raw,
                               "snippet": txt.splitlines()[line - 1].strip()[:110]})
    checks.append({
        "id": "A5", "title": "代码中无不透明游离色值（色值全部来自 token）",
        "status": "pass" if not strays else "fail",
        "evidence": {"count": len(strays), "strays": strays[:60]},
    })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {"tokenFile": str(token_file), "brand": brand_hex,
            "tokenCount": len(light), "darkTokenCount": len(dark),
            "totalChecks": len(checks), "passed": len(checks) - len(failed),
            "failed": failed, "checks": checks}


# --------------------------------------------------------------------------
GOOD_CSS = """
:root {
  --brand-500: #E4572E;
  --n-900: #171412;
  --n-600: #56504B;
  --bg-page: var(--n-50);
  --n-50: #F8F5F2;
  --bg-surface: #FFFFFF;
  --text-1: var(--n-900);
  --text-2: var(--n-600);
  --border: #DED8D2;
}
[data-theme="dark"] {
  --bg-page: #17130F;
  --bg-surface: #211B16;
  --text-1: #F5F0EA;
  --text-2: #C4BAB0;
  --border: #3A312A;
}
"""

BAD_CSS = """
:root {
  --brand-500: #E4572E;
  --n-900: #171412;
  --n-600: #56504B;
  --bg-page: #F8F5F2;
  --bg-surface: #FFFFFF;
  --text-1: var(--n-900);
  --text-2: var(--n-600);
  --border: #DED8D2;
  --ring-brand: 0 0 0 3px rgba(228,87,46,.18);
}
[data-theme="dark"] {
  --bg-page: #17130F;
}
"""

BAD_JSX = 'const x = <div style={{color:"#56504B"}}/>;\nconst y = <b style={{color:"#123456"}}/>;'
GOOD_JSX = 'const x = <div style={{color:"var(--text-2)"}}/>;'


def _write(tmp: Path, css: str, jsx: str) -> Path:
    (tmp / "assets").mkdir(parents=True, exist_ok=True)
    (tmp / "assets" / "tokens.css").write_text(css, encoding="utf-8")
    (tmp / "src").mkdir(parents=True, exist_ok=True)
    (tmp / "src" / "a.jsx").write_text(jsx, encoding="utf-8")
    return tmp


def selftest() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        good = analyze(_write(tmp / "g", GOOD_CSS, GOOD_JSX))
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        bad = analyze(_write(tmp / "b", BAD_CSS, BAD_JSX))

    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == ["A1", "A2", "A3", "A5"]
    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿     : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望 A1/A2/A3/A5 红 : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="03 设计 · 设计令牌检查器")
    ap.add_argument("root", nargs="?", help="designs/<项目> 目录")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.root:
        ap.print_help()
        return 2

    root = Path(args.root)
    result = analyze(root)
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2
    result["root"] = str(root)

    print(f"tokens.css : {result['tokenFile']}")
    print(f"主色       : {result['brand']}")
    print(f"token 总数 : {result['tokenCount']}（深色主题覆盖 {result['darkTokenCount']}）")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "pass" else "FAIL"
        print(f"  [{mark}] {c['id']} {c['title']}")
        ev = c["evidence"]
        if c["id"] == "A1" and c["status"] == "fail":
            for o in ev["extraOccurrences"]:
                print(f"         {o['file']}:{o['line']}  {o['raw']}")
                print(f"           {o['snippet']}")
            for o in ev.get("documentMentions", []):
                print(f"         (文档提及，不判定) {o['file']}:{o['line']}  {o['raw']}")
        elif c["id"] == "A2" and c["status"] == "fail":
            print(f"         复制 token 色值 {ev['count']} 处")
            for e in ev["escaped"][:15]:
                print(f"         {e['file']}:{e['line']}  {e['value']}"
                      f"  == {','.join(e['equalsToken'])}")
        elif c["id"] == "A5" and c["status"] == "fail":
            print(f"         游离色值 {ev['count']} 处")
            for e in ev["strays"][:15]:
                print(f"         {e['file']}:{e['line']}  {e['value']}")
                print(f"           {e['snippet']}")
        elif c["id"] == "A3":
            if ev["missing"]:
                print(f"         未覆盖 {len(ev['missing'])} 项: {', '.join(ev['missing'])}")
        elif c["id"] == "A4":
            for m in ev["measured"]:
                print(f"         {m['fg']} on {m['bg']}: {m['ratio']}:1")
            for m in ev["advisoryNotJudged"]:
                print(f"         (参考，不判定) {m['fg']} on {m['bg']}: {m['ratio']}:1")

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
