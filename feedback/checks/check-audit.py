#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
00 盘点阶段质量检查器 · 对audit.json 执行 A1–A6
================================================================
实现 00-audit rubric 的 A 类判据 —— 可脚本化、必须自动判、不许推给人。

用法:
    python check-audit.py <audit.json> [--downstream <requirement.json|prd.json> ...]
    python check-audit.py --selftest# 变异测试：证明检查有判别力

判据:
    A1  数据源结构完整（模块有 features，功能有 id/name/status）
    A2  功能点编号连续唯一（按模块前缀分组）
    A3  status 取值在 闭集内
    A4  盘点项数与视图声明数一致（两侧都现算）
    A5  项目性质已声明，且与存量内容量自洽
    A6  新增/改造项在下游有落点（跨阶段；未提供下游时 SKIP）

退出码: 0 = 全部通过（或仅 skip）；1 = 存在失败项；2 = 运行错误

为什么这个阶段值得有自己的检查器
--------------------------------
盘点的产物是**后续所有阶段的对照基线**。它盘漏了一项，01 就不会有那条需求，
02 就不会有那条规则 —— 而且**没人会发现**，因为下游只看得到「上游没给的东西」，
看不到「本来就该有的东西」。这是全流程里唯一一处「漏检等于静默失效」的位置。

A4 为什么要「两侧都现算」
-------------------------
视图里的数字如果是从数据源渲染的，两侧必然相等，A4 永真 —— 永真的判据等于没有判据。
所以判据检查的是**视图里写的数字是否等于现算值**；若视图数字是运行时算出来的，
脚本识别得出这一点并SKIP，而不是给一个永真的绿灯。

判据不许认识某一个项目的端名 / 模块名 / 表名
--------------------------------------------
元规则 4。01 阶段的检查器曾硬编码一份端名白名单，换项目后好文档 100% 假阳性 ——
那是本工作流已犯过的错。这里的模块前缀**全部现算**，不写死任何一个模块代号。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STATUSES = ("新增", "改造", "保留", "待定")
NATURES = ("全新项目", "存量改造", "存量扩展")

# 编号形态：<前缀>-<数字>，前缀 1–8 位大写字母/数字。
# 前缀长度不写死成 1 —— 那是按某一个项目的命名习惯去规定通用工作流。
ID_RE = re.compile(r"^([A-Z][A-Z0-9]{0,7})-(\d+)$")


