#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03 设计 · 设计令牌检查器
=========================
实现 03-design rubric 的 A 类判据 —— 可脚本化、必须自动判。

用法:
    python check-design-tokens.py <designs/<项目> > [--spec <交互说明书.md>]
                                   [--ui <公共组件源码文件或目录>] [--json <输出路径>]
    python check-design-tokens.py --selftest

判据:
    A1  主色单一事实源：品牌主色值全仓只允许出现一处（token 定义处）
    A2  Token 逃逸：除 tokens.css 外的文件不得复制 token 色值
    A3  深色主题完整性：--bg-* / --text-* / --border* 必须全部被深色主题覆盖
    A4  正文对比度：--text-1 / --text-2 在 --bg-page / --bg-surface 上 ≥ 4.5:1
    A5  无游离色值：不透明色值必须全部来自 token
    A6  公共组件声明与实现可机械对齐（+ 四态齐备）；需 --spec

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么 A1 是这里最重要的一条
----------------------------
tokens.css 的文件头写着「改主色只需改 --brand-500 一处」。
这是一个**可被证伪的承诺** —— 只要任何地方出现了该色值的另一种写法
（hex / rgb() / rgba()），承诺就是假的，而使用者不会知道。
把承诺变成检查，是 rubric 存在的意义。

A6 是同一类承诺的另一处
------------------------
交互说明书 §6 开篇写着这些组件名存在的目的是「便于设计稿与代码对齐」。
名字对不上，承诺就是假的 —— 设计师拿着 `MoneyText` 去代码里搜，搜不到，
而文档不会报错。**把承诺变成检查，同样适用。**
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


# --------------------------------------------------------------------------
# A6 用的解析：公共组件「声明侧」= 交互说明书第六章；「实现侧」= 设计系统源码
#
# 声明侧有三种书写形态（都实测存在于真实文档，不是猜的）：
#   ① 表头行含「组件名」列          `| 状态 | 使用场景 | 设计要求 | 组件名 |`
#   ② 行首标签行（2 列表格的末行）   `| 组件名 | \`MoneyText\`（含 \`precision\`…） |`
#   ③ 加粗引导行                    `**组件名**：\`ConfirmDialog\`（…）`
# 不一律要求某一种 —— 三种都是「把组件名列出来」的稳定写法；
# 但**解析不到任何声明就判失败**，否则差集在空集上恒真。
#
# 别名登记写法（唯一）：
#   `` `声明名`（实现 `实现名`） `` —— 紧跟声明名之后。
# 允许别名是必需的：`EmptyState` / `ErrorState` 在实现里都是 `State`（用 art 区分），
# 把声明侧改成 `State` 会**丢掉「四态」这个信息**，改名不是正确答案。
SPEC_HEADING_RE = re.compile(r"^##\s*六[、.．]")
SPEC_SUB_RE = re.compile(r"^###\s*(\d+\.\d+)\s*(.*)")
SPEC_FOUR_STATE_RE = re.compile(r"四态|四态组件")
COMP_QUOTED_RE = re.compile(r"`([A-Z][A-Za-z0-9]*)`")
COMP_ALIAS_RE = re.compile(r"`([A-Z][A-Za-z0-9]*)`\s*[（(]\s*实现\s*`([A-Z][A-Za-z0-9]*)`")
COMP_FN_RE = re.compile(r"\bfunction\s+([A-Z][A-Za-z0-9]*)\s*\(")
COMP_EXPORT_RE = re.compile(r"\bwindow\.([A-Z][A-Za-z0-9]*)\s*=")


def _is_sep_row(cells: list[str]) -> bool:
    return bool(cells) and set("".join(cells)) <= set("-: ")


