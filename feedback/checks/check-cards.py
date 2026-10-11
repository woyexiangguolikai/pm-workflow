#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06 需求卡片画布 质量检查器 · 对《卡片文档》执行 A1–A6
============================================================
实现 06-cards rubric 的 A 类判据 —— 可脚本化、必须自动判、不许推给人。

用法:
    python check-cards.py <卡片文档.md>
                          [--features <需求清单.md>] [--pages <交互文档.md>]
                          [--json <输出路径>]
    python check-cards.py --selftest        # 变异测试：证明检查有判别力

判据:
    A1  卡编号与功能列表一一对应（差集为空）
    A2  每卡六段齐全
    A3  关联四类逐类表态且非空
    A4  涉及端取值在闭集内（UC/MC/RC/OA/CS/SVC）
    A5  优先级与对应 FR 与功能列表一致（防末层副本漂移）
    A6  页面流转引用的页面编号在上游存在

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么这里的判据都是「取差集 / 逐条比对」
------------------------------------------
卡片层是交付链的**末层**，它把前面每一层的内容再抄一遍。它引用上游，不定义上游。
所以这里的核心风险不是「卡片写得不好看」，而是**末层副本悄悄漂移** ——
优先级抄错、FR 抄成另一个、页面编号指向不存在的页。前面全对也救不回来。

为什么 A5 不判「引用本身是否合法」
-----------------------------------
`F-M-41` 的对应 FR 写成 `8.3`（不是 FR 编号）是 **01 阶段的缺陷**，由 01 的 A5 报。
本阶段只判「卡片与上游是否一致」。若每个阶段都重新校验引用合法性，
同一个问题会被报 6 次 → 人会整体忽略这条判据 → **判据被无视一次就永久失效**。
**同一缺陷只在一个阶段报。**

踩过的坑（与 rubric 的「两个已知坑」对应）
--------------------------------------------
1. **编号互相包含**：`F-U-01` 里含子串 `U-01`。用 `\\bU-\\d{2}\\b` 提页面号，
   会把 207 个卡号全当成页面号（实测多报 100+）。
   → 先屏蔽 `F-[A-Z]-\\d+`，再用负向后顾 `(?<![A-Za-z0-9-])`。
2. **段名出现在字段定义章节**：第二章也写着这些段名，全文 grep 计数会多 3–5 个。
   → **先切卡片块，再在块内解析**。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

END_CODES = ("UC", "MC", "RC", "OA", "CS", "SVC")

CARD_HEAD_RE = re.compile(r"^####\s+(F-[UMROC]-\d+)\s+(.*)$")
SECTION_RE = re.compile(r"^#{2,3}\s")
FIELD_RE = {
    "优先级 / 对应 FR": re.compile(r"\*\*优先级\s*/\s*对应\s*FR\*\*\s*[：:]\s*(.*)"),
    "需求要点": re.compile(r"\*\*需求要点\*\*\s*[：:]\s*(.*)"),
    "关联与数据来源": re.compile(r"\*\*关联与数据来源\*\*\s*[：:]\s*(.*)"),
    "变更影响面": re.compile(r"\*\*变更影响面\*\*\s*[：:]\s*(.*)"),
    "页面流转": re.compile(r"\*\*页面流转\*\*\s*[：:]\s*(.*)"),
}
LINK_CLASSES = ("功能依赖", "数据来源", "状态联动", "流程上下游")
LINK_RE = re.compile(r"\*\*(功能依赖|数据来源|状态联动|流程上下游)\*\*\s*[：:]\s*(.*)")

FR_EXPAND_RE = re.compile(r"FR-(\d+)((?:\s*/\s*\d+)*)")
FR_HEAD_RE = re.compile(r"^F-([A-Z])-(\d+)$")

# 页面编号：先屏蔽 F-x-nn，再用负向后顾
MASK_CARD_RE = re.compile(r"F-[A-Z]-\d+")
PAGE_RE = re.compile(r"(?<![A-Za-z0-9-])([UMROC])-(\d{2})(?!\d)")

