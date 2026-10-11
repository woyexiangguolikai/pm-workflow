# -*- coding: utf-8 -*-
"""
build-req.py —— 装配 requirement.json（01 需求阶段数据源）

用法:
    python build-req.py <需求原始记录.json> [-o requirement.json]

输入格式
--------
{
  "clarify": {                       // 🔴 澄清闸门，见下
    "confirmed": ["项目性质", "业务目标", "用户与角色", "端范围", "主流程"],
    "suspended": [                  // 显式挂起：写原因 + 谁拍板。**「没问到」不算一种状态**
      {"domain": "非功能", "reason": "甲方未给指标", "owner": "待定"}
    ],
    "assumptions": [],              // 每条形如 {"text": "...", "confirmedBy": "..."}；
                                    // 有未确认的假设就别想过闸
    "rounds": [                     // 来源要留痕：source 要能追到某轮问答
      {"round": 1, "q": "谁在什么场景用？", "a": "…", "landed": "需求卡片「定位」"}
    ]
  },
  "modules": [
    {
      "name": "登录",
      "code": "LOGIN",
      "features": [
        {
          "name": "手机号登录",
          "priority": "P0",
          "ends": ["用户小程序"],           // 🔴 只能是 SKILL.md 的端枚举
          "source": "客户原话 R1Q2",        // 或 盘点发现:PAY-01 / 合规要求:…
          "status": "新增",
          "detail": "验证码 60秒有效，同号 1 分钟 1 条"
        }
      ]
    }
  ]
}

你填 name/priority/ends/source/status/detail；本脚本负责算id、统计、落meta。

三条硬约束（脚本会拒收，不是提醒）
----------------------------------
1. **ends 必须在端枚举内**：用户小程序 / 管理后台 / 收银端 / 商家端 / 服务端。
   端枚举之外的参与方（第三方平台、硬件厂商…）写"外部系统"，
   **不要发明新端名** —— 端名一改，04/06 的过滤与统计全跟着错。
2. **source 非空**。「客户说的」和「我推测的」是两种东西，
   后续开发质疑时要知道找谁对。没来源的需求不许进清单。
3. **priority 只能 P0/P1/P2**。

id 形态与 01 检查器的关系
-----------------------
`RQ-<模块code>-<序号>`。检查器 A5/A6 判的是「对应 FR」列与 PRD 的闭环，
不依赖本脚本的 id 形态；但**模块 code 必须大写且稳定** —— 它是章节标题里
`## 二、登录（RQ-LOGIN）` 的一部分，标题形态是端/模块绑定的权威来源。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 🔴 端枚举的唯一事实源在 SKILL.md「端枚举（固定，全流程统一）」。
#    这里必须与它一致；改这里之前先改 SKILL.md。
ENDPOINTS = ("用户小程序", "管理后台", "收银端", "商家端", "服务端", "外部系统")
PRIORITIES = ("P0", "P1", "P2")
STATUSES = ("新增", "改造", "保留")


def build(src: dict) -> dict:
    modules = []
    total = 0
    for m in src.get("modules") or []:
        code = (m.get("code") or "").strip().upper()
        name = m.get("name") or ""
        if not code:
            raise ValueError("模块「%s」缺 code —— 需求编号靠它生成。" % name)
        if not name:
            raise ValueError("模块 code=%s 缺 name。" % code)
        feats = []
        for i, f in enumerate(m.get("features") or [], start=1):
            where = "模块「%s」第 %d 项「%s」" % (name, i, f.get("name") or "?")
            p = f.get("priority")
            if p not in PRIORITIES:
                raise ValueError("%s 的 priority=%r，只能是 %s"
                                 % (where, p, "/".join(PRIORITIES)))
            ends = f.get("ends") or []
            if not ends:
                raise ValueError("%s 的 ends 为空 —— 至少要有一端。" % where)
            bad = [e for e in ends if e not in ENDPOINTS]
            if bad:
                raise ValueError(
                    "%s 的 ends 含端枚举外的值 %s。\n"
                    "  端枚举只有：%s\n"
                    "  端枚举之外的参与方请写「外部系统」，**不要发明新端名** ——\n"
                    "  端名一改，04/06 的过滤与统计全跟着错。"
                    % (where, "/".join(map(repr, bad)), " / ".join(ENDPOINTS)))
            if not (f.get("source") or "").strip():
                raise ValueError(
                    "%s 的 source 为空。「客户说的」和「我推测的」是两种东西，\n"
                    "  后续开发质疑时要知道找谁对 —— 没来源的需求不许进清单。\n"
                    "  写法：客户原话 R<轮>Q<题> / 盘点发现 <功能点id> / 合规要求:<条款>"
                    % where)
            st = f.get("status")
            if st not in STATUSES:
                raise ValueError("%s 的 status=%r，只能是 %s"
                                 % (where, st, "/".join(STATUSES)))
            feats.append({
                "id": "RQ-%s-%02d" % (code, i),
                "title": f.get("name") or "",
                "priority": p,
                "ends": list(ends),
                "source": (f.get("source") or "").strip(),
                "status": st,
                "detail": f.get("detail") or "",
            })
        total += len(feats)
        modules.append({"code": code, "name": name, "features": feats})

    # —— 澄清闸门：三条全过才算过闸，这里只做**机器能查的那两条**
    #   （第3 条 source 可追溯由source 非空 + 上面拒收保证）
    clarify = src.get("clarify") or {}
    confirmed = set(clarify.get("confirmed") or [])
    suspended = {s.get("domain") for s in (clarify.get("suspended") or [])}
    unconfirmed = clarify.get("assumptions") or []
    gate = {
        "confirmed": sorted(confirmed),
        "suspended": sorted(x for x in suspended if x),
        # 「没问到」不是一种状态 —— 未被列入 confirmed 也不在 suspended 的域列出来
        "unasked": None,   # 12 域全量由下游按 references 的表核对，本脚本不硬编码域清单
        "assumptionsPending": [a for a in unconfirmed if not a.get("confirmedBy")],
        "rounds": clarify.get("rounds") or [],
    }

    # —— 统计一律现算
    feats_all = [f for m in modules for f in m["features"]]
    meta = {
        "total": total,
        "moduleCount": len(modules),
        "byPriority": {p: sum(1 for f in feats_all if f["priority"] == p) for p in PRIORITIES},
        "byEnd": {e: sum(1 for f in feats_all if e in f["ends"]) for e in ENDPOINTS},
        "byStatus": {s: sum(1 for f in feats_all if f["status"] == s) for s in STATUSES},
    }

    return {"meta": meta, "clarifyGate": gate,
            "modules": modules}


def main() -> int:
    ap = argparse.ArgumentParser(description="装配 requirement.json")
    ap.add_argument("source", help="需求原始记录.json（格式见本文件头）")
    ap.add_argument("-o", "--out", default=None)
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

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.source)), "requirement.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    g = data["clarifyGate"]
    print("已写出: %s" % out)
    print("  需求 %d 条 / 模块 %d 个" % (data["meta"]["total"], data["meta"]["moduleCount"]))
    print("  优先级分布: %s" % " ".join("%s=%d" % kv for kv in data["meta"]["byPriority"].items()))
    print("  端分布: %s" % " ".join("%s=%d" % kv for kv in data["meta"]["byEnd"].items() if kv[1]))
    print("  澄清闸门: 已确认 %d 域 / 显式挂起 %d 域 / 待确认假设 %d 条"
          % (len(g["confirmed"]), len(g["suspended"]), len(g["assumptionsPending"])))
    if g["assumptionsPending"]:
        print("\n🔴 有未确认的假设 —— 按 references「澄清闸门」，过不了闸不许进 02。")
        for a in g["assumptionsPending"]:
            print("     · %s" % a.get("text"))
    print("\n下一步: python ../../feedback/checks/check-requirements.py <需求清单.md>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())