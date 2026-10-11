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

PRIORITIES = ("Must", "Should", "Could")

# 端前缀允许多字符（F-U / F-POS / F-APP 都合法）。
# 早先写死 `[A-Z]` 单字母同样是「按一个项目的命名习惯去规定通用工作流」。
ROW_ID_RE = re.compile(r"^F-([A-Z][A-Z0-9]*)-(\d+)$")

# ---------------------------------------------------------------- 行编号形态
#
# 🔴 编号形态必须认 references 的规定，不能认某一个项目的习惯。
#
# 踩坑经过：本检查器初版只认 `F-U-01`（某项目的功能列表形态），
# 而 references/00-audit-and-01-requirements.md 第 53 行明确写的是 **`RQ-xxx`**。
# 结果：模板按 references 生成的需求清单，**一条都抓不到**——
#「未抓到任何明细行」直接 return，连 A5 的跨文档闭环都不跑，整个检查等于空转。
# 一个只认 `F-` 的判据，实际上只对**用过 F- 形态的项目**有效。
#
# 所以：先认规范里的 `RQ-`（含 / 不含模块分段），再兼容 `F-` 形态。
# 前缀长度一律不写死。
# 序号一律用**命名组** `num` 取，不用数字下标 ——
# 数字下标在下标标被调整过一次后整体错位（group(1) 变字母前缀），
# 而这种错只在特定输入下才炸，属于最难查的一类。
ROW_ID_RES = (
    re.compile(r"^RQ-[A-Z][A-Z0-9]*-(?P<num>\d+)$"),   # RQ-LOGIN-01（references 规定形态）
    re.compile(r"^RQ-(?P<num>\d+)$"),                   # RQ-01（无模块分段）
    re.compile(r"^F-[A-Z][A-Z0-9]*-(?P<num>\d+)$"),     # F-U-01（功能列表形态，兼容）
)


def parse_row_id(cell: str):
    """行首编号 -> (前缀, 序号)；三种形态都不认得时返回 None。"""
    s = strip_marks(cell)
    for rx in ROW_ID_RES:
        m = rx.match(s)
        if m:
            return s.rsplit("-", 1)[0], int(m.group("num"))
    return None

# ---------------------------------------------------------------- 端名 ↔ 前缀绑定
#
# 🔴 这一段是被判据逼出来的，不是为了好看。
#
# 原实现持有一份硬编码端名白名单（用户端小程序/商家端/骑手端/运营后台/客服工作台），
# 靠关键词把概览表首列猜成前缀。换一个项目的端名（用户小程序/管理后台/收银端…）
# 一个都猜不中 → collect_overview 整表识别不到 → declared 为空 →
# **每一个**前缀都被报成「无概览行」。好文档 100% 假阳性。
#
# 后果比「漏判」严重得多：判据一旦被无视过一次就永久失效（AP-06）。
# 而它之所以一直没被发现，正是因为变异样本用的是**恰好在那份白名单里**的端名 ——
# 样本是照着代码挑的，不是照着判据该覆盖的范围挑的。
#
# 现在端名从**文档自身**解析，三路信号：
#   1. 章节标题里的 `端名（F-X）` —— 权威来源
#   2. 概览表首列自带 `（F-X）`
#   3. `--end-map` 显式传入（前三路都拿不到时的逃生口）
# 三路都拿不到 → 该端报「无法对应」并说清怎么改，而不是猜一个。
TOTAL_ROW_RE = re.compile(r"^(合计|总计|汇总|小计|全端)")
HEADING_END_RE = re.compile(
    r"^#{1,6}\s*(?:第?[0-9一二三四五六七八九十百]+[、.．]\s*)?"
    r"(?P<name>[^\n（(【\[]+?)\s*[（(]\s*(?P<pfx>(?:RQ|F)-[A-Z0-9][A-Z0-9-]*)\s*[)）]")
OVERVIEW_PREFIX_RE = re.compile(r"F-([A-Z][A-Z0-9]*)")


