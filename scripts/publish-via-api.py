#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 Git Data API 发布本仓库 —— `git push` 不通时的兜底路径。

────────────────────────────────────────────────────────────
 什么时候用
────────────────────────────────────────────────────────────
有些网络环境**只放通 `api.github.com`、挡掉 `github.com:443`**。
典型症状：`curl https://github.com` 报 `502 CONNECT tunnel failed`，
而 `https://api.github.com/user` 正常返回。此时 `git push` 用不了，只能走 API。

方法层规则见 `PUBLISHING.md §7-1`；本脚本是它的可执行形态。

────────────────────────────────────────────────────────────
 四条硬规则（都是踩过的坑，别绕过）
────────────────────────────────────────────────────────────
1. **造 blob 的字节取自 `git cat-file blob`，绝不读工作区文件。**
   工作区可能是 CRLF（Windows 上尤其），读出来会污染整个远端。
2. **造 tree 用 `base_tree`** 只提交变化条目，`path` 可以直接写带 `/` 的完整路径。
3. **提交对象显式传 author / committer（含 date）与未剥离的完整消息**，
   否则远端 sha 与本地对不上。
4. **消息不要 `.strip()`** —— 尾换行少一个字节，整个对象就不同了。

────────────────────────────────────────────────────────────
 验收标准
────────────────────────────────────────────────────────────
**只有一条：tree sha 相同。**
两个 sha 相同 ⇒ 全部路径 + 全部内容 + 全部文件模式逐字节一致。
文件数量相同、网页上看着对，都**不算**证据。

用法：
    python scripts/publish-via-api.py              # 发布当前 HEAD 并打标签
    python scripts/publish-via-api.py --dry-run    # 只算不推
    python scripts/publish-via-api.py --no-tag     # 不打标签

凭据（按顺序尝试）：
    1. 环境变量 GH_TOKEN / GITHUB_TOKEN
    2. `--helper <可执行文件>` 指定的 git credential helper
    3. 自动定位的 git-credential-wincred.exe（Windows + PortableGit）
    4. `git credential fill`（带超时；本机已知会挂死，超时会被明确报出来）
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT = 180
CRED_TIMEOUT = 20

REPO_DIR = Path(__file__).resolve().parents[1]


# ──────────────────────────── 基础工具 ────────────────────────────

class Fail(SystemExit):
    def __init__(self, msg: str):
        super().__init__("✗ " + msg)


def run(args, cwd=None, binary=False, timeout=None, check=True):
    r = subprocess.run(args, cwd=str(cwd or REPO_DIR), capture_output=True, timeout=timeout)
    if check and r.returncode != 0:
        raise Fail("命令失败: %s\n%s" % (" ".join(map(str, args)), r.stderr.decode("utf-8", "replace")))
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def git(*args, binary=False, check=True):
    return run(["git", *args], binary=binary, check=check)


def gittext(*args):
    return git(*args).rstrip("\n")


# ──────────────────────────── 凭据 ────────────────────────────

def _wincred_candidates() -> list[Path]:
    """从 `git --exec-path` 反推 PortableGit 里的 wincred helper —— 不写死盘符。"""
    out = []
    try:
        exec_path = Path(gittext("--exec-path"))
    except Fail:
        return out
    # <gitroot>/mingw64/libexec/git-core  →  <gitroot>/mingw64/bin
    for up in (exec_path, *exec_path.parents):
        for sub in ("bin/git-credential-wincred.exe", "mingw64/bin/git-credential-wincred.exe"):
            cand = up / sub
            if cand.exists():
                out.append(cand)
    return out


def _ask_helper(exe: Path) -> tuple[str, str]:
    """向一个 credential helper 要 github.com 的凭据。"""
    payload = "protocol=https\nhost=github.com\n\n"
    r = subprocess.run([str(exe), "get"], input=payload.encode(),
                       capture_output=True, timeout=CRED_TIMEOUT)
    if r.returncode != 0:
        return "", ""
    user = passwd = ""
    for line in r.stdout.decode("utf-8", "replace").split("\n"):
        if line.startswith("username="):
            user = line[9:].strip()
        elif line.startswith("password="):
            passwd = line[9:].strip()
    return user, passwd