def parse_declared_components(text: str) -> dict:
    """从交互说明书第六章取「声明名 -> {alias, section, line}」。

    只认三种明确形态，不做全文 CamelCase 扫 —— 那会把正文里顺手提到的名字
    也算成声明（假阳性）。**判据不能把「提及」读成「声明」。**
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if SPEC_HEADING_RE.match(l)), None)
    if start is None:
        return {}
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))

    found: dict[str, dict] = {}
    sec = None
    hdr_col = None

    def take(raw: str, ln: int):
        for m in COMP_ALIAS_RE.finditer(raw):
            found.setdefault(m.group(1), {"alias": m.group(2), "section": sec, "line": ln})
        for m in COMP_QUOTED_RE.finditer(raw):
            found.setdefault(m.group(1), {"alias": None, "section": sec, "line": ln})

    for i in range(start, end):
        raw = lines[i]
        st = raw.strip()
        m = SPEC_SUB_RE.match(st)
        if m:
            sec, hdr_col = m.group(1), None
            continue
        if not sec:
            continue
        if st.startswith("|"):
            cells = [c.strip() for c in st.strip("|").split("|")]
            if _is_sep_row(cells):
                continue
            # ② 行首标签行
            if cells and cells[0].strip("*") == "组件名":
                take(" ".join(cells[1:]), i + 1)
                continue
            # ① 表头行（下一行是分隔行）且含「组件名」列
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            nxt_cells = [c.strip() for c in nxt.strip("|").split("|")] if nxt.startswith("|") else []
            if _is_sep_row(nxt_cells) and "组件名" in cells:
                hdr_col = cells.index("组件名")
                continue
            if hdr_col is not None and hdr_col < len(cells):
                take(cells[hdr_col], i + 1)
            continue
        # ③ 加粗引导行
        m = re.match(r"^\*\*组件名\*\*\s*[：:]\s*(.*)", st)
        if m:
            take(m.group(1), i + 1)
    return found


def count_four_state_rows(text: str) -> int | None:
    """定位标题含「四态」的小节，数它有「组件名」的表格行。找不到小节返回 None。"""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and SPEC_HEADING_RE.match(l)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    sec_start = None
    for i in range(start, end):
        m = SPEC_SUB_RE.match(lines[i].strip())
        if m:
            if sec_start is not None:
                break
            if SPEC_FOUR_STATE_RE.search(m.group(2)):
                sec_start = i
    if sec_start is None:
        return None
    sec_end = next((i for i in range(sec_start + 1, end) if SPEC_SUB_RE.match(lines[i].strip())), end)

    n = 0
    hdr_col = None
    for i in range(sec_start, sec_end):
        st = lines[i].strip()
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if _is_sep_row(cells):
            continue
        if "组件名" in cells and _is_sep_row(
                [c.strip() for c in (lines[i + 1].strip().strip("|").split("|"))] if i + 1 < len(lines) else []):
            hdr_col = cells.index("组件名")
            continue
        if hdr_col is not None and hdr_col < len(cells) and COMP_QUOTED_RE.search(cells[hdr_col]):
            n += 1
    return n


def parse_impl_components(path: Path) -> dict:
    """实现侧：源码里 `function Xxx(` 定义的组件（外加 `window.Xxx =` 导出）。"""
    out: dict[str, list[str]] = {}
    files = [path] if path.is_file() else sorted(path.glob("*.jsx"))
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in COMP_FN_RE.finditer(line):
                out.setdefault(m.group(1), []).append(f"{f.name}:{i}")
            for m in COMP_EXPORT_RE.finditer(line):
                out.setdefault(m.group(1), []).append(f"{f.name}:{i}")
    return out


def analyze(root: Path, spec: Path | None = None, ui: Path | None = None) -> dict:
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

    # ---------- A6 公共组件声明与实现可机械对齐 ----------
    # B4「组件状态齐备」升级而来。判的是**两侧能不能机械对上**，不是「好不好看」：
    # 交互说明书 §6 开篇自己写着「前端对应组件命名建议写在每项末尾的括号中，
    # 便于设计稿与代码对齐」—— 那这个声明就必须是**可核对的**，否则该目的落空。
    ui_path = ui or (root / "src" / "ui.jsx")
    if not ui_path.exists():
        ui_path = root / "src"
    if spec is None or not Path(spec).exists():
        checks.append({
            "id": "A6", "title": "公共组件声明与实现可机械对齐",
            "status": "skip",
            "evidence": {"reason": "未提供 --spec（交互说明书），无法取声明侧"},
        })
    else:
        declared = parse_declared_components(Path(spec).read_text(encoding="utf-8"))
        impl = parse_impl_components(Path(ui_path)) if Path(ui_path).exists() else {}
        four = count_four_state_rows(Path(spec).read_text(encoding="utf-8"))

        if not declared or not impl:
            # 控制项。任一侧解析为空，差集必然为空 —— 那不是「对齐」，是没看。
            checks.append({
                "id": "A6", "title": "公共组件声明与实现可机械对齐",
                "status": "fail",
                "evidence": {"reason": "两侧样本为空，差集恒真，故直接判失败",
                             "declaredCount": len(declared), "implCount": len(impl),
                             "spec": str(spec), "ui": str(ui_path)},
            })
        else:
            unmatched, aliased = [], []
            for name, meta in sorted(declared.items()):
                if name in impl:
                    continue
                tgt = meta["alias"]
                if tgt and tgt in impl:
                    aliased.append({"name": name, "alias": tgt, "line": meta["line"],
                                    "impl": impl[tgt][:2]})
                    continue
                unmatched.append({"name": name, "section": meta["section"], "line": meta["line"],
                                  "alias": tgt,
                                  "aliasMissing": bool(tgt) and tgt not in impl})
            # 四态齐备：不按节号定位（重编号就失效），按标题里有没有「四态」定位
            four_bad = (four is None) or (four != 4)
            bad = bool(unmatched) or four_bad
            checks.append({
                "id": "A6", "title": "公共组件声明与实现可机械对齐",
                "status": "fail" if bad else "pass",
                "evidence": {
                    "spec": str(spec), "ui": str(ui_path),
                    "declaredCount": len(declared), "implCount": len(impl),
                    "unmatched": unmatched, "aliased": aliased,
                    "implOnly": sorted(n for n in impl if n not in declared)[:40],
                    "fourStateRows": four,
                    "reason": ("未找到标题含「四态」的小节" if four is None
                               else f"「四态」小节只解析出 {four} 个含组件名的状态行") if four_bad else None,
                },
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

# ---------------------------------------------------------------- A6 样本
UI_GOOD = """
function EmptyState({}) {}
function Skeleton({}) {}
function ErrorState({}) {}
function NetworkBanner({}) {}
function MoneyText({ value }) {}
function ConfirmDialog({}) {}
"""

SPEC_GOOD = """
## 六、公共组件与设计规范

