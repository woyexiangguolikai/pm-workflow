#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板洁净度守卫 —— 模板是要被拷贝进新项目的，**带旧项目内容就是污染源**。

背景（真实发生过）：`assets/templates/` 里那批「模板」其实是上一个项目的
真实脚本：项目名写在 `<title>` 里、业务实体（一卡通 / 甲方人事系统）写进数据模型与泳道、
甚至写着「42 条需求」这种字面量（**模板自己违反了工作流铁律 2：期望值从数据源现算**）。
拷贝它去开新项目，等于把废案的数据模型和文案一起继承下来。

四条 BLOCK 判据：

| 编号 | 判什么 | 为什么不许 |
|---|---|---|
| **T1** | 模板里出现**项目词**（读 `scripts/publish-denylist.txt`） | 项目词 = 某个项目的商业 know-how；模板是跨项目资产 |
| **T2** | `<title>` 标签内容**不含占位符**（`{{` / `%(` / `{`） | 文档标题写死 = 拷贝过去的人不会发现要改 |
| **T3** | **已下线/已取消阶段**的模板目录仍在 | SKILL.md 说「不要读、不要引」，模板目录却在分发它 |
| **T4** | 含 `lane` 的行里，被引号引用的**中文名不属于端枚举 ∪ {外部系统}** | 泳道必须对齐 SKILL.md 的端枚举；发明新端会让 04/06 的统计全错 |

一条 WARN：**T5** 模板目录与 SKILL.md 阶段表对不上（说明文档或目录有一边过期）。

> ⚠️ **没有配置 `scripts/publish-denylist.txt` 时，T1 报「未扫描」而不是「通过」** ——
> 静默通过 = 什么都没查。这与 `check-publish-safe.py` 是同一条纪律。

用法：
    python scripts/check-templates-clean.py <skill 目录>
    python scripts/check-templates-clean.py --selftest
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

# ---------- 判据常量 ----------

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
# ⚠️ 出现在「解析用正则」里的 <title> 不是要渲染的文档标题 —— 那是探针在抓别人的标题。
# 不排除会报 3 处假阳性（`re.search(r'<title>R:(.*?)</title>'...)`）。
# 判据的假阳性必须改判据，不能靠人工忽略。
PARSE_CTX_RE = re.compile(r"re\.(?:search|match|compile|findall|sub|finditer)\s*\(")
# 占位符形态：{{项目名}} · %(title)s · {name} · %s
PLACEHOLDER_RE = re.compile(r"\{\{|%\(\w+\)|\{[^{}]+\}|%[sd]")
LANE_LINE_RE = re.compile(r"lane", re.I)
# 泳道相关行里的中文名（被引号包住）
QUOTED_CN_RE = re.compile(r"""['"]([^'"]{2,12})['"]""")
CN_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{2,12}$")
# SKILL.md 里声明「已取消 / 已下线」的阶段号
RETIRED_RE = re.compile(r"^.*?\b(\d{2}[a-z]?)\b[^\n]*?(?:已取消|已下线)", re.M)
# SKILL.md 阶段表里的阶段名（「| **00 盘点** |」这种行）
STAGE_ROW_RE = re.compile(r"^\|\s*\*\*(\d{2}[a-z]?)\s*[^*]*\*\*", re.M)
# 端枚举块（「## 端枚举」之后直到下一个 ## 之间，类似「用户小程序 / 管理后台 / …」）
ENDPOINTS_RE = re.compile(r"^##\s*端枚举.*?\n```\n(.*?)\n```", re.S | re.M)