def run_checks(data: dict, downstream_texts: dict[str, str] | None) -> dict:
    checks: list[dict] = []

    # ---------- A1 结构完整 ----------
    struct_err: list[str] = []
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        struct_err.append("顶层缺 modules 数组（或为空）")
        modules = []
    seen_in: dict[str, str] = {}
    for mi, m in enumerate(modules):
        where = f"modules[{mi}]"
        if not isinstance(m, dict):
            struct_err.append(f"{where} 不是对象")
            continue
        mname = m.get("name") or m.get("id") or f"#{mi}"
        where = f"模块「{mname}」"
        feats = m.get("features")
        if not isinstance(feats, list):
            struct_err.append(f"{where}缺 features 数组")
            continue
        for fi, f in enumerate(feats):
            if not isinstance(f, dict):
                struct_err.append(f"{where}.features[{fi}] 不是对象")
                continue
            fid = f.get("id")
            if not fid or not isinstance(fid, str):
                struct_err.append(f"{where}.features[{fi}] 缺 id")
            else:
                if fid in seen_in:
                    struct_err.append(f"{where}.features[{fi}] id 重复：{fid}"
                                      f"（已见于 {seen_in[fid]}）")
                else:
                    seen_in[fid] = where
            if not f.get("name"):
                struct_err.append(f"{where}.features[{fi}]（{fid or'#' + str(fi)}）缺 name")
            if f.get("status") not in STATUSES:
                struct_err.append(
                    f"{where}.features[{fi}]（{fid or '#' + str(fi)}）"
                    f"status={f.get('status')!r} 不在闭集 {STATUSES}")

    # 重复 id 同时也算 A2 的输入不齐，这里只报结构，A2 报重复
    dup_ids = [v["id"] for v in struct_err if "id 重复" in v]
    checks.append({
        "id": "A1",
        "title": "数据源结构完整",
        "status": "fail" if [e for e in struct_err if "id 重复" not in e] else "pass",
        "evidence": {"errors": struct_err,
                     "moduleCount": len(modules),
                     "featureCount": len(seen_in)},
    })

    # ---------- A2 编号连续唯一 ----------
    by_prefix: dict[str, list[int]] = {}
    bad_form: list[dict] = []
    for m in modules:
        if not isinstance(m, dict):
            continue
        mname = m.get("name") or m.get("id") or "?"
        for f in (m.get("features") or []):
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            mm = ID_RE.match(fid) if isinstance(fid, str) else None
            if not mm:
                bad_form.append({"module": mname, "id": fid})
                continue
            by_prefix.setdefault(mm.group(1), []).append(int(mm.group(2)))

    a2_problems: list[dict] = []
    for pfx, nums in sorted(by_prefix.items()):
        seen, dup = set(), set()
        for n in nums:
            if n in seen:
                dup.add(n)
            seen.add(n)
        missing = sorted(set(range(1, max(nums) + 1)) - seen)
        if dup or missing:
            a2_problems.append({"prefix": pfx, "duplicates": sorted(dup), "missing": missing})

    checks.append({
        "id": "A2",
        "title": "功能点编号连续唯一",
        "status": "fail" if (a2_problems or bad_form) else "pass",
        "evidence": {"prefixes": {k: len(v) for k, v in sorted(by_prefix.items())},
                     "violations": a2_problems,
                     "badForm": bad_form},
    })

    # ---------- A3 status 闭集 ----------
    # A1 已经逐条报过 status 非法；此处只报**汇总视图**，便于一眼看比例。
    all_feats = [f for m in modules if isinstance(m, dict)
                 for f in (m.get("features") or []) if isinstance(f, dict)]
    bad_status = [{"id": f.get("id"), "module": m.get("name") or m.get("id")}
                  for m in modules if isinstance(m, dict)
                  for f in (m.get("features") or []) if isinstance(f, dict)
                  and f.get("status") not in STATUSES]
    checks.append({
        "id": "A3",
        "title": "status 取值在闭集内",
        "status": "fail" if bad_status else "pass",
        "evidence": {"violations": bad_status, "allowed": list(STATUSES),
                     "distribution": {s: sum(1 for f in all_feats if f.get("status") == s)
                                      for s in STATUSES}},
    })

    # ---------- A4 盘点项数与视图声明数一致 ----------
    # 视图声明数只认两种来源：显式的 meta.totals，或文本里标着「共N 项」的声明。
    # 两者都拿不到 → SKIP（不给永真绿灯）。
    declared_total = None
    decl_src = None
    meta = data.get("meta")
    if isinstance(meta, dict):
        for key in ("total", "featureTotal", "auditTotal"):
            if isinstance(meta.get(key), int):
                declared_total = meta[key]
                decl_src = f"meta.{key}"
                break
    if declared_total is None:
        m2 = re.search(r"(?:共|合计|总计)\s*(\d+)\s*(?:项|条|个功能)", str(data.get("summary", "")))
        if m2:
            declared_total = int(m2.group(1))
            decl_src = "summary 文本"

    actual_total = len(all_feats)
    if declared_total is None:
        checks.append({
            "id": "A4", "title": "盘点项数与视图声明数一致",
            "status": "skip",
            "evidence": {"reason": "数据源里没有可核对的声明数（meta.total / summary 未给）。"
                                   "无声明不等于通过，故跳过。",
                         "actualTotal": actual_total},
        })
    else:
        checks.append({
            "id": "A4", "title": "盘点项数与视图声明数一致",
            "status": "pass" if declared_total == actual_total else "fail",
            "evidence": {"source": decl_src, "declared": declared_total,
                         "actual": actual_total},
        })

    # ---------- A5 项目性质已声明且自洽 ----------
    nature = data.get("nature") or (meta or {}).get("nature")
    existing = sum(1 for f in all_feats if f.get("status") in ("改造", "保留"))
    if nature is None:
        checks.append({
            "id": "A5", "title": "项目性质已声明且与存量内容量自洽",
            "status": "fail",
            "evidence": {"reason": "未声明 nature（取值应为 全新项目/存量改造/存量扩展）。"
                                   "不声明则下游无法判断盘点该不该做、PRD 该写差异还是全量。"},
        })
    elif nature not in NATURES:
        checks.append({
            "id": "A5", "title": "项目性质已声明且与存量内容量自洽",
            "status": "fail",
            "evidence": {"declared": nature, "allowed": list(NATURES)},
        })
    elif nature in ("存量改造", "存量扩展") and existing == 0:
        # warn 级：不是失败，是「你大概忘了盘」
        checks.append({
            "id": "A5", "title": "项目性质已声明且与存量内容量自洽",
            "status": "warn",
            "evidence": {"declared": nature, "existingFeatureCount": 0,
                         "reason": "声明为存量项目，但没有任何「改造/保留」条目 —— "
                                   "存量功能地图大概没盘。"},
        })
    else:
        checks.append({
            "id": "A5", "title": "项目性质已声明且与存量内容量自洽",
            "status": "pass",
            "evidence": {"declared": nature, "existingFeatureCount": existing},
        })

    # ---------- A6 新增/改造项在下游有落点 ----------
    todo = [f.get("id") for f in all_feats if f.get("status") in ("新增", "改造")]
    todo = [t for t in todo if t]
    if not downstream_texts:
        checks.append({
            "id": "A6", "title": "新增/改造项在下游有落点",
            "status": "skip",
            "evidence": {"reason": "未提供 --downstream。跨阶段判据，00 阶段跑时下游还不存在；"
                                   "应在 01/02 阶段回补跑一次。",
                         "pendingCount": len(todo)},
        })
    else:
        blob = "\n".join(downstream_texts.values())
        orphan = [t for t in todo if t not in blob]
        checks.append({
            "id": "A6", "title": "新增/改造项在下游有落点",
            "status": "fail" if orphan else "pass",
            "evidence": {"checked": len(todo), "orphans": orphan,
                         "downstream": sorted(downstream_texts.keys())},
        })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    warned = [c["id"] for c in checks if c["status"] == "warn"]
    skipped = [c["id"] for c in checks if c["status"] == "skip"]
    return {
        "checks": checks,
        "failed": failed,
        "warned": warned,
        "skipped": skipped,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "totalChecks": len(checks),
        "moduleCount": len(modules),
        "featureCount": actual_total,
    }