def norm_end(s: str) -> str:
    """端名归一：去 markdown 标记、去 `（F-X）`、去一切括注、压掉空白。

    归一是必需的：概览表写 `平台客服工作台（Web）`、章节标题写 `平台客服工作台`，
    是同一端。不归一就会判成「无法对应」，把格式差异报成结构缺陷。
    """
    s = strip_marks(s)
    s = re.sub(r"[（(]\s*F-[A-Za-z][A-Za-z0-9]*\s*[)）]", " ", s)
    s = re.sub(r"[（(][^()（）]*[)）]", " ", s)
    return re.sub(r"\s+", "", s)


def collect_end_map(lines: list[str]) -> dict[str, str]:
    """从章节标题解析「前缀 -> 端名」，如 `## 二、用户小程序（RQ-LOGIN）` -> {'RQ-LOGIN': 用户小程序}。

    🔴 key 必须是 `parse_row_id` 产出的**同一个前缀形态**（含 `RQ-`/`F-` 前缀）。
    曾经这里只取字母部分（`LOGIN`）而明细行给的是 `RQ-LOGIN`，
    两边对不上 → 所有端都变成「有声明无明细」+「无概览行」双重误报。
    **绑定的两端必须用同一个 key 生成函数**，这是不能省的约束。

    只认标题形态：正文里随口写的 `F-U（用户小程序）` 是**引用**不是**绑定**，
    两者在形态上就能分开 —— 这与 A6 的「只认行首」是同一个道理。
    """
    out: dict[str, str] = {}
    for line in lines:
        m = HEADING_END_RE.match(line.strip())
        if m:
            name = norm_end(m.group("name"))
            if name:
                out.setdefault(m.group("pfx").upper(), name)
    return out


def parse_end_map(spec: str) -> dict[str, str]:
    """`--end-map` 解析：`端名=前缀,端名2=前缀2`。"""
    out: dict[str, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"--end-map 片段 {part!r} 缺 '='，应形如 端名=前缀")
        name, pfx = part.split("=", 1)
        out[pfx.strip()] = norm_end(name)
    return out
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
    """抓明细行。

    🔴 列位置**按表头名定位，不按列号**。
    初版写死 `cells[3]`=优先级、`cells[4]`=对应 FR —— 那是某一个项目的表格布局。
    换一个项目的表（列数、列序、列名都不同）就会静默取错列：
    取到的是「来源」或「状态」这种文本，于是 A3 全判非法、A5 全判形态非法，
    而报告里看不出「我取错列了」。**按列号取字段 = 把别人的表格布局当标准。**

    表头认这些名字（含常见别名）；找不到表头时退回列号并在证据里说明。
    """
    rows = []
    hdr: dict[str, int] = {}
    hdr_line = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s.startswith("|"):
            # 遇到非表格行，表头作用域结束 —— 防止把上一节的表头用到下一节
            hdr = {}
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        low = [strip_marks(c).lower() for c in cells]
        if any("编号" in c or c.lower().startswith("id") for c in low) and \
           any("优先级" in c or "priority" in c for c in low):
            hdr = {}
            for j, c in enumerate(low):
                if c.startswith("编号") or c == "id":
                    hdr["id"] = j
                elif "优先级" in c or c == "priority":
                    hdr["priority"] = j
                elif ("对应" in c and ("fr" in c or "br" in c)) or c in ("fr", "br"):
                    hdr["ref"] = j
            hdr_line = i + 1
            continue

        if len(cells) < 5:
            continue
        id_idx = hdr.get("id", 0)
        if id_idx >= len(cells):
            continue
        parsed = parse_row_id(cells[id_idx])
        if not parsed:
            continue
        pfx, num = parsed

        def cell(key: str, default_idx: int) -> str:
            j = hdr.get(key, default_idx)
            return strip_marks(cells[j]) if j < len(cells) else ""

        rows.append({
            "id": strip_marks(cells[id_idx]),
            "prefix": pfx,
            "num": num,
            "line": i + 1,
            "priority": cell("priority", 3),
            "fr_cell": cell("ref", 4),
        })
    if rows and not hdr:
        rows[0].setdefault("_noHeader", True)
    return rows


