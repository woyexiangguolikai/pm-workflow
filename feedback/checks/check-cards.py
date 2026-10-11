#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06 需求卡片画布 质量检查器 · 对《卡片文档》执行 A1–A7
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
    A7  变更影响面写明具体表现（覆盖率 + 空话模板 + 复述检测）

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

A7 为什么是三条机制，以及它为什么只配当「地板」
--------------------------------------------------
B2 原来的写法是「写的是具体表现，不是『同步更新』——出现空话即不过」。
它可判，因为**两侧都有稳定形态**：一边是「具体表现：」这个落点标记，
一边是套话模板。所以它按纪律必须升级成 A 类，不能留在「等有空再说」。

但它只能判到三种**形态**缺陷：
| 机制 | 抓什么 | 抓不到什么 |
|---|---|---|
| 覆盖率 | 整批卡片不再写落点标记 | 写了但内容空 |
| 空话模板 | 「具体表现：同步更新。」这类纯模板 | 换了词的套话 |
| 复述检测 | 把前半句整段复制过来 | 换几个词重说一遍（约 0.5–0.8 重合） |

「这段具体表现**说得够不够具体**」需要懂这张卡的业务语境，正则判不了 →
**那部分仍留在 B2**，由人判。**把 B 类升级成 A 类，是把可判的部分自动化，
不是宣布剩下的部分已经判过了。**
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

# ---------------------------------------------------------------- A7 用的常量
# 「具体表现」是《变更影响面》段里**必须出现**的落点标记：它把「影响哪些卡」推进到
# 「改下去会出什么事」。缺了它，这一段就只剩影响面清单，等于没写变更后果。
DETAIL_MARK_RE = re.compile(r"具体表现\s*[：:]")

# 套话模板。**注意比对的是「剥掉模板后还剩多少字」，不是「有没有出现模板词」。**
# 「须全端同步更新金额明细」里出现了「同步更新」，但它是有内容的 —— 判「是否出现」
# 会把它误判成空话（一误报，判据就被整体忽略）。
STOCK_PHRASES = (
    "同步更新", "同步修改", "相应更新", "视情况而定", "待定", "后续同步", "后续再定",
    "待补充", "待确认", "另行通知", "按需处理", "评估影响", "需注意", "视情况",
    "略", "见上", "同上", "暂无", "不涉及", "无", "tbd", "n/a", "na", "-",
)

DETAIL_COVER = 0.95   # 「具体表现」落点覆盖率下限
DETAIL_MIN = 8        # 剥掉套话模板后子句至少剩下多少字
MAX_OVERLAP = 0.85    # 子句与前半句的 3-gram 重合上限（≥ 即视为复述）

_NORM_STRIP_RE = re.compile(r"""[。，、；：\s"'“”‘’《》（）()\[\]【】…~·,.!?:;|/\\]+""")
_ID_STRIP_RE = re.compile(r"`[^`]*`|F-[A-Z]-\d+|[A-Z]{2,3}")


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


# ------------------------------------------------------------ A7 的辅助函数
def norm_detail(s: str, drop_ids: bool = False) -> str:
    """归一化：去标点 / 空白，可选去编号。**只用于「有没有实质内容」的比较。**"""
    if drop_ids:
        s = _ID_STRIP_RE.sub("", s)
    return _NORM_STRIP_RE.sub("", s).lower()