# ---------------------------------------------------------------- 变异测试
#🔴 样本里的模块名 / 前缀刻意用中性词（PAY/ORDER/USER），**不用任何一个真实项目名**。
#    元规则 4：判据与样本都不许认识某一个项目。
GOOD = {
    "nature": "存量改造",
    "summary": "共 6 项",
    "modules": [
        {"name": "支付", "features": [
            {"id": "PAY-01", "name": "下单并支付", "status": "改造"},
            {"id": "PAY-02", "name": "退款", "status": "保留"},
        ]},
        {"name": "订单", "features": [
            {"id": "ORDER-01", "name": "订单状态机", "status": "改造"},
            {"id": "ORDER-02", "name": "订单列表", "status": "新增"},
            {"id": "ORDER-03", "name": "导出", "status": "待定"},
        ]},
        {"name": "用户", "features": [
            {"id": "USER-01", "name": "登录", "status": "保留"},
        ]},
    ],
}

#逐植入 6处缺陷：A1 缺 name / A2 缺号 + 形态非法 / A3 status 非法 / A4 声明数错
#                / A6 悬空id
BAD = {
    "nature": "存量改造",
    "summary": "共 99 项",
    "modules": [
        {"name": "支付", "features": [
            {"id": "PAY-01", "name": "下单并支付", "status": "改造"},
            {"id": "PAY-03", "name": "退款", "status": "保留"},
            {"id": "pay-02", "name": "对账", "status": "上线"},          # A2 形态非法 + A3
            {"id": "PAY-04", "name": "", "status": "保留"},                # A1 缺 name
        ]},
        {"name": "孤儿", "features": [
            {"id": "GHOST-01", "name": "没人接的需求", "status": "新增"},   # A6 悬空
        ]},
    ],
}