def collect_overview(lines: list[str]) -> dict[str, tuple]:
    """抓概览表。

    🔴 与 collect_rows 同理：**按表头名定位列**，不按列号。
    初版要求「首列 + 恰好 5 个数字列」，那是某一个项目的概览表布局。
    这里的做法是：认表头里的「功能点数/需求数/条目数」列作为总数列，
    再把**所有名字出现在优先级词表里的列**按顺序收集起来（P0/P1/P2、
    Must/Should/Could 都认）。数量对不上就报数量，不猜。

    返回 (概览字典, 前缀字典, 优先级词表) —— 前缀与词表都是概览表自带的列，
    与数字一起现算，不从别处猜。
    """
    PRI_WORDS = ("P0", "P1", "P2", "P3", "Must", "Should", "Could", "Won't")
    declared: dict[str, tuple] = {}
    prefix_col_data: dict[str, str] = {}
    words: list[str] = []
    hdr_idx: dict = {}
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            hdr_idx = {}
            continue
        cells = [strip_marks(c) for c in s.strip("|").split("|")]
        low = [c.lower() for c in cells]
        has_total = any(("功能点" in c or "需求数" in c or "条目数" in c)
                         for c in cells) or any(c.startswith("feature") for c in low)
        if cells and ("端" in cells[0] or "模块" in cells[0] or "end" in low[0]
                      or "module" in low[0]) and has_total:
            total_col = None
            pri_cols: list[int] = []
            pfx_col = None
            for j, c in enumerate(cells):
                cl = c.lower()
                if ("功能点" in c or "需求数" in c or "条目数" in c
                        or cl.startswith("feature")):
                    total_col = j
                elif ("编号前缀" in c or cl == "前缀" or cl in ("prefix", "code")):
                    pfx_col = j
                elif any(w.lower() == cl for w in PRI_WORDS):
                    pri_cols.append(j)
            hdr_idx = {"total": total_col, "pri": pri_cols, "pfx": pfx_col}
            for j in pri_cols:
                w = cells[j]
                if w and w not in words:
                    words.append(w)
            continue

        if not hdr_idx or hdr_idx.get("total") is None:
            continue
        # 🔴 什么算「可绑定的那张概览表」——试过三版，两版都是错的：
        #
        #   v1 只认「恰好 5 个数字列」        → 换列数就整表失联
        #   v2 认「有前缀列的表」            → 没前缀列的合法概览表被误判（过严）
        #   v3 认「有前缀列 **或** 优先级列」 → 端分布附表只有总数列，被排除 ✅
        #
        #   依据是**结构**而非项目习惯：一张分维度汇总表必然带优先级分布列
        #   （否则它只是总数表，没有「分布」可言）。附表通常只有一列数字。
        if hdr_idx.get("pfx") is None and not hdr_idx.get("pri"):
            continue
        total_col = hdr_idx["total"]
        if total_col >= len(cells) or not re.fullmatch(r"\d+", cells[total_col]):
            continue
        head = norm_end(cells[0])
        if not head or TOTAL_ROW_RE.match(head):
            continue
        pri_vals = []
        ok = True
        for j in hdr_idx["pri"]:
            if j >= len(cells):
                ok = False
                break
            if not re.fullmatch(r"\d+", cells[j]):
                ok = False
                break
            pri_vals.append(int(cells[j]))
        if not ok:
            continue
        declared[head] = tuple([int(cells[total_col])] + pri_vals)
        pj = hdr_idx.get("pfx")
        if pj is not None and pj < len(cells):
            v = cells[pj].strip()
            if v and v != "—":
                prefix_col_data[head] = v
    return declared, prefix_col_data, words