PRIORITIES = ("Must", "Should", "Could")


def mask_card_ids(text: str) -> str:
    """把 F-U-01 这类卡号整体替换掉，避免其尾缀被当成页面编号。"""
    return MASK_CARD_RE.sub(lambda m: "#" * len(m.group(0)), text)


def strip_marks(s: str) -> str:
    return re.sub(r"[`*]", "", s).strip()


def expand_fr(cell: str) -> list[int]:
    out: list[int] = []
    for m in FR_EXPAND_RE.finditer(cell):
        out.append(int(m.group(1)))
        for n in re.findall(r"\d+", m.group(2)):
            out.append(int(n))
    return out


def norm_raw(s: str) -> str:
    s = strip_marks(s)
    return re.sub(r"[\s/、,，;；]+", ",", s).strip(",")


PAREN_RE = re.compile(r"[（(][^）)]*[）)]")


def base_cell(cell: str) -> str:
    """剥掉括号批注，**保留原有分隔符**。

    卡片允许在上游原文后**追加说明**（如上游 `—`、卡片 `—（合规必需）`），
    这**不是漂移** —— 事实没变，只是把理由写出来了。
    若不剥，A5 会对每一个「写到位的批注」报假阳性，人很快就不看了。

    ⚠️ 这里**不能顺手把 `/` 归一成 `,`**：`FR-02/05` 的 `/` 是「同一组的续号」，
    归一后会退化成 `FR-02` 一条，把上游的两条引用读成一条（踩过一次）。
    分隔符归一交给 norm_raw，只在原始字符串比对时用。
    """
    return strip_marks(PAREN_RE.sub("", cell)).strip()


def key_raw(s: str) -> str:
    """仅在「两侧都没有 FR 编号」时用于原始比对，此时才归一分隔符。"""
    return re.sub(r"[\s/、,，;；]+", ",", s).strip(",")


# ------------------------------------------------------------ 解析卡片
def parse_cards(text: str) -> list[dict]:
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if CARD_HEAD_RE.match(l)]
    cards = []
    for idx, s in enumerate(starts):
        # 块尾：下一张卡，或下一个 `## / ###` 标题
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        for j in range(s + 1, e):
            if SECTION_RE.match(lines[j]):
                e = j
                break

        head = CARD_HEAD_RE.match(lines[s])
        cid, rest = head.group(1), head.group(2)

        ends = []
        if "涉及端" in rest:
            parts = rest.split("｜")
            idx = next((i for i, p in enumerate(parts) if "涉及端" in p), None)
            seg = "｜".join(parts[idx:]).split("涉及端", 1)[1] if idx is not None else ""
            ends = re.findall(r"`([A-Z]{2,3})`", seg)
            if not ends:
                ends = re.findall(r"\b([A-Z]{2,3})\b", seg)

        fields: dict[str, str] = {}
        links: dict[str, str] = {}
        for j in range(s + 1, e):
            ln = lines[j]
            for name, rx in FIELD_RE.items():
                m = rx.search(ln)
                if m and name not in fields:
                    fields[name] = m.group(1).strip()
            m = LINK_RE.search(ln)
            if m and m.group(1) not in links:
                links[m.group(1)] = m.group(2).strip()

        cards.append({
            "id": cid,
            "line": s + 1,
            "ends": ends,
            "fields": fields,
            "links": links,
        })
    return cards


def parse_feature_refs(path: Path) -> dict[str, dict]:
    """从功能列表取出 编号 -> {priority, fr_cell}。"""
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        cid = strip_marks(cells[0])
        if not FR_HEAD_RE.match(cid):
            continue
        out[cid] = {"priority": strip_marks(cells[3]), "fr_cell": strip_marks(cells[4])}
    return out


def collect_pages(text: str) -> set[str]:
    return {f"{m.group(1)}-{m.group(2)}"
            for m in PAGE_RE.finditer(mask_card_ids(text))}


