#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04 原型 · 高保真原型检查器
===========================
实现 04-prototype rubric 的 A 类判据。

用法:
    python check-prototype.py <designs/<项目> > [--json <输出路径>]
    python check-prototype.py --selftest

判据:
    A1  HTML 合法嵌套：<a> 不嵌套 <a>；<span> 内不含块级元素
    A2  离线包本地引用可达：href / src 中的本地相对路径目标必须存在
    A3  页面数与声明一致，且各处声明自洽
    A4  五端齐备：5 个端注册表，每端至少 1 页

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么 A2 只查 href / src 属性
------------------------------
首版按「任意 .html 字符串」扫描，结果两处全是假阳性：
  · `error-decoder.html` —— React 生产包自带的错误解码器引用，不是我们的链接
  · `index.html` —— 交付导航页里的一句正文「index.html 本页 · 交付导航台」
判据一旦把文档正文和第三方产物当成死链，人就会开始忽略它。
→ 收窄为只查**显式链接属性**。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCREENS_RE = re.compile(r"window\.(\w+)_SCREENS\s*=\s*\[")
CODE_RE = re.compile(r'code:\s*"([A-Z]+-\d+)"')
PAGE_DECL_RE = re.compile(r"(?:([一二三四五六七八九十])端)?\s*(\d+)\s*页")

# 硬约束表：`const HARD = [ ["序号", "约束正文", "落点页面"], ... ]`
HARD_RE = re.compile(r"const\s+HARD\s*=\s*\[(.*?)\n\s*\];", re.S)
HARD_ROW_RE = re.compile(
    r'\[\s*"(\d+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\]')
# 页面编号：先屏蔽 F-X-nn（其尾缀形如 U-01，会假命中），再用负向后顾
MASK_CARD_RE = re.compile(r"F-[A-Z]-\d+")
PROTO_PAGE_RE = re.compile(r"(?<![A-Za-z0-9-])([UMROC]-\d{2})(?!\d)")
WILDCARD_REF = ("全部", "全端", "所有端", "—", "-")# `(?:(?!/>)[^>])*` 只吃「不含 >、且不以 /> 收尾」的字符，从而跳过自闭合标签。
# 首版没排除自闭合，把 <span ... /> 后面的兄弟 <div> 当成了子节点 —— 5 处全是假阳性。
NEST_A_RE = re.compile(r"<a\b(?:(?!/>)[^>])*>((?:(?!</a>).)*?)<a\b", re.S)
BLOCK_IN_SPAN_RE = re.compile(
    r"<span\b(?:(?!/>)[^>])*>((?:(?!</span>).)*?)<(div|p|h[1-6])\b", re.S)
ATTR_RE = re.compile(r'\b(?:href|src)\s*=\s*"([^"]+)"')
EXTERNAL_PREFIX = ("http://", "https://", "//", "#", "mailto:", "data:", "javascript:")