def selftest() -> int:
    good = run_checks(GOOD, {"requirement.json": json.dumps(
        {"requirements": [{"id": "PAY-01"}, {"id": "PAY-02"}, {"id": "ORDER-01"},
                          {"id": "ORDER-02"}, {"id": "ORDER-03"}, {"id": "USER-01"}]},
        ensure_ascii=False)})
    # 好样本额外跑一次「无下游」：A6 应 SKIP 而不是 FAIL（跨阶段是客观事实）
    good_nodown = run_checks(GOOD, None)
    bad = run_checks(BAD, {"requirement.json": json.dumps(
        {"requirements": [{"id": "PAY-01"}, {"id": "PAY-03"}, {"id": "pay-02"},
                          {"id": "PAY-04"}]}, ensure_ascii=False)})

    #🔴 逐植入缺陷断言命中 —— 不断言「有命中」。
    #    只断言「有命中」会掩盖「某条规则从未被验证过」（AP-06）。
    expect_bad = {"A1", "A2", "A3", "A4", "A6"}
    got_bad = set(bad.get("failed", []))
    missed = sorted(expect_bad - got_bad)

    ok_good = good.get("failed") == []
    ok_good_skip = good_nodown.get("failed") == [] and "A6" in good_nodown.get("skipped", [])
    ok_bad = not missed

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿: {'通过' if ok_good else '失败'}"
          f"(实得 failed={good.get('failed')})")
    print(f"  好样本 无下游期望 A6 跳过: {'通过' if ok_good_skip else '失败'}"
          f"(实得 skipped={good_nodown.get('skipped')})")
    print(f"  坏样本 期望五项全红: {'通过' if ok_bad else '失败'}"
          f"(实得 failed={bad.get('failed')}"
          f"{'，漏报=' + str(missed) if missed else ''})")
    if not (ok_good and ok_good_skip and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        if missed:
            print(f"  ↳ 漏报 {missed}：这些判据在坏样本上从未触发过，等于没写。")
        return 1
    print("\n判别力成立：同一套探针在两种世界状态下产出不同结果。")
    return 0


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="00 盘点阶段质量检查器")
    ap.add_argument("source", nargs="?", help="audit.json 的路径")
    ap.add_argument("--downstream", action="append", default=[],
                    help="下游数据源（requirement.json / prd.json），可重复传")
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
    if not isinstance(data, dict):
        print("顶层必须是对象", file=sys.stderr)
        return 2

    downstream: dict[str, str] = {}
    for p in args.downstream:
        dp = Path(p)
        if not dp.exists():
            print(f"下游数据源不存在: {dp}", file=sys.stderr)
            return 2
        downstream[dp.name] = dp.read_text(encoding="utf-8")

    result = run_checks(data, downstream or None)
    result["source"] = str(path)

    print(f"来源: {path.name}")
    print(f"模块 {result['moduleCount']} 个 / 盘点项 {result['featureCount']} 条")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项"
          + (f"，警告 {len(result['warned'])}" if result["warned"] else "")
          + (f"，跳过 {len(result['skipped'])}" if result["skipped"] else ""))
    for c in result["checks"]:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "warn": "WARN"}[c["status"]]
        print(f"  [{mark}] {c['id']} {c['title']}")
        ev = c["evidence"]
        if c["status"] == "skip":
            print(f"         {ev.get('reason')}")
        elif c["id"] == "A1" and c["status"] == "fail":
            for e in ev["errors"]:
                print(f"         {e}")
        elif c["id"] == "A2" and c["status"] == "fail":
            for v in ev["violations"]:
                print(f"         前缀 {v['prefix']}: 重复 {v['duplicates']} 缺号 {v['missing']}")
            for v in ev["badForm"]:
                print(f"         模块「{v['module']}」编号形态非法: {v['id']!r}")
        elif c["id"] == "A3" and c["status"] == "fail":
            for v in ev["violations"]:
                print(f"         {v['id']}: status 不在闭集")
        elif c["id"] == "A4" and c["status"] == "fail":
            print(f"         {ev['source']} 声明 {ev['declared']} / 现算 {ev['actual']}")
        elif c["id"] == "A5" and c["status"] in ("fail", "warn"):
            print(f"         {ev.get('reason') or ev}")
        elif c["id"] == "A6" and c["status"] == "fail":
            print(f"         改了却下游无落点（{len(ev['orphans'])} 条）: "
                  + ", ".join(ev["orphans"][:12])
                  + ("…" if len(ev["orphans"]) > 12 else ""))

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入: {out}")

    return 1 if result["failed"] else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())