### 6.1 状态组件（四态，每页必配）

| 状态 | 使用场景 | 设计要求 | 组件名 |
|---|---|---|---|
| 空状态 | 列表无数据 | 插画 + 一个动作 | `EmptyState` |
| 加载态 | 首次加载 | 骨架屏 | `Skeleton` |
| 错误态 | 请求失败 | 原因 + 重试 | `ErrorState` |
| 网络异常态 | 弱网 | 常驻提示条 | `NetworkBanner` |

### 6.2 金额展示规范

| 规则 | 要求 |
|---|---|
| 精度 | 一律到分 |
| 组件名 | `MoneyText` |

### 6.4 二次确认规范

| 操作类型 | 是否二次确认 |
|---|---|
| 不可逆 / 涉及资金 | 必须 |

**组件名**：`ConfirmDialog`（`riskLevel: normal | high | critical`）

## 七、页面状态矩阵
"""

SPEC_UNMATCHED = SPEC_GOOD.replace("`MoneyText`", "`MoneyBadge`")
UI_RENAMED_ONLY = UI_GOOD.replace("function MoneyText(", "function Money(")
SPEC_ALIASED = SPEC_GOOD.replace("`MoneyText`", "`MoneyText`（实现 `Money`）")
SPEC_THREE_STATES = SPEC_GOOD.replace("| 网络异常态 | 弱网 | 常驻提示条 | `NetworkBanner` |\n", "")
SPEC_NO_NAMES = "## 六、公共组件与设计规范\n\n### 6.1 状态组件（四态，每页必配）\n\n（本节暂无组件名声明）\n\n## 七、页面状态矩阵\n"


def _write(tmp: Path, css: str, jsx: str, ui: str = "", spec: str = "") -> Path:
    (tmp / "assets").mkdir(parents=True, exist_ok=True)
    (tmp / "assets" / "tokens.css").write_text(css, encoding="utf-8")
    (tmp / "src").mkdir(parents=True, exist_ok=True)
    (tmp / "src" / "a.jsx").write_text(jsx, encoding="utf-8")
    if ui:
        (tmp / "src" / "ui.jsx").write_text(ui, encoding="utf-8")
    if spec:
        (tmp / "spec.md").write_text(spec, encoding="utf-8")
    return tmp


def selftest() -> int:
    import tempfile

    def run(css, jsx, ui="", spec=""):
        with tempfile.TemporaryDirectory() as d:
            tmp = _write(Path(d) / "x", css, jsx, ui, spec)
            sp = (tmp / "spec.md") if spec else None
            return analyze(tmp, spec=sp)

    good = run(GOOD_CSS, GOOD_JSX, UI_GOOD, SPEC_GOOD)
    bad = run(BAD_CSS, BAD_JSX, UI_RENAMED_ONLY, SPEC_UNMATCHED)

    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == ["A1", "A2", "A3", "A5", "A6"]

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿            : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望 A1/A2/A3/A5/A6 红 : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")

    # ------------------------------------------------ A6 专项：五条路径各要一个反例
    # 只让「未对齐」有反例是不够的 —— 控制项与别名机制如果不各有一个反例，
    # 它们是不是真的接上了线，没人知道。
    def a6_status(css, jsx, ui="", spec=""):
        r = run(css, jsx, ui, spec)
        for c in r["checks"]:
            if c["id"] == "A6":
                return c["status"], c["evidence"].get("reason") or ""
        return "missing", ""

    a6_cases = [
        ("控制项·声明侧为空", GOOD_CSS, GOOD_JSX, UI_GOOD, SPEC_NO_NAMES, "fail"),
        ("控制项·实现侧为空", GOOD_CSS, GOOD_JSX, "", SPEC_GOOD, "fail"),
        ("未对齐（无别名）", GOOD_CSS, GOOD_JSX, UI_RENAMED_ONLY, SPEC_UNMATCHED, "fail"),
        ("别名登记救回", GOOD_CSS, GOOD_JSX, UI_RENAMED_ONLY, SPEC_ALIASED, "pass"),
        ("四态只有 3 行", GOOD_CSS, GOOD_JSX, UI_GOOD, SPEC_THREE_STATES, "fail"),
    ]
    ok_a6 = True
    for name, css, jsx, ui, spec, expect in a6_cases:
        got, reason = a6_status(css, jsx, ui, spec)
        hit = got == expect
        ok_a6 = ok_a6 and hit
        print(f"  A6 反例「{name}」: {'通过' if hit else '失败'}"
              f"  (期望 {expect} / 实得 {got})")

    if not (ok_good and ok_bad and ok_a6):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="03 设计 · 设计令牌检查器")
    ap.add_argument("root", nargs="?", help="designs/<项目> 目录")
    ap.add_argument("--spec", dest="spec", help="交互说明书 Markdown（A6 声明侧）")
    ap.add_argument("--ui", dest="ui", help="公共组件源码文件或目录（A6 实现侧，默认 src/ui.jsx）")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.root:
        ap.print_help()
        return 2

    root = Path(args.root)
    result = analyze(root, spec=Path(args.spec) if args.spec else None,
                     ui=Path(args.ui) if args.ui else None)
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
        elif c["id"] == "A6":
            if ev.get("reason"):
                print(f"         {ev['reason']}")
            if ev.get("declaredCount") is not None:
                print(f"         声明侧 {ev['declaredCount']} 个 / 实现侧 {ev['implCount']} 个"
                      f"  · 四态行 {ev.get('fourStateRows')}")
            for u in ev.get("unmatched", []):
                extra = (f"（登记的别名 {u['alias']} 也不存在）" if u.get("aliasMissing")
                         else (f"（登记了别名 {u['alias']}）" if u.get("alias") else ""))
                print(f"         {u['name']}  声明于 {u['section']} · 第 {u['line']} 行{extra}")
            if ev.get("aliased"):
                print(f"         (已登记别名，判定通过) "
                      + ", ".join(f"{a['name']}→{a['alias']}" for a in ev["aliased"]))

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