def analyze(root: Path, upstream: set | None = None) -> dict:
    src = root / "src"
    offline = root / "离线版"
    jsx_files = sorted(src.glob("*.jsx")) if src.exists() else []
    if not jsx_files:
        return {"error": f"未在 {root} 下找到 src/*.jsx"}

    sources = {p.name: p.read_text(encoding="utf-8", errors="ignore") for p in jsx_files}
    checks = []

    # ---------- A1 HTML 合法嵌套 ----------
    offenders = []
    for name, txt in sources.items():
        for m in NEST_A_RE.finditer(txt):
            offenders.append({"file": name, "kind": "a 嵌套 a",
                              "line": txt[: m.start()].count("\n") + 1})
        for m in BLOCK_IN_SPAN_RE.finditer(txt):
            offenders.append({"file": name, "kind": f"span 内含 <{m.group(2)}>",
                              "line": txt[: m.start()].count("\n") + 1})
    checks.append({
        "id": "A1", "title": "JSX 嵌套合法（无 a 套 a / span 含块级）",
        "status": "pass" if not offenders else "fail",
        "evidence": {"scanned": len(sources), "offenders": offenders[:40]},
    })

    # ---------- A2 离线包本地引用可达 ----------
    broken, scanned_links = [], 0
    if offline.exists():
        for p in sorted(offline.glob("*.html")):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for m in ATTR_RE.finditer(txt):
                target = m.group(1).strip()
                if not target or target.startswith(EXTERNAL_PREFIX):
                    continue
                scanned_links += 1
                pure = target.split("#")[0].split("?")[0]
                if not pure:
                    continue
                if not (p.parent / pure).exists():
                    broken.append({"file": p.name, "target": target,
                                   "line": txt[: m.start()].count("\n") + 1})
    checks.append({
        "id": "A2", "title": "离线包 href / src 本地目标均存在",
        "status": "pass" if not broken else "fail",
        "evidence": {"scannedLinks": scanned_links, "broken": broken[:40]},
    })

    # ---------- A3 页面数与声明一致 ----------
    per_end, declared = {}, {}
    for name, txt in sources.items():
        for m in SCREENS_RE.finditer(txt):
            end = m.group(1)
            tail = txt[m.end():]
            stop = tail.find("\n  ];")
            if stop < 0:
                stop = tail.find("];")
            codes = CODE_RE.findall(tail[:stop if stop > 0 else len(tail)])
            per_end[end] = codes
        for m in PAGE_DECL_RE.finditer(txt):
            declared.setdefault(int(m.group(2)), []).append(name)
    total = sum(len(v) for v in per_end.values())
    decl_values = sorted(declared)
    consistent = len(decl_values) == 1
    ok = consistent and decl_values and decl_values[0] == total
    checks.append({
        "id": "A3", "title": "页面数与各处声明一致",
        "status": "pass" if ok else "fail",
        "evidence": {"actual": total, "perEnd": {k: len(v) for k, v in per_end.items()},
                     "declared": decl_values, "declaredAt": declared},
    })

    # ---------- A4 五端齐备 ----------
    empty = sorted(k for k, v in per_end.items() if not v)
    checks.append({
        "id": "A4", "title": "5 个端注册表且每端至少 1 页",
        "status": "pass" if len(per_end) == 5 and not empty else "fail",
        "evidence": {"ends": sorted(per_end), "count": len(per_end), "emptyEnds": empty},
    })

    # ---------- A5 硬约束落点可指认（原 B2 升级为 A 类） ----------
    # 判据来源：`const HARD` 的第二列是约束正文、第三列是**落点页面编号**。
    # 只要落点写成页面编号，这件事就是机械可查的 —— 那就没有理由推给人。
    hard_src, hard_rows = None, []
    for name, txt in sources.items():
        m = HARD_RE.search(txt)
        if m:
            hard_src = name
            for row in HARD_ROW_RE.finditer(m.group(1)):
                hard_rows.append({"no": row.group(1), "text": row.group(2),
                                  "ref": row.group(3), "file": name})
            break

    proto_pages = {c for codes in per_end.values() for c in codes}
    if not hard_rows:
        checks.append({
            "id": "A5", "title": "硬约束落点可指认",
            "status": "fail",
            "evidence": {"reason": "未找到 `const HARD` 硬约束表 —— "
                                   "样本为 0 判失败，不是「无事通过」"},
        })
    else:
        no_ref, not_in_proto, not_upstream, no_landing = [], [], [], []
        for h in hard_rows:
            raw = h["ref"].strip()
            if raw in WILDCARD_REF:
                continue
            ids = PROTO_PAGE_RE.findall(MASK_CARD_RE.sub("###", raw))
            if not ids:
                no_ref.append({"no": h["no"], "ref": raw, "file": h["file"]})
                continue
            resolved, missing = 0, []
            for pid in ids:
                if pid in proto_pages:
                    resolved += 1
                    continue
                missing.append(pid)
                rec = {"no": h["no"], "page": pid, "file": h["file"],
                       "text": h["text"][:28]}
                if upstream is not None and pid not in upstream:
                    not_upstream.append(rec)
                else:
                    not_in_proto.append(rec)
            # ★ 关键分层：一条约束列了多个落点，只要**还有**一个能解析，
            #   它就是「落点清单里有冗余页面」，**不是**「约束无处落地」。
            #   这两件事的修法完全不同 —— 混淆会让评审去改错的东西（AP-09 的同一个教训）。
            if resolved == 0 and missing:
                no_landing.append({"no": h["no"], "ref": raw, "file": h["file"],
                                   "missing": missing, "text": h["text"][:28]})

        bad_a5 = bool(no_ref or not_in_proto or not_upstream)
        checks.append({
            "id": "A5", "title": "硬约束落点可指认",
            "status": "fail" if bad_a5 else "pass",
            "evidence": {"source": hard_src, "constraintCount": len(hard_rows),
                         "protoPages": sorted(proto_pages),
                         "upstreamChecked": upstream is not None,
                         "noRef": no_ref, "notInPrototype": not_in_proto,
                         "notInUpstream": not_upstream, "noLanding": no_landing},
        })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {"totalChecks": len(checks), "passed": len(checks) - len(failed),
            "pages": total, "failed": failed, "checks": checks}


# --------------------------------------------------------------------------
GOOD_JSX = """
/* 五端 5 页 */
window.UC_SCREENS = [
  { code: "U-02", name: "首页", Comp: A },
];
window.MC_SCREENS = [
  { code: "M-02", name: "工作台", Comp: B },
];
window.RC_SCREENS = [
  { code: "R-02", name: "抢单", Comp: C },
];
window.OA_SCREENS = [
  { code: "O-11", name: "订单", Comp: D },
];
window.CS_SCREENS = [
  { code: "C-02", name: "工作台", Comp: E },
];
const HARD = [
  ["1", "某硬约束有落点", "U-02"],
  ["2", "另一约束作用于全部页面", "全部"],
];
"""

