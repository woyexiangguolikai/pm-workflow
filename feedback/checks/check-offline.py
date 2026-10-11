#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04 原型 · 离线包真实渲染检查器（04 A6，由 B4 升级而来）
=======================================================
实现 04-prototype rubric 的 A6 判据 —— **只能靠真渲染判**的那一部分。

用法:
    python check-offline.py <designs/<项目>> [--json <输出路径>] [--workers N]
    python check-offline.py --selftest

判据:
    A6-1  渲染零报错：每个 HTML 以 file:// 真实渲染，
          exceptionThrown + console.error + Log(error) 合计必须为 0
    A6-2  跨页锚点真实生效：导航到 `<目标>.html#<fragment>` 后，渲染结果
          必须**确实变化**；与「无 hash 基线」相同的最多允许 1 个（那是默认页）
    A6-3  可达性：从入口页出发，顺着站内链接必须能走到每一个页面
    A6-4  判别力自证：两次无 hash 加载的渲染签名必须完全一致。
          基线本身不可复现的话，A6-2 的「变了 / 没变」就只是噪声 → 一并作废

退出码: 0 = 全部通过; 1 = 存在失败项; 2 = 运行错误

为什么必须真渲染，而不是查源码
--------------------------------
原型是 Babel 在浏览器里现编译的 React 应用，**页面结构不存在于 HTML 源码里**。
对源码 grep `id="U-02"` 一个都找不到，而运行时 23 个页面一个不少 ——
静态查会把「全通」报成「全断」。

而且**就算真有 id 也不能只看 id**：本项目页面切换走
`history.replaceState(null,"","#"+code)`，DOM 里根本没有对应 id。
唯一可靠的做法就是：真导航过去，看渲染结果是否确实变了。

🔴 一个花了两轮才定位的假绿
----------------------------
首版从 `A.html` 导航到 `A.html#X`，结果 23 个锚点**全部**报「未变化」。
原因是**同文档导航**：只改 hash 不触发 load、不重跑脚本，
而应用只在 mount 时读 `location.hash` → 导航无效，探针等 load 等到超时后
采样到旧 DOM。
→ 修法：每次导航都带一个唯一的 `?wb_probe=N`，把「同文档」变成「跨文档」。

⚠️ 这条判据**很贵**（要起浏览器）。默认每个 HTML 起一次浏览器实例，
多文件并行。实测本项目 3 个单文件约 50 秒。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / "_offline_probe.js"

# 离线包里允许作为「站内链接」的扩展名
LOCAL_EXT = (".html", ".htm")
OFFLINE_DIRNAME = "离线版"


def _find_node() -> str:
    """自动定位 managed Node。

    🔴 不要写死 `C:/Users/<用户名>/...` —— 换机器必错，也没法发布给别人用。
    覆盖顺序：WB_NODE → ~/.workbuddy/binaries/node/versions/*/node.exe（取版本最大）→ PATH。
    """
    p = os.environ.get("WB_NODE")
    if p and os.path.exists(p):
        return p
    base = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "node", "versions")
    if os.path.isdir(base):
        cands = sorted(
            os.path.join(base, d, "node.exe")
            for d in os.listdir(base)
            if os.path.exists(os.path.join(base, d, "node.exe"))
        )
        if cands:
            return cands[-1]
    return "node"


NODE = _find_node()
NODE_MODULES = os.environ.get("WB_NODE_MODULES") or os.path.join(
    os.path.expanduser("~"), ".workbuddy", "binaries", "node", "workspace", "node_modules"
)


# --------------------------------------------------------------------------
# 探针调用
# --------------------------------------------------------------------------
def run_probe(html: Path, frags: list[str], timeout: int = 420) -> dict:
    """起一次浏览器，跑 baseline + 反例 + 每个 fragment。"""
    tmp = Path(tempfile.mkdtemp(prefix="wb_offline_"))
    out = tmp / "probe.json"
    env = dict(os.environ)
    env["NODE_PATH"] = NODE_MODULES
    cmd = [NODE, str(PROBE), "--file", str(html), "--out", str(out)]
    if frags:
        cmd += ["--frags", ",".join(frags)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                           cwd=str(HERE), timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"_error": f"探针超时（{timeout}s）"}
    if out.exists():
        try:
            j = json.loads(out.read_text(encoding="utf-8"))
            j["_stdout_ok"] = True
            return j
        except Exception as e:
            return {"_error": f"探针输出无法解析: {e}"}
    return {"_error": "探针没有产出结果文件\n" + (r.stderr or r.stdout or "")[-800:]}


