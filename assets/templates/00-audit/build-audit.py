# -*- coding: utf-8 -*-
"""
build-audit.py —— 由盘点原始记录装配 audit.json（00 盘点阶段数据源）

用法:
    python build-audit.py <盘点原始记录.json> [-o audit.json]

输入格式（这是**唯一**需要你填的东西，其余全部现算）
----------------------------------------------------
{
  "nature": "存量改造",          // 全新项目 / 存量改造 / 存量扩展 —— 第 0 问的答案
  "summary": "共 {{N}} 项",       // 可省略；给了就现算校验（A4 会核对它）
  "modules": [
    {
      "name": "支付",
      "code": "PAY",// 模块编号前缀，模块内功能点按它连号（如 PAY-01、PAY-02）
      "features": [
        {"name": "下单并支付", "status": "改造", "note": "只改了退款路径"},
        {"name": "对账", "status": "待定", "note": ""}
      ]
    }
  ]
}

字段 `name` / `status` / `note` 由你填；`id` 由本脚本按模块 code 现算。
`note` 用来写「已知问题」的证据指向（表名 / 接口 / 页面 / 现象）——
rubric B4 要求每条已知问题都能指到具体位置，写不出指向的等于没盘。

为什么 id 不让你手填
--------------------
编号是**下游的锚**（01/02/04/06 都要引用它）。手填就一定会出现同模块重号、
跨模块撞号，而这种错误在文档里看不出来、也不会有人去查。现算是唯一可靠的做法。

为什么 status 是闭集
--------------------
`新增 / 改造 / 保留 / 待定` 四个值是 01 阶段「需求 status」的取值来源，
先在盘点这里定死，下游才不会长出第五种说法。

自查
----
    python ../../feedback/checks/check-audit.py audit.json
    python ../../feedback/checks/check-audit.py audit.json --downstream ../01-requirements/requirement.json
（A6 跨阶段：00 阶段跑会 SKIP，请在 01 或 02 阶段回补跑一次。）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

STATUSES = ("新增", "改造", "保留", "待定")
NATURES = ("全新项目", "存量改造", "存量扩展")


def build(src: dict) -> dict:
    nature = src.get("nature")
    if nature not in NATURES:
        raise ValueError(
            "nature 必须是 %s 之一，收到 %r。\n"
            "这是第 0 问的答案，它决定 00 是否必做、PRD 写差异还是写全量 —— "
            "先回答它，再往下填。" % ("/".join(NATURES), nature)
        )

    modules = []
    total = 0
    seen_ids: dict[str, str] = {}

    for m in src.get("modules") or []:
        code = (m.get("code") or "").strip().upper()
        if not code:
            raise ValueError("模块「%s」缺 code —— 功能点编号靠它生成。" % (m.get("name") or "?"))
        feats = []
        # 每个模块内部独立连号；不用全局连号，方便中途插入模块。
        for i, f in enumerate(m.get("features") or [], start=1):
            status = f.get("status")
            if status not in STATUSES:
                raise ValueError(
                    "模块「%s」第 %d 项「%s」的 status=%r 不在闭集 %s"
                    % (m.get("name"), i, f.get("name"), status, "/".join(STATUSES))
                )
            fid = "%s-%02d" % (code, i)
            if fid in seen_ids:
                #理论上不会发生（编号是现算的），留着是为了万一有人改了 code。
                raise ValueError("编号冲突：%s 同时出现在模块「%s」和「%s」"
                                 % (fid, seen_ids[fid], m.get("name")))
            seen_ids[fid] = m.get("name") or "?"
            feats.append({
                "id": fid,
                "name": f.get("name") or "",
                "status": status,
                "note": f.get("note") or "",
            })
        total += len(feats)
        modules.append({"code": code, "name": m.get("name") or code, "features": feats})

    # summary 里的 {{N}} 现算填入。写了字面量的话，数据源一改它就变成谎言。
    summary = src.get("summary") or ""
    if "{{N}}" in summary:
        summary = summary.replace("{{N}}", str(total))
    elif not summary:
        summary = "共 %d 项" % total

    return {
        "nature": nature,
        "summary": summary,
        # meta.total 是给 A4 核对的声明数。**它必须等于现算值**，
        # 否则 A4 报fail —— 这正是 A4 存在的意义。
        "meta": {"total": total, "moduleCount": len(modules)},
        "modules": modules,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="装配 audit.json")
    ap.add_argument("source", help="盘点原始记录.json（格式见本文件头）")
    ap.add_argument("-o", "--out", default=None, help="输出路径，默认与输入同目录 audit.json")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        print("输入不存在: %s" % args.source, file=sys.stderr)
        return 2
    with open(args.source, encoding="utf-8") as f:
        src = json.load(f)

    try:
        data = build(src)
    except ValueError as e:
        print("装配失败: %s" % e, file=sys.stderr)
        return 2

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.source)), "audit.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("已写出: %s" % out)
    print("  项目性质: %s" % data["nature"])
    print("  模块 %d 个 / 盘点项 %d 条" % (len(data["modules"]), data["meta"]["total"]))
    print("\n下一步: python ../../feedback/checks/check-audit.py %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())