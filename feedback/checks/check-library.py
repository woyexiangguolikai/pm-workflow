#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03b 素材库 质量检查器 · 对 library/ 目录执行 A1–A8
====================================================
库不是「一次性产出」，是**持续增长、被反复检索的资产**。所以判据也不同于其他阶段：
其他阶段判「这一次做得好不好」，本阶段要判「**这条素材以后还敢不敢用**」。

用法:
    python check-library.py <library_dir> [--json <输出路径>] [--index] [--today YYYY-MM-DD]
    python check-library.py --selftest        # 变异测试：证明检查有判别力

    --index  同时写出 library/index.json（由条目生成，禁止手写）

判据:
    A1  必填字段齐全
    A2  id 唯一，且前缀与 type 匹配（c-/m-/p-）
    A3  来源可溯（sourceUrl 非空 + capturedAt 是合法日期）
    A4  许可在白名单内（GPL / NC / 未标注一律拦下）★ 硬门槛
    A5  无重复条目（type + tags + summary 指纹唯一）
    A6  support 表态度（含版本数字，否则将来无法判失效）
    A7  status 合法；deprecated / stale 必须给 replacedBy 或 keepReason，且 replacedBy 指向存在的 id
    A8  index.json 与目录一致（单一数据源铁律）

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么 A4 是硬门槛，而且必须自动化
-------------------------------------
网上捞来的素材最大风险**不是不好看，是不敢用**。GPL / CC-BY-NC 的组件进了商业交付，
是法务问题而不是设计问题；而「忘了记许可」和「许可就是不允许商用」在数据上长得一样。
**人是记不住 200 条素材的许可的，机器记得住** —— 所以这条绝不能推给人。

为什么 A6 要抠「有没有版本数字」
----------------------------------
`support: 现代浏览器` 看着像填了，实际等于没填 —— 三年后没人能判断它是否还能用。
这类「看起来填了、实际不可判」的字段是最隐蔽的假绿（同 AP-06）。

为什么 A8 存在
--------------
`index.json` 若可手写，就必然与目录漂移。它只能由本脚本 `--index` 生成 ——
与其他阶段同一条铁律：**单一数据源，改数据源 → 重新生成视图**。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

TYPES = ("component", "motion", "pattern")
PREFIX = {"component": "c", "motion": "m", "pattern": "p"}

REQUIRED = ("id", "type", "name", "tags", "summary", "license",
            "sourceUrl", "capturedAt", "support", "status", "usedBy")

# 允许的许可：可商用 + 可再分发。original = 自有原创。
ALLOWED_LICENSES = {
    "original", "public-domain", "cc0-1.0",
    "mit", "apache-2.0", "isc", "0bsd",
    "bsd-2-clause", "bsd-3-clause",
    "cc-by-4.0", "cc-by-3.0",
}
# 明确拦下：传染性 / 禁商用 / 禁演绎。给出理由，便于人一眼看懂为什么被拦。
BLOCKED_REASONS = {
    "gpl": "传染性许可：衍生作品也须开源，不可用于闭源商业交付",
    "gpl-2.0": "传染性许可（GPL-2.0）",
    "gpl-3.0": "传染性许可（GPL-3.0）",
    "agpl": "传染性许可（AGPL，网络服务亦触发）",
    "agpl-3.0": "传染性许可（AGPL-3.0，网络服务亦触发）",
    "lgpl": "弱传染性许可，需逐案评估",
    "cc-by-nc": "禁止商用（NC）",
    "cc-by-nc-4.0": "禁止商用（CC-BY-NC-4.0）",
    "cc-by-nc-sa": "禁止商用 + 相同方式共享",
    "cc-by-nd": "禁止演绎（ND）",
    "bsd-4-clause": "含广告条款，需逐案评估",
    "proprietary": "专有许可，未获授权不得使用",
    "unknown": "许可未标注 —— 与「不允许使用」等价处理",
}

STATUSES = ("active", "stale", "deprecated")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[cmp]-\d{4}$")
VERSION_DIGIT_RE = re.compile(r"\d")
MD_NAME_RE = re.compile(r"^[cmp]-\d{4}-[a-z0-9-]+\.md$")