def resolve_token(explicit_helper: str | None) -> tuple[str, str]:
    """返回 (token, 来源说明)。取不到就抛出并说清卡在哪一步。"""
    for env in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(env, "").strip()
        if v:
            return v, "环境变量 %s" % env

    tried = []
    helpers: list[Path] = []
    if explicit_helper:
        helpers.append(Path(explicit_helper))
    helpers.extend(_wincred_candidates())
    for h in helpers:
        if not h.exists():
            tried.append("%s（不存在）" % h)
            continue
        try:
            user, passwd = _ask_helper(h)
        except subprocess.TimeoutExpired:
            tried.append("%s（超时 %ds）" % (h.name, CRED_TIMEOUT))
            continue
        if passwd:
            return passwd, "%s（用户 %s）" % (h.name, user or "?")
        tried.append("%s（未返回密码）" % h.name)

    # 最后试 git 自己 —— 这一步在本机已知会挂死，所以必须带超时，
    # 并且**把「超时」和「没配凭据」分开报**，否则会被引向错误结论。
    try:
        r = subprocess.run(["git", "credential", "fill"], cwd=str(REPO_DIR),
                           input=b"protocol=https\nhost=github.com\n\n",
                           capture_output=True, timeout=CRED_TIMEOUT)
        for line in r.stdout.decode("utf-8", "replace").split("\n"):
            if line.startswith("password=") and line[9:].strip():
                return line[9:].strip(), "git credential fill"
        tried.append("git credential fill（未返回密码）")
    except subprocess.TimeoutExpired:
        tried.append("git credential fill（**超时 %ds —— 这与「没配凭据」不是一回事**）" % CRED_TIMEOUT)

    raise Fail("取不到 GitHub 凭据。依次试过：\n           - " + "\n           - ".join(tried) +
               "\n         可显式传入：--helper <git-credential-xxx 的路径>，或设置 GH_TOKEN。")


# ──────────────────────────── GitHub API ────────────────────────────