# ------------------------------------------------------------ 判据
def analyze(text: str,
            feat: dict[str, dict] | None = None,
            pages: set[str] | None = None) -> dict:
    cards = parse_cards(text)
    if not cards:
        return {"error": "未抓到任何卡片（形如 `#### F-U-01 卡名 ｜ 涉及端：...`）"}

    checks: list[dict] = []
    ids = [c["id"] for c in cards]

    # ---------- A1 卡编号与功能列表一一对应 ----------
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if feat is None:
        checks.append({
            "id": "A1", "title": "卡编号唯一且与功能列表一一对应",
            "status": "fail" if dup else "skip",
            "evidence": {"duplicates": dup,
                         "reason": None if dup else "未提供 --features，无法取差集"},
        })
    else:
        fs = set(feat)
        cs = set(ids)
        only_card = sorted(cs - fs)
        only_feat = sorted(fs - cs)
        bad = bool(dup or only_card or only_feat)
        checks.append({
            "id": "A1", "title": "卡编号唯一且与功能列表一一对应",
            "status": "fail" if bad else "pass",
            "evidence": {"cardCount": len(cs), "featCount": len(fs),
                         "duplicates": dup,
                         "onlyInCards": only_card, "onlyInFeatures": only_feat},
        })

    # ---------- A2 每卡六段齐全 ----------
    # 「关联与数据来源」是容器段，其正文在子项里，故只判「段名是否出现」；
    # 子项的空缺由 A3 负责。其余四段是标量段，出现但为空同样算缺。
    missing = []
    for c in cards:
        lack: list[str] = []
        if not c["ends"]:
            lack.append("涉及端")
        for n in FIELD_RE:
            if n not in c["fields"]:
                lack.append(n)
            elif n != "关联与数据来源" and not c["fields"][n].strip():
                lack.append(f"{n}（空）")
        if lack:
            missing.append({"id": c["id"], "line": c["line"], "missing": lack})
    checks.append({
        "id": "A2", "title": "每卡六段齐全",
        "status": "fail" if missing else "pass",
        "evidence": {"violations": missing, "cardCount": len(cards)},
    })

    # ---------- A3 关联四类逐类表态且非空 ----------
    empty_links = []
    for c in cards:
        lack = [k for k in LINK_CLASSES if not c["links"].get(k)]
        if lack:
            empty_links.append({"id": c["id"], "line": c["line"], "missing": lack})
    checks.append({
        "id": "A3", "title": "关联四类逐类表态且非空",
        "status": "fail" if empty_links else "pass",
        "evidence": {"violations": empty_links, "classes": list(LINK_CLASSES)},
    })

    # ---------- A4 涉及端取值在闭集内 ----------
    bad_end = []
    for c in cards:
        bad = [e for e in c["ends"] if e not in END_CODES]
        if bad:
            bad_end.append({"id": c["id"], "line": c["line"], "values": bad})
    checks.append({
        "id": "A4", "title": "涉及端取值在闭集内",
        "status": "fail" if bad_end else "pass",
        "evidence": {"violations": bad_end, "allowed": list(END_CODES)},
    })

    # ---------- A5 优先级与对应 FR 与功能列表一致 ----------
    if feat is None:
        checks.append({
            "id": "A5", "title": "优先级与对应 FR 与功能列表一致",
            "status": "skip",
            "evidence": {"reason": "未提供 --features"},
        })
    else:
        drift = []
        for c in cards:
            up = feat.get(c["id"])
            if up is None:
                continue
            cell = c["fields"].get("优先级 / 对应 FR", "")
            pri = cell.split("/", 1)[0].strip()
            fr_part = cell.split("/", 1)[1].strip() if "/" in cell else ""
            if pri != up["priority"]:
                drift.append({"id": c["id"], "line": c["line"], "field": "优先级",
                              "upstream": up["priority"], "card": pri})
            up_base, card_base = base_cell(up["fr_cell"]), base_cell(fr_part)
            a, b = sorted(expand_fr(up_base)), sorted(expand_fr(card_base))
            if a != b or (not a and key_raw(up_base) != key_raw(card_base)):
                drift.append({"id": c["id"], "line": c["line"], "field": "对应 FR",
                              "upstream": up["fr_cell"], "card": fr_part or "（空）"})
        checks.append({
            "id": "A5", "title": "优先级与对应 FR 与功能列表一致",
            "status": "fail" if drift else "pass",
            "evidence": {"violations": drift},
        })

    # ---------- A6 页面编号在上游存在 ----------
    if pages is None:
        checks.append({
            "id": "A6", "title": "页面编号在上游存在",
            "status": "skip",
            "evidence": {"reason": "未提供 --pages"},
        })
    else:
        dangling = []
        for c in cards:
            # 逐卡：只在本卡的「页面流转」段内提页面号
            seg = c["fields"].get("页面流转", "")
            for p in sorted(collect_pages(seg)):
                if p not in pages:
                    dangling.append({"id": c["id"], "line": c["line"], "page": p})
        checks.append({
            "id": "A6", "title": "页面编号在上游存在",
            "status": "fail" if dangling else "pass",
            "evidence": {"upstreamPageCount": len(pages), "dangling": dangling},
        })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {
        "checks": checks,
        "failed": failed,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "totalChecks": len(checks),
        "cardCount": len(cards),
    }