# ------------------------------------------------------------ front-matter
def parse_front_matter(text: str) -> tuple[dict, str]:
    """解析 md 头部 `---` 包裹的 `key: value` 块。零依赖，不用 yaml。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    end = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
        s = lines[i].strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, "\n".join(lines[end + 1:])


def as_list(v: str) -> list[str]:
    s = (v or "").strip()
    if not s or s in ("[]", "-"):
        return []
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [x.strip().strip("'\"") for x in re.split(r"[,，]", s) if x.strip()]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


# ------------------------------------------------------------ 判据
def analyze(lib: Path, today: str | None = None) -> dict:
    if not lib.is_dir():
        return {"error": f"目录不存在: {lib}"}

    entries: list[dict] = []
    for p in sorted(lib.rglob("*.md")):
        rel = p.relative_to(lib)
        if p.name.lower() == "readme.md":
            continue
        meta, body = parse_front_matter(p.read_text(encoding="utf-8"))
        entries.append({
            "path": str(rel).replace("\\", "/"),
            "rel": rel,
            "meta": meta,
            "body": body,
            "inLocal": rel.parts[0] == "local",
            "hasFrontMatter": bool(meta),
        })

    if not entries:
        return {"error": "库中没有任何条目（*.md）"}

    checks: list[dict] = []

    # ---------- A1 必填字段齐全 ----------
    no_fm = [e["path"] for e in entries if not e["hasFrontMatter"]]
    lack = []
    for e in entries:
        if not e["hasFrontMatter"]:
            continue
        miss = [f for f in REQUIRED
                if f not in e["meta"] or e["meta"][f].strip() in ("", "-")]
        if miss:
            lack.append({"path": e["path"], "missing": miss})
    bad_a1 = bool(lack or no_fm)
    checks.append({
        "id": "A1", "title": "必填字段齐全",
        "status": "fail" if bad_a1 else "pass",
        "evidence": {"fields": list(REQUIRED), "violations": lack,
                     "noFrontMatter": no_fm},
    })

    # 无 front-matter 的文件已在 A1 报过，后续判据不再重复处理它们。
    # 纪律：**同一缺陷只报一次** —— 重复报警会让人整体忽略判据。
    judged = [e for e in entries if e["hasFrontMatter"]]

    # ---------- A2 id 唯一 + 前缀与 type 匹配 + 文件名以 id 开头 ----------
    ids = [e["meta"].get("id", "") for e in judged]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    bad_id, bad_prefix, bad_name = [], [], []
    for e in judged:
        cid, typ = e["meta"].get("id", ""), e["meta"].get("type", "")
        if not ID_RE.match(cid):
            bad_id.append({"path": e["path"], "id": cid})
            continue
        want = PREFIX.get(typ)
        if want is None:
            bad_prefix.append({"path": e["path"], "type": typ,
                               "problem": f"type 不在 {list(TYPES)} 内"})
        elif not cid.startswith(want + "-"):
            bad_prefix.append({"path": e["path"], "id": cid, "type": typ,
                               "problem": f"应为 {want}- 开头"})
        if not e["rel"].name.startswith(cid + "-"):
            bad_name.append({"path": e["path"], "id": cid,
                             "problem": f"文件名应以 {cid}- 开头"})
    bad_a2 = bool(dup or bad_id or bad_prefix or bad_name)
    checks.append({
        "id": "A2", "title": "id 唯一、前缀匹配 type、文件名以 id 开头",
        "status": "fail" if bad_a2 else "pass",
        "evidence": {"duplicates": dup, "badFormat": bad_id,
                     "prefixMismatch": bad_prefix, "badFileName": bad_name,
                     "types": list(TYPES)},
    })

    # ---------- A3 来源可溯 ----------
    bad_src = []
    for e in judged:
        url = e["meta"].get("sourceUrl", "")
        cap = e["meta"].get("capturedAt", "")
        problems = []
        if not url:
            problems.append("sourceUrl 为空")
        if not DATE_RE.match(cap):
            problems.append(f"capturedAt 不是 YYYY-MM-DD：{cap!r}")
        else:
            try:
                datetime.strptime(cap, "%Y-%m-%d")
            except ValueError:
                problems.append(f"capturedAt 不是合法日期：{cap!r}")
        if problems:
            bad_src.append({"path": e["path"], "problems": problems})
    checks.append({
        "id": "A3", "title": "来源可溯（sourceUrl + capturedAt）",
        "status": "fail" if bad_src else "pass",
        "evidence": {"violations": bad_src},
    })

    # ---------- A4 许可白名单（硬门槛） ----------
    local_exempt = [e["path"] for e in judged if e["inLocal"]]
    bad_lic, blocked = [], []
    for e in [x for x in judged if not x["inLocal"]]:
        lic = norm(e["meta"].get("license", ""))
        if lic in ALLOWED_LICENSES:
            continue
        if lic in BLOCKED_REASONS:
            blocked.append({"path": e["path"], "license": lic,
                            "reason": BLOCKED_REASONS[lic]})
        else:
            bad_lic.append({"path": e["path"], "license": lic or "（空）",
                            "reason": "不在白名单内 —— 与「不允许使用」等价处理"})
    bad_a4 = bool(bad_lic or blocked)
    checks.append({
        "id": "A4", "title": "许可在白名单内",
        "status": "fail" if bad_a4 else "pass",
        "evidence": {"allowed": sorted(ALLOWED_LICENSES),
                     "notAllowed": bad_lic, "explicitlyBlocked": blocked},
    })

    # ---------- A5 无重复条目 ----------
    seen: dict[str, list[str]] = {}
    for e in judged:
        m = e["meta"]
        fp = "|".join([norm(m.get("type", "")),
                       ",".join(sorted(norm(t) for t in as_list(m.get("tags", "")))),
                       norm(m.get("summary", ""))])
        seen.setdefault(fp, []).append(e["path"])
    dupes = [{"paths": v} for v in seen.values() if len(v) > 1]
    checks.append({
        "id": "A5", "title": "无重复条目（type+tags+summary 指纹）",
        "status": "fail" if dupes else "pass",
        "evidence": {"duplicates": dupes, "unique": len(seen), "total": len(entries)},
    })

    # ---------- A6 support 表态度 ----------
    bad_sup = []
    for e in judged:
        sup = e["meta"].get("support", "")
        problems = []
        if not sup.strip():
            problems.append("support 为空")
        elif not VERSION_DIGIT_RE.search(sup):
            problems.append(f"support 无版本数字，将来无法判失效：{sup!r}")
        if problems:
            bad_sup.append({"path": e["path"], "problems": problems})
    checks.append({
        "id": "A6", "title": "support 含版本数字（可判失效）",
        "status": "fail" if bad_sup else "pass",
        "evidence": {"violations": bad_sup},
    })

    # ---------- A7 status 合法 + 退役必须交代后事 ----------
    known_ids = {i for i in ids if i}
    bad_st, no_from = [], []
    for e in judged:
        m = e["meta"]
        st = norm(m.get("status", ""))
        if st not in STATUSES:
            bad_st.append({"path": e["path"], "status": m.get("status", "")})
            continue
        if st in ("deprecated", "stale"):
            rep = m.get("replacedBy", "").strip()
            keep = m.get("keepReason", "").strip()
            if not rep and not keep:
                no_from.append({"path": e["path"], "status": st,
                                "problem": "退役素材未给 replacedBy 或 keepReason"})
            elif rep and rep not in known_ids:
                no_from.append({"path": e["path"], "status": st,
                                "problem": f"replacedBy 指向不存在的 id：{rep}"})
    bad_a7 = bool(bad_st or no_from)
    checks.append({
        "id": "A7", "title": "status 合法，退役素材交代后事",
        "status": "fail" if bad_a7 else "pass",
        "evidence": {"allowed": list(STATUSES),
                     "badStatus": bad_st, "noFollowUp": no_from},
    })

    # ---------- A8 index 与目录一致 ----------
    gen = build_index(judged)
    idx_path = lib / "index.json"
    if not idx_path.exists():
        checks.append({
            "id": "A8", "title": "index.json 与目录一致",
            "status": "fail",
            "evidence": {"reason": "index.json 不存在 —— 用 --index 生成",
                         "expectedCount": gen["count"]},
        })
    else:
        try:
            cur = json.loads(idx_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as ex:
            cur = None
            checks.append({
                "id": "A8", "title": "index.json 与目录一致",
                "status": "fail",
                "evidence": {"reason": f"index.json 解析失败: {ex}"},
            })
        if cur is not None:
            cur_ids = sorted(c.get("id", "") for c in cur.get("entries", []))
            gen_ids = sorted(c.get("id", "") for c in gen["entries"])
            drift = {"onlyInIndex": sorted(set(cur_ids) - set(gen_ids)),
                     "onlyInFiles": sorted(set(gen_ids) - set(cur_ids))}
            bad_a8 = bool(drift["onlyInIndex"] or drift["onlyInFiles"]) \
                or cur.get("count") != gen["count"]
            checks.append({
                "id": "A8", "title": "index.json 与目录一致",
                "status": "fail" if bad_a8 else "pass",
                "evidence": {"indexCount": cur.get("count"),
                             "actualCount": gen["count"], **drift},
            })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {
        "checks": checks,
        "failed": failed,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "totalChecks": len(checks),
        "entryCount": len(judged),
        "byType": {t: sum(1 for e in judged if e["meta"].get("type") == t)
                   for t in TYPES},
        "licenseHistogram": _histogram([norm(e["meta"].get("license", ""))
                                        for e in judged if not e["inLocal"]]),
        "usedCount": sum(1 for e in judged if as_list(e["meta"].get("usedBy", ""))),
        "localExempt": local_exempt,
    }


def _histogram(xs: list[str]) -> dict:
    h: dict[str, int] = {}
    for x in xs:
        h[x] = h.get(x, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


def build_index(entries: list[dict]) -> dict:
    out = []
    for e in entries:
        m = e["meta"]
        out.append({
            "id": m.get("id", ""),
            "type": m.get("type", ""),
            "name": m.get("name", ""),
            "tags": as_list(m.get("tags", "")),
            "summary": m.get("summary", ""),
            "license": m.get("license", ""),
            "status": m.get("status", ""),
            "usedBy": as_list(m.get("usedBy", "")),
            "path": e["path"],
        })
    out.sort(key=lambda c: c["id"])
    return {"count": len(out), "entries": out}


# ------------------------------------------------------------ 变异测试
GOOD_MD = """---
id: c-0001
type: component
name: 加载按钮
tags: [button, loading]
summary: 提交时原地变 Spinner 并锁定宽度
license: original
sourceUrl: _original_
capturedAt: 2026-10-11
support: Chrome 90+ / Safari 15+
status: active
usedBy: []
---
正文
"""

GOOD_MD2 = """---
id: m-0001
type: motion
name: 骨架屏微光
tags: [skeleton, loading]
summary: 加载占位上的横向微光扫过
license: mit
sourceUrl: https://example.com/shimmer
capturedAt: 2026-10-11
support: Chrome 88+
status: active
usedBy: [example-project]
---
正文
"""

BAD_MD = """---
id: c-1
type: motion
name: 某个组件
tags: [button, loading]
summary: 提交时原地变 Spinner 并锁定宽度
license: gpl-3.0
sourceUrl:
capturedAt: 2026/10/11
support: 现代浏览器
status: 在用
usedBy: []
---
正文
"""


def _mk(tmp: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


def selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        good = _mk(root / "good", {
            "components/c-0001-loading-button.md": GOOD_MD,
            "motions/m-0001-skeleton-shimmer.md": GOOD_MD2,
        })
        (good / "index.json").write_text(
            json.dumps(build_index(_load(good)), ensure_ascii=False), encoding="utf-8")

        bad = _mk(root / "bad", {
            "components/c-0001-dup.md": BAD_MD,
            "motions/m-0001-dup2.md": BAD_MD,
        })
        # 坏样本：无 index.json；且两条指纹相同 → A5 也红

        g = analyze(good)
        b = analyze(bad)
    expect_bad = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]
    ok_good = g.get("failed") == []
    ok_bad = b.get("failed") == expect_bad

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿       : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={g.get('failed')})")
    print(f"  坏样本 期望八项全红   : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={b.get('failed')})")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立：同一套探针在两种世界状态下产出不同结果。")
    return 0


def _load(lib: Path) -> list[dict]:
    """读库内全部 .md。**不做「静默跳过」** —— 被跳过的文件必须被看见。

    踩过的坑：曾用「文件名以 `_` 开头则跳过」的约定，结果 `_draft-c-0003.md`
    这类文件会**完全消失在统计之外**（不报错、不计入、无法察觉）。
    这就是 AP-06 那一类「静默假绿」——**它不报错，它当没看见**。
    现在的规则：只跳 README；没有 front-matter 的 .md 会被记下来并判 A1 失败。
    """
    out = []
    for p in sorted(lib.rglob("*.md")):
        rel = p.relative_to(lib)
        if p.name.lower() == "readme.md":
            continue
        meta, body = parse_front_matter(p.read_text(encoding="utf-8"))
        out.append({"path": str(rel).replace("\\", "/"), "rel": rel,
                    "meta": meta, "body": body, "inLocal": rel.parts[0] == "local",
                    "hasFrontMatter": bool(meta)})
    return out


# ------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="03b 素材库 质量检查器")
    ap.add_argument("source", nargs="?", help="library 目录")
    ap.add_argument("--json", dest="json_out", help="结果写入的 JSON 路径")
    ap.add_argument("--index", action="store_true", help="同时生成 index.json")
    ap.add_argument("--selftest", action="store_true", help="运行变异测试")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.source:
        ap.print_help()
        return 2

    lib = Path(args.source)
    entries = _load(lib) if lib.is_dir() else []
    if args.index and entries:
        (lib / "index.json").write_text(
            json.dumps(build_index(entries), ensure_ascii=False, indent=2),
            encoding="utf-8")

    result = analyze(lib)
    result["source"] = str(lib)

    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2

    print(f"来源: {lib}")
    print(f"条目总数: {result['entryCount']}"
          f"（组件 {result['byType']['component']} / 动效 {result['byType']['motion']}"
          f" / 交互 {result['byType']['pattern']}）")
    print(f"已被引用: {result['usedCount']} / {result['entryCount']}")
    lic_hist = " / ".join(
        "{}×{}".format(k or "（空）", v) for k, v in result["licenseHistogram"].items())
    print(f"许可分布: {lic_hist}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
        print(f"  [{mark}] {c['id']} {c['title']}")
        if c["status"] != "fail":
            continue
        ev = c["evidence"]
        if c["id"] == "A1":
            for v in ev["violations"]:
                print(f"         {v['path']}: 缺 {', '.join(v['missing'])}")
        elif c["id"] == "A2":
            if ev["duplicates"]:
                print(f"         重复 id: {ev['duplicates']}")
            for v in ev["badFormat"]:
                print(f"         {v['path']}: id {v['id']!r} 形态不合法")
            for v in ev["prefixMismatch"]:
                print(f"         {v['path']}: {v['problem']}")
        elif c["id"] == "A3":
            for v in ev["violations"]:
                print(f"         {v['path']}: {'；'.join(v['problems'])}")
        elif c["id"] == "A4":
            for v in ev["explicitlyBlocked"]:
                print(f"         ⛔ {v['path']}: {v['license']} —— {v['reason']}")
            for v in ev["notAllowed"]:
                print(f"         ⚠️  {v['path']}: {v['license']} —— {v['reason']}")
        elif c["id"] == "A5":
            for v in ev["duplicates"]:
                print(f"         指纹重复: {' + '.join(v['paths'])}")
        elif c["id"] == "A6":
            for v in ev["violations"]:
                print(f"         {v['path']}: {'；'.join(v['problems'])}")
        elif c["id"] == "A7":
            for v in ev["badStatus"]:
                print(f"         {v['path']}: status = {v['status']!r}")
            for v in ev["noFollowUp"]:
                print(f"         {v['path']}: {v['problem']}")
        elif c["id"] == "A8":
            if ev.get("reason"):
                print(f"         {ev['reason']}")
            else:
                print(f"         index {ev['indexCount']} / 实际 {ev['actualCount']}")
                if ev["onlyInIndex"]:
                    print(f"         index 多出: {ev['onlyInIndex']}")
                if ev["onlyInFiles"]:
                    print(f"         文件多出: {ev['onlyInFiles']}")

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