def analyze(text: str, prd_text: str | None = None,
            end_map_override: dict[str, str] | None = None) -> dict:
    lines = text.splitlines()
    rows = collect_rows(lines)
    declared, overview_prefix, ov_words = collect_overview(lines)
    # 前缀 -> 端名。override（--end-map）优先，其次文档章节标题。
    end_map: dict[str, str] = dict(collect_end_map(lines))
    if end_map_override:
        end_map.update(end_map_override)
    checks: list[dict] = []

    def label(pfx: str) -> str:
        """前缀的显示名。认不出端名时如实显示前缀本身 —— 显示 `F-X` 比编一个名字诚实。"""
        return end_map.get(pfx, f"端 {pfx}")

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
                "prefix": pfx,
                "end": label(pfx),
                "duplicates": sorted(dup),
                "missing": missing,
            })

    checks.append({
        "id": "A1",
        "title": "功能点编号分端连续唯一",
        "status": "fail" if problems else "pass",
        "evidence": {
            "ends": {label(k): len(v) for k, v in sorted(by_prefix.items())},
            "endMap": end_map,
            "violations": problems,
        },
    })

    # ---------- A2 声明的数量与现算一致 ----------
    # 优先级词表：概览表头说的（ov_words）用于**列对应**，
    # 但「实际用了哪些取值」必须从**明细行现算** ——
    # 概览表头写 Must/Should/Could 而明细里混进了 P0，是词表混用，
    # 只看表头会漏掉它（A3 的职责，见下）。
    pri_words = list(ov_words) if ov_words else []
    used_pri: list[str] = []
    for r in rows:
        if r["priority"] and r["priority"] not in used_pri:
            used_pri.append(r["priority"])

    actual: dict[str, dict] = {}
    for pfx in by_prefix:
        sub = [r for r in rows if r["prefix"] == pfx]
        d = {"features": len(sub)}
        for w in pri_words:
            d[w] = sum(1 for r in sub if r["priority"] == w)
        actual[pfx] = d

    # 概览行 -> 前缀。三路来源，优先级从高到低：
    #   1. 概览表自己的「编号前缀 / 前缀 / code」列  ← 最可靠，同表自证
    #   2. 章节标题里的 `端名（RQ-LOGIN）`
    #   3. 端名互相包含（兜底，最弱）
    # 🔴 早期版本只认第 2 路，而模板把前缀放在概览表里 —— 于是概览整表认不出前缀，
    #    所有端双重误报。**绑定来源要按可靠性排序，且要多路兜底**：
    #    任何一路单独失效都不该让整张概览表失联。
    dec_to_pfx: dict[str, str] = {}
    unmapped: list[str] = []
    pri_to_pfx: dict[str, str] = {}
    for name, pfx in (overview_prefix or {}).items():
        pri_to_pfx.setdefault(norm_end(pfx).upper(), name)

    by_endname: dict[str, str] = {}
    for pfx, name in end_map.items():
        by_endname.setdefault(name, pfx)

    for name in sorted(declared):
        raw = (overview_prefix or {}).get(name)
        hit = None
        src = ""
        if raw:
            cand = raw.strip().upper()
            # 前缀列可能写全（RQ-LOGIN）也可能只写模块码（LOGIN）——
            # 两种都试，但**只在确实存在的前缀里选**，不凭空造。
            for c in (cand, "RQ-" + cand, "F-" + cand):
                if c in by_prefix:
                    hit, src = c, "概览表前缀列"
                    break
        if hit is None:
            cand = by_endname.get(name)
            if cand in by_prefix:
                hit, src = cand, "章节标题"
        if hit is None:
            for pfx, pname in end_map.items():
                if pfx in by_prefix and pname and (pname in name or name in pname):
                    hit, src = pfx, "端名包含"
                    break
        if hit is None:
            unmapped.append(name)
        else:
            dec_to_pfx[name] = hit
            end_map.setdefault(hit, name)

    mismatches = []
    for name in sorted(dec_to_pfx):
        pfx = dec_to_pfx[name]
        dec = declared[name]
        if pfx not in actual:
            mismatches.append({
                "end": label(pfx),
                "field": "整端",
                "declared": "有声明",
                "actual": "无明细行",
            })
            continue
        a = actual[pfx]
        # dec = (总数, 各优先级计数…)，总数与优先级逐项都比 —— 两侧都现算
        if dec[0] != a["features"]:
            mismatches.append({
                "end": label(pfx), "field": "总数",
                "declared": dec[0], "actual": a["features"],
            })
        for k, dv in enumerate(dec[1:], start=1):
            word = pri_words[k - 1] if k - 1 < len(pri_words) else f"#{k}"
            av = a.get(word, 0)
            if dv != av:
                mismatches.append({
                    "end": label(pfx), "field": word,
                    "declared": dv, "actual": av,
                })
    for pfx in actual:
        if pfx not in dec_to_pfx.values():
            mismatches.append({
                "end": label(pfx),
                "field": "整端",
                "declared": "无概览行",
                "actual": actual[pfx]["features"],
            })

    checks.append({
        "id": "A2",
        "title": "各端数量与概览表声明一致",
        "status": "fail" if (mismatches or unmapped) else "pass",
        "evidence": {
            "declaredEnds": {name: declared[name] for name in sorted(declared)},
            "actualEnds": {label(k): v for k, v in sorted(actual.items())},
            "endMap": end_map,
            "priorityWords": pri_words,
            "unmappedOverviewRows": unmapped,
            "mismatches": mismatches,
        },
    })

    # ---------- A3 优先级取值合法 ----------
    # 🔴 优先级词表**不写死**。初版写死Must/Should/Could，
    # 而 references/00-audit-and-01-requirements.md 规定的是 **P0/P1/P2** ——
    # 换个项目（或按规范用 P0/P1/P2）就会全表判非法。
    #
    # 现在 A3 只判两件与项目无关的事：
    #   1. 非空（漏填比填错更常见，且漏填会让 A2 的分布统计悄悄失真）
    #   2. **词表内部一致** —— 同一份文档里不许前一行P0 后一行 Must
    #      （两套词表混用是真实的、机器能抓的缺陷）
    # 至于「本项目该用哪套词表」，是 references 的事，不是判据的事。
    bad_pri: list[dict] = []
    for r in rows:
        if not r["priority"]:
            bad_pri.append({"id": r["id"], "line": r["line"], "value": "",
                            "why": "优先级为空"})
    # 🔴 「词表混用」的判据不是「取值超过 N 个」，而是**两套前缀同时出现**：