# ------------------------------------------------------------ 变异测试
GOOD_FEATURES = """
| 编号 | 功能点 | 说明 | 优先级 | 对应 FR | 设计状态 |
|---|---|---|---|---|---|
| F-U-01 | 校区识别进入 | 略 | Must | FR-02/05 | 待设计 |
| F-U-02 | 手机号登录 | 略 | Should | FR-03 | 待设计 |
"""

GOOD_PAGES = """
# 交互说明书
页面清单：校区进入/授权页（U-01）、首页（U-02）。
"""

GOOD = """
#### F-U-01 校区识别进入 ｜ 涉及端：`UC`（识别并展示）｜ `OA`（配置侧）

- **优先级 / 对应 FR**：Must / FR-02、FR-05
- **需求要点**：通过小程序 AppID 自动识别校区。
- **关联与数据来源**：
  - **功能依赖**：`F-U-02`。
  - **数据来源**：由 `OA` 产生，`UC` 只读。
  - **状态联动**：校区停用 → 启动即拦截。
  - **流程上下游**：启动 → **本卡** → `F-U-02`。
- **变更影响面**：影响 `F-U-02`；涉及存量用户档案。具体表现：换 AppID 后需重新授权。
- **页面流转**：启动 → **校区进入/授权页（U-01）** → 首页（U-02）。

#### F-U-02 手机号登录 ｜ 涉及端：`UC`（授权）｜ `SVC`（建档）

- **优先级 / 对应 FR**：Should / FR-03（合规必需）
- **需求要点**：首次进入需授权。
- **关联与数据来源**：
  - **功能依赖**：`F-U-01`。
  - **数据来源**：档案由 `SVC` 生成。
  - **状态联动**：登录态失效 → 重新授权。
  - **流程上下游**：`F-U-01` → **本卡** → 首页。
- **变更影响面**：影响 `F-U-01`；涉及历史订单。具体表现：改档案口径后订单归属需迁移。
- **页面流转**：校区进入/授权页（U-01） → **【授权弹窗】** → 首页（U-02）。
"""