def detail_clause(cell: str) -> str | None:
    """取「具体表现：」之后的子句；没有该标记则返回 None。"""
    parts = DETAIL_MARK_RE.split(cell, maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else None


def restatement_overlap(first_half: str, clause: str) -> float:
    """子句里有多大比例的内容已在前半句出现过（3-gram 覆盖率）。

    1.0 = 整句复制前半句。**这个指标只能抓「复制粘贴式复述」** ——
    中间程度的复述（换几个词重说一遍）抓不到，那部分仍归 B2 人判。
    它是地板，不是天花板。
    """
    a, b = norm_detail(first_half, True), norm_detail(clause, True)
    if len(a) < 3 or len(b) < 3:
        return 0.0
    grams = {a[i:i + 3] for i in range(len(a) - 2)}
    gb = [b[i:i + 3] for i in range(len(b) - 2)]
    if not gb:
        return 0.0
    return sum(1 for g in gb if g in grams) / len(gb)


# ------------------------------------------------------------ 判据
def analyze(text: str,
            feat: dict[str, dict] | None = None,
            pages: set[str] | None = None,
            opts: dict | None = None) -> dict:
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

    # ---------- A7 变更影响面写明具体表现（覆盖率 + 空话拦截 + 复述检测） ----------
    # 为什么是三条机制而不是一条：
    #   覆盖率   → 管「规模性退化」（整批卡片不再写具体表现）
    #   空话模板 → 管「逐卡糊弄」（写「具体表现：同步更新。」凑格式）
    #   复述检测 → 管「把前半句复制成具体表现」—— 模板法抓不到这种，因为一个字都不是套话
    # 三者分工不同，缺任一条都会留一个静默退化的入口。
    o = opts or {}
    cover_min = float(o.get("detail_cover", DETAIL_COVER))
    detail_min = int(o.get("min_detail", DETAIL_MIN))
    overlap_max = float(o.get("max_overlap", MAX_OVERLAP))

    scanned = [c for c in cards if c["fields"].get("变更影响面", "").strip()]
    if not scanned:
        # 🔴 控制项：空集上「覆盖率」恒等于 1，集合判据也恒真。样本为 0 必须判失败，
        #    否则格式一变（段名改了、表格化了）就会静默全绿 —— 这正是「橡皮图章」的成因。
        checks.append({
            "id": "A7", "title": "变更影响面写明具体表现（非空话）",
            "status": "fail",
            "evidence": {"reason": "未抓到任何「变更影响面」正文 —— 样本为 0，"
                                   "覆盖率在空集上恒真，故直接判失败",
                         "scanned": 0,
                         "cardsSeen": len(cards)},
        })
    else:
        no_mark, stock_only, restated = [], [], []
        for c in scanned:
            cell = c["fields"]["变更影响面"]
            cl = detail_clause(cell)
            if cl is None or not norm_detail(cl):
                no_mark.append({"id": c["id"], "line": c["line"], "cell": cell[:80]})
                continue
            left = norm_detail(cl)
            for p in STOCK_PHRASES:
                left = left.replace(norm_detail(p), "")
            if len(left) < detail_min:
                stock_only.append({"id": c["id"], "line": c["line"],
                                   "clause": cl[:60], "remaining": len(left)})
            ov = restatement_overlap(DETAIL_MARK_RE.split(cell, maxsplit=1)[0], cl)
            if ov >= overlap_max:
                restated.append({"id": c["id"], "line": c["line"],
                                 "overlap": round(ov, 2), "clause": cl[:60]})
        cov = (len(scanned) - len(no_mark)) / len(scanned)
        bad = bool(no_mark or stock_only or restated) or cov < cover_min
        checks.append({
            "id": "A7",
            "title": f"变更影响面写明具体表现（覆盖率 ≥ {cover_min:.0%}，非空话）",
            "status": "fail" if bad else "pass",
            "evidence": {"scanned": len(scanned), "coverage": round(cov, 4),
                         "threshold": cover_min, "minDetail": detail_min,
                         "maxOverlap": overlap_max,
                         "missingDetail": no_mark, "stockPhrase": stock_only,
                         "restated": restated},
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
    expect_bad = ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]

    # ------------------------------------------------ A7 专项：四条机制各要一个反例
    # 只让「覆盖率」有反例是不够的 —— 空话模板与复述检测如果不各有一个反例，
    # 它们是不是真的接上了线，没人知道（写得再漂亮都可能是死代码）。
    a7_cases: list[tuple[str, str, list[str]]] = [
        ("控制项·样本为 0",
         GOOD.replace("- **变更影响面**：影响 `F-U-02`；涉及存量用户档案。具体表现：换 AppID 后需重新授权。",
                      "- **变更影响面**：")
             .replace("- **变更影响面**：影响 `F-U-01`；涉及历史订单。具体表现：改档案口径后订单归属需迁移。",
                      "- **变更影响面**："),
         ["A2", "A7"]),          # A2 报空段 + A7 报样本为 0；要点是 A7 不能在空集上假绿
        ("缺「具体表现」落点",
         GOOD.replace("。具体表现：换 AppID 后需重新授权。", "。")
             .replace("。具体表现：改档案口径后订单归属需迁移。", "。"),
         ["A7"]),
        ("只写套话模板",
         GOOD.replace("具体表现：换 AppID 后需重新授权。", "具体表现：同步更新。")
             .replace("具体表现：改档案口径后订单归属需迁移。", "具体表现：待定。"),
         ["A7"]),
        ("把前半句复制成具体表现",
         GOOD.replace("具体表现：换 AppID 后需重新授权。",
                      "具体表现：影响 `F-U-02`；涉及存量用户档案。")
             .replace("具体表现：改档案口径后订单归属需迁移。",
                      "具体表现：影响 `F-U-01`；涉及历史订单。"),
         ["A7"]),
    ]

    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == expect_bad

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望七项全绿   : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望七项全红   : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")

    ok_a7 = True
    for name, text, expect in a7_cases:
        r = analyze(text, parse_feat_string(GOOD_FEATURES), collect_pages(GOOD_PAGES))
        got = r.get("failed")
        hit = got == expect
        ok_a7 = ok_a7 and hit
        print(f"  A7 反例「{name}」: {'通过' if hit else '失败'}"
              f"  (期望 {expect} / 实得 {got})")

    if not (ok_good and ok_bad and ok_a7):
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
    ap.add_argument("--detail-cover", dest="detail_cover", type=float,
                    default=DETAIL_COVER, help=f"A7 具体表现覆盖率下限（默认 {DETAIL_COVER}）")
    ap.add_argument("--min-detail", dest="min_detail", type=int,
                    default=DETAIL_MIN, help=f"A7 剥掉套话后最少剩余字数（默认 {DETAIL_MIN}）")
    ap.add_argument("--max-overlap", dest="max_overlap", type=float,
                    default=MAX_OVERLAP, help=f"A7 复述重合度上限（默认 {MAX_OVERLAP}）")
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

    result = analyze(path.read_text(encoding="utf-8"), feat, pages,
                     {"detail_cover": args.detail_cover,
                      "min_detail": args.min_detail,
                      "max_overlap": args.max_overlap})
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
        elif c["id"] == "A7":
            if ev.get("reason"):
                print(f"         {ev['reason']}")
            print(f"         落点覆盖率 {ev.get('coverage', 0):.1%} / 扫描 {ev.get('scanned', 0)} 张卡")
            for v in ev.get("missingDetail", []):
                print(f"         第 {v['line']} 行 {v['id']}: 无「具体表现」落点")
            for v in ev.get("stockPhrase", []):
                print(f"         第 {v['line']} 行 {v['id']}: 剥掉套话后只剩 {v['remaining']} 字"
                      f" → {v['clause']!r}")
            for v in ev.get("restated", []):
                print(f"         第 {v['line']} 行 {v['id']}: 与前半句重合 {v['overlap']:.0%}"
                      f" → {v['clause']!r}")

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