#    `P0/P1/P2`（P 系）与 `Must/Should/Could`（M 系）是两套不同的优先级口径，
#    同一份文档里并存必然导致排序与统计打架。
#    阈值法（">3 个就报"）会误伤「P0/P1/P2 + 一个自定义紧急级」这类合法四档。
    #所以判**前缀族**而不是数量。
    P_FAMILY = {"P0", "P1", "P2", "P3"}
    M_FAMILY = {"Must", "Should", "Could", "Won't"}
    # 🔴 判的是**明细行实际出现**的取值（used_pri），不是概览表头声明的词表。
    #    概览表头写 Must/Should/Could 而明细里混进 P0 —— 这才是词表混用。
    #    只看表头的话，混用完全不可见。
    has_p = any(w in P_FAMILY for w in used_pri)
    has_m = any(w in M_FAMILY for w in used_pri)
    if has_p and has_m:
        bad_pri.append({"id": "(整份文档)", "line": 0,
                        "value": "/".join(used_pri),
                        "why": "同一份文档混用了两套优先级口径：%s"
                               % ("、".join(w for w in used_pri
                                              if w in P_FAMILY | M_FAMILY))})
    if len(used_pri) > 4:
        bad_pri.append({"id": "(整份文档)", "line": 0,
                        "value": "/".join(used_pri),
                        "why": "优先级取值超过 4 种 —— 要么混用词表，要么有一堆一次性取值"})
    checks.append({
        "id": "A3",
        "title": "优先级取值非空且词表内部一致",
        "status": "fail" if bad_pri else "pass",
        "evidence": {"violations": bad_pri, "usedWords": list(used_pri),
                     "overviewWords": list(ov_words),
                     "note": "词表内容由文档现算，不与任何外部约定比对"},
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

# 🔴 陌生端名好样本 —— 这条样本是被一个真实缺陷逼出来的，加它有明确理由。
#
# 缺陷：检查器曾持有硬编码端名白名单（用户端小程序 / 商家端 / 骑手端 /
#      运营后台 / 平台客服工作台），靠关键词把概览表首列猜成端前缀。
# 后果：换一个项目的端名，一个都猜不中 → 概览表整表识别不到 →
#      每个前缀都被报「无概览行」→ **好文档 100% 假阳性**。
#
# 为什么一直没被发现：上面 GOOD / BAD 两个样本用的端名**恰好都在那份白名单里**。
# 样本是照着代码的假设挑的，不是照着判据该覆盖的范围挑的 ——
# 这与 AP-06（变异测试假绿）是同一个错误，只是长在样本选取上而不是断言上。
#
# 所以这条样本刻意使用 SKILL.md「端枚举」里的五端，与旧白名单**零交集**，
# 且前缀用多字符（F-POS），顺带固定住 ROW_ID_RE 的放宽。
# 若将来有人又把端名写死回来，这条样本会立刻判红。
GOOD_OTHER_ENDS = """
## 一、功能总量概览
| 端 | 页面数 | 功能点数 | Must | Should | Could |
|---|---|---|---|---|---|
| 用户小程序 | 2 | 5 | 5 | 0 | 0 |
| 收银端 | 1 | 3 | 3 | 0 | 0 |
| **合计** | **3** | **8** | **8** | **0** | **0** |

## 二、用户小程序（F-U）
| 编号 | 功能点 | 说明 / 规则要点 | 优先级 | 对应 FR | 设计状态 |
|---|---|---|---|---|---|
| F-U-01 | 校区识别进入 | 略 | Must | FR-01 | 待设计 |
| F-U-02 | 定位授权校验 | 略 | Must | FR-02 | 待设计 |
| F-U-03 | 手机号授权登录 | 略 | Must | FR-03 | 待设计 |
| F-U-04 | 隐私政策确认 | 略 | Must | — | 待设计 |
| F-U-05 | 订阅消息引导 | 略 | Must | FR-05 | 待设计 |

## 六、收银端（F-POS）
| 编号 | 功能点 | 说明 / 规则要点 | 优先级 | 对应 FR | 设计状态 |
|---|---|---|---|---|---|
| F-POS-01 | 账号登录与身份校验 | 略 | Must | FR-04 | 待设计 |
| F-POS-02 | 用户信息脱敏查看 | 略 | Must | NFR-02 | 待设计 |
| F-POS-03 | 看板按校区下钻 | 略 | Must | §13.4 | 待设计 |

### 产品补充功能点清单（=「对应 FR」列为 `—` 的全部行）

- F-U-04
"""


def selftest() -> int:
    good = analyze(GOOD, GOOD_PRD)
    bad = analyze(BAD, GOOD_PRD)
    # 🔴 陌生端名样本 —— 这条样本的存在理由见下。
    other = analyze(GOOD_OTHER_ENDS, GOOD_PRD)
    expect_bad = ["A1", "A2", "A3", "A4", "A5", "A6"]

    ok_good = good.get("failed") == []
    ok_bad = bad.get("failed") == expect_bad
    ok_other = other.get("failed") == []

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿       : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望六项全红   : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    print(f"  陌生端名 好样本期望全绿: {'通过' if ok_other else '失败'}"
          f"  (实得 failed={other.get('failed')})")
    if not (ok_good and ok_bad and ok_other):
        print("\n判别力不足 —— 该检查等于没有检查。")
        if not ok_other:
            print("  ↳ 陌生端名样本判红 = 判据把端名写死了。"
                  "换项目的端名就会全表落空，好文档 100% 假阳性。")
        return 1
    print("\n判别力成立：同一套探针在两种世界状态下产出不同结果。")
    return 0


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="01 需求阶段质量检查器（功能列表）")
    ap.add_argument("source", nargs="?", help="需求清单的 Markdown 路径")
    ap.add_argument("--prd", dest="prd", help="PRD 的 Markdown 路径（A5 跨文档闭环）")
    ap.add_argument("--end-map", dest="end_map",
                    help="显式绑定端名与编号前缀，形如 `用户小程序=U,收银端=POS`。"
                         "文档章节标题写成 `## 二、用户小程序（F-U）` 时可省略。")
    ap.add_argument("--json", dest="json_out", help="结果写入的 JSON 路径")
    ap.add_argument("--selftest", action="store_true", help="运行变异测试")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.source:
        ap.print_help()
        return 2

    end_map_override = None
    if args.end_map:
        try:
            end_map_override = parse_end_map(args.end_map)
        except ValueError as e:
            print(str(e), file=sys.stderr)
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

    result = analyze(path.read_text(encoding="utf-8"), prd_text, end_map_override)
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
            for name in ev.get("unmappedOverviewRows", []):
                print(f"         概览行「{name}」认不出对应的编号前缀 —— "
                      f"该端数量未参与核对。请把章节标题写成 `## 二、{name}（F-X）`，"
                      f"或运行时加 --end-map `{name}=X`")
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