def strip_fragment(href: str) -> tuple[str, str]:
    """拆出 (路径, fragment)。只处理站内相对链接。"""
    if not href or href.startswith(("http://", "https://", "//", "mailto:", "data:", "javascript:")):
        return "", ""
    path, _, frag = href.partition("#")
    return path, frag


def is_local_html(path: str) -> bool:
    return bool(path) and path.lower().endswith(LOCAL_EXT) and not path.startswith("/")


# --------------------------------------------------------------------------
# 主分析
# --------------------------------------------------------------------------
def analyze(root: Path, workers: int = 3) -> dict:
    off = root / OFFLINE_DIRNAME
    if not off.is_dir():
        return {"error": f"找不到离线包目录: {off}", "checks": [], "failed": []}

    htmls = sorted(p for p in off.iterdir()
                   if p.is_file() and p.suffix.lower() in LOCAL_EXT)
    if not htmls:
        return {"error": f"离线包里没有 HTML: {off}", "checks": [], "failed": []}

    # ---- 第一轮：先各跑一次 baseline，拿到每个文件的出站链接 ----
    # 用单线程起步是为了把「链接关系」先建立起来，才知道要给谁喂哪些 fragment。
    # baseline 这一轮顺带把 A6-1（零报错）和 A6-4（反例控制）拿下。
    base: dict[str, dict] = {}
    for h in htmls:
        base[h.name] = run_probe(h, [])

    # ---- 建立 fragment 关系：目标文件 -> 需要的 fragment 集合 ----
    wants: dict[str, set[str]] = {h.name: set() for h in htmls}
    link_records: list[dict] = []
    for h in htmls:
        pr = base[h.name]
        if pr.get("_error"):
            continue
        for lk in pr.get("links", []):
            path, frag = strip_fragment(lk.get("href", ""))
            if not is_local_html(path):
                continue
            target = (off / path).resolve()
            link_records.append({
                "from": h.name, "href": lk.get("href", ""),
                "text": lk.get("text", ""), "visible": lk.get("visible"),
                "targetExists": target.exists(),
                "target": Path(path).name,
            })
            if frag and target.exists() and target.name in wants:
                wants[target.name].add(frag)

    # ---- 第二轮：带 fragment 重跑需要的文件（可并行）----
    need = [h for h in htmls if wants[h.name]]
    if need:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(need)))) as ex:
            futs = {ex.submit(run_probe, h, sorted(wants[h.name])): h for h in need}
            for f in futs:
                h = futs[f]
                base[h.name] = f.result()

    checks = []

    # ---------- A6-1 渲染零报错 ----------
    err_files = []
    total_errors = 0
    for h in htmls:
        pr = base[h.name]
        if pr.get("_error"):
            err_files.append({"file": h.name, "errors": [pr["_error"]]})
            total_errors += 1
        elif pr.get("errors"):
            err_files.append({"file": h.name, "errors": pr["errors"]})
            total_errors += len(pr["errors"])
    checks.append({
        "id": "A6-1", "title": "离线包 file:// 渲染零报错",
        "status": "fail" if err_files else "pass",
        "evidence": {"files": [h.name for h in htmls],
                     "errorCount": total_errors, "offenders": err_files},
    })

    # ---------- A6-4 判别力自证 ----------
    # 判的不是「应用怎么处理未知 fragment」（那是应用自由），而是**渲染本身可不可复现**：
    # 两次无 hash 加载的签名必须一模一样。基线就不稳定的话，
    # 后面所有「变了 / 没变」的判断都只是噪声 —— 那时候 A6-2 的结论一并作废。
    bad_ctl = []
    for h in htmls:
        pr = base[h.name]
        if pr.get("_error"):
            continue
        if pr.get("baseStable") is False:
            bad_ctl.append({"file": h.name,
                            "sig1": (pr.get("baseSig") or "")[:90],
                            "sig2": (pr.get("baseSig2") or "")[:90]})
    checks.append({
        "id": "A6-4", "title": "判别力自证：无 hash 渲染可复现（两次签名一致）",
        "status": "fail" if bad_ctl else "pass",
        "evidence": {"offenders": bad_ctl, "note": (
            "基线两次加载签名不同 ⇒ 渲染不确定，「变了」这个信号不可信，"
            "A6-2 的结论一并作废（不是「通过」）" if bad_ctl
            else "基线两次加载签名完全一致")},
    })

    # ---------- A6-2 跨页锚点真实生效 ----------
    dead, same_base, checked = [], [], []
    for h in htmls:
        pr = base[h.name]
        if pr.get("_error") or not wants[h.name]:
            continue
        res = pr.get("fragResults", {}) or {}
        for frag, v in sorted(res.items()):
            checked.append({"target": h.name, "frag": frag,
                            "differs": v.get("differs"), "mode": "crossdocument"})
            if not v.get("differs"):
                same_base.append({"target": h.name, "frag": frag})
    # 与基线相同的最多允许 1 个 —— 那是目标文档的默认页，属正常
    if len(same_base) > 1:
        dead = same_base
    multi_page = len(htmls) > 1
    if not checked and multi_page:
        checks.append({
            "id": "A6-2", "title": "跨页锚点真实生效",
            "status": "fail",
            "evidence": {"reason": f"多页离线包（{len(htmls)} 个 HTML）但**零个**带 fragment 的"
                                   f"站内链接 —— 样本为 0 判失败，不是「无事通过」"},
        })
    else:
        checks.append({
            "id": "A6-2", "title": "跨页锚点真实生效",
            "status": "fail" if dead else "pass",
            "evidence": {"checked": len(checked), "noEffect": dead,
                         "sameAsDefault": same_base,
                         "detail": checked},
        })

    # ---------- A6-3 可达性（不是「有没有入站」）----------
    # 入口页天然没有入站链接，按「有没有入站」判会把自己的入口判成孤页（首版就是这个假阳性）。
    # 正确的性质是**可达**：从入口出发，顺着站内链接能走到每一个页面。
    outs: dict[str, set[str]] = {}
    inbound: dict[str, set[str]] = {}
    for r in link_records:
        if not r["targetExists"]:
            continue
        outs.setdefault(r["from"], set()).add(r["target"])
        inbound.setdefault(r["target"], set()).add(r["from"])
    names = [h.name for h in htmls]
    entries = [n for n in names if n not in inbound]
    if not entries and names:
        entries = [max(names, key=lambda n: len(outs.get(n, ())))]
    seen, stack = set(entries), list(entries)
    while stack:
        for nx in outs.get(stack.pop(), ()):
            if nx not in seen:
                seen.add(nx)
                stack.append(nx)
    unreachable = [n for n in names if n not in seen] if len(htmls) > 1 else []
    checks.append({
        "id": "A6-3", "title": "从入口出发每页都可达（无孤页）",
        "status": "fail" if unreachable else "pass",
        "evidence": {"pages": names, "entries": entries,
                     "reached": sorted(seen), "unreachable": unreachable},
    })

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {"totalChecks": len(checks), "passed": len(checks) - len(failed),
            "failed": failed, "checks": checks, "links": link_records,
            "offlineDir": str(off)}