class Client:
    def __init__(self, token: str, slug: str):
        self.headers = {
            "Authorization": "token " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "pm-workflow-publish-via-api",
            "Content-Type": "application/json",
        }
        self.slug = slug

    def call(self, method: str, path: str, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(API + path, data=body, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            if e.code == 422 and "already exists" in detail:
                return {"_already_exists": True}
            raise Fail("HTTP %d  %s %s\n%s" % (e.code, method, path, detail[:900]))


def parse_slug(remote_url: str) -> str:
    m = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?/?$", remote_url.strip())
    if not m:
        raise Fail("无法从 origin 解析 owner/repo：%s\n      可先：git remote set-url origin https://github.com/<owner>/<repo>.git" % remote_url)
    return "%s/%s" % (m.group(1), m.group(2))


# ──────────────────────────── 发布 ────────────────────────────

def ident_to_iso(line: str) -> tuple[str, str, str]:
    m = re.match(r"^(.*) <(.*)> (\d+) ([+-])(\d{2})(\d{2})$", line)
    if not m:
        raise Fail("无法解析 identity 行：" + line)
    name, mail, epoch, sign, hh, mm = m.groups()
    offset = int(hh) * 3600 + int(mm) * 60
    if sign == "-":
        offset = -offset
    tz = _dt.timezone(_dt.timedelta(seconds=offset))
    stamp = _dt.datetime.fromtimestamp(int(epoch), tz).strftime("%Y-%m-%dT%H:%M:%S")
    return name, mail, "%s%s%s:%s" % (stamp, sign, hh, mm)


def publish(cli: Client, dry_run: bool, make_tag: bool) -> int:
    local_head = gittext("rev-parse", "HEAD")
    local_tree = gittext("rev-parse", "HEAD^{tree}")
    local_parent = gittext("rev-parse", "HEAD^")
    print("本地 HEAD   = %s" % local_head)
    print("本地 tree   = %s" % local_tree)
    print("本地 parent = %s" % local_parent)

    remote = cli.call("GET", "/repos/%s/commits/main" % cli.slug)
    remote_sha, remote_tree = remote["sha"], remote["commit"]["tree"]["sha"]
    print("远端 main   = %s" % remote_sha)
    print("远端 tree   = %s" % remote_tree)

    if remote_sha == local_head:
        print("\n⚠ 远端已经是这个提交了，没有东西要发。")
        return 0
    if remote_sha != local_parent:
        raise Fail("远端 main 不是本地 HEAD 的父提交 —— 拒绝强推，需要人工判定（远端可能被别人推进过）。")
    if remote_tree != gittext("rev-parse", local_parent + "^{tree}"):
        raise Fail("远端 tree 与本地父提交 tree 不一致 —— 两边已经有分歧，先查清再发。")

    changed = [p for p in git("diff", "--name-only", "-z", local_parent, local_head).split("\0") if p]
    print("\n变化 %d 个文件：" % len(changed))

    # 规则 1：字节取自 git 对象库，不读工作区。
    entries = []
    for p in sorted(changed):
        raw = git("cat-file", "blob", "HEAD:" + p, binary=True)
        b64 = base64.b64encode(raw).decode("ascii")
        sha = cli.call("POST", "/repos/%s/git/blobs" % cli.slug, {"content": b64, "encoding": "base64"})["sha"]
        entries.append({"path": p, "mode": "100644", "type": "blob", "sha": sha})
        print("  %s %9d  %s" % (sha[:10], len(raw), p))

    if dry_run:
        print("\n(dry-run) 到此为止，不动远端。")
        return 0

    # 规则 2：base_tree 增量造树。
    new_tree = cli.call("POST", "/repos/%s/git/trees" % cli.slug,
                        {"base_tree": remote_tree, "tree": entries})["sha"]
    print("\n新 tree = %s" % new_tree)
    if new_tree != local_tree:
        print("⚠ 增量树与本地不一致 → 回退为整树重建")
        full = []
        for line in git("ls-tree", "-r", "-z", local_head).split("\0"):
            if not line:
                continue
            meta, path = line.split("\t", 1)
            mode, typ, sha = meta.split(" ")
            full.append({"path": path, "mode": mode, "type": typ, "sha": sha})
        print("  整树条目 %d 个" % len(full))
        new_tree = cli.call("POST", "/repos/%s/git/trees" % cli.slug, {"tree": full})["sha"]
        print("  重建 tree = %s" % new_tree)

    if new_tree != local_tree:
        raise Fail("tree 仍不一致 —— 停止，**不要挪 ref**。先把两边差异找出来。")

    # 规则 3 / 4：复现提交对象。
    commit_raw = git("cat-file", "commit", local_head)
    header, message = commit_raw.split("\n\n", 1)   # 不 strip —— 尾换行也是内容
    a = ident_to_iso(re.search(r"^author (.*)$", header, re.M).group(1))
    c = ident_to_iso(re.search(r"^committer (.*)$", header, re.M).group(1))
    print("\n消息 %d 字节 · author date = %s" % (len(message.encode("utf-8")), a[2]))

    commit = cli.call("POST", "/repos/%s/git/commits" % cli.slug, {
        "message": message,
        "tree": new_tree,
        "parents": [local_parent],
        "author": {"name": a[0], "email": a[1], "date": a[2]},
        "committer": {"name": c[0], "email": c[1], "date": c[2]},
    })
    if commit["sha"] == local_head:
        print("✅ 远端提交 sha 与本地完全一致 = %s" % local_head)
    else:
        print("⚠ 提交 sha 与本地不同（tree 已一致，可接受）：远端 %s / 本地 %s" % (commit["sha"], local_head))

    cli.call("PATCH", "/repos/%s/git/refs/heads/main" % cli.slug, {"sha": commit["sha"], "force": True})
    print("ref main 已更新")

    # ── 验收：唯一的证据 ──
    after = cli.call("GET", "/repos/%s/commits/main" % cli.slug)["commit"]["tree"]["sha"]
    ok = after == local_tree
    print("\n验收：远端 tree = %s" % after)
    print("      本地 tree = %s" % local_tree)
    print("      结论 = %s" % ("✅ 一致（逐字节相同）" if ok else "❌ 不一致"))
    if not ok:
        raise Fail("远端 tree 与本地不一致 —— 这次发布不算成功。")

    if make_tag:
        skill_md = (REPO_DIR / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"ai\.workbuddy\.version:\s*([0-9.]+)", skill_md)
        if not m:
            print("\n⚠ SKILL.md 里找不到版本号，跳过打标签。")
        else:
            tag = "v" + m.group(1)
            res = cli.call("POST", "/repos/%s/git/refs" % cli.slug,
                           {"ref": "refs/tags/" + tag, "sha": commit["sha"]})
            print("\n标签 %s %s" % (tag, "已存在，跳过" if res.get("_already_exists") else "已创建"))
            print("  记得同步建 Release（CHANGELOG 段头 / SKILL.md / tag 三处版本号必须一致）。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="通过 Git Data API 发布本仓库（git push 不通时用）")
    ap.add_argument("--dry-run", action="store_true", help="只计算与打印，不改远端")
    ap.add_argument("--no-tag", action="store_true", help="不打标签")
    ap.add_argument("--helper", default=None, help="git credential helper 的可执行文件路径")
    ap.add_argument("--repo-url", default=None, help="覆盖 origin（默认读 git remote get-url origin）")
    ap.add_argument("--token", default=None, help="直接给 token（不推荐，优先环境变量）")
    args = ap.parse_args()

    if not (REPO_DIR / ".git").exists():
        raise Fail("这里不是 git 仓库：%s" % REPO_DIR)

    url = args.repo_url or gittext("remote", "get-url", "origin")
    slug = parse_slug(url)

    if args.token:
        token, src = args.token, "--token 参数"
    else:
        token, src = resolve_token(args.helper)
    print("仓库   = %s" % slug)
    print("凭据   = %s" % src)
    print("目标   = main（本脚本不发别的分支）\n")

    return publish(Client(token, slug), args.dry_run, not args.no_tag)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        print(str(e))
        sys.exit(1)