BAD = """
#### F-U-01 校区识别进入 ｜ 涉及端：`UC`（识别并展示）

- **优先级 / 对应 FR**：Must / FR-09
- **需求要点**：通过小程序 AppID 自动识别校区。
- **关联与数据来源**：
  - **功能依赖**：`F-U-02`。
  - **数据来源**：
  - **状态联动**：校区停用 → 启动即拦截。
- **变更影响面**：影响 `F-U-02`。

#### F-U-02 手机号登录 ｜ 涉及端：`UX`（授权）

- **优先级 / 对应 FR**：Should / FR-03
- **需求要点**：首次进入需授权。
- **关联与数据来源**：
  - **功能依赖**：`F-U-01`。
  - **数据来源**：档案由 `SVC` 生成。
  - **状态联动**：登录态失效 → 重新授权。
  - **流程上下游**：`F-U-01` → **本卡** → 首页。
- **变更影响面**：影响 `F-U-01`。
- **页面流转**：启动 → **校区进入/授权页（U-99）** → 首页（U-02）。

#### F-U-03 多余卡片 ｜ 涉及端：`UC`

- **优先级 / 对应 FR**：Must / FR-03
- **需求要点**：不在功能列表里。
- **关联与数据来源**：
  - **功能依赖**：无。
  - **数据来源**：无。
  - **状态联动**：无。
  - **流程上下游**：无。
- **变更影响面**：无。
- **页面流转**：无。
"""


def selftest() -> int:
    good = analyze(GOOD, parse_feat_string(GOOD_FEATURES), collect_pages(GOOD_PAGES))
    bad = analyze(BAD, parse_feat_string(GOOD_FEATURES), collect_pages(GOOD_PAGES))
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


def parse_feat_string(text: str) -> dict[str, dict]:
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        cid = strip_marks(cells[0])
        if not FR_HEAD_RE.match(cid):
            continue
        out[cid] = {"priority": strip_marks(cells[3]), "fr_cell": strip_marks(cells[4])}
    return out


# ------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="06 需求卡片画布 质量检查器")
    ap.add_argument("source", nargs="?", help="卡片文档的 Markdown 路径")
    ap.add_argument("--features", dest="features", help="需求清单 Markdown（A1/A5）")
    ap.add_argument("--pages", dest="pages", help="交互文档 Markdown（A6）")
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

    feat = None
    if args.features:
        p = Path(args.features)
        if not p.exists():
            print(f"功能列表不存在: {p}", file=sys.stderr)
            return 2
        feat = parse_feature_refs(p)

    pages = None
    if args.pages:
        p = Path(args.pages)
        if not p.exists():
            print(f"交互说明书不存在: {p}", file=sys.stderr)
            return 2
        pages = collect_pages(p.read_text(encoding="utf-8"))

    result = analyze(path.read_text(encoding="utf-8"), feat, pages)
    result["source"] = str(path)
    result["features"] = str(args.features) if args.features else None
    result["pages"] = str(args.pages) if args.pages else None

    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2

    print(f"来源: {path.name}")
    print(f"卡片总数: {result['cardCount']}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
        print(f"  [{mark}] {c['id']} {c['title']}")
        if c["status"] != "fail":
            continue
        ev = c["evidence"]
        if c["id"] == "A1":
            if ev["duplicates"]:
                print(f"         重复编号: {ev['duplicates']}")
            if ev["onlyInCards"]:
                print(f"         仅在卡片中: {ev['onlyInCards']}")
            if ev["onlyInFeatures"]:
                print(f"         仅在功能列表中: {ev['onlyInFeatures'][:20]}"
                      f"{' …' if len(ev['onlyInFeatures']) > 20 else ''}"
                      f"（共 {len(ev['onlyInFeatures'])}）")
        elif c["id"] == "A2":
            for v in ev["violations"]:
                print(f"         第 {v['line']} 行 {v['id']}: 缺 {', '.join(v['missing'])}")
        elif c["id"] == "A3":
            for v in ev["violations"]:
                print(f"         第 {v['line']} 行 {v['id']}: 缺 {', '.join(v['missing'])}")
        elif c["id"] == "A4":
            for v in ev["violations"]:
                print(f"         第 {v['line']} 行 {v['id']}: 涉及端 {v['values']}")
        elif c["id"] == "A5":
            for v in ev["violations"]:
                print(f"         第 {v['line']} 行 {v['id']} · {v['field']}: "
                      f"上游 {v['upstream']!r} / 卡片 {v['card']!r}")
        elif c["id"] == "A6":
            for v in ev["dangling"]:
                print(f"         第 {v['line']} 行 {v['id']}: {v['page']} 上游不存在")

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
