#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# wb-publish-scan: ignore-file
#   ↑ 本文件是**检测器**，它的测试样本里必然含「像密钥、像本机路径」的字符串。
#     带此标记表示：本文件整体豁免扫描，且豁免行为会在输出里列出（不静默跳过）。
#     这是本仓库唯一一个豁免文件 —— 新增豁免必须在 PUBLISHING.md 里写明理由。
"""
发布前自检 · 扫描 skill 目录里的「不该发出去的东西」
====================================================
把 skill 发布到 git（尤其公开仓库）之前跑一次。**可反复跑** —— 每次加了新素材、
新评审记录之后再跑一遍即可，不要指望记住清单。

用法:
    python check-publish-safe.py <skill_dir> [--json <输出>] [--strict]
    python check-publish-safe.py --selftest

    --strict  把 WARN 也当作失败（建议在 CI / pre-commit 里用）

退出码: 0 = 可发布; 1 = 有 BLOCK 级问题（或 --strict 下有 WARN）; 2 = 运行错误

为什么要有它（而不是一份手工清单）
------------------------------------
发布前的泄露风险是**动态的**：每次跑完工作流，`feedback/review/` 就多一份含客户数据的记录；
每次往库加素材，就可能多一条来源不明的条目。
**手工清单一定会过期。** 所以这条判据必须可复跑。

三级分类（不要混）
-------------------
  BLOCK  绝对不能发：凭据 / 私钥 / 真实客户数据 / 本机用户名与绝对路径
  WARN   谨慎：可能可识别到具体客户或人（客户名、真实姓名、手机号形态串）
  INFO   只是提醒：版本号、日期等
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------- 规则 ----------------
# BLOCK：凭据与密钥形态
SECRET_PATTERNS = [
    ("私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("微信/支付宝类长串密钥", re.compile(r"\b(?:sk|pk|ak|api[_-]?key)[_-]?[A-Za-z0-9]{24,}\b", re.I)),
    ("Bearer/Token 赋值", re.compile(r"(?i)\b(?:authorization|token|secret|password)\s*[:=]\s*[\"'][^\"']{16,}[\"']")),
    ("数据库连接串", re.compile(r"(?i)\b(?:mysql|postgres|mongodb|redis)://[^\s\"']+:[^\s\"']+@")),
]

# BLOCK：本机环境指纹（用户名 / 本机绝对路径）
LOCAL_ENV_PATTERNS = [
    ("Windows 用户目录绝对路径", re.compile(r"[A-Za-z]:[\\/]Users[\\/](?!<|%|\{|YOUR|username)[A-Za-z0-9._-]+")),
    ("Unix home 绝对路径", re.compile(r"/(?:home|Users)/(?!<|\$|\{|YOUR|username)[a-z0-9._-]+/")),
]

# WARN：可能是真实客户/个人信息
CLIENT_HINTS = [
    ("中国大陆手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("身份证号形态", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("真实邮箱", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.|test\.|xxx)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]

# 默认应被 git 忽略的路径（若存在但未被忽略，提醒）
SHOULD_BE_IGNORED = [
    "feedback/review",
    "feedback/review-log.jsonl",
    "library/local",
    # 黑名单本身列的就是敏感词，绝不能发出去
    "scripts/publish-denylist.txt",
    "**/node_modules",
    "**/__pycache__",
]

TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".jsonl", ".js", ".jsx", ".ts", ".tsx", ".css",
    ".html", ".txt", ".yml", ".yaml", ".toml", ".ps1", ".sh", ".cfg", ".ini",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

# 文件级豁免标记。**必须显式、且必须被打印出来。**
# 用途：扫描器自己（它的测试样本里必然含「像密钥、像路径」的字符串）。
# ⚠️ 不做「静默跳过」—— 被跳过的文件一定要出现在输出里，否则就成了 AP-06 那种静默假绿。
EXEMPT_MARKER = "wb-publish-scan: ignore-file"

# ── 项目词黑名单 ──────────────────────────────────────────────
# 为什么需要它：上面的规则只扫「密钥 / PII / 本机路径」，**扫不到商业 know-how** ——
# 真实阈值、分成比例、付款通道、合作方名称、内部文档名。
# 这类内容泄露的后果比一个手机号严重得多，而常规规则一个都抓不到。
# 名单由使用者按项目维护；**名单本身不进版本库**（它列的就是敏感词）。
DENYLIST_NAME = "scripts/publish-denylist.txt"
DENYLIST_EXAMPLE = "scripts/publish-denylist.example.txt"


def load_denylist(root: Path) -> tuple[list[str], str]:
    """返回 (词表, 状态说明)。

    状态会被**打印出来** —— 「没有黑名单」不能表现为「没有命中」。
    """
    p = root / DENYLIST_NAME
    if not p.exists():
        return [], f"未配置（缺 {DENYLIST_NAME}）→ ⚠️ 项目词这一类**未扫描**"
    terms = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            terms.append(s)
    if not terms:
        return [], f"{DENYLIST_NAME} 是空的 → ⚠️ 项目词这一类**未扫描**"
    return terms, f"{len(terms)} 个词"


def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def is_exempt(p: Path) -> bool:
    if p.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")[:2000]
    except OSError:
        return False
    return EXEMPT_MARKER in head


def scan_text(text: str, rel: str, deny: tuple = ()) -> list[dict]:
    hits = []
    for label, rx in SECRET_PATTERNS:
        for m in rx.finditer(text):
            hits.append({"level": "BLOCK", "kind": label, "path": rel,
                         "line": text.count("\n", 0, m.start()) + 1,
                         "sample": m.group(0)[:40]})
    for label, rx in LOCAL_ENV_PATTERNS:
        for m in rx.finditer(text):
            hits.append({"level": "BLOCK", "kind": label, "path": rel,
                         "line": text.count("\n", 0, m.start()) + 1,
                         "sample": m.group(0)[:60]})
    # 项目词：BLOCK 级。子串匹配、大小写不敏感。
    for term in deny:
        for m in re.finditer(re.escape(term), text, re.I):
            hits.append({"level": "BLOCK", "kind": f"项目词「{term}」", "path": rel,
                         "line": text.count("\n", 0, m.start()) + 1,
                         "sample": m.group(0)[:40]})
    for label, rx in CLIENT_HINTS:
        for m in rx.finditer(text):
            hits.append({"level": "WARN", "kind": label, "path": rel,
                         "line": text.count("\n", 0, m.start()) + 1,
                         "sample": m.group(0)[:40]})
    return hits


def is_gitignored(root: Path, rel: str) -> bool:
    """只做朴素前缀匹配 —— 够用，且不依赖 git 命令可用。"""
    gi = root / ".gitignore"
    if not gi.exists():
        return False
    lines = [l.strip() for l in gi.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    rel = rel.replace("\\", "/")
    for pat in lines:
        p = pat.rstrip("/")
        if p.startswith("**/"):
            if p[3:] in rel:
                return True
        elif rel == p or rel.startswith(p + "/"):
            return True
    return False


def analyze(root: Path, strict: bool = False) -> dict:
    if not root.is_dir():
        return {"error": f"目录不存在: {root}"}

    deny, deny_status = load_denylist(root)
    deny_set = tuple(deny)

    findings: list[dict] = []
    scanned = 0
    exempt_files: list[str] = []
    for p in iter_files(root):
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if is_exempt(p):
            exempt_files.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        findings.extend(scan_text(text, rel, deny_set))

    # 分离：已被 .gitignore 排除的文件单独统计（它们不会发出去）
    visible, ignored = [], []
    for h in findings:
        (ignored if is_gitignored(root, h["path"]) else visible).append(h)

    # 应忽略但未配的路径
    not_ignored = []
    for pat in SHOULD_BE_IGNORED:
        p = root / pat.replace("**/", "")
        if p.exists() and not is_gitignored(root, pat):
            not_ignored.append(pat)

    blocks = [h for h in visible if h["level"] == "BLOCK"]
    warns = [h for h in visible if h["level"] == "WARN"]
    failed = bool(blocks or (strict and warns))
    return {
        "scannedFiles": scanned,
        "exemptFiles": exempt_files,
        "denylist": deny_status,
        "denylistTerms": len(deny),
        "blocks": blocks,
        "warns": warns,
        "ignoredHits": ignored,
        "shouldBeIgnored": not_ignored,
        "ignoredFileHits": {k: sum(1 for h in ignored if h["path"] == k)
                            for k in sorted({h["path"] for h in ignored})},
        "failed": failed,
    }


# ------------------------------------------------------------ 变异测试
GOOD_DIR = {
    "README.md": "# 一个干净的 skill\n\n路径写成 `~/.workbuddy/skills/`，或用 `$env:USERPROFILE`。\n",
    "SKILL.md": "示例邮箱用 you@example.com，示例密钥用 <YOUR_TOKEN>。\n",
    ".gitignore": "feedback/review/\nlibrary/local/\n",
}

BAD_DIR = {
    "config.md": "路径：C:/Users/someone/.workbuddy/binaries/python.exe\n",
    "creds.json": '{"token": "abcdefghijklmnopqrstuvwxyz123456"}\n',
    "note.md": "客户联系人手机 13800138000\n",
}

# 项目词场景：常规规则**完全扫不到**这类内容 —— 这正是加黑名单的理由
DENY_DIR = {
    "scripts/publish-denylist.txt": "# 测试用黑名单\n某内部代号\n某合作方\n",
    "handbook.md": "本文档记录了 某内部代号 的分成与账期口径。\n",
}

# 有黑名单文件但内容为空 / 缺文件 —— 用来证明「未扫描」会被**报出来**而不是静默通过
NO_DENY_DIR = {
    "readme.md": "这里提到了 某内部代号，但本目录没有配置黑名单。\n",
}


def _write(base: Path, files: dict) -> Path:
    for name, content in files.items():
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return base


def selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        good = analyze(_write(Path(d) / "good", GOOD_DIR))
    with tempfile.TemporaryDirectory() as d:
        bad = analyze(_write(Path(d) / "bad", BAD_DIR))
    with tempfile.TemporaryDirectory() as d:
        deny = analyze(_write(Path(d) / "deny", DENY_DIR))
    with tempfile.TemporaryDirectory() as d:
        nodeny = analyze(_write(Path(d) / "nodeny", NO_DENY_DIR))

    ok_good = not good["failed"]
    ok_bad = bool(bad["blocks"])
    # 黑名单命中 → 必须 BLOCK，且 kind 要标明是「项目词」
    ok_deny = bool(deny["blocks"]) and any("项目词" in h["kind"] for h in deny["blocks"])
    # 无黑名单 → 不能静默通过：必须报「未扫描」，且不算失败（用户尚未配置）
    ok_nodeny = (nodeny["denylistTerms"] == 0
                 and "未扫描" in nodeny["denylist"]
                 and not nodeny["failed"])

    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望可发布     : {'通过' if ok_good else '失败'}"
          f"  (实得 BLOCK={len(good['blocks'])} WARN={len(good['warns'])})")
    print(f"  坏样本 期望有 BLOCK   : {'通过' if ok_bad else '失败'}"
          f"  (实得 BLOCK={len(bad['blocks'])})")
    print(f"  项目词 期望被 BLOCK   : {'通过' if ok_deny else '失败'}"
          f"  (实得 BLOCK={len(deny['blocks'])})")
    print(f"  无黑名单 期望报「未扫描」: {'通过' if ok_nodeny else '失败'}"
          f"  (实得 {nodeny['denylist']})")
    if not (ok_good and ok_bad and ok_deny and ok_nodeny):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


# ------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="发布前敏感信息自检")
    ap.add_argument("source", nargs="?", help="skill 目录")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--strict", action="store_true", help="WARN 也算失败")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.source:
        ap.print_help()
        return 2

    root = Path(args.source)
    r = analyze(root, args.strict)
    if r.get("error"):
        print(r["error"], file=sys.stderr)
        return 2

    print(f"扫描 {r['scannedFiles']} 个文本文件（{root}）")
    print(f"  BLOCK {len(r['blocks'])} · WARN {len(r['warns'])}"
          f" · 已忽略目录内命中 {len(r['ignoredHits'])}（不会发出去）")
    print(f"  项目词黑名单: {r['denylist']}")
    if r["denylistTerms"] == 0:
        print(f"     ⚠️ 常规规则扫不到「商业 know-how」（阈值 / 分成比例 / 合作方 / 内部文档名）。")
        print(f"     复制 {DENYLIST_EXAMPLE} 为 {DENYLIST_NAME} 并按项目填写。")
    if r["exemptFiles"]:
        print(f"  已豁免 {len(r['exemptFiles'])} 个文件（带 `{EXEMPT_MARKER}` 标记，逐个列出）：")
        for f in r["exemptFiles"]:
            print(f"     {f}")

    if r["blocks"]:
        print("\n🔴 BLOCK —— 绝对不要发布：")
        for h in r["blocks"]:
            print(f"   [{h['kind']}] {h['path']}:{h['line']}  {h['sample']}")
    if r["warns"]:
        print("\n🟡 WARN —— 可能可识别到具体客户/人，逐个确认：")
        for h in r["warns"]:
            print(f"   [{h['kind']}] {h['path']}:{h['line']}  {h['sample']}")
    if r["shouldBeIgnored"]:
        print("\n🟡 这些路径存在但没被 .gitignore 排除：")
        for p in r["shouldBeIgnored"]:
            print(f"   {p}")
    if r["ignoredFileHits"]:
        print("\nℹ️ 已排除文件里的命中（不会发布，仅列出）：")
        for k, v in r["ignoredFileHits"].items():
            print(f"   {k}  ×{v}")

    if not (r["blocks"] or r["warns"] or r["shouldBeIgnored"]):
        print("\n✅ 未发现需要处理的问题。")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入: {out}")

    return 1 if r["failed"] else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
