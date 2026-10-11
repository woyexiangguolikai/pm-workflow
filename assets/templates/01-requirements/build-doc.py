# -*- coding: utf-8 -*-
"""
build-doc.py —— 由 requirement.json 生成《需求清单.md》（01 阶段交付物）

用法:
    python build-doc.py [requirement.json] [-o 需求清单.md]

为什么要有这一步
----------------
`01-requirements/check-requirements.py` 判的是**Markdown 交付物**
（它的 A 类判据里有「跨文档闭环」「例外清单自洽」，都要看成品文档）。
数据源是 json、判据读的是 md —— 中间必须有一道转换，
否则「数据源改了但没重新生成文档」这类漂移就永远发现不了。

🔴 章节标题必须写成 `## 二、<模块名>（<模块code>）`
------------------------------------------------
这不是排版偏好，是**机器读法的约定**：
`check-requirements.py` 靠标题里的 `（RQ-XXX）` 建立「模块 ↔ 编号前缀」的绑定。
标题不带code，checker 就认不出这个模块对应哪些编号，
概览表与明细行对不上时会给出「认不出对应前缀」而不是误判。

所有数字现算 —— 概览表的合计、功能点数、优先级分布全部由 requirement.json 渲染。
写死字面量的话，改了数据源这些数字不会变，视图就成了摆设。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
      "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八",
      "十九", "二十", "二十一", "二十二", "二十三", "二十四", "二十五"]

# 编号前缀的形态，与 build-req.py 里生成的 id 前缀逐字一致。
# 概览表、章节标题、明细编号三处必须用同一个函数生成 —— 同一事实只有一处定义。
ID_PREFIX = "RQ-"


def prefix_of(module: dict) -> str:
    return ID_PREFIX + (module.get("code") or "")


def build_md(data: dict) -> str:
    meta = data.get("meta") or {}
    modules = data.get("modules") or []
    feats = [f for m in modules for f in (m.get("features") or [])]
    total = len(feats)
    pri = meta.get("byPriority") or {}
    by_end = meta.get("byEnd") or {}

    out: list[str] = []
    w = out.append
    w("# {{项目名}} · 需求清单 v1.0")
    w("")
    w("> 全部数字由 `requirement.json` 现算渲染。改数据源后**必须重跑本脚本**。")
    w("")

    # ---- 一、概览（数字现算）----
    #
    # 🔴 概览表按**模块**分组，不是按端。
    #
    # 原因：明细表按模块分组（## 二、登录（RQ-LOGIN）），概览表必须与它**同维度**，
    # 否则 `check-requirements.py` 的 A2（声明数 vs 现算数）永远对不上。
    # 曾经按「端」分组，结果概览的 3 行对明细的 2 个模块，全部落空。
    #
    # 端分布不是不能写，是**另一个维度**，单独一张表（见第一节末），
    # 而且它不参与 A2 —— 一个数字只有一个真相来源，两个表都声明同一个数必然漂移。
    w("## 一、功能总量概览")
    w("")
    # 🔴 「编号前缀」列必须写**完整前缀**（RQ-LOGIN，不是 LOGIN）——
    #    与明细行的编号前缀逐字一致，`check-requirements.py` 才能把两边对上。
    w("| 模块 | 编号前缀 | 需求数 | P0 | P1 | P2 |")
    w("|---|---|---|---|---|---|")
    for m in modules:
        fs = m.get("features") or []
        if not fs:
            continue
        w("| %s | %s | %d | %d | %d | %d |"
          % (m.get("name"), prefix_of(m), len(fs),
             sum(1 for f in fs if f["priority"] == "P0"),
             sum(1 for f in fs if f["priority"] == "P1"),
             sum(1 for f in fs if f["priority"] == "P2")))
    w("| **合计** | — | **%d** | **%d** | **%d** | **%d** |"
      % (total, pri.get("P0", 0), pri.get("P1", 0), pri.get("P2", 0)))
    w("")

    # ---- 端分布：单独一张表，明确标注它不参与 A2 ----
    w("### 附：端分布（另一维度，不参与上表的数量核对）")
    w("")
    w("| 端 | 需求数 |")
    w("|---|---|")
    for end, n in by_end.items():
        if n:
            w("| %s | %d |" % (end, n))
    w("| **合计** | **%d** |" % total)
    w("")
    w("> 一条需求可涉及多端，所以上表各行之和 ≥ 合计 —— 这是正常的，不是错误。")
    w("")

    # ---- 二、澄清闸门 ----
    g = data.get("clarifyGate") or {}
    w("## 二、澄清闸门状态")
    w("")
    w("| 项 | 值 |")
    w("|---|---|")
    w("| 已确认域 | %d |" % len(g.get("confirmed") or []))
    w("| 显式挂起域 | %d |" % len(g.get("suspended") or []))
    w("| 待确认假设 | %d |" % len(g.get("assumptionsPending") or []))
    rounds = g.get("rounds") or []
    w("| 澄清轮次 | %d |" % len(rounds))
    w("")
    if g.get("assumptionsPending"):
        w("🔴 **有未确认的假设 —— 按 references「澄清闸门」，过不了闸不许进 02。**")
        w("")
        for a in g["assumptionsPending"]:
            w("- %s" % a.get("text"))
        w("")

    # ---- 三、需求明细 ----
    w("## 三、需求明细")
    w("")
    idx = 0
    for m in modules:
        fs = m.get("features") or []
        if not fs:
            continue
        idx += 1
        # 🔴 标题带 code：这是机器读法（见本文件头说明），别改成纯模块名
        head = CN[idx - 1] if idx - 1 < len(CN) else str(idx)
        w("### %s、%s（%s）" % (head, m.get("name"), prefix_of(m)))
        w("")
        w("| 编号 | 需求 | 端 | 优先级 | 来源 | 状态 | 规则要点 |")
        w("|---|---|---|---|---|---|---|")
        for f in fs:
            detail = (f.get("detail") or "").replace("|", "\\|").replace("\n", "<br>")
            title = (f.get("title") or "").replace("|", "\\|")
            w("| %s | %s | %s | %s | %s | %s | %s |"
              % (f["id"], title, "、".join(f.get("ends") or []),
                 f.get("priority"), f.get("source"), f.get("status"), detail))
        w("")

    w("## 四、编号与来源约定")
    w("")
    w("- 编号 `RQ-<模块code>-<两位序号>`，模块内独立连号。")
    w("- 来源三态：`客户原话 R<轮>Q<题>` / `盘点发现 <功能点id>` / `合规要求:<条款>`。")
    w("- 端取值只能来自 SKILL.md「端枚举」；端枚举之外的参与方写「外部系统」。")
    w("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成需求清单.md")
    ap.add_argument("source", nargs="?", default="requirement.json")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.source):
        print("数据源不存在: %s" % args.source, file=sys.stderr)
        return 2
    with open(args.source, encoding="utf-8") as f:
        data = json.load(f)

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.source)), "需求清单.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_md(data))
    print("已写出: %s" % out)
    n = (data.get("meta") or {}).get("total", 0)
    print("  需求 %d 条，全部数字现算" % n)
    print("\n下一步: python ../../feedback/checks/check-requirements.py \"%s\"" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())