# --------------------------------------------------------------------------
# 变异测试
# --------------------------------------------------------------------------
GOOD_B = """<!doctype html><meta charset="utf-8"><title>B</title>
<body><div id="out">默认页</div><script>
function draw(){var h=(location.hash||"").replace("#","")||"P0";
  document.getElementById("out").textContent="页面:"+h+"|"+h.length;}
draw(); addEventListener("hashchange",draw);
</script></body>"""

GOOD_A = """<!doctype html><meta charset="utf-8"><title>A</title>
<body><div id="out">入口</div>
<a href="B.html#P1">去 P1</a><a href="B.html#P2">去 P2</a></body>"""

# 坏样本：B 只在 mount 时读一次 hash，但**忽略它**（永远渲染默认页）
BAD_B = """<!doctype html><meta charset="utf-8"><title>B</title>
<body><div id="out">默认页</div><script>
document.getElementById("out").textContent="页面:默认页|固定内容";
</script></body>"""


def _mk(base: Path, a_html: str, b_html: str) -> Path:
    off = base / OFFLINE_DIRNAME
    off.mkdir(parents=True, exist_ok=True)
    (off / "A.html").write_text(a_html, encoding="utf-8")
    (off / "B.html").write_text(b_html, encoding="utf-8")
    return base


def selftest() -> int:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _mk(p / "g", GOOD_A, GOOD_B)
        good = analyze(p / "g", workers=2)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _mk(p / "b", GOOD_A, BAD_B)
        bad = analyze(p / "b", workers=2)

    ok_good = good.get("failed") == []
    # 坏样本里 B 忽略 hash ⇒ P1/P2 都不生效 ⇒ A6-2 必须红
    ok_bad = "A6-2" in (bad.get("failed") or [])
    print("变异测试 —— 证明检查有判别力")
    print(f"  好样本 期望全绿        : {'通过' if ok_good else '失败'}"
          f"  (实得 failed={good.get('failed')})")
    print(f"  坏样本 期望 A6-2 变红  : {'通过' if ok_bad else '失败'}"
          f"  (实得 failed={bad.get('failed')})")
    if bad.get("failed"):
        ev = next((c for c in bad["checks"] if c["id"] == "A6-2"), {})
        print(f"         坏样本 A6-2 证据: 检查 {ev.get('evidence', {}).get('checked')} 个，"
              f"失效 {len(ev.get('evidence', {}).get('noEffect') or [])} 个")
    if not (ok_good and ok_bad):
        print("\n判别力不足 —— 该检查等于没有检查。")
        return 1
    print("\n判别力成立。")
    return 0


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="04 原型 · 离线包真实渲染检查器")
    ap.add_argument("root", nargs="?")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.root:
        ap.print_help()
        return 2

    result = analyze(Path(args.root), workers=args.workers)
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2
    result["root"] = str(args.root)

    print(f"离线包目录 : {result['offlineDir']}")
    print(f"通过 {result['passed']}/{result['totalChecks']} 项")
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "pass" else "FAIL"
        print(f"  [{mark}] {c['id']} {c['title']}")
        ev = c["evidence"]
        if c["id"] == "A6-1":
            print(f"         {len(ev['files'])} 个文件，报错合计 {ev['errorCount']}")
            for o in ev["offenders"]:
                print(f"         🔴 {o['file']}")
                for e in o["errors"][:6]:
                    print(f"              {e}")
        elif c["id"] == "A6-2":
            if ev.get("reason"):
                print(f"         {ev['reason']}")
            else:
                print(f"         检查 {ev['checked']} 个锚点；无效果 {len(ev['noEffect'])} 个"
                      f"（与默认页相同 {len(ev['sameAsDefault'])} 个）")
                for o in ev["noEffect"]:
                    print(f"         🔴 {o['target']}#{o['frag']} 导航后渲染结果未变化")
                for o in ev["sameAsDefault"]:
                    print(f"         ·  {o['target']}#{o['frag']} 与默认页相同（正常）")
        elif c["id"] == "A6-3":
            print(f"         页面 {len(ev['pages'])} 个；入口 {ev['entries']}；"
                  f"可达 {len(ev['reached'])} 个")
            for o in ev["unreachable"]:
                print(f"         🔴 {o} 从入口出发无法到达（孤页）")
        elif c["id"] == "A6-4":
            print(f"         {ev['note']}")
            for o in ev["offenders"]:
                print(f"         🔴 {o['file']}：两次基线签名不同")

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