TEXT_SUFFIXES = {".py", ".js", ".md", ".css", ".html"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
DENY_REL = "scripts/publish-denylist.txt"
EXTRA_ALLOWED_CN = {"外部系统"}      # 端枚举之外的合法泳道
# 明确「不建项目模板目录」的阶段 —— 写清理由，否则 T5 会一直报警到被人无视
NO_TEMPLATE_STAGES = {
    "03b": "03b 是 skill 级、跨项目累积的库，不随项目建目录（SKILL.md 第 2 步已写明）",
}


# ---------- 扫描 ----------

def load_denylist(skill: Path) -> tuple[list[str], bool]:
    p = skill / DENY_REL
    if not p.exists():
        return [], False
    terms = []
    for line in p.read_text(encoding="utf-8").split("\n"):
        s = line.strip()
        if s and not s.startswith("#"):
            terms.append(s)
    return terms, True


def skill_facts(skill: Path) -> tuple[set[str], set[str], set[str]]:
    """从 SKILL.md 取：已下线阶段号 / 已声明阶段号 / 端枚举。"""
    md = (skill / "SKILL.md")
    if not md.exists():
        return set(), set(), set()
    t = md.read_text(encoding="utf-8")
    retired = set(RETIRED_RE.findall(t))
    stages = set(STAGE_ROW_RE.findall(t))
    ends: set[str] = set()
    m = ENDPOINTS_RE.search(t)
    if m:
        for part in re.split(r"[/、,，\n]", m.group(1)):
            s = part.strip()
            if s:
                ends.add(s)
    return retired, stages, ends


def scan_text(rel: str, text: str, terms: list[str]) -> list[dict]:
    hits: list[dict] = []
    for i, line in enumerate(text.split("\n"), 1):
        # T2 —— <title> 必须含占位符（解析用的正则不算）
        if not PARSE_CTX_RE.search(line):
            for mt in TITLE_RE.finditer(line):
                content = mt.group(1).strip()
                if content and not PLACEHOLDER_RE.search(content):
                    hits.append({"level": "BLOCK", "kind": "T2 文档标题写死（无占位符）",
                                 "path": rel, "line": i, "sample": line.strip()[:90]})
        # T1 —— 项目词
        for w in terms:
            if w and w in line:
                hits.append({"level": "BLOCK", "kind": "T1 项目词「%s」" % w,
                             "path": rel, "line": i, "sample": line.strip()[:90]})
                break
        # T4 —— 泳道行的中文名必须在端枚举内
        if LANE_LINE_RE.search(line):
            for qm in QUOTED_CN_RE.finditer(line):
                name = qm.group(1)
                if not CN_NAME_RE.match(name):
                    continue
                if name in _ALLOWED_CN:
                    continue
                hits.append({"level": "BLOCK", "kind": "T4 泳道名「%s」不在端枚举内" % name,
                             "path": rel, "line": i, "sample": line.strip()[:90]})
    return hits


_ALLOWED_CN: set[str] = EXTRA_ALLOWED_CN   # 运行时会并上端枚举


def analyze(skill: Path) -> dict:
    global _ALLOWED_CN
    terms, has_deny = load_denylist(skill)
    retired, stages, ends = skill_facts(skill)
    _ALLOWED_CN = EXTRA_ALLOWED_CN | ends

    tpl_root = skill / "assets" / "templates"
    hits: list[dict] = []

    if tpl_root.exists():
        for p in sorted(tpl_root.rglob("*")):
            if p.is_dir() or p.suffix not in TEXT_SUFFIXES:
                continue
            if any(d in p.parts for d in SKIP_DIRS):
                continue
            rel = str(p.relative_to(skill))
            hits += scan_text(rel, p.read_text(encoding="utf-8", errors="replace"), terms)

        # T3 —— 已下线阶段的模板目录仍在
        for d in sorted(tpl_root.iterdir()):
            if not d.is_dir() or d.name in SKIP_DIRS:
                continue
            m = re.match(r"^(\d{2}[a-z]?)", d.name)
            if m and m.group(1) in retired:
                hits.append({"level": "BLOCK",
                             "kind": "T3 已下线阶段 %s 的模板目录仍在" % m.group(1),
                             "path": str(d.relative_to(skill)), "line": 0,
                             "sample": "SKILL.md 已声明该阶段取消，模板却还在分发"})

        # T5 —— 目录与阶段表对不上（WARN）
        if stages:
            have = {re.match(r"^(\d{2}[a-z]?)", d.name).group(1)
                    for d in tpl_root.iterdir()
                    if d.is_dir() and re.match(r"^(\d{2}[a-z]?)", d.name)}
            missing = sorted(stages - have - retired - set(NO_TEMPLATE_STAGES))
            for s in missing:
                hits.append({"level": "WARN",
                             "kind": "T5 阶段 %s 在 SKILL.md 里但没有模板目录" % s,
                             "path": "assets/templates/", "line": 0,
                             "sample": "要么补模板，要么把它加进 check-templates-clean.py 的 "
                                       "NO_TEMPLATE_STAGES 并写清理由"})

    blocks = [h for h in hits if h["level"] == "BLOCK"]
    warns = [h for h in hits if h["level"] == "WARN"]
    return {"denylist": ("%d 个词" % len(terms)) if has_deny else "未配置（缺 %s）→ ⚠️ 项目词这一类**未扫描**" % DENY_REL,
            "denylistTerms": len(terms),
            "blocks": blocks, "warns": warns, "failed": bool(blocks)}


# ---------- 变异测试 ----------

SELFTEST_SKILL = """---
name: pm-workflow
---
## 何时用哪个阶段

| 阶段 | 触发词 | 产出 |
|---|---|---|
| **02 PRD** | x | y |
| **06 需求卡片画布** | x | y |

> **05 标注（连线）已取消** —— 只保留卡片形态。

## 端枚举（固定，全流程统一）

```
用户小程序 / 管理后台 / 收银端 / 商家端 / 服务端
```
"""

GOOD = {
    "SKILL.md": SELFTEST_SKILL,
    "scripts/publish-denylist.txt": "# 示例\n某内部代号\n",
    "assets/templates/02-prd/build-view.py": (
        "TPL = r'''<title>PRD · {{项目名}}</title>'''\n"
        "LANE_STYLE = {'用户小程序': ('laneApp', '#3fb950'), '外部系统': ('laneExt', '#58a6ff')}\n"
        # 解析用正则里的 <title> 不是要渲染的标题 —— 固定住这条假阳性
        "m = re.search(r'<title>R:(.*?)</title>', r.stdout or '', re.S)\n"
    ),
}

# 每种缺陷各植一条 —— 断言必须**逐条**命中，否则某个判据可能从未被验证过
BAD = {
    "SKILL.md": SELFTEST_SKILL,
    "scripts/publish-denylist.txt": "# 示例\n某内部代号\n",
    "assets/templates/02-prd/build-view.py": "<title>PRD · 某真实项目名</title>\n",          # T2
    "assets/templates/02-prd/leak.py": "NOTE = '某内部代号 的分成口径'\n",                    # T1
    "assets/templates/02-prd/lane.py": "LANE = {'甲方人事系统': ('laneHr', '#39c5bb')}\n",    # T4
    "assets/templates/05-annotation/build-anno.py": "# 已下线阶段的模板\n",                    # T3
}


def selftest() -> int:
    with tempfile.TemporaryDirectory() as d:
        good = analyze(_mkskill(Path(d) / "good", GOOD))
    with tempfile.TemporaryDirectory() as d:
        bad = analyze(_mkskill(Path(d) / "bad", BAD))

    ok_good = not good["failed"]
    # 逐判据断言：T1–T4 每一条都必须被命中
    kinds = {h["kind"].split()[0] for h in bad["blocks"]}
    expect = {"T1", "T2", "T3", "T4"}
    missed = sorted(expect - kinds)
    ok_bad = not missed

    print("变异测试 —— 证明检查有判别力")
    print("  好样本 期望可发布   : %s  (实得 BLOCK=%d WARN=%d)"
          % ("通过" if ok_good else "失败", len(good["blocks"]), len(good["warns"])))
    print("  坏样本 期望逐判据命中: %s  (实得 BLOCK=%d，命中 %s%s)"
          % ("通过" if ok_bad else "失败", len(bad["blocks"]), sorted(kinds),
             "" if ok_bad else "，**漏掉 %s**" % missed))
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


def _mkskill(base: Path, files: dict) -> Path:
    for name, content in files.items():
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return base


# ---------- CLI ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="模板洁净度守卫")
    ap.add_argument("source", nargs="?", help="skill 目录")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--strict", action="store_true", help="WARN 也算失败")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.source:
        print("需要给一个 skill 目录（或用 --selftest）")
        return 2

    r = analyze(Path(args.source))
    if args.json_out:
        import json
        Path(args.json_out).write_text(
            json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    print("项目词黑名单:", r["denylist"])
    print("  BLOCK %d · WARN %d" % (len(r["blocks"]), len(r["warns"])))
    if r["blocks"]:
        print("\n🔴 BLOCK —— 模板带进了不该有的东西：")
        for h in r["blocks"]:
            print("   [%s] %s:%s  %s" % (h["kind"], h["path"], h["line"] or "-", h["sample"]))
    if r["warns"]:
        print("\n🟡 WARN：")
        for h in r["warns"]:
            print("   [%s] %s  %s" % (h["kind"], h["path"], h["sample"]))
    if not r["blocks"] and not r["warns"]:
        print("\n✅ 未发现需要处理的问题。")
    if r["blocks"] or (args.strict and r["warns"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