BAD_JSX = """
/* 五端 9 页 */
window.UC_SCREENS = [
  { code: "U-02", name: "首页", Comp: A },
];
window.MC_SCREENS = [
  { code: "M-02", name: "工作台", Comp: B },
];
window.RC_SCREENS = [
  { code: "R-02", name: "抢单", Comp: C },
];
window.OA_SCREENS = [];
const HARD = [
  ["1", "某硬约束落到了不存在的页面", "U-77"],
];
const bad = <a href="/x"><a href="/y">双链</a></a>;
const bad2 = <span><div>块级进 span</div></span>;
"""

GOOD_HTML = '<a href="设计系统.html">设计系统</a><link href="favicon.svg">'
BAD_HTML = '<a href="missing-page.html">死链</a>'


def _make(base: Path, jsx: str, html: str) -> Path:
    (base / "src").mkdir(parents=True, exist_ok=True)
    (base / "src" / "app.jsx").write_text(jsx, encoding="utf-8")
    off = base / "离线版"
    off.mkdir(parents=True, exist_ok=True)
    # 刻意保留中文文件名：离线包最容易出问题的一类就是「中文文件名链接改写」，
    # 换成 ASCII 会把这个坑测掉。
    (off / "交付导航.html").write_text(html, encoding="utf-8")
    (off / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (off / "设计系统.html").write_text("<html></html>", encoding="utf-8")
    return base


UPSTREAM = {"U-02", "M-02", "R-02", "O-11", "C-02", "M-07", "U-10"}


def selftest() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        good = analyze(_make(Path(d) / "g", GOOD_JSX, GOOD_HTML), UPSTREAM)
    with tempfile.TemporaryDirectory() as d:
        bad = analyze(_make(Path(d) / "b", BAD_JSX, BAD_HTML), UPSTREAM)

    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == ["A1", "A2", "A3", "A4", "A5"]
    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿            : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望 A1-A5 全红  : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="04 原型 · 高保真原型检查器")
    ap.add_argument("root", nargs="?")
    ap.add_argument("--pages", dest="pages",
                    help="交互文档 Markdown（A5 校验落点编号是否在上游存在）")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.root:
        ap.print_help()
        return 2

    root = Path(args.root)
    upstream = None
    if args.pages:
        up = Path(args.pages)
        if not up.exists():
            print(f"交互说明书不存在: {up}", file=sys.stderr)
            return 2
        txt = MASK_CARD_RE.sub("###", up.read_text(encoding="utf-8"))
        upstream = set(PROTO_PAGE_RE.findall(txt))
    result = analyze(root, upstream)
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2
    result["root"] = str(root)

    print(f"注册页面数 : {result['pages']}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "pass" else "FAIL"
        print(f"  [{mark}] {c['id']} {c['title']}")
        ev = c["evidence"]
        if c["id"] == "A1" and c["status"] == "fail":
            for o in ev["offenders"]:
                print(f"         {o['file']}:{o['line']}  {o['kind']}")
        elif c["id"] == "A2" and c["status"] == "fail":
            for o in ev["broken"]:
                print(f"         {o['file']}:{o['line']}  → {o['target']}（不存在）")
        elif c["id"] == "A3":
            print(f"         实际 {ev['actual']} 页；分端 {ev['perEnd']}")
            print(f"         声明 {ev['declared']}；出处 {ev['declaredAt']}")
        elif c["id"] == "A4":
            print(f"         端注册表 {ev['ends']}（{ev['count']} 个）")
        elif c["id"] == "A5":
            if ev.get("reason"):
                print(f"         {ev['reason']}")
            else:
                tag = "已启用" if ev["upstreamChecked"] else "未启用（未传 --pages）"
                print(f"         硬约束 {ev['constraintCount']} 条"
                      f"（取自 {ev['source']}；上游比对 {tag}）")
                for o in ev["noRef"]:
                    print(f"         #{o['no']} 未写页面落点：{o['ref']!r}")
                for o in ev["noLanding"]:
                    print(f"         🔴 #{o['no']} **无任何可解析落点** "
                          f"（{', '.join(o['missing'])} 均不存在）：{o['text']}")
                for o in ev["notInUpstream"]:
                    print(f"         #{o['no']} 落点 {o['page']} 上游不存在（真悬空）：{o['text']}")
                for o in ev["notInPrototype"]:
                    print(f"         #{o['no']} 落点 {o['page']} 上游有、本原型未实现"
                          f"（仍有其他落点）：{o['text']}")

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
